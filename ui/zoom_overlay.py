"""图片放大灯箱组件

交互:
- 单击 / Esc: 关闭灯箱
- 鼠标滚轮: 以鼠标位置为锚点缩放 (1x ~ 6x)
- 左键拖拽: 移动图片查看局部
- 双击 / R 键: 重置到适应窗口
"""
from typing import Optional

from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import (
    QImage,
    QMouseEvent,
    QPainter,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import QFrame, QLabel


class ZoomOverlay(QFrame):
    """全屏图片放大灯箱

    用 paintEvent 自绘图片以灵活支持缩放与位移。
    """

    closed = Signal()

    MIN_SCALE = 1.0  # 相对适应窗口的最小倍率
    MAX_SCALE = 6.0  # 相对适应窗口的最大倍率

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("zoomOverlay")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setFocusPolicy(Qt.StrongFocus)
        # 深色半透明背景
        self.setStyleSheet(
            "QFrame#zoomOverlay { background-color: rgba(12,14,20,235); }"
        )

        self._qimage: Optional[QImage] = None
        self._pixmap: Optional[QPixmap] = None
        self._prompt: str = ""

        # 缩放与位移状态
        self._fit_scale: float = 1.0  # 适应窗口的初始缩放系数
        self._scale: float = 1.0      # 相对 _fit_scale 的倍率
        self._offset: QPoint = QPoint(0, 0)  # 图片中心相对窗口中心的偏移

        # 拖拽状态
        self._dragging: bool = False
        self._drag_start: QPoint = QPoint()
        self._offset_start: QPoint = QPoint()

        # 底部提示词标签 (浮于图片之上)
        self.prompt_label = QLabel(self)
        self.prompt_label.setAlignment(Qt.AlignCenter)
        self.prompt_label.setWordWrap(True)
        self.prompt_label.setMaximumWidth(800)
        self.prompt_label.setStyleSheet(
            "color: rgba(255,255,255,0.88); font-size: 12px;"
            " background: rgba(255,255,255,0.07); border-radius: 8px;"
            " padding: 6px 14px; border: none;"
        )
        self.prompt_label.hide()

        # 操作提示
        self.hint_label = QLabel(self)
        self.hint_label.setText("滚轮缩放 · 拖拽移动 · 双击重置 · 单击/Esc 关闭")
        self.hint_label.setStyleSheet(
            "color: rgba(255,255,255,0.45); font-size: 11px;"
            " background: transparent; border: none;"
        )
        self.hint_label.adjustSize()

        self.hide()

    # ---------------- 入口 ----------------
    def show_image(self, qimage: QImage, prompt: str = "") -> None:
        """展示图片，按可用区域等比缩放"""
        self._qimage = qimage
        self._pixmap = QPixmap.fromImage(qimage)
        self._prompt = prompt

        # 重置缩放与位移
        self._scale = 1.0
        self._offset = QPoint(0, 0)

        # 覆盖父组件整个区域
        if self.parentWidget() is not None:
            self.setGeometry(self.parentWidget().rect())

        self._fit_to_view()
        self._layout_hints()

        # 提示词
        if prompt:
            self.prompt_label.setText(prompt)
            self.prompt_label.adjustSize()
            self.prompt_label.show()
        else:
            self.prompt_label.hide()

        self.raise_()
        self.show()
        self.setFocus()
        self.setCursor(Qt.OpenHandCursor)
        self.update()

    # ---------------- 几何计算 ----------------
    def _fit_to_view(self) -> None:
        """计算适应窗口的初始缩放系数"""
        if self._pixmap is None or self._pixmap.isNull():
            self._fit_scale = 1.0
            return
        avail = self.rect().adjusted(48, 48, -48, -90)
        if avail.width() <= 0 or avail.height() <= 0:
            self._fit_scale = 1.0
            return
        sw = avail.width() / self._pixmap.width()
        sh = avail.height() / self._pixmap.height()
        # 不超过原始分辨率
        self._fit_scale = min(sw, sh, 1.0)
        if self._fit_scale <= 0:
            self._fit_scale = 1.0

    def _layout_hints(self) -> None:
        """底部提示词与操作提示布局"""
        # 提示词 (底部偏上)
        if self.prompt_label.isVisible():
            pw = self.prompt_label.sizeHint().width()
            ph = self.prompt_label.sizeHint().height()
            self.prompt_label.setGeometry(
                (self.width() - pw) // 2, self.height() - 70, pw, ph
            )
        # 操作提示 (最底部)
        hw = self.hint_label.sizeHint().width()
        hh = self.hint_label.sizeHint().height()
        self.hint_label.setGeometry(
            (self.width() - hw) // 2, self.height() - 30, hw, hh
        )

    def _current_display_size(self) -> tuple[int, int]:
        """当前实际显示的图片宽高 (考虑 fit_scale * scale)"""
        if self._pixmap is None or self._pixmap.isNull():
            return 0, 0
        actual = self._fit_scale * self._scale
        w = max(1, int(self._pixmap.width() * actual))
        h = max(1, int(self._pixmap.height() * actual))
        return w, h

    # ---------------- 绘制 ----------------
    def paintEvent(self, e):
        super().paintEvent(e)
        if self._pixmap is None or self._pixmap.isNull():
            return
        dw, dh = self._current_display_size()
        disp = self._pixmap.scaled(
            dw, dh, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        # 居中 + 偏移
        x = (self.width() - disp.width()) // 2 + self._offset.x()
        y = (self.height() - disp.height()) // 2 + self._offset.y()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(x, y, disp)

    # ---------------- 滚轮缩放 ----------------
    def wheelEvent(self, e: QWheelEvent):
        if self._pixmap is None or self._pixmap.isNull():
            return
        delta = e.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else 1 / 1.15
        new_scale = self._scale * factor
        new_scale = max(self.MIN_SCALE, min(self.MAX_SCALE, new_scale))
        if new_scale == self._scale:
            return

        # 以鼠标位置为锚点缩放: 鼠标在图片上的相对位置保持不变
        anchor = e.position().toPoint()
        # 鼠标相对图片中心的向量 (在旧缩放下)
        dw, dh = self._current_display_size()
        img_cx = (self.width() - dw) // 2 + self._offset.x() + dw / 2
        img_cy = (self.height() - dh) // 2 + self._offset.y() + dh / 2
        vec_x = anchor.x() - img_cx
        vec_y = anchor.y() - img_cy
        # 缩放后该向量按比例放大
        ratio = new_scale / self._scale
        new_img_cx = anchor.x() - vec_x * ratio
        new_img_cy = anchor.y() - vec_y * ratio
        # 反推新的 offset
        new_dw = int(self._pixmap.width() * self._fit_scale * new_scale)
        new_dh = int(self._pixmap.height() * self._fit_scale * new_scale)
        self._offset = QPoint(
            int(new_img_cx - (self.width() - new_dw) // 2 - new_dw / 2),
            int(new_img_cy - (self.height() - new_dh) // 2 - new_dh / 2),
        )
        self._scale = new_scale
        self.update()

    # ---------------- 拖拽移动 ----------------
    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_start = e.position().toPoint()
            self._offset_start = QPoint(self._offset)
            self.setCursor(Qt.ClosedHandCursor)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent):
        if self._dragging:
            delta = e.position().toPoint() - self._drag_start
            self._offset = self._offset_start + delta
            self.update()
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent):
        if e.button() == Qt.LeftButton and self._dragging:
            moved = (e.position().toPoint() - self._drag_start).manhattanLength()
            self._dragging = False
            # 放大状态下恢复 OpenHand 光标，否则恢复 PointingHand
            if self._scale > 1.001:
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.setCursor(Qt.PointingHandCursor)
            # 几乎未移动 → 视为单击关闭
            if moved < 4:
                self.close_overlay()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        """双击: 重置到适应窗口"""
        self._reset_view()

    # ---------------- 键盘 ----------------
    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close_overlay()
        elif e.key() == Qt.Key_R:
            self._reset_view()
        else:
            super().keyPressEvent(e)

    def _reset_view(self) -> None:
        """重置缩放与位移"""
        self._scale = 1.0
        self._offset = QPoint(0, 0)
        self.setCursor(Qt.PointingHandCursor)
        self.update()

    # ---------------- 几何变化 ----------------
    def resizeEvent(self, e):
        if self.parentWidget() is not None:
            self.setGeometry(self.parentWidget().rect())
        self._fit_to_view()
        self._layout_hints()
        self.update()
        super().resizeEvent(e)

    # ---------------- 关闭 ----------------
    def close_overlay(self) -> None:
        self._dragging = False
        self._scale = 1.0
        self._offset = QPoint(0, 0)
        self._pixmap = None
        self._qimage = None
        self.prompt_label.hide()
        self.hide()
        self.closed.emit()
