# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 项目概述

**视频帧提取工具 v6.0** — 基于 FFmpeg + tkinter 的桌面应用，将视频文件按指定张数切分为图片帧。

- **单文件架构**：核心代码 `video_frame_extractor.py`（约 2900 行），包含所有业务逻辑和 UI
- **Python 3.8+**，Windows 平台，使用 `ttkbootstrap` 主题化 tkinter
- **必须依赖**：`ffmpeg.exe` 和 `ffprobe.exe` 需放在项目根目录（打包时嵌入）

## 三种切分模式

| 模式 | 入口方法 | 说明 |
|------|----------|------|
| 单视频 | `start_single_video()` → `_process_single_video()` | 处理单个视频文件 |
| 单目录 | `start_single_directory()` → `_process_directory()` / `_process_directory_separate()` | 批量处理目录内所有视频 |
| 多目录并发 | `start_multi_directory()` → `BatchProcessor` | 同时处理多个目录，支持并发 |

## 核心架构

```
Config              # 配置管理（JSON持久化）
VideoInfo           # 视频信息数据类
ExtractConfig       # 切分配置数据类
TaskItem            # 任务项数据类
FFmpegFrameExtractor # FFmpeg封装：探测视频信息、扫描文件、提取帧
BatchProcessor      # 多线程批处理器（ThreadPoolExecutor）
VideoFrameExtractorApp # 主应用类（tkinter UI + 事件循环）
```

## 常用命令

```bash
# 直接运行
python video_frame_extractor.py

# 打包为可执行文件（需要 ffmpeg.exe + ffprobe.exe 在根目录）
build.bat
# 或
python build.py
```

## 依赖安装

```bash
pip install ttkbootstrap opencv-python
# 打包时额外需要
pip install pyinstaller
```

## 已知问题（待修复）

详见 `optimization_plan.md`，包含 12 项问题：
- **严重级**：多目录模式消息队列窃取、线程池泄漏、`stop_event` 未重置、单视频异常未捕获、单目录索引错位
- **中优先级**：闭包变量捕获、多选删除、空双击崩溃、`os.startfile` 路径错误、控件存在性检查、trace 累加、快捷按钮禁用不全

## 配置与持久化

- `config.json`：窗口大小、上次模式、输出格式、线程数等用户偏好
- 输出文件命名格式：`月日时分_三位随机数_四位递增数_宽_高.格式`

## 注意事项

- 使用中文变量名和中文日志消息
- UI 切换模式时调用 `clear_content()` 销毁旧控件，回调中操作控件前需检查 `winfo_exists()`
- 多线程与 UI 交互通过 `queue.Queue` + `root.after()` 轮询实现
- `stop_event`（`threading.Event`）用于取消操作，每次开始新任务前需 `.clear()`
