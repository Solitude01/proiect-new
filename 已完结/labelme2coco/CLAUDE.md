# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Labelme 到 COCO 格式转换器，带 Material Design 风格 GUI（tkinter）。将 Labelme JSON 标注转换为 COCO 数据集格式，支持多文件夹合并、数据集自动切分、数据质量检查和标签管理。

## 关键命令

```bash
# 启动 GUI 程序
python label2coco2.7.py

# 安装依赖
pip install -r requirements.txt

# 打包为 Windows 可执行文件
build.bat
```

## 核心架构

`label2coco2.7.py`（单文件 ~7700 行）包含四层：

1. **`SimpleLabelme2COCO`**（第30行）— 核心转换引擎。将 Labelme JSON 转为 COCO `images`/`categories`/`annotations` 格式，支持多边形和矩形标注，处理 bbox 计算和坐标归一化。

2. **`DatasetSplitter`**（第115行）— 简单数据集切分器，按 train/test/verify 比例对单文件列表随机打乱后分割。

3. **`MultiFolderDatasetSplitter`**（第169行）— 多文件夹数据集切分器，对每个文件夹独立切分后合并，支持大文件夹自动拆子文件夹（`max_images_per_folder`，默认 2000）。

4. **`MaterialDesignGUI`**（第332行）— 主 GUI 类。tkinter 实现，包含 Material Design 3 配色。管理：
   - 文件夹导入与扫描
   - 标签映射编辑（重命名/删除/正则替换/前缀后缀）
   - 数据质量检查（9 类：缺图、缺 JSON、JSON 损坏、空标注、标注越界、无效多边形、无效矩形、空标签名、面积为 0）
   - 转换与数据集切分配置
   - 多线程转换（`threading.Thread` + `tqdm`）

`main()` 函数（第7670行）创建 `MaterialDesignGUI` 实例并启动 tkinter 主循环。

## 输出结构

转换后在输出目录生成 `train/`、`test/`、`verify/` 子目录，每个含 `images/` 和 `annotations/instance_*.json`，以及 `label_mapping.txt`、`folder_split_info.txt`、`subset_split_info.txt`。

## 跨平台注意

- tkinter 在 Windows 上内置于标准库；Linux 下可能需要 `python3-tk`
- 代码有 GBK/UTF-8 多编码兼容处理，适配不同系统生成的 Labelme JSON 文件
- `resource_path()` 函数处理 PyInstaller 打包后的资源路径
