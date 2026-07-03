"""Excel 读写工具 (基于 pandas + openpyxl)

约定:
- 输入文件列名大小写不敏感
- 必填列: ``prompt``
- 可选列: ``size`` / ``quality`` / ``watermark`` / ``system_prompt``
  (缺失或空值则回退到左侧全局配置)
- ``watermark`` 列接受: true/false/是/否/1/0 (大小写不敏感)

输出文件:
- 在选定输出目录生成 ``{原文件名}_结果.xlsx``
- 在原列基础上追加: ``image_path`` / ``status`` / ``error`` / ``generated_at``
- 仅导出勾选行
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

# 列名规范化映射 (小写 -> 标准列名)
COLUMN_ALIASES = {
    "prompt": "prompt",
    "提示词": "prompt",
    "size": "size",
    "尺寸": "size",
    "quality": "quality",
    "质量": "quality",
    "watermark": "watermark",
    "水印": "watermark",
    "system_prompt": "system_prompt",
    "系统提示词": "system_prompt",
    "image_path": "image_path",
    "图片路径": "image_path",
    "status": "status",
    "状态": "status",
    "error": "error",
    "错误": "error",
    "generated_at": "generated_at",
    "生成时间": "generated_at",
}


@dataclass
class BatchRow:
    """批量任务单行数据

    所有 *_override 字段为 None 表示未在 Excel 中指定, 应回退到全局配置。

    单图模式 (n=1): 使用 image_data / image_path
    组图模式 (n>1): 使用 images_data / image_paths (长度 == n_expected)
    """
    source_index: int               # 在原 Excel 中的行号 (0-based, 不含表头)
    prompt: str
    size_override: Optional[str] = None
    quality_override: Optional[str] = None
    watermark_override: Optional[bool] = None
    system_prompt_override: Optional[str] = None
    # 单图模式生成结果 (运行时填充)
    image_data: Optional[bytes] = None
    image_path: Optional[str] = None
    status: str = "pending"         # pending / running / success / failed
    error: Optional[str] = None
    generated_at: Optional[str] = None
    # 标识是否勾选 (默认勾选最新一次生成)
    selected: bool = True
    # 唯一 ID (用于重绘追加新行时区分)
    item_id: int = 0
    # 组图模式相关字段
    n_expected: int = 1                          # 该行预期生成图片数
    images_data: list = field(default_factory=list)   # 多图二进制 (组图模式)
    image_paths: list = field(default_factory=list)   # 多图导出路径 (组图模式)


def _normalize_column(name: Any) -> str:
    """列名规范化: 去空白、转小写、查别名表"""
    if name is None:
        return ""
    s = str(name).strip().lower()
    return COLUMN_ALIASES.get(s, s)


def _parse_watermark(value: Any) -> Optional[bool]:
    """解析 watermark 单元格的值, 返回 None 表示未指定"""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if not s:
        return None
    if s in ("true", "1", "是", "yes", "y", "on"):
        return True
    if s in ("false", "0", "否", "no", "n", "off"):
        return False
    return None


def read_excel(path: str | Path) -> list[BatchRow]:
    """读取 Excel 文件, 返回 BatchRow 列表

    Args:
        path: Excel 文件路径

    Returns:
        BatchRow 列表 (跳过 prompt 为空的行)

    Raises:
        ValueError: 缺少 prompt 列
    """
    df = pd.read_excel(path)
    if df.empty:
        return []

    # 重命名列为标准名
    rename_map = {col: _normalize_column(col) for col in df.columns}
    df = df.rename(columns=rename_map)

    if "prompt" not in df.columns:
        raise ValueError("Excel 缺少必填列: prompt (提示词)")

    rows: list[BatchRow] = []
    for idx, record in df.iterrows():
        prompt_raw = record.get("prompt")
        prompt = "" if pd.isna(prompt_raw) else str(prompt_raw).strip()
        if not prompt:
            continue

        size = record.get("size")
        quality = record.get("quality")
        system_prompt = record.get("system_prompt")

        rows.append(BatchRow(
            source_index=int(idx),
            prompt=prompt,
            size_override=None if pd.isna(size) else str(size).strip() or None,
            quality_override=None if pd.isna(quality) else str(quality).strip() or None,
            watermark_override=_parse_watermark(record.get("watermark")),
            system_prompt_override=(
                None if pd.isna(system_prompt)
                else str(system_prompt).strip() or None
            ),
        ))
    return rows


def write_excel(
    src_path: str | Path,
    rows: list[BatchRow],
    out_dir: str | Path,
) -> Path:
    """把勾选的行回填到新 Excel, 返回输出文件路径

    Args:
        src_path: 原 Excel 文件路径 (用于保留原列结构)
        rows: 所有 BatchRow (仅写 selected=True 的行)
        out_dir: 输出目录

    Returns:
        输出文件路径
    """
    src_path = Path(src_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    out_name = f"{src_path.stem}_结果.xlsx"
    out_path = out_dir / out_name

    # 读取原文件结构 (保留原始列顺序与表头)
    src_df = pd.read_excel(src_path)
    rename_map = {col: _normalize_column(col) for col in src_df.columns}
    src_df = src_df.rename(columns=rename_map)

    # 构造结果 DataFrame (仅勾选行)
    selected = [r for r in rows if r.selected]
    if not selected:
        # 仍写出空表, 包含所有原列 + 结果列
        result_df = src_df.copy()
        result_df["image_path"] = []
        result_df["status"] = []
        result_df["error"] = []
        result_df["generated_at"] = []
        result_df = result_df.iloc[0:0]
    else:
        # 按 source_index 对齐原行, 写入结果列
        result_df = src_df.copy()
        result_df["image_path"] = ""
        result_df["status"] = ""
        result_df["error"] = ""
        result_df["generated_at"] = ""
        for r in selected:
            if 0 <= r.source_index < len(result_df):
                result_df.at[r.source_index, "image_path"] = r.image_path or ""
                result_df.at[r.source_index, "status"] = r.status
                result_df.at[r.source_index, "error"] = r.error or ""
                result_df.at[r.source_index, "generated_at"] = r.generated_at or ""
        # 仅保留勾选行
        selected_indices = [r.source_index for r in selected]
        result_df = result_df.loc[selected_indices].reset_index(drop=True)

    result_df.to_excel(out_path, index=False)
    return out_path


def write_excel_safe(
    src_path: str | Path,
    rows: list[BatchRow],
    out_dir: str | Path,
) -> Path:
    """带 PermissionError 处理的写盘: 若目标被占用, 自动追加 _N 后缀重试

    Raises:
        PermissionError: 多次重试均失败时抛出, 由调用方提示用户关闭已打开的 Excel
    """
    src_path = Path(src_path)
    out_dir = Path(out_dir)
    base_name = f"{src_path.stem}_结果"
    candidates = [out_dir / f"{base_name}.xlsx"]
    for i in range(2, 20):
        candidates.append(out_dir / f"{base_name}_{i}.xlsx")

    last_err: Optional[Exception] = None
    for cand in candidates:
        try:
            _write_excel_to_path(src_path, rows, cand)
            return cand
        except PermissionError as e:
            last_err = e
            continue  # 该文件被占用 (通常是被 Excel 打开), 试下一个
        except OSError as e:
            last_err = e
            continue
    raise PermissionError(
        f"无法写入 Excel (可能被其他程序占用): {last_err}"
    )


def _write_excel_to_path(
    src_path: Path, rows: list[BatchRow], out_path: Path
) -> None:
    """实际写盘逻辑 (与原 write_excel 一致), 抛出底层异常供上层处理"""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    src_df = pd.read_excel(src_path)
    rename_map = {col: _normalize_column(col) for col in src_df.columns}
    src_df = src_df.rename(columns=rename_map)

    selected = [r for r in rows if r.selected]
    if not selected:
        result_df = src_df.copy()
        result_df["image_path"] = []
        result_df["status"] = []
        result_df["error"] = []
        result_df["generated_at"] = []
        result_df = result_df.iloc[0:0]
    else:
        result_df = src_df.copy()
        result_df["image_path"] = ""
        result_df["status"] = ""
        result_df["error"] = ""
        result_df["generated_at"] = ""
        for r in selected:
            if 0 <= r.source_index < len(result_df):
                result_df.at[r.source_index, "image_path"] = r.image_path or ""
                result_df.at[r.source_index, "status"] = r.status
                result_df.at[r.source_index, "error"] = r.error or ""
                result_df.at[r.source_index, "generated_at"] = r.generated_at or ""
        selected_indices = [r.source_index for r in selected]
        result_df = result_df.loc[selected_indices].reset_index(drop=True)

    result_df.to_excel(out_path, index=False)
