"""全局 QSS 样式表 (暗色主题)

设计语言: 与 Streamlit 版暗色风格对齐。
- 主背景 #0f1117 / 卡片 #1a1d27 / 输入 #252834
- 主色 靛蓝 #6366f1 / 悬停 #818cf8
- 圆角统一 10/12px，柔和层次
- 输入控件聚焦态用主色描边，无突兀背景
"""

# ============ 配色常量 (供 Python 代码中动态样式引用) ============
BG_MAIN = "#0f1117"        # 主背景
BG_CARD = "#1a1d27"        # 卡片 / 侧边栏背景
BG_INPUT = "#252834"       # 输入框背景
BG_HOVER = "#2d3142"       # 悬停态
ACCENT = "#6366f1"         # 主色 (靛蓝)
ACCENT_HOVER = "#818cf8"   # 主色悬停
ACCENT_PRESSED = "#4f46e5" # 主色按下
TEXT_PRIMARY = "#e2e8f0"   # 主文字
TEXT_SECONDARY = "#94a3b8" # 次要文字
TEXT_WEAK = "#64748b"      # 弱化文字
BORDER = "rgba(255, 255, 255, 0.08)"          # 默认描边
BORDER_HOVER = "rgba(255, 255, 255, 0.16)"    # 悬停描边
BORDER_FOCUS = "rgba(99, 102, 241, 0.55)"     # 聚焦描边 (主色半透明)
DANGER = "#ef4444"
SUCCESS = "#22c55e"
WARNING = "#f59e0b"

ACCENT_GRADIENT = (
    "qlineargradient(x1:0, y1:0, x2:1, y2:1,"
    " stop:0 #6366f1, stop:1 #8b5cf6)"
)

STYLE = f"""
* {{
    font-family: 'Microsoft YaHei UI', 'Segoe UI', 'PingFang SC', sans-serif;
    font-size: 13px;
    color: {TEXT_PRIMARY};
}}

QMainWindow, QWidget#root {{
    background-color: {BG_MAIN};
}}

/* ============ 侧边栏 ============ */
QFrame#sidebar {{
    background-color: {BG_CARD};
    border-right: 1px solid {BORDER};
}}

QFrame#sidebarHeader {{
    border: none;
}}

QLabel#sectionLabel {{
    color: {TEXT_SECONDARY};
    font-size: 12px;
    font-weight: 600;
}}

QLabel#hintLabel {{
    color: {TEXT_WEAK};
    font-size: 11px;
}}

/* ============ 输入控件 (圆角 10px) ============ */
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 9px 11px;
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
}}

QLineEdit:hover, QPlainTextEdit:hover, QComboBox:hover {{
    border: 1px solid {BORDER_HOVER};
}}

/* 聚焦态: 仅主色描边，无突兀背景 */
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
    border: 1px solid {BORDER_FOCUS};
    background-color: {BG_INPUT};
}}

QLineEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled {{
    background-color: {BG_CARD};
    color: {TEXT_WEAK};
}}

QLineEdit::placeholder, QPlainTextEdit::placeholder {{
    color: {TEXT_WEAK};
}}

QComboBox::drop-down {{
    border: none;
    width: 26px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {TEXT_SECONDARY};
    margin-right: 10px;
}}

QComboBox QAbstractItemView {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
    outline: none;
    padding: 4px;
}}

/* ============ 数字微调框 ============ */
QSpinBox {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 6px 28px 6px 10px;
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
    min-height: 22px;
}}

QSpinBox:hover {{
    border: 1px solid {BORDER_HOVER};
}}

QSpinBox:focus {{
    border: 1px solid {BORDER_FOCUS};
}}

QSpinBox:disabled {{
    background-color: {BG_CARD};
    color: {TEXT_WEAK};
}}

/* 上下按钮: 贴右侧, 18px 宽 */
QSpinBox::up-button, QSpinBox::down-button {{
    background-color: transparent;
    border: none;
    width: 18px;
    margin: 1px 2px;
}}

QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background-color: {BG_HOVER};
    border-radius: 4px;
}}

QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {{
    background-color: {ACCENT_PRESSED};
    border-radius: 4px;
}}

/* 上/下箭头 (默认无图片, 由 MainWindow 启动时通过 icons 注入临时 PNG 路径) */
QSpinBox::up-arrow, QSpinBox::down-arrow {{
    width: 12px;
    height: 12px;
}}

/* ============ 主按钮 (圆角 10px) ============ */
QPushButton {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 9px 18px;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: {BG_HOVER};
    border: 1px solid {BORDER_FOCUS};
}}

QPushButton:pressed {{
    background-color: {ACCENT_PRESSED};
    border: 1px solid {ACCENT_PRESSED};
}}

QPushButton:disabled {{
    background-color: {BG_CARD};
    color: {TEXT_WEAK};
    border: 1px solid {BORDER};
}}

/* 主按钮 (强调色渐变) */
QPushButton#primaryBtn {{
    background-image: {ACCENT_GRADIENT};
    border: none;
    color: #ffffff;
    font-weight: 600;
}}

QPushButton#primaryBtn:hover {{
    background-image: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #818cf8, stop:1 #a78bfa);
}}

QPushButton#primaryBtn:pressed {{
    background-image: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4f46e5, stop:1 #7c3aed);
}}

QPushButton#primaryBtn:disabled {{
    background-color: {BG_CARD};
    color: {TEXT_WEAK};
    border: 1px solid {BORDER};
}}

QPushButton#secondaryBtn {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
}}

QPushButton#secondaryBtn:hover {{
    background-color: {BG_HOVER};
    border: 1px solid {BORDER_FOCUS};
}}

QPushButton#secondaryBtn:pressed {{
    background-color: {ACCENT_PRESSED};
}}

QPushButton#ghostBtn {{
    background-color: transparent;
    color: {ACCENT_HOVER};
    border: 1px solid {ACCENT};
}}

QPushButton#ghostBtn:hover {{
    background-color: rgba(99, 102, 241, 0.12);
}}

QPushButton#ghostBtn:pressed {{
    background-color: rgba(99, 102, 241, 0.22);
}}

QPushButton#ghostBtn:disabled {{
    color: {TEXT_WEAK};
    border: 1px solid {BORDER};
}}

/* ============ 复选框 ============ */
QCheckBox {{
    spacing: 8px;
    color: {TEXT_PRIMARY};
    background: transparent;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1px solid {BORDER_HOVER};
    background-color: {BG_INPUT};
}}

QCheckBox::indicator:hover {{
    border: 1px solid {BORDER_FOCUS};
}}

QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border: 1px solid {ACCENT};
}}

/* ============ 滚动条 ============ */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 2px;
}}

QScrollBar::handle:vertical {{
    background: rgba(255, 255, 255, 0.12);
    border-radius: 5px;
    min-height: 36px;
}}

QScrollBar::handle:vertical:hover {{
    background: rgba(99, 102, 241, 0.55);
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px 4px;
}}

QScrollBar::handle:horizontal {{
    background: rgba(255, 255, 255, 0.12);
    border-radius: 5px;
    min-width: 36px;
}}

QScrollBar::handle:horizontal:hover {{
    background: rgba(99, 102, 241, 0.55);
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

QScrollArea {{
    background-color: transparent;
    border: none;
}}

/* ============ 图片卡片 (圆角 12px) ============ */
QFrame#imageCard {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}

QFrame#imageCard:hover {{
    border: 1px solid rgba(99, 102, 241, 0.35);
}}

QFrame#promptCard {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}

QLabel#cardPrompt {{
    color: {TEXT_SECONDARY};
    font-size: 12px;
}}

QLabel#cardStatus {{
    color: {TEXT_WEAK};
    font-size: 11px;
}}

QLabel#cardStatusSuccess {{
    color: {SUCCESS};
    font-size: 11px;
    font-weight: 600;
}}

QLabel#cardStatusFail {{
    color: {DANGER};
    font-size: 11px;
    font-weight: 600;
}}

QLabel#cardStatusLoading {{
    color: {WARNING};
    font-size: 11px;
    font-weight: 600;
}}

/* ============ 进度条 ============ */
QProgressBar {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 5px;
    max-height: 8px;
    font-size: 0px;
    color: transparent;
}}

QProgressBar::chunk {{
    background-image: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #6366f1, stop:1 #8b5cf6);
    border-radius: 5px;
}}

/* ============ 分组框 ============ */
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    margin-top: 14px;
    padding-top: 12px;
    background-color: {BG_CARD};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: {TEXT_PRIMARY};
    font-weight: 600;
}}

/* ============ 选项卡 ============ */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    background-color: {BG_CARD};
    top: -1px;
}}

QTabBar::tab {{
    background-color: transparent;
    color: {TEXT_SECONDARY};
    padding: 9px 20px;
    border: none;
    font-weight: 500;
}}

QTabBar::tab:selected {{
    color: {ACCENT_HOVER};
    border-bottom: 2px solid {ACCENT};
}}

QTabBar::tab:hover:!selected {{
    color: {TEXT_PRIMARY};
}}

/* ============ 状态栏 ============ */
QStatusBar {{
    background-color: {BG_CARD};
    border-top: 1px solid {BORDER};
    color: {TEXT_SECONDARY};
    font-size: 12px;
}}

QStatusBar::item {{
    border: none;
}}

/* ============ 工具提示 ============ */
QToolTip {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 10px;
}}
"""


def spinbox_arrow_qss() -> str:
    """生成包含箭头 PNG 路径的 QSS 片段

    在 MainWindow 启动时调用, 把着色后的箭头 PNG 路径注入 QSS,
    覆盖 STYLE 中默认的无图片状态。需要 QApplication 已存在,
    因此不能在 styles.py 模块顶层调用。
    """
    # 延迟导入, 避免 styles.py 模块加载时依赖 QApplication
    from ui.icons import arrow_temp_path
    from ui.styles import ACCENT_HOVER, TEXT_SECONDARY

    up_normal = arrow_temp_path(up=True, color=TEXT_SECONDARY, size=12)
    down_normal = arrow_temp_path(up=False, color=TEXT_SECONDARY, size=12)
    up_hover = arrow_temp_path(up=True, color=ACCENT_HOVER, size=12)
    down_hover = arrow_temp_path(up=False, color=ACCENT_HOVER, size=12)

    return f"""
QSpinBox::up-arrow {{
    image: url({up_normal});
}}
QSpinBox::up-arrow:hover {{
    image: url({up_hover});
}}
QSpinBox::down-arrow {{
    image: url({down_normal});
}}
QSpinBox::down-arrow:hover {{
    image: url({down_hover});
}}
"""
