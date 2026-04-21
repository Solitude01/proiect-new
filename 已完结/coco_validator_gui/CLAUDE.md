# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

COCO Validator GUI 是一个桌面应用程序，用于验证 COCO 格式的 JSON 标注文件是否符合官方标准。提供图形界面，支持多文件验证、多线程处理、跨目录重复检测、JSON与图片对应检查、一键修复去重、日志导出和展开查看。

## 运行方式

```bash
python coco_validator_gui.py
```

- **无外部依赖** — 仅使用 Python 标准库（tkinter, json, concurrent.futures, hashlib, shutil）
- **Python 3.6+**

## 代码架构

单文件应用 `coco_validator_gui.py`，核心类 `COCOValidatorGUI`：

### 主要模块

1. **GUI 布局** — 三栏设计：
   - 左侧：17+4 个可勾选验证项（17 项单文件检查 + 4 项跨文件/跨目录检查）
   - 中间：文件列表、目录结构显示、错误统计
   - 右侧：操作按钮（开始核查、清空结果、导出日志、修复去重）、进度条、详细结果（含展开日志按钮）

2. **单文件验证** — `validate_coco_file()` 执行 17 项检查：
   - JSON 格式、顶级键、ID 唯一性、必需键、bbox 边界、segmentation 格式等

3. **跨目录/跨文件检查** — 自动执行：
   - `check_cross_dir_duplicate_images()` — 检测不同目录中重复的图片文件名
   - `check_cross_dir_duplicate_annotations()` — 使用 MD5 哈希检测跨目录重复标注
   - `check_cross_json_duplicate_annotations()` — 检测不同 JSON 文件间的重复标注
   - `check_json_image_mismatch()` — 严格按 COCO 标准结构检测 JSON 标注与图片是否一一对应

4. **一键修复** — `_execute_fix()`：
   - 图片去重：对重复图片的 `file_name` 添加目录前缀
   - 标注去重：移除重复标注，重新编号 annotation ID
   - 自动备份原始文件

5. **日志导出** — `export_log()`：导出核查报告为文本文件

6. **展开日志** — `show_full_log()`：弹出新窗口显示完整日志

### 默认配置

- 多线程：**默认启用**
- 目录模式：**默认启用**
- 所有验证项：**默认全部勾选**

### 关键数据结构

```python
self.directory_structure  # {subdir_name: [json_paths]}  目录模式下的文件分组
self.validation_stats     # {file_path: {"total_errors": int, "error_types": {type: count}}}
self.cross_dir_results    # {
                          #   "duplicate_images": {img_name: [dirs]},
                          #   "duplicate_annotations": {hash: [dirs]},
                          #   "duplicate_json_annotations": {hash: [json_files]},
                          #   "json_image_mismatch": {coco_root: {"json_only": [...], "file_only": [...], ...}}
                          # }
self._listbox_file_indices  # [file_path, ...]  listbox中文件项的路径映射（用于目录模式）
```

### 目录扫描

`_scan_directory_structure()` 使用 `rglob("*.json")` 递归扫描所有子目录中的 JSON 文件，按相对路径分组。支持嵌套的 COCO 格式目录结构。

### 跨目录检查逻辑

`_run_cross_dir_checks()` 会自动检测运行模式：
- **有目录结构**：使用 `self.directory_structure` 进行分组检查
- **无目录结构**：自动将 `self.selected_files` 按父目录名分组后执行相同检查
- 如果所有文件都在同一目录，跳过跨目录检查

### JSON与图片对应检查

`check_json_image_mismatch()` 严格按 COCO 标准结构工作：
- 检测 JSON 文件是否在 `annotations/` 目录中
- 如果是，在**同级的 `images/` 目录**中搜索图片文件
- 每个 `annotations/` 目录独立对比，不同 COCO 目录的图片不混淆

### 添加新验证项

1. 在 `validation_checks` 字典中添加新条目（`tk.BooleanVar`）
2. 单文件检查：在 `validate_coco_file()` 中实现
3. 跨目录/跨文件检查：实现对应 `check_xxx()` 方法，并在 `_run_cross_dir_checks()` 中调用

## 无构建/测试系统

这是单文件 GUI 工具，没有构建流程、单元测试或 CI 配置。
