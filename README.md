# 批量文生图工具

基于 [智谱清言 glm-image](https://open.bigmodel.cn/) 模型的桌面端文生图工具,采用 PySide6 构建,支持手动单图生成、Excel 批量任务、组图模式与本地历史归档。界面采用现代暗色主题,主色靛蓝 `#4f6df5`,卡片化布局配合圆角与柔和阴影。
<img width="1378" height="828" alt="image" src="https://github.com/user-attachments/assets/974d86cb-5fd2-4a3d-9468-52c15e71b8cf" />

## 功能特性

### 三大主面板(右侧 Tab 切换)

- **手动生成**:顶部提示词输入 + 流式布局卡片墙,支持编辑重绘、重新生成、单张保存
- **批量任务**:导入 Excel 即可批量生成,可配置并发数,实时进度跟踪,勾选导出结果
- **历史记录**:本地归档卡片网格,缩略图点击放大,支持回填提示词到手动生成

### 核心能力

- **单图 / 组图模式**:一次请求生成 1~4 张图片(`n` 参数)
- **系统提示词库**:左侧边栏维护可复用的系统提示词,下拉切换
- **Excel 批量驱动**:列名大小写不敏感,支持中英文列名(`prompt`/`提示词`、`size`/`尺寸` 等);可选列缺省时回退到全局配置
- **并发调度**:基于 `QThreadPool` + `QRunnable`,可配置并发数,支持随时停止未启动任务
- **本地归档**:生成结果按日期分目录归档到 `outputs/`
  - `outputs/images/YYYYMMDD/HHMMSS_mmm_xxxxxx.jpeg` — 图片按日期分文件夹
  - `outputs/history.json` — 全量历史记录(最新在前)
  - `outputs/results_YYYYMMDD.xlsx` — 按日期聚合的 Excel
- **图片放大灯箱**:单击任意缩略图全屏放大查看
- **配置持久化**:基于 Pydantic 管理全局配置,持久化到 `config.json`

## 技术栈

| 模块 | 技术选型 |
| --- | --- |
| GUI 框架 | PySide6 6.8.3 |
| API 客户端 | httpx |
| 配置管理 | Pydantic v2 |
| Excel 读写 | pandas + openpyxl |
| 图像处理 | Pillow |

## 目录结构

```
text2image_tool/
├── main.py                 # 程序入口
├── api_client.py           # 智谱图像生成 API 客户端 (glm-image)
├── config.py               # Pydantic 全局配置 + 提示词库
├── workers.py              # 单图生成 QThread 工作线程
├── batch_worker.py         # 批量任务 QRunnable + QThreadPool 调度
├── excel_io.py             # Excel 读写 (列名规范化、结果回填)
├── output_manager.py       # 本地归档 (图片/history.json/results.xlsx)
├── config.json             # 运行时配置 (含 API Key,需自行填写)
├── requirements.txt
├── ui/                     # 界面层
│   ├── main_window.py      # 主窗口 (左侧配置 + 右侧 Tab)
│   ├── config_panel.py     # 左侧配置面板
│   ├── manual_panel.py     # 手动生成面板 (流式布局)
│   ├── batch_panel.py      # 批量任务面板
│   ├── batch_item_widget.py# 批量列表单行控件
│   ├── history_panel.py    # 历史记录面板
│   ├── image_card.py       # 图片卡片
│   ├── zoom_overlay.py    # 灯箱放大覆盖层
│   ├── icons.py            # SVG 图标加载
│   └── styles.py           # 全局样式 (暗色主题)
├── icons/                  # 图标资源
├── ref/                    # 参考资源
└── outputs/                # 运行时输出 (自动生成)
```

## 快速开始

### 1. 环境准备

需要 Python 3.11+。建议使用虚拟环境:

```bash
python -m venv .venv
.venv\Scripts\activate     # Windows
# source .venv/bin/activate  # macOS/Linux
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置 API Key

首次启动后在左侧边栏填写智谱 AI 的 API Key,或直接编辑 `config.json`:

```json
{
  "api_key": "你的智谱 API Key",
  "api_url": "https://open.bigmodel.cn/api/paas/v4/images/generations",
  "size": "1280x1280",
  "quality": "hd",
  "watermark_enabled": false
}
```

API Key 申请:前往 [智谱开放平台](https://open.bigmodel.cn/) 注册并创建。

### 4. 启动应用

```bash
python main.py
```

## 使用指南

### 手动生成

1. 左侧配置 API Key、系统提示词、尺寸、质量、水印
2. 切到「手动生成」Tab,输入提示词
3. 点击生成,卡片以流式布局自动排列
4. 卡片支持:编辑重绘、重新生成、保存到本地、点击放大

### 批量任务

1. 准备 Excel 文件,**必填列**:`prompt`(或 `提示词`)
2. **可选列**:`size`/`尺寸`、`quality`/`质量`、`watermark`/`水印`、`system_prompt`/`系统提示词`
   - 可选列留空则回退到左侧全局配置
   - `watermark` 接受:`true/false/是/否/1/0`(大小写不敏感)
3. 切到「批量任务」Tab,导入 Excel,选择输出目录,调整并发数
4. 点击开始,实时查看每行状态与缩略图
5. 完成后勾选需要导出的行,点击「导出勾选」,生成 `{原文件名}_结果.xlsx`
   - 追加列:`image_path`、`status`、`error`、`generated_at`

### 历史记录

- 所有生成(手动 + 批量)自动归档到 `outputs/`
- 历史卡片支持:点击放大、回填提示词到手动生成、清空历史

## 可选尺寸

| 尺寸 | 说明 |
| --- | --- |
| `1280x1280` | 默认方形 |
| `1568x1056` | 横向 |
| `1056x1568` | 纵向 |
| `1024x1024` | 方形 |
| `768x1024` | 纵向 |
| `1024x768` | 横向 |

质量选项:`hd` / `standard`

## 安全提示

- `config.json` 含 API Key,**切勿提交到公开仓库**
- 建议在 `.gitignore` 中加入:
  ```
  config.json
  outputs/
  __pycache__/
  *.pyc
  ```

## 许可证

本项目仅供学习交流使用。使用前请遵守智谱 AI 的服务条款。
