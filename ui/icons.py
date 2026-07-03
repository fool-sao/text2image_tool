"""图标加载工具

读取 ``icons/`` 目录下的 SVG 文件，按指定颜色渲染为 QPixmap / QIcon。
SVG 文本中的 ``fill="..."`` 会被正则替换为目标颜色，再用 QSvgRenderer 渲染，
从而让图标颜色与主题适配 (暗色主题下使用浅色图标)。
"""
import re
import tempfile
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap, QTransform
from PySide6.QtSvg import QSvgRenderer

ICON_DIR = Path(__file__).resolve().parent.parent / "icons"

# 临时 PNG 缓存目录 (供 QSS image: url() 引用)
_TMP_DIR = Path(tempfile.gettempdir()) / "text2image_v3_icons"


def _recolor_svg(svg_text: str, color: str) -> bytes:
    """替换 SVG 中所有 fill="..." 为指定颜色"""
    new_text = re.sub(r'fill="[^"]*"', f'fill="{color}"', svg_text)
    return new_text.encode("utf-8")


def render_pixmap(
    svg_path: Path,
    color: str = "#94a3b8",
    size: int = 18,
) -> QPixmap:
    """渲染 SVG 为指定颜色与尺寸的 QPixmap"""
    if not svg_path.exists():
        return QPixmap()
    text = svg_path.read_text(encoding="utf-8")
    data = _recolor_svg(text, color)
    renderer = QSvgRenderer(QByteArray(data))
    if not renderer.isValid():
        return QPixmap()
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    return pix


def eye_icon(visible: bool, color: str = "#94a3b8", size: int = 18) -> QIcon:
    """眼睛图标

    Args:
        visible: True 表示当前为"显示"态，使用睁眼图标；
                 False 表示"隐藏"态，使用闭眼图标。
    """
    name = "眼睛_显示_o.svg" if visible else "眼睛_隐藏_o.svg"
    pix = render_pixmap(ICON_DIR / name, color=color, size=size)
    return QIcon(pix)


def trash_icon(color: str = "#94a3b8", size: int = 16) -> QIcon:
    """垃圾桶图标 (用于删除按钮)

    Args:
        color: 图标颜色, 默认次要灰; 危险态可传红色
        size: 像素尺寸
    """
    pix = render_pixmap(ICON_DIR / "垃圾桶.svg", color=color, size=size)
    return QIcon(pix)


def _save_temp_pixmap(pix: QPixmap, name: str) -> str:
    """保存 QPixmap 到临时目录, 返回文件路径 (供 QSS image: url() 引用)"""
    _TMP_DIR.mkdir(parents=True, exist_ok=True)
    path = _TMP_DIR / name
    # 用正斜杠, QSS url() 在 Windows 上对反斜杠不友好
    pix.save(str(path), "PNG")
    return str(path).replace("\\", "/")


def arrow_temp_path(
    up: bool,
    color: str = "#94a3b8",
    size: int = 12,
) -> str:
    """渲染箭头图标到临时 PNG, 返回路径

    Args:
        up: True 为向上箭头 (原样); False 为向下箭头 (垂直翻转)
        color: 图标颜色
        size: 像素尺寸

    Returns:
        PNG 文件绝对路径 (正斜杠分隔), 可直接用于 QSS ``image: url(...)``
    """
    pix = render_pixmap(ICON_DIR / "箭头.svg", color=color, size=size)
    if not up:
        # 垂直翻转
        transform = QTransform()
        transform.scale(1, -1)
        pix = pix.transformed(transform, Qt.SmoothTransformation)
    color_tag = color.lstrip("#")
    return _save_temp_pixmap(pix, f"arrow_{'up' if up else 'down'}_{color_tag}_{size}.png")

