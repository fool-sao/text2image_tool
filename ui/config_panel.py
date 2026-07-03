"""配置面板 (左侧边栏)

管理全局配置: API Key、系统提示词、默认尺寸/质量/水印。
配置修改后点击"保存配置"持久化，并通过 config_changed 信号通知主窗口。
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config import SIZE_OPTIONS, QUALITY_OPTIONS, DEFAULT_API_URL, AppConfig
from ui.icons import eye_icon, trash_icon
from ui.styles import (
    ACCENT_GRADIENT,
    BG_CARD,
    BG_INPUT,
    BORDER,
    DANGER,
    TEXT_SECONDARY,
)


class ConfigPanel(QFrame):
    """左侧配置面板"""

    config_changed = Signal()

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(320)
        self.config = config
        self._build_ui()
        self._load_values()

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- 固定渐变标题栏 ----
        header = QFrame()
        header.setObjectName("sidebarHeader")
        header.setStyleSheet(
            f"QFrame#sidebarHeader {{"
            f" background-image: {ACCENT_GRADIENT};"
            f" border: none;"
            f"}}"
        )
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(20, 20, 20, 18)
        h_layout.setSpacing(2)

        brand = QLabel("🎨 文生图")
        brand.setStyleSheet(
            "color: #ffffff; font-size: 16px; font-weight: 700;"
            " background: transparent; border: none;"
        )
        h_layout.addWidget(brand)

        sub = QLabel("批量图像生成工具")
        sub.setStyleSheet(
            "color: rgba(255,255,255,0.82); font-size: 11px;"
            " background: transparent; border: none;"
        )
        h_layout.addWidget(sub)

        outer.addWidget(header)

        # ---- 可滚动内容 ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {BG_CARD}; border: none; }}"
        )

        container = QWidget()
        container.setStyleSheet(f"background-color: {BG_CARD};")
        v = QVBoxLayout(container)
        v.setContentsMargins(20, 18, 20, 20)
        v.setSpacing(16)

        # ---- API 地址 ----
        v.addWidget(self._section("🔗  API 地址"))
        self.api_url_edit = QLineEdit()
        self.api_url_edit.setPlaceholderText("图像生成接口地址")
        v.addWidget(self.api_url_edit)

        url_hint = QLabel("默认为智谱官方接口，可按需自定义")
        url_hint.setObjectName("hintLabel")
        url_hint.setWordWrap(True)
        v.addWidget(url_hint)
        
        # ---- API Key (输入框内嵌眼睛图标按钮) ----
        v.addWidget(self._section("🔑  API KEY"))
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("输入智谱 AI Bearer Token")
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        # 内嵌眼睛图标 (TrailingPosition = 输入框右侧)
        self.show_key_action = self.api_key_edit.addAction(
            eye_icon(visible=False, color=TEXT_SECONDARY, size=18),
            QLineEdit.ActionPosition.TrailingPosition,
        )
        self.show_key_action.setToolTip("显示 / 隐藏 API Key")
        self.show_key_action.triggered.connect(self._toggle_key_visibility)
        v.addWidget(self.api_key_edit)



        # ---- 系统提示词 ----
        v.addWidget(self._section("💬  系统提示词"))

        # 提示词库下拉选择 (从已保存的提示词中读取)
        prompt_sel_row = QHBoxLayout()
        prompt_sel_row.setSpacing(6)
        self.prompt_combo = QComboBox()
        self.prompt_combo.setToolTip("从提示词库中选择一条填入编辑框")
        self.prompt_combo.addItem("— 选择已保存的提示词 —")
        self.prompt_combo.currentIndexChanged.connect(self._on_prompt_selected)
        prompt_sel_row.addWidget(self.prompt_combo, 1)

        self.btn_del_prompt = QPushButton()
        self.btn_del_prompt.setFixedSize(34, 30)
        self.btn_del_prompt.setCursor(Qt.PointingHandCursor)
        self.btn_del_prompt.setToolTip("从提示词库删除当前选中项")
        self.btn_del_prompt.setIcon(trash_icon(color="#94a3b8", size=16))
        self._del_prompt_normal_style = (
            f"QPushButton {{"
            f" background-color: {BG_INPUT};"
            f" border: 1px solid {BORDER};"
            f" border-radius: 8px;"
            f"}}"
            f"QPushButton:hover {{"
            f" background-color: rgba(239, 68, 68, 0.18);"
            f" border: 1px solid rgba(239, 68, 68, 0.5);"
            f"}}"
            f"QPushButton:pressed {{"
            f" background-color: rgba(239, 68, 68, 0.3);"
            f"}}"
        )
        self.btn_del_prompt.setStyleSheet(self._del_prompt_normal_style)
        self.btn_del_prompt.clicked.connect(self._on_delete_prompt)
        # hover 时图标变红, leave 时恢复灰
        self.btn_del_prompt.enterEvent = self._on_del_btn_enter
        self.btn_del_prompt.leaveEvent = self._on_del_btn_leave
        prompt_sel_row.addWidget(self.btn_del_prompt)
        v.addLayout(prompt_sel_row)

        # 提示词编辑框 (当前生效的系统提示词)
        self.system_prompt_edit = QPlainTextEdit()
        self.system_prompt_edit.setPlaceholderText(
            "全局系统提示词 (可选)，会拼接到每次生成的提示词前"
        )
        self.system_prompt_edit.setMaximumHeight(80)
        v.addWidget(self.system_prompt_edit)

        # 新增到提示词库按钮
        self.btn_add_prompt = QPushButton("＋ 存为提示词")
        self.btn_add_prompt.setObjectName("secondaryBtn")
        self.btn_add_prompt.setCursor(Qt.PointingHandCursor)
        self.btn_add_prompt.setToolTip("把当前编辑框内容保存到提示词库")
        self.btn_add_prompt.clicked.connect(self._on_add_prompt)
        v.addWidget(self.btn_add_prompt)

        # ---- 默认参数 ----
        v.addWidget(self._section("⚙️  默认参数"))
        form = QFormLayout()
        form.setSpacing(12)
        form.setContentsMargins(0, 0, 0, 0)
        form.setLabelAlignment(Qt.AlignLeft)

        self.size_combo = QComboBox()
        self.size_combo.addItems(SIZE_OPTIONS)
        form.addRow(self._form_label("尺寸"), self.size_combo)

        self.quality_combo = QComboBox()
        self.quality_combo.addItems(QUALITY_OPTIONS)
        form.addRow(self._form_label("质量"), self.quality_combo)

        self.watermark_check = QCheckBox("开启水印")
        form.addRow(self._form_label("水印"), self.watermark_check)

        v.addLayout(form)

        v.addStretch()

        # ---- 保存按钮 (仅持久化到本地, 下次打开软件时使用) ----
        # 用更显眼的样式: 主色实色背景 + 亮边框 + 加大字号/padding
        self.save_btn = QPushButton("💾  保存到本地")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setToolTip("把当前配置写入 config.json, 下次打开软件时生效\n参数已实时生效, 无需点击此按钮")
        self.save_btn.setStyleSheet(
            f"QPushButton {{"
            f" background-color: #6366f1;"
            f" color: #ffffff;"
            f" border: 1px solid #818cf8;"
            f" border-radius: 10px;"
            f" padding: 11px 20px;"
            f" font-size: 14px;"
            f" font-weight: 600;"
            f"}}"
            f"QPushButton:hover {{"
            f" background-color: #818cf8;"
            f" border: 1px solid #a5b0fc;"
            f"}}"
            f"QPushButton:pressed {{"
            f" background-color: #4f46e5;"
            f" border: 1px solid #6366f1;"
            f"}}"
        )
        self.save_btn.clicked.connect(self._save_config)
        v.addWidget(self.save_btn)

        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

        # ---- 控件变更即通知 (实时响应, 无需点保存) ----
        self.api_key_edit.textChanged.connect(self._on_field_changed)
        self.api_url_edit.textChanged.connect(self._on_field_changed)
        self.system_prompt_edit.textChanged.connect(self._on_field_changed)
        self.size_combo.currentTextChanged.connect(self._on_field_changed)
        self.quality_combo.currentTextChanged.connect(self._on_field_changed)
        self.watermark_check.stateChanged.connect(self._on_field_changed)

    def _on_field_changed(self) -> None:
        """任意控件变更即通知主窗口刷新客户端; 不写盘 (保存按钮才写盘)"""
        self.config_changed.emit()

    @staticmethod
    def _section(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionLabel")
        return lbl

    @staticmethod
    def _form_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setMinimumWidth(40)
        return lbl

    # ---------------- 数据加载/保存 ----------------
    def _load_values(self) -> None:
        self.api_key_edit.setText(self.config.api_key)
        self.api_url_edit.setText(self.config.api_url)
        self.system_prompt_edit.setPlainText(self.config.system_prompt)
        self._refresh_prompt_combo()
        self._set_combo(self.size_combo, self.config.size)
        self._set_combo(self.quality_combo, self.config.quality)
        self.watermark_check.setChecked(self.config.watermark_enabled)

    def _refresh_prompt_combo(self) -> None:
        """刷新提示词库下拉 (第 0 项为占位, 其余为已保存提示词)"""
        # 暂时阻塞信号, 避免重建时触发 _on_prompt_selected
        self.prompt_combo.blockSignals(True)
        self.prompt_combo.clear()
        self.prompt_combo.addItem("— 选择已保存的提示词 —")
        for p in self.config.system_prompts:
            # 截断显示, 完整内容在 tooltip
            display = p if len(p) <= 40 else p[:40] + "…"
            self.prompt_combo.addItem(display)
            self.prompt_combo.setItemData(self.prompt_combo.count() - 1, p, Qt.ToolTipRole)
        self.prompt_combo.blockSignals(False)

    def _on_prompt_selected(self, idx: int) -> None:
        """下拉选择: 把选中的提示词填入编辑框"""
        if idx <= 0:
            return  # 占位项
        # 取完整文本 (display 可能被截断, 从 config.system_prompts 取)
        if idx - 1 < len(self.config.system_prompts):
            self.system_prompt_edit.setPlainText(self.config.system_prompts[idx - 1])

    def _on_add_prompt(self) -> None:
        """把当前编辑框内容保存到提示词库"""
        text = self.system_prompt_edit.toPlainText().strip()
        if not text:
            return
        self.config.add_prompt(text)
        self.config.save()
        self._refresh_prompt_combo()
        # 选中新加入的项 (最后一项)
        self.prompt_combo.setCurrentIndex(self.prompt_combo.count() - 1)

    def _on_delete_prompt(self) -> None:
        """从提示词库删除当前下拉选中的提示词"""
        idx = self.prompt_combo.currentIndex()
        if idx <= 0:
            return
        if idx - 1 < len(self.config.system_prompts):
            text = self.config.system_prompts[idx - 1]
            self.config.remove_prompt(text)
            self.config.save()
            self._refresh_prompt_combo()

    def _on_del_btn_enter(self, e) -> None:
        """hover 时图标变红"""
        self.btn_del_prompt.setIcon(trash_icon(color=DANGER, size=16))

    def _on_del_btn_leave(self, e) -> None:
        """离开时图标恢复灰"""
        self.btn_del_prompt.setIcon(trash_icon(color="#94a3b8", size=16))

    @staticmethod
    def _set_combo(combo: QComboBox, value: str) -> None:
        idx = combo.findText(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        elif combo.count() > 0:
            combo.setCurrentIndex(0)

    def _save_config(self) -> None:
        """保存按钮: 仅持久化当前控件值到 config.json (供下次打开软件使用)

        实时响应已在 ``_on_field_changed`` 中通过 ``config_changed`` 信号完成;
        因此此处只写盘, 不再 emit 信号。
        """
        self.config.api_key = self.api_key_edit.text().strip()
        self.config.api_url = self.api_url_edit.text().strip() or DEFAULT_API_URL
        self.config.system_prompt = self.system_prompt_edit.toPlainText().strip()
        # 若当前提示词非空且不在库中, 自动加入库
        if self.config.system_prompt:
            self.config.add_prompt(self.config.system_prompt)
        self.config.size = self.size_combo.currentText()
        self.config.quality = self.quality_combo.currentText()
        self.config.watermark_enabled = self.watermark_check.isChecked()
        self.config.save()
        self._refresh_prompt_combo()

    # ---------------- 外部接口 ----------------
    def get_current_config(self) -> AppConfig:
        """返回当前面板上的配置 (未保存也可读取)"""
        return AppConfig(
            api_key=self.api_key_edit.text().strip(),
            api_url=self.api_url_edit.text().strip() or DEFAULT_API_URL,
            system_prompt=self.system_prompt_edit.toPlainText().strip(),
            system_prompts=list(self.config.system_prompts),
            size=self.size_combo.currentText(),
            quality=self.quality_combo.currentText(),
            watermark_enabled=self.watermark_check.isChecked(),
        )

    def _toggle_key_visibility(self) -> None:
        """切换 API Key 显示/隐藏，并同步眼睛图标"""
        if self.api_key_edit.echoMode() == QLineEdit.Password:
            self.api_key_edit.setEchoMode(QLineEdit.Normal)
            self.show_key_action.setIcon(
                eye_icon(visible=True, color=TEXT_SECONDARY, size=18)
            )
        else:
            self.api_key_edit.setEchoMode(QLineEdit.Password)
            self.show_key_action.setIcon(
                eye_icon(visible=False, color=TEXT_SECONDARY, size=18)
            )
