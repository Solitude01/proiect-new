# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

COCO 标注本地查看/预览工具 — 使用 FiftyOne + tkinter 加载 COCO 格式的目标检测标注数据集，并在浏览器中交互式浏览。

## 运行方式

```bash
# GUI 版本（推荐）
python view_coco.py

# CLI 版本（需手动修改硬编码路径）
python load_coco_fiftyone.py
```

依赖（fiftyone、pycocotools）在首次运行时自动检测并提示安装，也可手动安装：
```bash
pip install fiftyone pycocotools
```

## 项目结构

- `view_coco.py` — 主程序，tkinter GUI，665 行。含自动依赖安装、FiftyOne 数据集加载、交互式浏览器启动
- `load_coco_fiftyone.py` — 简化版 CLI 脚本，硬编码路径，适合测试
- `aa/annotations/` — 单张样本图片的 COCO 标注 JSON
- `aa/images/` — 样本图片 (2560x1440)

## 核心架构

**view_coco.py 主要组件：**

| 类/函数 | 行号 | 职责 |
|---|---|---|
| `check_and_install()` | 25 | 自动检测缺失依赖并 pip 安装 |
| `CocoViewerApp.__init__()` | 61 | 创建主窗口，初始化 UI 控件 |
| `_build_ui()` | 76 | 构建 tkinter 布局（路径选择、高级选项、日志面板） |
| `_load_dataset()` | 345 | 验证路径、解析 JSON、启动后台加载线程 |
| `_do_load()` | 451 | 后台线程：FiftyOne 加载、缩略图生成、编码兼容处理 |
| `_on_loaded()` / `_on_error()` | 612/618 | 加载完成/失败后的 UI 回调 |
| `_open_browser()` / `_do_launch()` | 623/633 | 启动 FiftyOne App 并打开浏览器 |

## Windows 特有注意事项

- **GBK 编码兼容**: `_make_gbk_safe_copy()` 将含中文的 JSON 转为 ASCII-safe 的临时文件，避免 eta 库解码失败
- **MongoDB 端口清理**: FiftyOne 依赖 MongoDB，若端口被占用自动执行 `taskkill /f /im mongod.exe`
- **Python 环境**: 项目使用 `D:/proiect/.venv/Scripts/python.exe`

## 关键配置

启动时可配置的参数（UI 高级选项）：
- 数据集名称、Web 端口（默认 5151）
- 日志级别（简要/详细/调试）
- 样本上限（0=不限制）、随机抽样（seed=42）
- 缩略图模式（省内存但加载慢）
- 网格缩放级别（1-10）

## 样本数据

`aa/` 下提供 N10 板件缺陷检测的样本数据（1 张图片 + 对应 JSON），可用于快速验证工具功能。
