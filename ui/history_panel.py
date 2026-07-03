"""历史记录面板

从 ``outputs/history.json`` 读取全部生成记录, 以卡片网格展示:
- 可伸缩正方形缩略图 (宽度跟随卡片, 高度=宽度)
- 提示词 / 时间戳 / 状态 / 元信息
- 单击缩略图 → 灯箱放大 (沿用 ZoomOverlay)
- 「📋 回填到手动生成」→ 信号通知主窗口切换 tab 并填充提示词
- 「🔄 刷新」「🗑 清空历史」

设计语言与全局暗色主题对齐: 卡片 ``BG_CARD`` 底 + 圆角 12px + 柔和阴影。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QImage, QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from output_manager import load_history, clear_history, resolve_image_path
from ui.styles import (
    BG_CARD,
    BG_INPUT,
    BORDER,
    BORDER_FOCUS,
    DANGER,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_WEAK,
)


class _ResizableThumb(QLabel):
    """正方形缩略图

    尺寸由外部 (HistoryPanel) 统一传入, 避免不同卡片因 QGridLayout
    分配的宽度微小差异导致高度不一致。
    内部 pixmap 按 KeepAspectRatio 等比缩放, 始终居中显示。
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._thumb_size: int = 180          # 当前正方形边长, 由外部设置
        self.setFixedHeight(self._thumb_size)
        self._source: QPixmap = QPixmap()
        self._placeholder = "无图片"
        self.setStyleSheet(
            f"background-color: {BG_INPUT}; border-radius: 10px;"
            f" color: {TEXT_WEAK}; font-size: 12px; border: none;"
        )

    def set_thumb_size(self, size: int) -> None:
        """外部统一设置缩略图边长 (正方形)"""
        size = max(120, int(size))
        if size == self._thumb_size:
            return
        self._thumb_size = size
        self.setFixedHeight(size)
        self._update_pixmap()

    def set_source_pixmap(self, pix: QPixmap) -> None:
        self._source = pix
        self._placeholder = ""
        self._update_pixmap()

    def set_placeholder(self, text: str) -> None:
        self._source = QPixmap()
        self._placeholder = text
        self.setText(text)
        self._update_pixmap()

    def _update_pixmap(self) -> None:
        if self._source.isNull():
            if self._placeholder:
                self.setText(self._placeholder)
            return
        s = self._thumb_size
        if s <= 0:
            return
        scaled = self._source.scaled(
            s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        super().setPixmap(scaled)


class _HistoryCard(QFrame):
    """单条历史记录卡片

    信号:
        refill_clicked(dict): 回填参数 {prompt, size, quality}
        zoom_clicked(QImage, str): 单击缩略图放大, 携带全分辨率 QImage 与 prompt
    """

    refill_clicked = Signal(dict)
    zoom_clicked = Signal(object, str)

    def __init__(self, record: dict, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("historyCard")
        self._record = record
        self._qimage: Optional[QImage] = None

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.setStyleSheet(
            f"QFrame#historyCard {{"
            f" background-color: {BG_CARD};"
            f" border: 1px solid {BORDER};"
            f" border-radius: 12px;"
            f"}}"
        )

        # 卡片阴影
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        c = QColor(0, 0, 0, 120)
        shadow.setColor(c)
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 缩略图 (可伸缩正方形)
        self.thumb = _ResizableThumb()
        self.thumb.setCursor(Qt.PointingHandCursor)
        self.thumb.mousePressEvent = self._on_thumb_click
        layout.addWidget(self.thumb)

        # 加载图片
        self._load_thumb()

        # 提示词 (固定高度, 保证所有卡片一致)
        prompt_text = record.get("prompt", "") or ""
        prompt_label = QLabel(prompt_text)
        prompt_label.setWordWrap(True)
        prompt_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 12px;"
            f" background: transparent; border: none;"
        )
        # 固定高度 + 行高限制, 避免不同长度提示词导致卡片高度不一致
        prompt_label.setFixedHeight(48)
        prompt_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        prompt_label.setToolTip(prompt_text)
        layout.addWidget(prompt_label)

        # 时间戳 + 状态 (固定高度)
        ts = record.get("timestamp", "") or ""
        status = record.get("status", "") or ""
        status_color = "#22c55e" if status == "success" else DANGER
        meta_label = QLabel(
            f"🕐 {ts}　<span style='color:{status_color};'>{status}</span>"
        )
        meta_label.setTextFormat(Qt.RichText)
        meta_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px;"
            f" background: transparent; border: none;"
        )
        meta_label.setFixedHeight(18)
        layout.addWidget(meta_label)

        # 元信息: 尺寸 / 质量 / 模型 (始终添加, 保持卡片高度一致)
        meta_parts = []
        if record.get("size"):
            meta_parts.append(f"📐 {record['size']}")
        if record.get("quality"):
            meta_parts.append(f"✨ {record['quality']}")
        if record.get("model"):
            meta_parts.append(f"🤖 {record['model']}")
        info_label = QLabel("　".join(meta_parts) if meta_parts else " ")
        info_label.setStyleSheet(
            f"color: {TEXT_WEAK}; font-size: 11px;"
            f" background: transparent; border: none;"
        )
        info_label.setFixedHeight(18)
        layout.addWidget(info_label)

        # 操作按钮: 回填 + 放大 (并排)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.setContentsMargins(0, 0, 0, 0)

        self.btn_refill = QPushButton("📋 回填")
        self.btn_refill.setObjectName("primaryBtn")
        self.btn_refill.setCursor(Qt.PointingHandCursor)
        self.btn_refill.setToolTip("回填提示词到手动生成")
        self.btn_refill.clicked.connect(self._on_refill)
        btn_row.addWidget(self.btn_refill, 1)

        self.btn_zoom = QPushButton("🔍 放大")
        self.btn_zoom.setObjectName("secondaryBtn")
        self.btn_zoom.setCursor(Qt.PointingHandCursor)
        self.btn_zoom.setEnabled(self._qimage is not None)
        self.btn_zoom.clicked.connect(lambda: self._emit_zoom())
        btn_row.addWidget(self.btn_zoom, 1)

        layout.addLayout(btn_row)

    def _load_thumb(self) -> None:
        """加载缩略图; 失败时显示占位文字"""
        image_path = self._record.get("image_path", "")
        if not image_path:
            self.thumb.set_placeholder("❌ 无图片")
            return
        img_path = resolve_image_path(image_path)
        if not img_path.exists():
            self.thumb.set_placeholder("📁 文件缺失")
            return
        # 读取为 QImage (供放大用) + QPixmap (供缩略图用)
        qimg = QImage(str(img_path))
        if qimg.isNull():
            self.thumb.set_placeholder("⚠️ 无法加载")
            return
        self._qimage = qimg
        self.thumb.set_source_pixmap(QPixmap.fromImage(qimg))

    def update_thumb_size(self, size: int) -> None:
        """由 HistoryPanel 统一更新缩略图尺寸"""
        self.thumb.set_thumb_size(size)

    def _on_thumb_click(self, e) -> None:
        """单击缩略图: 有图则放大"""
        if e.button() == Qt.LeftButton and self._qimage is not None:
            self._emit_zoom()
            e.accept()
            return
        # 交给默认处理 (避免吞事件)
        QLabel.mousePressEvent(self.thumb, e)

    def _emit_zoom(self) -> None:
        if self._qimage is not None:
            self.zoom_clicked.emit(
                self._qimage, self._record.get("prompt", "")
            )

    def _on_refill(self) -> None:
        self.refill_clicked.emit({
            "prompt": self._record.get("prompt", ""),
            "size": self._record.get("size", ""),
            "quality": self._record.get("quality", ""),
        })


class HistoryPanel(QWidget):
    """历史记录页

    信号:
        refill_requested(dict): 用户点击回填, 主窗口切到手动 tab 并填充
        request_zoom(object, str): 单击放大, 携带 QImage + prompt
        status_message(str): 状态栏消息
    """

    refill_requested = Signal(dict)
    request_zoom = Signal(object, str)
    status_message = Signal(str)

    COLUMNS = 4  # 网格列数
    CARD_MARGIN_H = 24          # 卡片左右内边距合计 (12 + 12)
    THUMB_MIN = 120             # 缩略图最小边长

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._cards: list[_HistoryCard] = []
        self._current_thumb_size: int = 180   # 当前后统一缩略图边长
        self._build_ui()
        self.refresh()

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(12)

        # 顶部栏
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        title = QLabel("🕘 历史记录")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 16px; font-weight: 700;"
            f" background: transparent; border: none;"
        )
        top_row.addWidget(title)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px;"
            f" background: transparent; border: none;"
        )
        top_row.addWidget(self.count_label)

        top_row.addStretch()

        self.btn_refresh = QPushButton("🔄 刷新")
        self.btn_refresh.setObjectName("secondaryBtn")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.refresh)
        top_row.addWidget(self.btn_refresh)

        self.btn_clear = QPushButton("🗑 清空历史")
        self.btn_clear.setObjectName("dangerBtn")
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        self.btn_clear.setStyleSheet(
            f"QPushButton#dangerBtn {{"
            f" background-color: rgba(239, 68, 68, 0.15);"
            f" border: 1px solid rgba(239, 68, 68, 0.4);"
            f" color: {DANGER};"
            f" border-radius: 8px;"
            f" padding: 7px 16px;"
            f" font-weight: 500;"
            f"}}"
            f"QPushButton#dangerBtn:hover {{"
            f" background-color: rgba(239, 68, 68, 0.25);"
            f"}}"
        )
        self.btn_clear.clicked.connect(self._on_clear)
        top_row.addWidget(self.btn_clear)

        outer.addLayout(top_row)

        # 卡片网格滚动区
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet(
            "QScrollArea { background-color: transparent; border: none; }"
        )

        self._container = QWidget()
        self._container.setStyleSheet("background-color: transparent;")
        self._grid = QGridLayout(self._container)
        self._grid.setSpacing(12)
        self._grid.setContentsMargins(0, 0, 0, 0)
        # 4 列等宽 (卡片可随窗口伸缩)
        for col in range(self.COLUMNS):
            self._grid.setColumnStretch(col, 1)

        self.scroll.setWidget(self._container)
        outer.addWidget(self.scroll, 1)

        # 空状态
        self.empty_label = QLabel("📭 暂无历史记录\n生成图片后会自动归档到此")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(
            f"color: {TEXT_WEAK}; font-size: 14px; background-color: {BG_CARD};"
            f" border: 1px dashed {BORDER}; border-radius: 12px;"
        )
        self.empty_label.setMinimumHeight(200)
        outer.addWidget(self.empty_label)
        self.scroll.setVisible(False)

    # ---------------- 数据加载 ----------------
    def refresh(self) -> None:
        """刷新历史列表"""
        # 清空旧卡片
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._cards.clear()

        records = load_history()
        self.count_label.setText(f"共 {len(records)} 条")

        if not records:
            self.scroll.setVisible(False)
            self.empty_label.setVisible(True)
            return

        self.scroll.setVisible(True)
        self.empty_label.setVisible(False)

        for idx, rec in enumerate(records):
            card = _HistoryCard(rec)
            card.refill_clicked.connect(self._on_card_refill)
            card.zoom_clicked.connect(self._on_card_zoom)
            # 应用当前统一缩略图尺寸
            card.update_thumb_size(self._current_thumb_size)
            row, col = divmod(idx, self.COLUMNS)
            self._grid.addWidget(card, row, col)
            self._cards.append(card)

        # 首次加载时 _container 宽度可能已就绪, 主动计算一次
        self._update_thumb_size()

    # ---------------- 事件转发 ----------------
    def _on_card_refill(self, params: dict) -> None:
        self.refill_requested.emit(params)

    def _on_card_zoom(self, qimage, prompt: str) -> None:
        self.request_zoom.emit(qimage, prompt)

    def _on_clear(self) -> None:
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空全部历史记录吗？\n(仅清空 history.json, 不会删除已保存的图片文件)",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            clear_history()
            self.refresh()
            self.status_message.emit("已清空历史记录")

    def showEvent(self, event) -> None:
        """每次切换到该 Tab 时自动刷新"""
        super().showEvent(event)
        self.refresh()

    def resizeEvent(self, event) -> None:
        """窗口缩放时重新计算缩略图尺寸, 通知所有卡片"""
        super().resizeEvent(event)
        self._update_thumb_size()

    def _update_thumb_size(self) -> None:
        """根据 scroll viewport 宽度统一计算缩略图边长, 通知所有卡片

        计算公式: thumb_size = 列宽 - 卡片左右内边距
        列宽 = (viewport_width - (COLUMNS-1) * spacing) / COLUMNS
        """
        if self.scroll is None:
            return
        viewport_w = self.scroll.viewport().width()
        if viewport_w <= 0:
            return
        spacing = self._grid.spacing()
        col_w = (viewport_w - (self.COLUMNS - 1) * spacing) / self.COLUMNS
        thumb_size = max(self.THUMB_MIN, int(col_w - self.CARD_MARGIN_H))
        if thumb_size == self._current_thumb_size:
            return
        self._current_thumb_size = thumb_size
        for card in self._cards:
            card.update_thumb_size(thumb_size)
