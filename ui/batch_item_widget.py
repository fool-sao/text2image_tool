"""批量任务单行结果组件

布局:
┌──┬─────┬────────────────────────┬──────────┬──────────────┬──────────────┐
│☑ │ #3  | 提示词文本 (多行)      | 1280x1280| [缩略图列表] | ● 成功 12:30 │
│  │     |                        | hd 水印  | [⛶][⛶]...   | [⟳][💾][🗑] │
└──┴─────┴────────────────────────┴──────────┴──────────────┴──────────────┘

- checkbox: 勾选导出
- 序号: item_id
- 提示词: BatchRow.prompt (截断 + tooltip)
- 参数: size / quality / watermark
- 缩略图: 单图模式 1 个 80x80; 组图模式 N 个 56x56 横向排列, 每个独立点击放大
- 状态: pending/running/success/failed + 时间
- 操作: 重绘 / 保存 / 删除 (放大改为点击缩略图)

信号:
- selection_changed(int, bool): item_id, checked
- regenerate_clicked(int): item_id
- zoom_clicked(object, str): QImage, prompt  (单图) 或 zoom_index_clicked(int, int): item_id, index (组图)
- save_clicked(int): item_id
- delete_clicked(int): item_id
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from excel_io import BatchRow
from ui.styles import (
    BG_CARD,
    BG_INPUT,
    BORDER,
    BORDER_FOCUS,
    DANGER,
    SUCCESS,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_WEAK,
    WARNING,
)


class _ClickableThumb(QLabel):
    """可点击的缩略图 Label, 单击发 clicked 信号

    仅在有图时响应点击 (无图时 setEnabled(False) 即可禁用)。
    """

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self._has_image = False

    def set_has_image(self, has: bool) -> None:
        self._has_image = has
        self.setCursor(Qt.PointingHandCursor if has else Qt.ArrowCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self._has_image:
            self.clicked.emit()
            e.accept()
            return
        super().mousePressEvent(e)


class BatchItemWidget(QFrame):
    """单行批量结果组件

    根据 row.n_expected 决定缩略图区布局:
    - n=1: 单缩略图 80x80 (单图模式)
    - n>1: 横向排列 n 个 56x56 缩略图 (组图模式)
    """

    selection_changed = Signal(int, bool)         # item_id, checked
    regenerate_clicked = Signal(int)              # item_id
    zoom_clicked = Signal(object, str)            # QImage, prompt (单图模式)
    zoom_index_clicked = Signal(int, int)         # item_id, index (组图模式)
    save_clicked = Signal(int)                    # item_id
    delete_clicked = Signal(int)                  # item_id

    THUMB_SIZE_SINGLE = 80    # 单图模式缩略图尺寸
    THUMB_SIZE_MULTI = 56     # 组图模式每个缩略图尺寸

    def __init__(self, row: BatchRow, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("batchItem")
        self.row = row
        self._qimages: list[QImage] = []           # 组图模式下多张 QImage
        self._qimage: Optional[QImage] = None       # 单图模式兼容
        self._is_multi: bool = row.n_expected > 1

        # 行高: 组图模式根据 n 略增; 单图模式保持 96
        if self._is_multi:
            self._thumb_size = self.THUMB_SIZE_MULTI
            self.setFixedHeight(108)
        else:
            self._thumb_size = self.THUMB_SIZE_SINGLE
            self.setFixedHeight(96)
        self.setStyleSheet(self._frame_style())

        self._build_ui()
        self._refresh_status()

    # ---------------- UI ----------------
    def _frame_style(self) -> str:
        return (
            f"QFrame#batchItem {{"
            f" background-color: {BG_CARD};"
            f" border: 1px solid {BORDER};"
            f" border-radius: 10px;"
            f"}}"
            f"QFrame#batchItem:hover {{"
            f" border: 1px solid {BORDER_FOCUS};"
            f"}}"
        )

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # 勾选框
        self.check = QCheckBox()
        self.check.setChecked(self.row.selected)
        self.check.stateChanged.connect(self._on_check_changed)
        layout.addWidget(self.check, 0, Qt.AlignVCenter)

        # 序号
        self.id_label = QLabel(f"#{self.row.item_id}")
        self.id_label.setFixedWidth(40)
        self.id_label.setStyleSheet(
            f"color: {TEXT_WEAK}; font-size: 12px; font-weight: 600;"
            " background: transparent; border: none;"
        )
        self.id_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.id_label, 0, Qt.AlignVCenter)

        # 提示词 (多行截断)
        prompt_text = self.row.prompt
        if len(prompt_text) > 120:
            prompt_text = prompt_text[:120] + "…"
        self.prompt_label = QLabel(prompt_text)
        self.prompt_label.setToolTip(self.row.prompt)
        self.prompt_label.setWordWrap(True)
        self.prompt_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 12px;"
            " background: transparent; border: none;"
        )
        layout.addWidget(self.prompt_label, 1, Qt.AlignVCenter)

        # 参数标签 (size / quality / watermark / n)
        params = []
        if self.row.size_override:
            params.append(self.row.size_override)
        if self.row.quality_override:
            params.append(self.row.quality_override)
        if self.row.watermark_override is not None:
            params.append("水印" if self.row.watermark_override else "无水印")
        if self._is_multi:
            params.append(f"组图×{self.row.n_expected}")
        params_text = " · ".join(params) if params else "默认参数"
        self.params_label = QLabel(params_text)
        self.params_label.setFixedWidth(150)
        self.params_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px;"
            " background: transparent; border: none;"
        )
        self.params_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.params_label.setWordWrap(False)
        layout.addWidget(self.params_label, 0, Qt.AlignVCenter)

        # 缩略图区 (容器: 单图或组图)
        self.thumb_container = QWidget()
        self.thumb_container.setStyleSheet("background: transparent;")
        self.thumb_layout = QHBoxLayout(self.thumb_container)
        self.thumb_layout.setContentsMargins(0, 0, 0, 0)
        self.thumb_layout.setSpacing(6)
        self._thumbs: list[_ClickableThumb] = []

        if self._is_multi:
            # 组图模式: 预创建 n 个缩略图占位
            for i in range(self.row.n_expected):
                t = _ClickableThumb()
                t.setFixedSize(self._thumb_size, self._thumb_size)
                t.setAlignment(Qt.AlignCenter)
                t.setStyleSheet(
                    f"background-color: {BG_INPUT}; border-radius: 6px;"
                    f" color: {TEXT_WEAK}; font-size: 9px; border: none;"
                )
                t.setText(f"#{i+1}")
                t.set_has_image(False)
                # 用默认参数捕获 i, 避免闭包变量共享
                t.clicked.connect(lambda checked=False, idx=i: self._on_multi_thumb_click(idx))
                self.thumb_layout.addWidget(t)
                self._thumbs.append(t)
        else:
            # 单图模式: 仅一个缩略图
            t = _ClickableThumb()
            t.setFixedSize(self._thumb_size, self._thumb_size)
            t.setAlignment(Qt.AlignCenter)
            t.setStyleSheet(
                f"background-color: {BG_INPUT}; border-radius: 6px;"
                f" color: {TEXT_WEAK}; font-size: 10px; border: none;"
            )
            t.setText("等待")
            t.set_has_image(False)
            t.clicked.connect(self._on_zoom_clicked)
            self.thumb_layout.addWidget(t)
            self._thumbs.append(t)

        layout.addWidget(self.thumb_container, 0, Qt.AlignVCenter)

        # 右侧: 状态 + 操作按钮
        right = QVBoxLayout()
        right.setSpacing(4)
        right.setContentsMargins(0, 0, 0, 0)

        self.status_label = QLabel()
        self.status_label.setStyleSheet(
            f"color: {TEXT_WEAK}; font-size: 11px;"
            " background: transparent; border: none;"
        )
        self.status_label.setAlignment(Qt.AlignRight)
        right.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        btn_row.setContentsMargins(0, 0, 0, 0)

        self.btn_regen = self._mk_tool_btn("⟳")
        self.btn_regen.setToolTip("重绘")
        self.btn_regen.clicked.connect(
            lambda: self.regenerate_clicked.emit(self.row.item_id)
        )
        btn_row.addWidget(self.btn_regen)

        self.btn_save = self._mk_tool_btn("💾")
        self.btn_save.setToolTip("保存图片")
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(
            lambda: self.save_clicked.emit(self.row.item_id)
        )
        btn_row.addWidget(self.btn_save)

        self.btn_delete = self._mk_tool_btn("🗑", danger=True)
        self.btn_delete.setToolTip("删除此行")
        self.btn_delete.clicked.connect(
            lambda: self.delete_clicked.emit(self.row.item_id)
        )
        btn_row.addWidget(self.btn_delete)

        btn_row.addStretch()
        right.addLayout(btn_row)

        layout.addLayout(right, 0)

        # 阴影
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 3)
        c = shadow.color()
        c.setAlpha(80)
        shadow.setColor(c)
        self.setGraphicsEffect(shadow)

    def _mk_tool_btn(self, text: str, danger: bool = False) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(28, 26)
        btn.setCursor(Qt.PointingHandCursor)
        if danger:
            # 删除按钮: 红色调警示样式
            btn.setStyleSheet(
                f"QPushButton {{"
                f" background-color: {BG_INPUT};"
                f" color: {TEXT_SECONDARY};"
                f" border: 1px solid {BORDER};"
                f" border-radius: 6px;"
                f" font-size: 13px;"
                f" padding: 0;"
                f"}}"
                f"QPushButton:hover {{"
                f" background-color: rgba(239, 68, 68, 0.18);"
                f" color: {DANGER};"
                f" border: 1px solid rgba(239, 68, 68, 0.5);"
                f"}}"
                f"QPushButton:pressed {{"
                f" background-color: rgba(239, 68, 68, 0.3);"
                f"}}"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton {{"
                f" background-color: {BG_INPUT};"
                f" color: {TEXT_SECONDARY};"
                f" border: 1px solid {BORDER};"
                f" border-radius: 6px;"
                f" font-size: 13px;"
                f" padding: 0;"
                f"}}"
                f"QPushButton:hover {{"
                f" background-color: #2d3142;"
                f" color: {TEXT_PRIMARY};"
                f" border: 1px solid {BORDER_FOCUS};"
                f"}}"
                f"QPushButton:disabled {{"
                f" color: {TEXT_WEAK};"
                f" background-color: {BG_CARD};"
                f"}}"
            )
        return btn

    # ---------------- 状态切换 ----------------
    def set_loading(self) -> None:
        self.row.status = "running"
        for i, t in enumerate(self._thumbs):
            t.setText("生成中" if not self._is_multi else f"#{i+1}")
            t.setPixmap(QPixmap())
            t.set_has_image(False)
        self.btn_save.setEnabled(False)
        self._refresh_status()

    def set_success_single(self, qimage: QImage, image_data: bytes) -> None:
        """单图模式成功"""
        self._qimage = qimage
        self._qimages = [qimage]
        self.row.status = "success"
        self.row.image_data = image_data
        self.row.images_data = [image_data]
        self.row.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 设置缩略图
        t = self._thumbs[0]
        pix = QPixmap.fromImage(qimage)
        scaled = pix.scaled(
            self._thumb_size, self._thumb_size,
            Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation,
        )
        if scaled.width() > self._thumb_size or scaled.height() > self._thumb_size:
            x = (scaled.width() - self._thumb_size) // 2
            y = (scaled.height() - self._thumb_size) // 2
            scaled = scaled.copy(x, y, self._thumb_size, self._thumb_size)
        t.setText("")
        t.setPixmap(scaled)
        t.set_has_image(True)
        self.btn_save.setEnabled(True)
        self._refresh_status()

    def set_success_multi(self, qimages: list, images_data: list) -> None:
        """组图模式成功

        Args:
            qimages: QImage 列表 (长度可能 < n_expected, 个别失败)
            images_data: bytes 列表
        """
        self._qimages = list(qimages)
        self.row.status = "success"
        self.row.images_data = list(images_data)
        # 单图兼容字段: 取首张
        if qimages:
            self._qimage = qimages[0]
            self.row.image_data = images_data[0] if images_data else None
        self.row.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 逐个填充缩略图 (多余的保持占位)
        for i, t in enumerate(self._thumbs):
            if i < len(qimages):
                pix = QPixmap.fromImage(qimages[i])
                scaled = pix.scaled(
                    self._thumb_size, self._thumb_size,
                    Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation,
                )
                if scaled.width() > self._thumb_size or scaled.height() > self._thumb_size:
                    x = (scaled.width() - self._thumb_size) // 2
                    y = (scaled.height() - self._thumb_size) // 2
                    scaled = scaled.copy(x, y, self._thumb_size, self._thumb_size)
                t.setText("")
                t.setPixmap(scaled)
                t.set_has_image(True)
            else:
                t.setText("—")
                t.setPixmap(QPixmap())
                t.set_has_image(False)
        # 至少有一张图就可保存
        self.btn_save.setEnabled(bool(qimages))
        self._refresh_status()

    def set_failed(self, err_msg: str) -> None:
        self.row.status = "failed"
        self.row.error = err_msg
        self.row.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for i, t in enumerate(self._thumbs):
            t.setText("失败" if not self._is_multi else f"#{i+1}")
            t.setPixmap(QPixmap())
            t.set_has_image(False)
        self.btn_save.setEnabled(False)
        self._refresh_status()

    def _refresh_status(self) -> None:
        status = self.row.status
        if status == "pending":
            self.status_label.setText("● 待生成")
            self.status_label.setStyleSheet(
                f"color: {TEXT_WEAK}; font-size: 11px;"
                " background: transparent; border: none;"
            )
        elif status == "running":
            self.status_label.setText("● 生成中")
            self.status_label.setStyleSheet(
                f"color: {WARNING}; font-size: 11px; font-weight: 600;"
                " background: transparent; border: none;"
            )
        elif status == "success":
            ts = self.row.generated_at or ""
            self.status_label.setText(f"● 成功 {ts[-8:]}")
            self.status_label.setStyleSheet(
                f"color: {SUCCESS}; font-size: 11px; font-weight: 600;"
                " background: transparent; border: none;"
            )
        elif status == "failed":
            short = self.row.error or ""
            if len(short) > 18:
                short = short[:18] + "…"
            self.status_label.setText(f"● 失败: {short}")
            self.status_label.setToolTip(self.row.error or "")
            self.status_label.setStyleSheet(
                f"color: {DANGER}; font-size: 11px; font-weight: 600;"
                " background: transparent; border: none;"
            )

    # ---------------- 事件 ----------------
    def _on_check_changed(self, state: int) -> None:
        checked = state != 0
        self.row.selected = checked
        self.selection_changed.emit(self.row.item_id, checked)

    def _on_zoom_clicked(self) -> None:
        """单图模式: 单击缩略图放大"""
        if self._qimage is not None:
            self.zoom_clicked.emit(self._qimage, self.row.prompt)

    def _on_multi_thumb_click(self, idx: int) -> None:
        """组图模式: 单击第 idx 个缩略图放大"""
        if 0 <= idx < len(self._qimages):
            # 发送 item_id + index, 由主窗口/面板处理放大
            self.zoom_index_clicked.emit(self.row.item_id, idx)
