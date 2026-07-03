"""手动生成面板 (主区域)

功能:
- 顶部提示词输入框 + 生成按钮
- 下方可滚动的历史记录区域，图片卡片以流式布局排列
- 点击卡片的"编辑重绘"会把提示词回填到输入框
- 点击"重新生成"基于原提示词再次生成
- 点击"保存到本地"保存单张图片
"""
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from output_manager import save_generation

from api_client import ZhipuImageClient
from ui.image_card import ImageCard
from ui.styles import BG_CARD, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_WEAK
from workers import GenerateWorker


class FlowLayoutContainer(QWidget):
    """简易流式布局容器: 子控件自动换行排列

    按宽度自动换行排列卡片，无需依赖 QLayout 的复杂实现。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[QWidget] = []
        self._spacing = 16
        self.setMinimumHeight(0)

    def add_widget(self, widget: QWidget) -> None:
        widget.setParent(self)
        self._items.append(widget)
        widget.show()
        # 立即重新布局, 避免新卡片停在 (0,0) 与旧卡片重叠
        self._do_layout(self.width())
        self.updateGeometry()

    def clear_all(self) -> None:
        for w in self._items:
            w.setParent(None)
            w.deleteLater()
        self._items.clear()
        self.updateGeometry()

    def resizeEvent(self, event):
        self._do_layout(self.width())
        super().resizeEvent(event)

    def _do_layout(self, width: int) -> None:
        if not self._items:
            self.setMinimumHeight(0)
            return
        x = 0
        y = 0
        row_height = 0
        spacing = self._spacing
        for w in self._items:
            hint = w.sizeHint()
            ww = w.width() if w.width() > 0 else hint.width()
            wh = w.height() if w.height() > 0 else hint.height()
            if x + ww > width and x > 0:
                x = 0
                y += row_height + spacing
                row_height = 0
            w.setGeometry(x, y, ww, wh)
            x += ww + spacing
            row_height = max(row_height, wh)
        self.setMinimumHeight(y + row_height + spacing)


class ManualPanel(QFrame):
    """手动生成面板"""

    # 请求主窗口执行生成: (prompt, card_id)  card_id == -1 表示新建
    request_generate = Signal(str, int)
    # 请求主窗口保存单张图片: (card_id, raw_bytes, prompt)
    request_save = Signal(int, object, str)
    # 请求主窗口放大查看图片: (QImage, prompt)
    request_zoom = Signal(object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("root")
        self._cards: list[ImageCard] = []
        self._next_id = 0
        self._worker: Optional[GenerateWorker] = None
        self._build_ui()

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 16)
        outer.setSpacing(16)

        # 标题区
        title = QLabel("手动生成")
        title.setStyleSheet(
            f"font-size: 24px; font-weight: 700; color: {TEXT_PRIMARY};"
            " letter-spacing: 0.5px; background: transparent;"
        )
        outer.addWidget(title)

        subtitle = QLabel("输入提示词即时生成图片，结果保留在下方生成结果中")
        subtitle.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"
        )
        outer.addWidget(subtitle)

        # 提示词输入卡片 (样式由 QSS #promptCard 提供)
        prompt_box = QFrame()
        prompt_box.setObjectName("promptCard")
        # 真实阴影提升层次 (暗色背景下加深阴影)
        shadow = QGraphicsDropShadowEffect(prompt_box)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 120))
        prompt_box.setGraphicsEffect(shadow)
        pb_layout = QVBoxLayout(prompt_box)
        pb_layout.setContentsMargins(18, 16, 18, 16)
        pb_layout.setSpacing(10)

        pl = QLabel("提示词 (PROMPT)")
        pl.setObjectName("sectionLabel")
        pb_layout.addWidget(pl)

        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlaceholderText("输入要生成的图片描述…")
        self.prompt_edit.setMinimumHeight(80)
        self.prompt_edit.setMaximumHeight(140)
        pb_layout.addWidget(self.prompt_edit)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.clear_btn = QPushButton("清空")
        self.clear_btn.setObjectName("secondaryBtn")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self.prompt_edit.clear)
        btn_row.addWidget(self.clear_btn)
        btn_row.addStretch()
        self.gen_btn = QPushButton("生成图片")
        self.gen_btn.setObjectName("primaryBtn")
        self.gen_btn.setCursor(Qt.PointingHandCursor)
        self.gen_btn.clicked.connect(self._on_generate_clicked)
        btn_row.addWidget(self.gen_btn)
        pb_layout.addLayout(btn_row)

        outer.addWidget(prompt_box)

        # 历史记录标题
        hist_label = QLabel("生成结果")
        hist_label.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {TEXT_PRIMARY};"
            " background: transparent;"
        )
        outer.addWidget(hist_label)

        # 滚动容器
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background-color: transparent; }")

        self.flow = FlowLayoutContainer()
        self.flow.setStyleSheet("background-color: transparent;")
        self.scroll.setWidget(self.flow)
        outer.addWidget(self.scroll, 1)

        # 空状态提示 (与 scroll 互斥, 都给 stretch=1 让其填满剩余空间)
        self.empty_label = QLabel("还没有生成过图片\n在上方输入提示词开始吧 ✨")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(
            f"color: {TEXT_WEAK}; font-size: 14px; background-color: {BG_CARD};"
            f" border: 1px dashed {BORDER}; border-radius: 12px;"
        )
        self.empty_label.setMinimumHeight(120)
        outer.addWidget(self.empty_label, 1)

        # 初始: 无卡片时隐藏滚动区，只显示空状态
        self.scroll.setVisible(False)

    # ---------------- 生成入口 ----------------
    def _on_generate_clicked(self) -> None:
        prompt = self.prompt_edit.toPlainText().strip()
        if not prompt:
            self.empty_label.setText("⚠ 请先输入提示词")
            self.empty_label.setVisible(True)
            return
        # card_id = -1 表示新建卡片
        self.request_generate.emit(prompt, -1)

    def _on_edit_clicked(self, prompt: str) -> None:
        """编辑重绘: 把该卡片的提示词回填到输入框"""
        self.fill_prompt(prompt)

    def fill_prompt(self, prompt: str) -> None:
        """外部调用: 把指定提示词填入输入框并聚焦"""
        self.prompt_edit.setPlainText(prompt)
        self.prompt_edit.setFocus()
        cursor = self.prompt_edit.textCursor()
        cursor.movePosition(cursor.End)
        self.prompt_edit.setTextCursor(cursor)

    def _on_regenerate_clicked(self, card_id: int) -> None:
        """重新生成: 基于原提示词，用当前配置重绘该卡片"""
        self.request_generate.emit(self._find_card(card_id).prompt, card_id)

    def _on_save_clicked(self, card_id: int) -> None:
        card = self._find_card(card_id)
        if card and card.image_data:
            self.request_save.emit(card_id, card.image_data, card.prompt)

    # ---------------- 由主窗口调用: 实际发起生成 ----------------
    def start_generate(
        self,
        client: ZhipuImageClient,
        prompt: str,
        size: str,
        quality: str,
        watermark: bool,
        system_prompt: str,
        card_id: int = -1,
    ) -> None:
        """发起一次生成

        Args:
            card_id: -1 表示新建卡片; 否则为重绘指定卡片
        """
        if self._worker is not None and self._worker.isRunning():
            return  # 防止并发冲突 (阶段1串行处理)

        target_card = self._find_card(card_id) if card_id >= 0 else None

        if target_card is None:
            card = ImageCard(self._next_id, prompt, size=size, quality=quality)
            self._next_id += 1
            card.edit_clicked.connect(self._on_edit_clicked)
            card.regenerate_clicked.connect(self._on_regenerate_clicked)
            card.save_clicked.connect(self._on_save_clicked)
            card.image_clicked.connect(
                lambda img, c=card: self.request_zoom.emit(img, c.prompt)
            )
            self._cards.append(card)
            self.flow.add_widget(card)
            self._hide_empty()
            target_card = card
        else:
            # 重绘: 更新提示词并切换为加载中
            target_card.prompt = prompt
            target_card.set_loading()

        self._set_gen_btn_busy(True)

        self._worker = GenerateWorker(
            client, prompt, size, quality, watermark, system_prompt
        )
        self._worker.finished_ok.connect(
            lambda img, data: self._on_success(
                target_card, img, data, prompt, size, quality
            )
        )
        self._worker.failed.connect(
            lambda msg: self._on_failed(target_card, msg, prompt, size, quality)
        )
        self._worker.start()

    def _on_success(
        self,
        card: ImageCard,
        img: QImage,
        data: bytes,
        prompt: str,
        size: str,
        quality: str,
    ) -> None:
        card.set_success(img, data)
        # 额外保存到 outputs/ 归档
        try:
            save_generation(
                image_data=data,
                prompt=prompt,
                size=size,
                quality=quality,
                status="success",
            )
        except Exception:
            pass  # 归档失败不阻断主流程
        self._set_gen_btn_busy(False)

    def _on_failed(
        self,
        card: ImageCard,
        msg: str,
        prompt: str,
        size: str,
        quality: str,
    ) -> None:
        card.set_failed(msg)
        # 失败也记录到 outputs/ 历史
        try:
            save_generation(
                image_data=None,
                prompt=prompt,
                size=size,
                quality=quality,
                status="failed",
                error=msg,
            )
        except Exception:
            pass
        self._set_gen_btn_busy(False)

    # ---------------- 辅助 ----------------
    def _set_gen_btn_busy(self, busy: bool) -> None:
        self.gen_btn.setEnabled(not busy)
        self.gen_btn.setText("生成中…" if busy else "生成图片")

    def _hide_empty(self) -> None:
        self.empty_label.setVisible(False)
        self.scroll.setVisible(True)

    def _find_card(self, card_id: int) -> Optional[ImageCard]:
        for c in self._cards:
            if c.card_id == card_id:
                return c
        return None
