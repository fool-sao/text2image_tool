"""批量生成工作线程

设计:
- 单个 BatchGenerateTask 是 QRunnable, 通过 QThreadPool 调度, 实现用户配置并发数
- 每个 task 完成后通过信号回调主线程, 更新对应 BatchRow 状态
- BatchController 负责提交任务、跟踪进度、停止
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtCore import QObject, QRunnable, Qt, Signal, Slot
from PySide6.QtGui import QImage

from api_client import ZhipuImageClient
from excel_io import BatchRow


@dataclass
class BatchResult:
    """单个批量任务的执行结果

    单图模式: qimages 长度 1, images_data 长度 1
    组图模式: qimages / images_data 长度 == row.n_expected (个别失败可能更短)
    """
    item_id: int
    source_index: int
    ok: bool
    qimages: list = field(default_factory=list)        # list[QImage]
    images_data: list = field(default_factory=list)    # list[bytes]
    error: Optional[str] = None
    n_expected: int = 1                                # 预期生成图片数


class _GenerateTask(QRunnable):
    """单次生成任务 (QRunnable, 由 QThreadPool 调度)

    根据 row.n_expected 决定调用单图或组图接口:
    - n=1: 调用 client.generate(), 结果长度 1
    - n>1: 调用 client.generate_n(n=n), 结果长度 n
    """

    def __init__(
        self,
        client: ZhipuImageClient,
        row: BatchRow,
        default_size: str,
        default_quality: str,
        default_watermark: bool,
        default_system_prompt: str,
    ):
        super().__init__()
        self.client = client
        self.row = row
        # 参数优先级: Excel 单行 > 全局默认
        self.size = row.size_override or default_size
        self.quality = row.quality_override or default_quality
        self.watermark = (
            default_watermark
            if row.watermark_override is None
            else row.watermark_override
        )
        self.system_prompt = (
            default_system_prompt
            if row.system_prompt_override is None
            else row.system_prompt_override
        )
        # 信号对象 (QRunnable 不能直接发信号, 通过外层 signaler 转发)
        self.signaler: Optional[_BatchSignaler] = None

    def run(self) -> None:
        row = self.row
        if self.signaler is None:
            return
        self.signaler.started.emit(row.item_id, row.source_index)
        try:
            n = max(1, int(row.n_expected))
            if n > 1:
                # 组图模式
                images_bytes = self.client.generate_n(
                    prompt=row.prompt,
                    size=self.size,
                    quality=self.quality,
                    watermark_enabled=self.watermark,
                    system_prompt=self.system_prompt,
                    n=n,
                )
            else:
                # 单图模式 (保留原接口, 兼容性更好)
                single = self.client.generate(
                    prompt=row.prompt,
                    size=self.size,
                    quality=self.quality,
                    watermark_enabled=self.watermark,
                    system_prompt=self.system_prompt,
                )
                images_bytes = [single]

            # 解码为 QImage 列表
            qimages: list[QImage] = []
            for b in images_bytes:
                qimg = QImage()
                if not qimg.loadFromData(b, "PNG"):
                    qimg = QImage.fromData(b)
                if qimg.isNull():
                    raise RuntimeError("图片解码失败")
                qimages.append(qimg)

            result = BatchResult(
                item_id=row.item_id,
                source_index=row.source_index,
                ok=True,
                qimages=qimages,
                images_data=list(images_bytes),
                n_expected=n,
            )
            self.signaler.finished.emit(result)
        except Exception as e:  # noqa: BLE001
            self.signaler.finished.emit(BatchResult(
                item_id=row.item_id,
                source_index=row.source_index,
                ok=False,
                error=str(e),
                n_expected=max(1, int(row.n_expected)),
            ))


class _BatchSignaler(QObject):
    """跨线程信号转发器

    QRunnable 本身不能定义 Signal, 用独立的 QObject 持有信号。
    """
    started = Signal(int, int)            # item_id, source_index
    finished = Signal(object)             # BatchResult
    all_done = Signal()                   # 全部完成


class BatchController(QObject):
    """批量任务控制器

    用法:
        ctrl = BatchController(client, rows, defaults, concurrency=3)
        ctrl.started.connect(...)
        ctrl.finished.connect(...)
        ctrl.all_done.connect(...)
        ctrl.start()  # 提交到全局 QThreadPool
        ctrl.stop()   # 取消尚未开始的任务
    """

    started = Signal(int, int)            # item_id, source_index
    finished = Signal(object)             # BatchResult
    all_done = Signal()

    def __init__(
        self,
        client: ZhipuImageClient,
        rows: list[BatchRow],
        default_size: str,
        default_quality: str,
        default_watermark: bool,
        default_system_prompt: str,
        concurrency: int = 2,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.client = client
        self.rows = rows
        self.default_size = default_size
        self.default_quality = default_quality
        self.default_watermark = default_watermark
        self.default_system_prompt = default_system_prompt
        self.concurrency = max(1, int(concurrency))

        self._signaler = _BatchSignaler()
        self._signaler.started.connect(self._on_started)
        self._signaler.finished.connect(self._on_finished)
        self._signaler.all_done.connect(self.all_done)

        self._pending: list[_GenerateTask] = []
        self._running: int = 0
        self._completed: int = 0
        self._total: int = 0
        self._stopped: bool = False

    @Slot(int, int)
    def _on_started(self, item_id: int, source_index: int) -> None:
        self.started.emit(item_id, source_index)

    @Slot(object)
    def _on_finished(self, result: BatchResult) -> None:
        self._running -= 1
        self._completed += 1
        self.finished.emit(result)
        self._dispatch_next()
        if self._completed >= self._total and self._running == 0:
            self.all_done.emit()

    def _dispatch_next(self) -> None:
        if self._stopped:
            # 已停止: 把剩余 pending 标记为完成 (不发结果)
            while self._pending:
                self._pending.pop()
                self._completed += 1
            if self._running == 0:
                self.all_done.emit()
            return
        while self._pending and self._running < self.concurrency:
            task = self._pending.pop(0)
            self._running += 1
            from PySide6.QtCore import QThreadPool
            QThreadPool.globalInstance().start(task)

    def start(self) -> None:
        """提交所有任务到 QThreadPool"""
        if self._total > 0:
            return  # 已启动
        self._stopped = False
        self._total = len(self.rows)
        self._completed = 0
        self._running = 0
        self._pending = [
            _GenerateTask(
                self.client, row,
                self.default_size, self.default_quality,
                self.default_watermark, self.default_system_prompt,
            )
            for row in self.rows
        ]
        for t in self._pending:
            t.signaler = self._signaler
        self._dispatch_next()

    def stop(self) -> None:
        """取消尚未开始的任务 (已启动的无法中断)"""
        self._stopped = True
        self._dispatch_next()  # 触发清理逻辑

    @property
    def total(self) -> int:
        return self._total

    @property
    def completed(self) -> int:
        return self._completed

    @property
    def is_running(self) -> bool:
        return self._running > 0 or (self._total > 0 and self._completed < self._total)
