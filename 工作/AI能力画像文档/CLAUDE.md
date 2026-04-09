# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是"AI能力画像文档"项目，核心功能是将Excel格式的AI项目数据转换为JSON/JSONL/TXT格式，用于AI模型训练或知识库构建。

## 项目结构

```
工作/AI能力画像文档/
├── excel-2-json-jsonl.py       # GUI转换器：支持JSON/JSONL格式输出
├── excel-2-json-txt.py          # GUI转换器：支持JSON/TXT格式输出
├── excel-2-json-txt copy.py     # GUI转换器（增强版）：支持扫描列名/手动指定列
├── excel to json.py             # 简单脚本：固定C:L列转换
├── Excel表格数据同步脚本.py      # 同步Excel两个Sheet的数据
├── 转换标准格式.py               # 将JSON数据转为KV文本格式并按50条拆分
├── 调用API.md                   # 内部API端点配置
├── 数据库.md                     # MySQL数据库连接信息
└── 修正应用prompt.md             # AI文档整理的prompt模板
```

## 数据格式

Excel表格包含10列（C-L列）：
| 列 | 字段名 |
|---|---|
| C | 项目名称 |
| D | 工厂名称 |
| E | 项目目标 |
| F | 收益描述 |
| G | OK图片描述 |
| H | NG图片描述 |
| I | 应用场景简述 |
| J | 处理对象(输入) |
| K | 核心功能 |
| L | 输出形式/接口 |

## 常用命令

```bash
# 运行GUI转换工具（任选其一）
python "excel-2-json-jsonl.py"
python "excel-2-json-txt.py"
python "excel-2-json-txt copy.py"

# 简单脚本转换（固定路径）
python "excel to json.py"

# 数据同步
python "Excel表格数据同步脚本.py"

# 格式转换与拆分
python "转换标准格式.py"
```

## 依赖

- `pandas` - Excel读取
- `openpyxl` - Excel引擎
- `tkinter` - GUI（Python内置）

## 注意事项

- 数据库连接信息在 `数据库.md` 中（南通/无锡两个MySQL实例）
- API配置在 `调用API.md` 中（DeepSeek-R1、Qwen3-8B）
- 所有脚本均为内部工具，路径多为硬编码，修改时注意检查路径字符串
