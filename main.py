"""程序入口

启动智谱清言批量文生图工具主窗口。
运行: python main.py
"""
import sys
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow

from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("批量文生图工具")
    app.setWindowIcon(QIcon("icons/title.png"))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
