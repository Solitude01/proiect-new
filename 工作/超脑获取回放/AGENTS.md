# AGENTS.md

## 项目概述

海康威视 NVR (网络硬盘录像机) 视频回放与 AI 事件查询工具集，服务于"超脑"(Deepmind) 工业 AI 视觉检测平台。

**4 条核心工作流：**
- **生成回放链接** → `获取回放链接.py`
- **Webhook 下载 MP4** → `视频下载脚本.py`
- **批量下载指定片段 (GUI)** → `batch_download_gui.py`
- **批量事件查询 / 压力测试 (GUI)** → `超脑批量请求/super_brain_query_tool.py`

## 技术栈

- **Python 3.8+** · `requests` (HTTP Digest Auth) · `tkinter` (GUI) · `concurrent.futures` (线程池)
- **外部 API**: 海康威视 ISAPI (Intelligent Security API)
- **打包**: PyInstaller (`.spec` → Windows `.exe`)

## 关键约定

### 命名规范
- 文件名：中文 + 下划线 (`获取回放链接.py`)
- 类名：PascalCase (`HikvisionPlaybackURL`)
- 函数/方法：snake_case (`get_rtsp_url`, `load_deepmind_map`)
- 私有方法：`_` 前缀 (`_format_time`, `_build_ui`)
- 通道后缀：`01` = 主码流, `02` = 子码流（如 `501` = 通道 5 主码流）
- 海康时间格式：`YYYYMMDDTHHMMSSZ`（如 `20260210T133205Z`）

### 代码模式
- 认证统一用 `requests.auth.HTTPDigestAuth`
- 文件下载先写 `.part` 临时文件，完整后用 `os.replace()` 原子化重命名为 `.mp4`
- `playbackURI` 作为外层 query 参数时，内部 `&` 必须编码为 `%26`
- 禁用环境代理：`session.trust_env = False`（避免内网 NVR 请求被系统 HTTP_PROXY 劫持）

### 设备配置
- 设备注册表：`Deepmind.json`（20 台超脑设备的 IP、密码、端口映射）
- 加载方式：`download_event.py` 中的 `load_deepmind_map()`

## ⚠️ 常见陷阱

1. **playbackURI 中的 `&` 未编码** → NVR 返回 400/Invalid Operation。内层 RTSP URL 的 `&` 必须写成 `%26`
2. **代理干扰** → 如系统设了 `HTTP_PROXY`，内网请求会走代理而失败。新版 `download_event.py` 已禁用，但旧脚本未处理
3. **大文件超时** → 视频可能 >100MB，超时设 180s+，旧脚本仅 30s
4. **多线程并发** → NVR 硬件有限，建议 1~3 线程
5. **通道号类型** → 部分代码用 `int` 部分用 `str`，构建 URL 时需一致
6. **时间毫秒截断** → Webhook 传入 `"2026-02-10 13:32:05.552"`，统一用 `split('.')[0]` 截断毫秒
7. **PyInstaller 打包后路径** → 打包版 GUI 需检测 `sys.frozen` 用 `sys.executable` 定位 `Deepmind.json`

## 运行命令

```bash
# 安装依赖
pip install requests

# 工作流 A — 生成回放链接
python 获取回放链接.py

# 工作流 B — Webhook 下载视频
python 视频下载脚本.py

# 工作流 B — 测试所有回放接口
python 测试所有接口.py

# 工作流 C — 批量下载 GUI
python batch_download_gui.py

# 工作流 D — 批量事件查询 GUI
python 超脑批量请求/super_brain_query_tool.py

# 工作流 D — 压力测试
python 超脑批量请求/batch_stress_test.py

# 打包 EXE
cd 批量下载指定视频片段 && pyinstaller 超脑回放视频批量下载.spec
```

## 文档索引

| 文档 | 路径 | 内容 |
|------|------|------|
| 海康 ISAPI 下载接口 | `接口文档.md` | 视频下载/RTSP 接口的完整说明 |
| 海康 ISAPI AIOP 接口 | `超脑批量请求/API_INTERFACE.md` | 通道列表 + AI 事件查询 API |
| 工具使用说明 | `超脑批量请求/README.md` | 批量查询工具的操作指南 |
| 业务需求 | `新需求.md` | LA 预警对接、AI 优化需求 |
| 外部 API 参考 | `参考.md` | 海康开放平台回放取流 URL 文档 |
| Postman 测试集 | `General_Function.postman_collection(v8998).json` | 接口测试集合 |

## 已知问题

- **大量代码重复**：`获取回放链接.py` = `获取视频链接脚本.py`；`视频下载脚本.py` = `测试脚本.py`；`download_event.py` 在根目录和 `批量下载指定视频片段/` 各有一份。修改功能需同步更新所有副本。
- **硬编码凭据**：多个脚本 `__main__` 中硬编码了测试 NVR IP 和密码。生产环境应从 `Deepmind.json` 加载。
- **无单元测试**：所有 `.py` 均以 `if __name__ == "__main__"` 手动测试，无 `pytest`/`unittest`。
