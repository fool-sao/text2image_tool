"""主窗口

布局: 左侧配置面板 + 右侧 QTabWidget (手动生成 / 批量任务)。
职责:
- 加载/保存配置
- 接收 ManualPanel 的生成请求，构造 ZhipuImageClient 并发起生成
- 接收保存图片请求，弹出文件对话框保存单张图片
- 把 client 与 config 实时同步给 BatchPanel
- 应用全局样式
"""
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
    QWidget,

)
from PySide6.QtGui import QIcon

from api_client import ZhipuImageClient
from config import AppConfig
from ui.batch_panel import BatchPanel
from ui.config_panel import ConfigPanel
from ui.history_panel import HistoryPanel
from ui.manual_panel import ManualPanel
from ui.styles import STYLE, spinbox_arrow_qss
from ui.zoom_overlay import ZoomOverlay


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = AppConfig.load()
        self._client: ZhipuImageClient | None = None
        self.setWindowIcon(QIcon("icons/title.png")) 
        self.setWindowTitle("批量文生图工具")
        self.resize(1280, 800)
        self.setMinimumSize(1040, 680)

        self._build_ui()
        # 合并全局样式 + 启动时注入的 SpinBox 箭头 PNG 路径
        self.setStyleSheet(STYLE + spinbox_arrow_qss())
        self._refresh_client()
        self.statusBar().showMessage("就绪")

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("root")
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 左侧配置面板
        self.config_panel = ConfigPanel(self.config)
        self.config_panel.config_changed.connect(self._on_config_changed)
        layout.addWidget(self.config_panel)

        # 右侧选项卡
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.manual_panel = ManualPanel()
        self.manual_panel.request_generate.connect(self._on_request_generate)
        self.manual_panel.request_save.connect(self._on_request_save)
        self.manual_panel.request_zoom.connect(self._on_request_zoom)

        self.batch_panel = BatchPanel()
        self.batch_panel.request_zoom.connect(self._on_request_zoom)
        self.batch_panel.request_save.connect(self._on_batch_request_save)
        self.batch_panel.request_save_multi.connect(self._on_batch_request_save_multi)
        self.batch_panel.status_message.connect(
            lambda msg: self.statusBar().showMessage(msg, 4000)
        )

        self.history_panel = HistoryPanel()
        self.history_panel.refill_requested.connect(self._on_history_refill)
        self.history_panel.request_zoom.connect(self._on_request_zoom)
        self.history_panel.status_message.connect(
            lambda msg: self.statusBar().showMessage(msg, 4000)
        )

        self.tabs.addTab(self.manual_panel, "🎨 手动生成")
        self.tabs.addTab(self.batch_panel, "📊 批量任务")
        self.tabs.addTab(self.history_panel, "🕘 历史记录")
        layout.addWidget(self.tabs, 1)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

        # 图片放大灯箱 (覆盖整个中央区域)
        self.zoom_overlay = ZoomOverlay(central)

    # ---------------- 配置 ----------------
    def _on_config_changed(self) -> None:
        """侧边栏任意控件变更触发: 实时刷新客户端 (不写盘)"""
        self._refresh_client()

    def _refresh_client(self) -> None:
        cfg = self.config_panel.get_current_config()
        self.config = cfg
        if cfg.api_key:
            self._client = ZhipuImageClient(cfg.api_key, cfg.api_url)
            self.statusBar().showMessage("API Key 已加载", 2000)
        else:
            self._client = None
        # 实时同步给批量面板
        self.batch_panel.set_client(self._client)
        self.batch_panel.set_config(cfg)

    # ---------------- 手动生成 ----------------
    def _on_request_generate(self, prompt: str, card_id: int) -> None:
        if self._client is None:
            QMessageBox.warning(self, "未配置", "请先在左侧填写 API Key。")
            return

        cfg = self.config_panel.get_current_config()
        self.manual_panel.start_generate(
            client=self._client,
            prompt=prompt,
            size=cfg.size,
            quality=cfg.quality,
            watermark=cfg.watermark_enabled,
            system_prompt=cfg.system_prompt,
            card_id=card_id,
        )
        self.statusBar().showMessage("正在生成图片…")

    # ---------------- 图片放大 ----------------
    def _on_request_zoom(self, qimage, prompt: str) -> None:
        """单击图片: 弹出灯箱放大查看"""
        self.zoom_overlay.show_image(qimage, prompt)

    # ---------------- 历史回填 ----------------
    def _on_history_refill(self, params: dict) -> None:
        """历史卡片点击回填: 切到手动 tab, 填充提示词"""
        prompt = params.get("prompt", "")
        if prompt:
            self.manual_panel.fill_prompt(prompt)
        self.tabs.setCurrentWidget(self.manual_panel)
        self.statusBar().showMessage("已回填提示词到手动生成", 3000)

    # ---------------- 保存图片 ----------------
    def _on_request_save(self, card_id: int, raw_data: bytes, prompt: str) -> None:
        # 默认文件名: 时间戳 + 提示词前缀
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_prompt = "".join(c for c in prompt[:20] if c.isalnum() or c in "_-")
        default_name = f"{ts}_{safe_prompt or 'image'}.png"

        path, _ = QFileDialog.getSaveFileName(
            self, "保存图片", default_name, "PNG 图片 (*.png);;JPEG 图片 (*.jpg)"
        )
        if not path:
            return
        try:
            with open(path, "wb") as f:
                f.write(raw_data)
            self.statusBar().showMessage(f"已保存: {path}", 4000)
        except OSError as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def _on_batch_request_save(
        self, item_id: int, raw_data: bytes, prompt: str
    ) -> None:
        """批量面板单行保存请求: 复用同样逻辑"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_prompt = "".join(c for c in prompt[:20] if c.isalnum() or c in "_-")
        default_name = f"{ts}_{item_id}_{safe_prompt or 'image'}.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "保存图片", default_name,
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg)",
        )
        if not path:
            return
        try:
            with open(path, "wb") as f:
                f.write(raw_data)
            self.statusBar().showMessage(f"已保存: {path}", 4000)
        except OSError as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def _on_batch_request_save_multi(
        self, item_id: int, images_data: list, prompt: str
    ) -> None:
        """批量面板组图保存: 选择目录后, 把所有图按序号保存"""
        if not images_data:
            return
        # 选择目录
        out_dir = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not out_dir:
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_prompt = "".join(c for c in prompt[:20] if c.isalnum() or c in "_-")
        prefix = safe_prompt or "image"
        saved: list[str] = []
        try:
            for idx, raw in enumerate(images_data):
                fname = f"{ts}_{item_id}_{idx+1:02d}_{prefix}.png"
                fpath = Path(out_dir) / fname
                fpath.write_bytes(raw)
                saved.append(str(fpath))
        except OSError as e:
            QMessageBox.critical(self, "保存失败", str(e))
            return
        self.statusBar().showMessage(
            f"已保存 {len(saved)} 张图片到: {out_dir}", 5000
        )
