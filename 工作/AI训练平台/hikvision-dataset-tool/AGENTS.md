# Project Guidelines

海康 AI 开放平台标注数据集下载与 COCO 格式转换工具。详见 [CLAUDE.md](./CLAUDE.md)。

## Quick Commands

```bash
pip install -r requirements.txt    # 安装依赖
python main.py --gui                # GUI 模式（推荐）
python main.py --auto               # 自动模式（从浏览器页面读取数据集信息）
python main.py --dataset <id> --version <id> --token "<token>"   # 手动模式
python main.py --export-coco ./dataset_xxx_timestamp              # 导出 COCO
python main.py --export-hikvision ./dataset_xxx_timestamp          # 导出海康本地格式（简化版）
python main.py --export-hikvision-official ./dataset_xxx_timestamp # 导出海康官方完整格式
```

## Architecture

| 模块 | 职责 |
|------|------|
| `main.py` | CLI 入口，argparse 分发 |
| `core/auth.py` | Token/Cookie 管理，API 头构建 |
| `core/api_client.py` | Hikvision REST API 客户端 |
| `core/downloader.py` | 三阶段下载管线（列表→标注→并发下载），AES-ECB 解密 |
| `core/converter.py` | Hikvision JSON → COCO 格式（两遍转换） |
| `core/hikvision_format_converter.py` | Hikvision JSON → 海康本地平台 calibInfo 格式 |
| `browser/bb_browser_bridge.py` | Chrome DevTools Protocol，Cookie 获取 |
| `gui/main_window.py` | tkinter GUI |

下载输出结构：`dataset_{id}_{timestamp}/` → `images/` + `annotations/` → `--export-coco` → `COCO/` → `--export-hikvision` → `{output_dir}/` + `Result/` → `--export-hikvision-official` → `包含目标/Result/` + `不包含目标/`

## Key Conventions

- **Python 3.8+**，中文注释，UTF-8 编码
- 使用 `@dataclass` 定义核心数据结构（`ImageFile`, `Annotation`, `DownloadResult`, `ConversionResult`）
- 下载是幂等的：已存在的图片+标注会自动跳过
- `requirements.txt` 中 `aiohttp`、`aiofiles`、`PyYAML` 未被使用，实际 HTTP 用 `requests`
- `config.json` 存储 token 等密钥，已在 `.gitignore` 中

## Gotchas

- **无测试框架**。每个核心模块有内联 `if __name__ == "__main__"` 冒烟测试，须用真实海康凭证运行
- **Cookie 获取两层策略**：优先 `browser_cookie3.chrome()` 读本地 Chrome DB；失败则回退 WebSocket CDP
- **Chrome 111+** 自动模式下可能 WebSocket 403，需 `bb-browser --remote-allow-origins="*"`
- **AES-ECB 解密**：若 API 返回的 `ImageFile` 带 `key` 字段，下载后需 Base64 解码再 AES-ECB 解密
- **API 批限制**：标注查询每批最多 50 个 file_id；下载并发最多 5 线程
