"""图片卡片组件

设计要点:
- 卡片整体白底圆角 + 阴影，悬停时阴影加深、轻微上浮
- 图片占据主体，操作按钮默认隐藏，鼠标悬停在图片上时
  底部浮出半透明遮罩层，提供「编辑重绘 / 重新生成 / 保存」
- 图片下方显示提示词摘要与状态点
"""
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class _ImageArea(QFrame):
    """图片显示区 + 悬停遮罩层

    鼠标进入时显示底部半透明遮罩 (含操作按钮)，离开时隐藏。
    单击图片区域触发放大查看。
    """

    hover_changed = Signal(bool)
    clicked = Signal()  # 单击图片区域

    def __init__(self, thumb_size: int, parent=None):
        super().__init__(parent)
        self._thumb = thumb_size
        self.setFixedSize(thumb_size, thumb_size)
        self.setStyleSheet(
            "background-color: #252834; border-radius: 10px;"
        )

        # 图片标签
        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet(
            "background: transparent; border: none; color: #64748b;"
        )
        self.image_label.setGeometry(0, 0, thumb_size, thumb_size)

        # 遮罩层 (默认隐藏，悬停时显示)
        self._overlay_h = 52
        self.overlay = QFrame(self)
        self.overlay.setStyleSheet(
            "QFrame { background-color: rgba(0,0,0,180);"
            " border: none; border-bottom-left-radius: 10px;"
            " border-bottom-right-radius: 10px; }"
        )
        self.overlay.setGeometry(
            0, thumb_size - self._overlay_h, thumb_size, self._overlay_h
        )

        # 遮罩内按钮
        row = QHBoxLayout(self.overlay)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(6)

        self.btn_edit = self._mk_overlay_btn("✎ 编辑")
        self.btn_regen = self._mk_overlay_btn("⟳ 重绘")
        self.btn_save = self._mk_overlay_btn("⤓ 保存")
        row.addWidget(self.btn_edit)
        row.addWidget(self.btn_regen)
        row.addWidget(self.btn_save)

        self.overlay.hide()

    def _mk_overlay_btn(self, text: str) -> QPushButton:
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor)
        b.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.14); color: #ffffff;"
            " border: none; border-radius: 6px; padding: 6px 10px; font-size: 12px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.28); }"
            "QPushButton:disabled { color: rgba(255,255,255,0.4);"
            " background: rgba(255,255,255,0.06); }"
        )
        return b

    # -------- 几何 --------
    def resizeEvent(self, e):
        # 图片标签铺满
        self.image_label.setGeometry(0, 0, self.width(), self.height())
        # 遮罩贴底
        self.overlay.setGeometry(
            0, self.height() - self._overlay_h, self.width(), self._overlay_h
        )
        super().resizeEvent(e)

    # -------- 悬停 --------
    def enterEvent(self, e):
        self.hover_changed.emit(True)
        if self.image_label.pixmap() is not None or self.image_label.text():
            self.overlay.show()
            self.overlay.raise_()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.hover_changed.emit(False)
        self.overlay.hide()
        super().leaveEvent(e)

    # -------- 单击放大 --------
    def mousePressEvent(self, e):
        # 左键单击图片区域 (非遮罩按钮) 触发放大
        if e.button() == Qt.LeftButton:
            pix = self.image_label.pixmap()
            if pix is not None and not pix.isNull():
                self.clicked.emit()
        super().mousePressEvent(e)

    # -------- 设置图片 --------
    def set_image(self, qimage: QImage) -> None:
        pix = QPixmap.fromImage(qimage)
        scaled = pix.scaled(
            self._thumb, self._thumb, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )
        # 居中裁剪到正方形
        if scaled.width() > self._thumb or scaled.height() > self._thumb:
            x = (scaled.width() - self._thumb) // 2
            y = (scaled.height() - self._thumb) // 2
            scaled = scaled.copy(x, y, self._thumb, self._thumb)
        self.image_label.setPixmap(scaled)
        self.image_label.setText("")

    def set_placeholder(self, text: str) -> None:
        self.image_label.setPixmap(QPixmap())
        self.image_label.setText(text)

    def set_buttons_enabled(self, enabled: bool, save_enabled: bool) -> None:
        self.btn_edit.setEnabled(enabled)
        self.btn_regen.setEnabled(enabled)
        self.btn_save.setEnabled(save_enabled)


class ImageCard(QFrame):
    """单张图片卡片

    Signals:
        edit_clicked(str): 点击「编辑」回填提示词
        regenerate_clicked(int): 点击「重绘」基于原提示词重绘
        save_clicked(int): 点击「保存」保存图片
    """

    edit_clicked = Signal(str)
    regenerate_clicked = Signal(int)
    save_clicked = Signal(int)
    image_clicked = Signal(object)  # 单击放大, 携带全分辨率 QImage

    THUMB_SIZE = 280

    def __init__(
        self,
        card_id: int,
        prompt: str,
        parent: Optional[QWidget] = None,
        size: str = "",
        quality: str = "",
    ):
        super().__init__(parent)
        self.setObjectName("imageCard")
        self.card_id = card_id
        self.prompt = prompt
        self.size = size
        self.quality = quality
        self.timestamp = datetime.now()
        self.image_data: Optional[bytes] = None
        self._qimage: Optional[QImage] = None

        # 卡片尺寸: 图片 + 下方信息区
        info_h = 84
        self.setFixedSize(self.THUMB_SIZE + 24, self.THUMB_SIZE + info_h + 16)

        self._build_ui()
        self._apply_shadow()
        self.set_loading()

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 图片区 (含悬停遮罩)
        self.image_area = _ImageArea(self.THUMB_SIZE)
        self.image_area.btn_edit.clicked.connect(self._on_edit)
        self.image_area.btn_regen.clicked.connect(
            lambda: self.regenerate_clicked.emit(self.card_id)
        )
        self.image_area.btn_save.clicked.connect(
            lambda: self.save_clicked.emit(self.card_id)
        )
        self.image_area.clicked.connect(self._on_image_click)
        self.image_area.hover_changed.connect(self._on_hover)
        layout.addWidget(self.image_area, 0, Qt.AlignHCenter)

        # 提示词摘要
        self.prompt_label = QLabel(self.prompt)
        self.prompt_label.setObjectName("cardPrompt")
        self.prompt_label.setWordWrap(True)
        self.prompt_label.setMaximumHeight(38)
        layout.addWidget(self.prompt_label)

        # 状态行
        self.status_label = QLabel()
        self.status_label.setObjectName("cardStatusLoading")
        layout.addWidget(self.status_label)

    def _apply_shadow(self) -> None:
        effect = QGraphicsDropShadowEffect(self)
        effect.setBlurRadius(18)
        effect.setColor(Qt.black)
        effect.setOffset(0, 4)
        # 暗色背景下阴影需要更高 alpha 才可见
        c = effect.color()
        c.setAlpha(120)
        effect.setColor(c)
        self.setGraphicsEffect(effect)
        self._shadow = effect

    # ---------------- 状态切换 ----------------
    def set_loading(self) -> None:
        self.image_area.set_placeholder("生成中…")
        self.image_area.set_buttons_enabled(False, False)
        self.status_label.setObjectName("cardStatusLoading")
        self.status_label.setText("● 生成中")
        self._refresh_status_style()
        self._set_shadow_dim(False)

    def set_success(self, qimage: QImage, raw_data: bytes) -> None:
        self._qimage = qimage
        self.image_data = raw_data
        self.image_area.set_image(qimage)
        self.status_label.setObjectName("cardStatusSuccess")
        self.status_label.setText(
            f"● 成功 · {self.timestamp.strftime('%H:%M:%S')} · {self.size}"
        )
        self._refresh_status_style()
        self.image_area.set_buttons_enabled(True, True)

    def set_failed(self, err_msg: str) -> None:
        self.image_area.set_placeholder("生成失败")
        self.status_label.setObjectName("cardStatusFail")
        short = err_msg if len(err_msg) <= 24 else err_msg[:24] + "…"
        self.status_label.setText(f"● 失败: {short}")
        self._refresh_status_style()
        # 失败允许编辑/重绘，但保存禁用
        self.image_area.set_buttons_enabled(True, False)

    def _refresh_status_style(self) -> None:
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _set_shadow_dim(self, dim: bool) -> None:
        c = self._shadow.color()
        c.setAlpha(80 if dim else 120)
        self._shadow.setColor(c)

    # ---------------- 事件 ----------------
    def _on_edit(self) -> None:
        self.edit_clicked.emit(self.prompt)

    def _on_image_click(self) -> None:
        """单击图片: 触发放大查看 (仅在有图时)"""
        if self._qimage is not None:
            self.image_clicked.emit(self._qimage)

    def _on_hover(self, hovered: bool) -> None:
        """悬停时阴影加深、轻微上浮"""
        if hovered:
            self._shadow.setBlurRadius(30)
            self._shadow.setOffset(0, 8)
            c = self._shadow.color()
            c.setAlpha(180)
            self._shadow.setColor(c)
        else:
            self._shadow.setBlurRadius(18)
            self._shadow.setOffset(0, 4)
            c = self._shadow.color()
            c.setAlpha(120)
            self._shadow.setColor(c)

    # ---------------- 外部 ----------------
    def update_result(
        self, qimage: QImage, raw_data: bytes, prompt: Optional[str] = None
    ) -> None:
        if prompt is not None:
            self.prompt = prompt
            self.prompt_label.setText(prompt)
        self.timestamp = datetime.now()
        self.set_success(qimage, raw_data)
