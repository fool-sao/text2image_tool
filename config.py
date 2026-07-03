"""配置管理模块

使用 Pydantic 管理全局配置，并持久化到项目根目录的 config.json。
包含: API Key、系统提示词库、默认生成参数 (尺寸/质量/水印)。
"""
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field

# 配置文件存放于项目根目录
CONFIG_FILE = Path(__file__).parent / "config.json"

# 默认 API 地址 (可在界面中修改)
DEFAULT_API_URL = "https://open.bigmodel.cn/api/paas/v4/images/generations"

# 可选尺寸 (智谱 glm-image 推荐尺寸)
SIZE_OPTIONS = [
    "1280x1280",   # 默认方形
    "1568x1056",   # 横向
    "1056x1568",   # 纵向
    "1024x1024",
    "768x1024",
    "1024x768",
]

QUALITY_OPTIONS = ["hd", "standard"]


class AppConfig(BaseModel):
    """应用全局配置"""

    api_key: str = Field(default="", description="智谱 AI Bearer Token")
    api_url: str = Field(default=DEFAULT_API_URL, description="图像生成 API 地址")
    # 当前生效的系统提示词 (单条)
    system_prompt: str = Field(default="", description="当前生效的系统提示词")
    # 系统提示词库 (多条), 供下拉选择
    system_prompts: List[str] = Field(
        default_factory=list, description="系统提示词库"
    )
    size: str = Field(default="1280x1280", description="默认图片尺寸")
    quality: str = Field(default="hd", description="默认图片质量")
    watermark_enabled: bool = Field(default=True, description="是否开启水印")

    def save(self) -> None:
        """持久化到 config.json"""
        CONFIG_FILE.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls) -> "AppConfig":
        """从 config.json 读取，不存在或解析失败时返回默认配置"""
        if CONFIG_FILE.exists():
            try:
                return cls.model_validate_json(
                    CONFIG_FILE.read_text(encoding="utf-8")
                )
            except Exception:
                # 配置文件损坏则忽略，使用默认值
                pass
        return cls()

    # ---------------- 系统提示词库操作 ----------------
    def add_prompt(self, text: str) -> None:
        """新增一条系统提示词到库中 (去重, 去空白)"""
        text = text.strip()
        if not text:
            return
        if text in self.system_prompts:
            # 已存在则移到末尾 (最近使用优先)
            self.system_prompts.remove(text)
        self.system_prompts.append(text)

    def remove_prompt(self, text: str) -> None:
        """从库中删除指定提示词"""
        text = text.strip()
        if text in self.system_prompts:
            self.system_prompts.remove(text)
