"""后台工作线程

将耗时的 API 调用放入 QThread，避免阻塞主线程 UI。
提供:
- GenerateWorker: 单张图片生成
- BatchWorker: 批量任务 (阶段2使用)
"""
from typing import Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from api_client import ZhipuImageClient


class GenerateWorker(QThread):
    """单张图片生成工作线程"""

    # 成功信号: 发送 (QImage, 原始二进制)
    finished_ok = Signal(object, object)
    # 失败信号: 发送错误信息
    failed = Signal(str)

    def __init__(
        self,
        client: ZhipuImageClient,
        prompt: str,
        size: str,
        quality: str,
        watermark: bool,
        system_prompt: str,
        parent=None,
    ):
        super().__init__(parent)
        self._client = client
        self._prompt = prompt
        self._size = size
        self._quality = quality
        self._watermark = watermark
        self._system_prompt = system_prompt

    def run(self) -> None:
        try:
            data = self._client.generate(
                prompt=self._prompt,
                size=self._size,
                quality=self._quality,
                watermark_enabled=self._watermark,
                system_prompt=self._system_prompt,
            )
            img = QImage()
            if img.loadFromData(data):
                self.finished_ok.emit(img, data)
            else:
                self.failed.emit("图片数据解析失败")
        except Exception as e:
            self.failed.emit(str(e))
