"""批量任务面板 (主区域)

功能:
- 顶部工具栏: 导入 Excel / 并发数 / 输出目录选择 / 开始 / 停止 / 全选 / 反选 / 导出勾选
- 中间列表: 每行一个 BatchItemWidget (checkbox + 提示词 + 缩略图 + 状态)
- 底部: 进度条 + 状态文本

信号 (向主窗口请求):
- request_client: 主窗口提供当前 ZhipuImageClient
- request_config: 主窗口提供当前 AppConfig
- request_zoom(QImage, prompt): 放大查看
- request_save(int, bytes, str): 保存单张图片 (item_id, raw_bytes, prompt)
- status_message(str): 状态栏消息
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from api_client import ZhipuImageClient
from batch_worker import BatchController, BatchResult
from config import AppConfig
from excel_io import BatchRow, read_excel, write_excel_safe
from output_manager import save_generation
from ui.batch_item_widget import BatchItemWidget
from ui.styles import (
    BG_CARD,
    BG_INPUT,
    BORDER,
    BORDER_FOCUS,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_WEAK,
)


class _PromptEditDialog(QDialog):
    """提示词编辑对话框 (用于重绘时修改 prompt)

    静态方法 ``edit_prompt`` 返回用户输入的提示词 (str), 取消则返回 None。
    """

    @staticmethod
    def edit_prompt(
        parent: Optional[QWidget] = None,
        title: str = "修改提示词",
        initial: str = "",
    ) -> Optional[str]:
        dlg = _PromptEditDialog(parent, title, initial)
        if dlg.exec() == QDialog.Accepted:
            text = dlg.edit.toPlainText().strip()
            return text or None
        return None

    def __init__(
        self,
        parent: Optional[QWidget],
        title: str,
        initial: str,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(520, 280)
        self.setStyleSheet(f"QDialog {{ background-color: {BG_CARD}; }}")

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(12)

        hint = QLabel("修改提示词后点击「确定」开始重绘")
        hint.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"
        )
        v.addWidget(hint)

        self.edit = QPlainTextEdit()
        self.edit.setPlainText(initial)
        self.edit.setStyleSheet(
            f"QPlainTextEdit {{"
            f" background-color: {BG_INPUT};"
            f" border: 1px solid {BORDER};"
            f" border-radius: 8px;"
            f" padding: 10px;"
            f" color: {TEXT_PRIMARY};"
            f" font-size: 13px;"
            f"}}"
            f"QPlainTextEdit:focus {{ border: 1px solid {BORDER_FOCUS}; }}"
        )
        v.addWidget(self.edit, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        ok_btn = QPushButton("确定重绘")
        ok_btn.setObjectName("primaryBtn")
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        v.addLayout(btn_row)


class _DragListWidget(QListWidget):
    """支持内部拖拽重排的 QListWidget

    拖拽完成后发出 ``order_changed`` 信号, 由 BatchPanel 同步 self._rows 顺序。
    每个 item 通过 ``setData(Qt.UserRole, item_id)`` 携带行 ID。
    """

    order_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # 启用内部拖拽重排 (注意: setMovement(Static) 会强制 dragEnabled=False, 故不调用)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QListWidget.SingleSelection)
        # 视觉: 透明背景, 无边框, 无选中高亮 (选中态由 BatchItemWidget 自身处理)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(
            "QListWidget { background-color: transparent; border: none; }"
            "QListWidget::item { background: transparent; border: none;"
            " padding: 0; margin: 0; }"
            "QListWidget::item:selected { background: transparent; }"
        )
        self.setSpacing(8)
        self.setContentsMargins(0, 0, 0, 0)

    def dropEvent(self, e):
        """重写 dropEvent: 调用父类完成移动后, 发出 order_changed 信号"""
        super().dropEvent(e)
        self.order_changed.emit()


class BatchPanel(QFrame):
    """批量任务面板"""

    # 请求主窗口
    request_zoom = Signal(object, str)            # QImage, prompt (单图)
    request_save = Signal(int, object, str)       # item_id, raw_bytes, prompt (单图)
    request_save_multi = Signal(int, object, str) # item_id, list[bytes], prompt (组图)
    status_message = Signal(str)                  # 状态栏消息

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("root")

        # 状态
        self._rows: list[BatchRow] = []
        self._widgets: dict[int, BatchItemWidget] = {}  # item_id -> widget
        self._client: Optional[ZhipuImageClient] = None
        self._config: Optional[AppConfig] = None
        self._controller: Optional[BatchController] = None
        self._excel_path: Optional[Path] = None
        self._output_dir: Optional[Path] = None
        self._next_item_id: int = 1

        self._build_ui()
        self._update_action_state()

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 16)
        outer.setSpacing(14)

        # 标题
        title = QLabel("批量任务")
        title.setStyleSheet(
            f"font-size: 24px; font-weight: 700; color: {TEXT_PRIMARY};"
            " background: transparent;"
        )
        outer.addWidget(title)

        subtitle = QLabel("导入 Excel → 并发生成 → 勾选最终结果 → 导出")
        subtitle.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"
        )
        outer.addWidget(subtitle)

        # 工具栏卡片
        toolbar = QFrame()
        toolbar.setObjectName("promptCard")
        tb_layout = QVBoxLayout(toolbar)
        tb_layout.setContentsMargins(16, 12, 16, 12)
        tb_layout.setSpacing(10)

        # 第一行: 导入 / 输出目录
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.import_btn = QPushButton("📂 导入 Excel")
        self.import_btn.setObjectName("primaryBtn")
        self.import_btn.setCursor(Qt.PointingHandCursor)
        self.import_btn.clicked.connect(self._on_import)
        row1.addWidget(self.import_btn)

        self.excel_label = QLabel("未导入文件")
        self.excel_label.setStyleSheet(
            f"color: {TEXT_WEAK}; font-size: 12px; background: transparent;"
        )
        row1.addWidget(self.excel_label, 1)

        self.dir_btn = QPushButton("📁 选择输出目录")
        self.dir_btn.setObjectName("secondaryBtn")
        self.dir_btn.setCursor(Qt.PointingHandCursor)
        self.dir_btn.clicked.connect(self._on_select_dir)
        row1.addWidget(self.dir_btn)

        self.dir_label = QLabel("未选择")
        self.dir_label.setStyleSheet(
            f"color: {TEXT_WEAK}; font-size: 12px; background: transparent;"
        )
        self.dir_label.setMinimumWidth(120)
        self.dir_label.setMaximumWidth(200)
        row1.addWidget(self.dir_label)
        tb_layout.addLayout(row1)

        # 第二行: 并发数 / 组图模式 / n 参数 / 开始 / 停止 / 全选 / 反选 / 导出
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        row2.addWidget(QLabel("并发数:"))
        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(1, 10)
        self.concurrency_spin.setValue(2)
        self.concurrency_spin.setFixedWidth(90)
        self.concurrency_spin.setToolTip("同时调用 API 的并发数, 过高可能触发限流")
        row2.addWidget(self.concurrency_spin)

        row2.addSpacing(12)

        # 组图模式开关
        self.group_mode_check = QCheckBox("组图模式")
        self.group_mode_check.setCursor(Qt.PointingHandCursor)
        self.group_mode_check.setToolTip("开启后, 每个 prompt 一次性生成 n 张图, 行内显示缩略图列表")
        self.group_mode_check.setStyleSheet(
            f"QCheckBox {{ color: {TEXT_PRIMARY}; font-size: 12px;"
            f" background: transparent; spacing: 6px; }}"
            f"QCheckBox::indicator {{ width: 16px; height: 16px;"
            f" border: 1px solid {BORDER}; border-radius: 4px;"
            f" background-color: {BG_INPUT}; }}"
            f"QCheckBox::indicator:hover {{ border: 1px solid {BORDER_FOCUS}; }}"
            f"QCheckBox::indicator:checked {{ background-color: #6366f1;"
            f" border: 1px solid #818cf8; }}"
        )
        row2.addWidget(self.group_mode_check)

        row2.addWidget(QLabel("每行张数 n:"))
        self.n_spin = QSpinBox()
        self.n_spin.setRange(2, 4)
        self.n_spin.setValue(2)
        self.n_spin.setFixedWidth(90)
        self.n_spin.setToolTip("每个 prompt 一次生成的图片数 (2-4)")
        self.n_spin.setEnabled(False)  # 默认关闭, 组图模式开启后启用
        self.group_mode_check.toggled.connect(self.n_spin.setEnabled)
        row2.addWidget(self.n_spin)

        row2.addSpacing(12)

        self.start_btn = QPushButton("▶ 开始生成")
        self.start_btn.setObjectName("primaryBtn")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self._on_start)
        row2.addWidget(self.start_btn)

        self.stop_btn = QPushButton("■ 停止")
        self.stop_btn.setObjectName("secondaryBtn")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        row2.addWidget(self.stop_btn)

        row2.addStretch()

        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.setObjectName("secondaryBtn")
        self.select_all_btn.setCursor(Qt.PointingHandCursor)
        self.select_all_btn.clicked.connect(self._on_select_all)
        row2.addWidget(self.select_all_btn)

        self.invert_btn = QPushButton("反选")
        self.invert_btn.setObjectName("secondaryBtn")
        self.invert_btn.setCursor(Qt.PointingHandCursor)
        self.invert_btn.clicked.connect(self._on_invert)
        row2.addWidget(self.invert_btn)

        self.export_btn = QPushButton("💾 导出勾选结果")
        self.export_btn.setObjectName("primaryBtn")
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.clicked.connect(self._on_export)
        row2.addWidget(self.export_btn)

        tb_layout.addLayout(row2)
        outer.addWidget(toolbar)

        # 列表标题
        list_header = QHBoxLayout()
        list_header.setSpacing(8)
        self.list_title = QLabel(f"结果列表 (0)")
        self.list_title.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};"
            " background: transparent;"
        )
        list_header.addWidget(self.list_title)
        list_header.addStretch()
        self.selection_count_label = QLabel("已勾选 0 项")
        self.selection_count_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"
        )
        list_header.addWidget(self.selection_count_label)
        outer.addLayout(list_header)

        # 列表区 (QListWidget 支持拖拽重排, 自带滚动)
        self.list_widget = _DragListWidget()
        self.list_widget.order_changed.connect(self._on_order_changed)
        outer.addWidget(self.list_widget, 1)

        # 空状态 (与 list_widget 互斥, 都给 stretch=1 让其填满剩余空间)
        self.empty_label = QLabel("导入 Excel 后此处显示批量结果\n拖动行可调整顺序, 重绘会追加新行 ✨")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(
            f"color: {TEXT_WEAK}; font-size: 14px; background-color: {BG_CARD};"
            f" border: 1px dashed {BORDER}; border-radius: 12px;"
        )
        self.empty_label.setMinimumHeight(120)
        outer.addWidget(self.empty_label, 1)
        self.list_widget.setVisible(False)

        # 进度条
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        outer.addWidget(self.progress)

        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;"
        )
        self.progress_label.setVisible(False)
        outer.addWidget(self.progress_label)

    # ---------------- 外部接口 ----------------
    def set_client(self, client: Optional[ZhipuImageClient]) -> None:
        """主窗口在配置变更时调用"""
        self._client = client

    def set_config(self, config: AppConfig) -> None:
        """主窗口在配置变更时调用"""
        self._config = config

    # ---------------- 导入 / 输出目录 ----------------
    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Excel 文件", "", "Excel 文件 (*.xlsx *.xls)"
        )
        if not path:
            return
        try:
            rows = read_excel(path)
        except Exception as e:
            self.status_message.emit(f"导入失败: {e}")
            return
        if not rows:
            self.status_message.emit("Excel 中没有有效的 prompt 行")
            return

        self._excel_path = Path(path)
        self.excel_label.setText(f"📋 {self._excel_path.name}  ({len(rows)} 行)")
        self.excel_label.setToolTip(str(self._excel_path))

        # 根据组图模式设置每行预期图片数
        n_expected = self._current_n_expected()

        # 重置列表
        self._clear_list()
        for row in rows:
            row.item_id = self._next_item_id
            self._next_item_id += 1
            row.n_expected = n_expected
            self._rows.append(row)
            self._add_widget_for(row)
        self._refresh_list_title()
        self._hide_empty()
        self._update_action_state()
        mode_hint = f", 组图×{n_expected}" if n_expected > 1 else ""
        self.status_message.emit(f"已导入 {len(rows)} 行{mode_hint}, 点击「开始生成」执行批量")

    def _on_select_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if not path:
            return
        self._output_dir = Path(path)
        self.dir_label.setText(f"📁 {self._output_dir.name}")
        self.dir_label.setToolTip(str(self._output_dir))
        self._update_action_state()
        self.status_message.emit(f"输出目录: {self._output_dir}")

    # ---------------- 列表管理 ----------------
    def _clear_list(self) -> None:
        # 删除 QListWidget 中所有 item (setItemWidget 的 widget 会自动回收)
        self.list_widget.clear()
        self._widgets.clear()
        self._rows.clear()
        self._next_item_id = 1

    def _add_widget_for(self, row: BatchRow) -> BatchItemWidget:
        w = BatchItemWidget(row)
        w.selection_changed.connect(self._on_selection_changed)
        w.regenerate_clicked.connect(self._on_regenerate)
        w.zoom_clicked.connect(self._on_zoom)
        # 组图模式: 单击第 idx 个缩略图放大
        w.zoom_index_clicked.connect(self._on_zoom_index)
        w.save_clicked.connect(self._on_save_image)
        w.delete_clicked.connect(self._on_delete)
        # 创建 item, 携带 item_id, 设置固定高度后 setItemWidget
        # 行高与 BatchItemWidget.setFixedHeight 保持一致 (单图 96, 组图 108)
        item_h = 108 if row.n_expected > 1 else 96
        item = QListWidgetItem()
        item.setData(Qt.UserRole, row.item_id)
        item.setSizeHint(QSize(0, item_h))
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, w)
        self._widgets[row.item_id] = w
        return w

    def _current_n_expected(self) -> int:
        """获取当前组图模式下的 n 参数 (未开启组图模式返回 1)"""
        if self.group_mode_check.isChecked():
            return max(2, int(self.n_spin.value()))
        return 1

    def _on_delete(self, item_id: int) -> None:
        """删除指定行: 从 list_widget / _rows / _widgets 中移除"""
        # 找到对应的 QListWidgetItem
        target_row = -1
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            if it is not None and it.data(Qt.UserRole) == item_id:
                target_row = i
                break
        if target_row < 0:
            return
        # 从 list_widget 移除 (setItemWidget 的 widget 会被 Qt 回收)
        self.list_widget.takeItem(target_row)
        # 从 self._rows 移除
        self._rows = [r for r in self._rows if r.item_id != item_id]
        # 从 self._widgets 移除
        w = self._widgets.pop(item_id, None)
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        # 刷新标题与空状态
        self._refresh_list_title()
        if not self._rows:
            self.list_widget.setVisible(False)
            self.empty_label.setVisible(True)
        self.status_message.emit(f"已删除行 #{item_id}")

    def _hide_empty(self) -> None:
        self.empty_label.setVisible(False)
        self.list_widget.setVisible(True)

    def _on_order_changed(self) -> None:
        """拖拽重排后: 按 QListWidget 顺序重建 self._rows"""
        # 保留 source_index 不变, 仅重排 self._rows 顺序
        id_order: list[int] = []
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            if it is not None:
                id_order.append(it.data(Qt.UserRole))
        # 按 id 顺序重建 rows
        id_to_row = {r.item_id: r for r in self._rows}
        new_rows = [id_to_row[i] for i in id_order if i in id_to_row]
        # 补上不在列表中的行 (防御性, 通常不会发生)
        for r in self._rows:
            if r.item_id not in id_order:
                new_rows.append(r)
        self._rows = new_rows
        self.status_message.emit("已调整顺序")

    def _refresh_list_title(self) -> None:
        total = len(self._rows)
        selected = sum(1 for r in self._rows if r.selected)
        self.list_title.setText(f"结果列表 ({total})")
        self.selection_count_label.setText(f"已勾选 {selected} 项")

    def _on_selection_changed(self, item_id: int, checked: bool) -> None:
        self._refresh_list_title()
        self._update_action_state()

    # ---------------- 开始 / 停止 ----------------
    def _on_start(self) -> None:
        if self._client is None:
            self.status_message.emit("请先在左侧配置 API Key")
            return
        if not self._rows:
            self.status_message.emit("请先导入 Excel")
            return
        # 收集所有未成功 (pending / failed) 的行, 重新生成
        pending = [r for r in self._rows if r.status in ("pending", "failed")]
        if not pending:
            self.status_message.emit("所有行已成功, 如需重生成请点击行内 ⟳ 按钮")
            return
        # 标记 pending 行为 running 状态会通过 BatchController.started 信号触发
        cfg = self._config or AppConfig()
        self._controller = BatchController(
            client=self._client,
            rows=pending,
            default_size=cfg.size,
            default_quality=cfg.quality,
            default_watermark=cfg.watermark_enabled,
            default_system_prompt=cfg.system_prompt,
            concurrency=self.concurrency_spin.value(),
        )
        self._controller.started.connect(self._on_task_started)
        self._controller.finished.connect(self._on_task_finished)
        self._controller.all_done.connect(self._on_all_done)
        self._controller.start()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.import_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress_label.setVisible(True)
        self.progress.setRange(0, len(pending))
        self.progress.setValue(0)
        self.progress_label.setText(f"0 / {len(pending)} 已完成")
        self.status_message.emit(f"开始批量生成, 并发数 {self.concurrency_spin.value()}")

    def _on_stop(self) -> None:
        if self._controller is not None:
            self._controller.stop()
            self.status_message.emit("已停止, 未完成的任务将被取消")
        self.stop_btn.setEnabled(False)

    def _on_task_started(self, item_id: int, source_index: int) -> None:
        w = self._widgets.get(item_id)
        if w is not None:
            w.set_loading()

    def _on_task_finished(self, result: BatchResult) -> None:
        w = self._widgets.get(result.item_id)
        if w is None:
            return
        row = w.row
        # 计算实际使用的 size/quality (override > 默认)
        cfg = self._config or AppConfig()
        used_size = row.size_override or cfg.size
        used_quality = row.quality_override or cfg.quality
        is_multi = result.n_expected > 1
        if result.ok and result.qimages:
            if is_multi:
                w.set_success_multi(result.qimages, result.images_data)
            else:
                # 单图模式: qimages 长度 1
                w.set_success_single(result.qimages[0], result.images_data[0])
            # 默认勾选最新生成的结果: 取消勾选同 prompt 的旧结果
            self._select_latest_for_prompt(result.item_id, w.row.prompt)
            # 额外保存到 outputs/ 归档 (组图: 每张图各保存一条记录)
            for img_bytes in result.images_data:
                try:
                    save_generation(
                        image_data=img_bytes,
                        prompt=row.prompt,
                        size=used_size,
                        quality=used_quality,
                        status="success",
                    )
                except Exception:
                    pass
        else:
            w.set_failed(result.error or "未知错误")
            # 失败也记录到 outputs/ 历史
            try:
                save_generation(
                    image_data=None,
                    prompt=row.prompt,
                    size=used_size,
                    quality=used_quality,
                    status="failed",
                    error=result.error,
                )
            except Exception:
                pass
        # 更新进度
        if self._controller is not None:
            done = self._controller.completed
            total = self._controller.total
            self.progress.setValue(done)
            self.progress_label.setText(f"{done} / {total} 已完成")
        self._refresh_list_title()

    def _on_all_done(self) -> None:
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.import_btn.setEnabled(True)
        self.status_message.emit("批量生成完成")
        self._controller = None

    # ---------------- 默认勾选最新结果 ----------------
    def _select_latest_for_prompt(self, latest_id: int, prompt: str) -> None:
        """对于同一 prompt, 取消勾选旧结果, 仅保留最新勾选"""
        for r in self._rows:
            if r.prompt == prompt and r.item_id != latest_id:
                r.selected = False
                w = self._widgets.get(r.item_id)
                if w is not None:
                    # 阻止信号循环
                    w.check.blockSignals(True)
                    w.check.setChecked(False)
                    w.check.blockSignals(False)
            elif r.prompt == prompt and r.item_id == latest_id:
                r.selected = True
                w = self._widgets.get(r.item_id)
                if w is not None:
                    w.check.blockSignals(True)
                    w.check.setChecked(True)
                    w.check.blockSignals(False)
        self._refresh_list_title()

    # ---------------- 单行操作 ----------------
    def _on_regenerate(self, item_id: int) -> None:
        """单行重绘: 弹窗让用户编辑提示词, 用新 prompt 追加新行"""
        if self._client is None:
            self.status_message.emit("请先在左侧配置 API Key")
            return
        old = next((r for r in self._rows if r.item_id == item_id), None)
        if old is None:
            return
        # 弹窗编辑提示词 (预填原 prompt)
        new_prompt = _PromptEditDialog.edit_prompt(
            parent=self, title=f"重绘 #{item_id} - 修改提示词", initial=old.prompt
        )
        if new_prompt is None:
            return  # 用户取消
        # 创建新行 (复制原参数, 用新 prompt, 保留 n_expected)
        new_row = BatchRow(
            source_index=old.source_index,
            prompt=new_prompt,
            size_override=old.size_override,
            quality_override=old.quality_override,
            watermark_override=old.watermark_override,
            system_prompt_override=old.system_prompt_override,
            item_id=self._next_item_id,
            selected=True,
            n_expected=old.n_expected,
        )
        self._next_item_id += 1
        self._rows.append(new_row)
        self._add_widget_for(new_row)
        self._refresh_list_title()
        self._hide_empty()
        # 单独发起生成
        cfg = self._config or AppConfig()
        self._controller = BatchController(
            client=self._client,
            rows=[new_row],
            default_size=cfg.size,
            default_quality=cfg.quality,
            default_watermark=cfg.watermark_enabled,
            default_system_prompt=cfg.system_prompt,
            concurrency=1,
        )
        self._controller.started.connect(self._on_task_started)
        self._controller.finished.connect(self._on_task_finished)
        self._controller.all_done.connect(self._on_single_done)
        self._controller.start()
        self.status_message.emit(f"重绘 #{item_id} → 新行 #{new_row.item_id}")

    def _on_single_done(self) -> None:
        """单行重绘完成 (不切换主按钮状态)"""
        self.status_message.emit("重绘完成")

    def _on_zoom(self, qimage: QImage, prompt: str) -> None:
        self.request_zoom.emit(qimage, prompt)

    def _on_zoom_index(self, item_id: int, idx: int) -> None:
        """组图模式: 单击第 idx 张缩略图放大"""
        w = self._widgets.get(item_id)
        if w is None:
            return
        qimages = w._qimages  # list[QImage]
        if 0 <= idx < len(qimages):
            self.request_zoom.emit(qimages[idx], w.row.prompt)

    def _on_save_image(self, item_id: int) -> None:
        row = next((r for r in self._rows if r.item_id == item_id), None)
        if row is None:
            return
        if row.n_expected > 1:
            # 组图模式: 批量保存所有图
            if not row.images_data:
                return
            self.request_save_multi.emit(item_id, row.images_data, row.prompt)
        else:
            # 单图模式
            if not row.image_data:
                return
            self.request_save.emit(item_id, row.image_data, row.prompt)

    # ---------------- 全选 / 反选 ----------------
    def _on_select_all(self) -> None:
        for w in self._widgets.values():
            w.check.blockSignals(True)
            w.check.setChecked(True)
            w.check.blockSignals(False)
            w.row.selected = True
        self._refresh_list_title()
        self._update_action_state()

    def _on_invert(self) -> None:
        for w in self._widgets.values():
            new_state = not w.row.selected
            w.check.blockSignals(True)
            w.check.setChecked(new_state)
            w.check.blockSignals(False)
            w.row.selected = new_state
        self._refresh_list_title()
        self._update_action_state()

    # ---------------- 导出 ----------------
    def _on_export(self) -> None:
        if self._excel_path is None:
            self.status_message.emit("请先导入 Excel")
            return
        if self._output_dir is None:
            self.status_message.emit("请先选择输出目录")
            return
        selected = [r for r in self._rows if r.selected and r.status == "success"]
        if not selected:
            self.status_message.emit("没有可导出的勾选成功结果")
            return

        # 保存图片到输出目录
        # 单图模式: 文件名 序号_item_id_提示词前缀.png, image_path 列写单一路径
        # 组图模式: 文件名 序号_item_id_序号_提示词前缀.png, image_path 列用 ";" 拼接多路径
        out_dir = self._output_dir
        total_images = 0
        try:
            for r in selected:
                safe_prompt = "".join(
                    c for c in r.prompt[:16] if c.isalnum() or c in "_-"
                ) or "image"
                if r.n_expected > 1 and r.images_data:
                    # 组图: 按序号写多张
                    paths: list[str] = []
                    for idx, raw in enumerate(r.images_data):
                        fname = (
                            f"{r.source_index:03d}_{r.item_id:03d}_{idx+1:02d}_"
                            f"{safe_prompt}.png"
                        )
                        img_path = out_dir / fname
                        img_path.write_bytes(raw)
                        paths.append(str(img_path))
                        total_images += 1
                    r.image_paths = paths
                    # image_path 字段拼接所有路径 (Excel 中以 ";" 分隔)
                    r.image_path = ";".join(paths)
                else:
                    # 单图
                    fname = f"{r.source_index:03d}_{r.item_id:03d}_{safe_prompt}.png"
                    img_path = out_dir / fname
                    if r.image_data:
                        img_path.write_bytes(r.image_data)
                        r.image_path = str(img_path)
                        total_images += 1
            # 写 Excel (PermissionError 时自动重试新文件名)
            xlsx_path = write_excel_safe(self._excel_path, self._rows, out_dir)
        except PermissionError as e:
            self.status_message.emit(
                f"导出失败: Excel 文件被占用, 请关闭已打开的 {self._excel_path.stem}_结果.xlsx 后重试"
            )
            return
        except Exception as e:
            self.status_message.emit(f"导出失败: {e}")
            return

        self.status_message.emit(
            f"已导出 {total_images} 张图片 + Excel: {xlsx_path.name}"
        )

    # ---------------- 状态联动 ----------------
    def _update_action_state(self) -> None:
        has_rows = bool(self._rows)
        has_excel = self._excel_path is not None
        has_dir = self._output_dir is not None
        self.start_btn.setEnabled(has_rows and self._client is not None)
        self.select_all_btn.setEnabled(has_rows)
        self.invert_btn.setEnabled(has_rows)
        self.export_btn.setEnabled(has_rows and has_excel and has_dir)
