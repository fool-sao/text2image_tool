"""本地输出归档管理

所有生成的图片额外保存到本软件 ``outputs/`` 目录, 与 v2 版本的格式对齐:
- ``outputs/images/YYYYMMDD/HHMMSS_mmm_xxxxxx.jpeg``  图片按日期分文件夹
- ``outputs/history.json``                              全量历史记录
- ``outputs/results_YYYYMMDD.xlsx``                     按日期聚合的 Excel

文件名规则: ``HHMMSS_mmm_xxxxxx.jpeg``
- HHMMSS: 时分秒
- mmm: 毫秒前 3 位
- xxxxxx: 6 位随机 hex (secrets.token_hex(3))
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

# 输出根目录 (本软件 outputs/)
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
IMAGES_DIR = OUTPUT_DIR / "images"
HISTORY_FILE = OUTPUT_DIR / "history.json"

# 模型名 (与 API 客户端一致)
MODEL_NAME = "glm-image"


def save_generation(
    image_data: Optional[bytes],
    prompt: str,
    size: str,
    quality: str = "",
    status: str = "success",
    error: Optional[str] = None,
) -> dict:
    """保存一次生成到 outputs/, 返回记录字典

    Args:
        image_data: 图片二进制 (PNG/JPEG); 失败时为 None
        prompt: 提示词
        size: 尺寸 (如 "1280x1280")
        quality: 质量 (如 "hd")
        status: "success" / "failed"
        error: 失败时的错误信息

    Returns:
        记录字典, 含 id/timestamp/prompt/size/quality/model/status/image_path 等字段
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now()
    ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
    date_str = timestamp.strftime("%Y%m%d")
    time_str = timestamp.strftime("%H%M%S")
    ms_str = f"{timestamp.microsecond // 1000:03d}"
    hex_id = secrets.token_hex(3)  # 6 位

    image_path_rel = ""
    # 仅成功且有图片数据时保存图片
    if image_data and status == "success":
        img_dir = IMAGES_DIR / date_str
        img_dir.mkdir(parents=True, exist_ok=True)
        # 统一保存为 jpeg (与 v2 一致); 若原始是 PNG 也能保存为 jpeg
        img_name = f"{time_str}_{ms_str}_{hex_id}.jpeg"
        img_path = img_dir / img_name
        try:
            img_path.write_bytes(image_data)
            image_path_rel = f"images/{date_str}/{img_name}"
        except OSError:
            # 写盘失败不阻断主流程, 仅 image_path 留空
            image_path_rel = ""

    record = {
        "id": hex_id,
        "timestamp": ts_str,
        "prompt": prompt,
        "negative_prompt": "",
        "seed": None,
        "size": size,
        "quality": quality,
        "steps": 30,
        "model": MODEL_NAME,
        "status": status,
        "image_path": image_path_rel,
    }
    if error:
        record["error"] = error

    # 追加 history.json (失败不阻断)
    try:
        _append_history(record)
    except Exception:
        pass

    # 追加 results_YYYYMMDD.xlsx (失败不阻断)
    try:
        _append_results_excel(date_str, record)
    except Exception:
        pass

    return record


def _append_history(record: dict) -> None:
    """追加记录到 history.json (最新的放最前)"""
    history: list = []
    if HISTORY_FILE.exists():
        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                history = data
        except Exception:
            history = []
    history.insert(0, record)
    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _append_results_excel(date_str: str, record: dict) -> None:
    """追加记录到 outputs/results_YYYYMMDD.xlsx (最新的在最前)"""
    xlsx_path = OUTPUT_DIR / f"results_{date_str}.xlsx"
    df_new = pd.DataFrame([{
        "Timestamp": record["timestamp"],
        "Prompt": record["prompt"],
        "Negative_Prompt": record["negative_prompt"],
        "Image_Path": record["image_path"],
        "Seed": record["seed"],
        "Status": record["status"],
    }])
    if xlsx_path.exists():
        try:
            df_old = pd.read_excel(xlsx_path)
            df = pd.concat([df_new, df_old], ignore_index=True)
        except Exception:
            df = df_new
    else:
        df = df_new
    df.to_excel(xlsx_path, index=False)


def load_history(limit: Optional[int] = None) -> list[dict]:
    """读取历史记录 (最新在前)

    Args:
        limit: 最多返回条数, None 表示全部

    Returns:
        记录字典列表, 每条含 id/timestamp/prompt/size/quality/model/status/image_path 等
    """
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        if limit is not None:
            return data[:limit]
        return data
    except Exception:
        return []


def clear_history() -> None:
    """清空历史记录 (仅清空 history.json, 不删除图片文件)"""
    HISTORY_FILE.write_text("[]", encoding="utf-8")


def resolve_image_path(image_path: str) -> Path:
    """将记录中的相对路径解析为绝对路径

    Args:
        image_path: 相对路径 (如 "images/20260703/xxx.jpeg") 或绝对路径

    Returns:
        绝对 Path 对象
    """
    p = Path(image_path)
    if p.is_absolute():
        return p
    return OUTPUT_DIR / image_path
