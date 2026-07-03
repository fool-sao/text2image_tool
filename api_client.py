"""智谱 AI 图像生成 API 客户端

对接接口: POST https://open.bigmodel.cn/api/paas/v4/images/generations
模型: glm-image
返回: 兼容 url 与 b64_json 两种格式，统一输出图片二进制数据。
"""
import base64

import httpx

from config import DEFAULT_API_URL

MODEL = "glm-image"


class ImageGenerationError(Exception):
    """图像生成过程中的业务异常"""


class ZhipuImageClient:
    """智谱图像生成同步客户端 (在 QThread 中调用以避免阻塞 UI)"""

    def __init__(
        self,
        api_key: str,
        api_url: str = DEFAULT_API_URL,
        timeout: float = 120.0,
    ):
        self.api_key = api_key
        self.api_url = api_url or DEFAULT_API_URL
        self.timeout = timeout

    def generate(
        self,
        prompt: str,
        size: str,
        quality: str,
        watermark_enabled: bool,
        system_prompt: str = "",
    ) -> bytes:
        """生成单张图片，返回图片二进制数据 (等价于 n=1)"""
        images = self.generate_n(
            prompt=prompt,
            size=size,
            quality=quality,
            watermark_enabled=watermark_enabled,
            system_prompt=system_prompt,
            n=1,
        )
        return images[0]

    def generate_n(
        self,
        prompt: str,
        size: str,
        quality: str,
        watermark_enabled: bool,
        system_prompt: str = "",
        n: int = 1,
    ) -> list[bytes]:
        """生成 n 张图片，返回图片二进制数据列表

        Args:
            prompt: 用户提示词
            size: 尺寸, 如 "1280x1280"
            quality: 质量, "hd" 或 "standard"
            watermark_enabled: 是否开启水印
            system_prompt: 系统提示词 (会拼接到 prompt 前)
            n: 一次生成的图片数量 (1-4)

        Returns:
            图片二进制数据列表 (长度 == n, 个别失败时可能更短)
        """
        if not self.api_key:
            raise ImageGenerationError("未配置 API Key，请先在左侧设置中填写")
        n = max(1, min(int(n), 4))

        # 系统提示词拼接到用户提示词前
        full_prompt = f"{system_prompt}\n{prompt}" if system_prompt else prompt

        body = {
            "model": MODEL,
            "prompt": full_prompt,
            "size": size,
            "quality": quality,
            "watermark_enabled": watermark_enabled,
            "n": n,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # 发起生成请求
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(self.api_url, json=body, headers=headers)
        except httpx.RequestError as e:
            raise ImageGenerationError(f"网络请求失败: {e}") from e

        if resp.status_code != 200:
            raise ImageGenerationError(
                f"API 返回错误 {resp.status_code}: {resp.text}"
            )

        data = resp.json()
        items = data.get("data") or []
        if not items:
            raise ImageGenerationError(f"返回数据无图片字段: {data}")

        results: list[bytes] = []
        with httpx.Client(timeout=self.timeout) as dl_client:
            for item in items:
                # 情况1: 返回图片 URL，需下载
                url = item.get("url")
                if url:
                    try:
                        r = dl_client.get(url)
                        r.raise_for_status()
                        results.append(r.content)
                        continue
                    except httpx.RequestError as e:
                        raise ImageGenerationError(f"下载图片失败: {e}") from e

                # 情况2: 返回 base64 编码
                b64 = item.get("b64_json")
                if b64:
                    try:
                        results.append(base64.b64decode(b64))
                        continue
                    except Exception as e:
                        raise ImageGenerationError(f"base64 解码失败: {e}") from e

        if not results:
            raise ImageGenerationError(f"返回数据格式异常: {items}")

        return results
