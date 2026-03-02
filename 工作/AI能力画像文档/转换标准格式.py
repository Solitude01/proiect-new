# -*- coding: utf-8 -*-
"""
读取 D:\proiect\工作\AI能力画像文档\AI能力画像文档.json
将每条记录转为 1 条 {"type": "text", "content": "键：值\n..."}
输出到同目录下的多个文件夹中，按每 1000 条数据切分
"""

import json
import os
from pprint import pprint

# ====================== 文件路径 ======================
INPUT_PATH = r"D:\proiect\工作\AI能力画像文档\AI能力画像文档.json"
OUTPUT_DIR = r"D:\proiect\工作\AI能力画像文档\处理后拆分"  # 输出文件夹目录
CHUNK_SIZE = 50  # 每个文件夹最多存放多少条数据

# ====================== 检查文件是否存在 ======================
if not os.path.exists(INPUT_PATH):
    raise FileNotFoundError(f"未找到输入文件：{INPUT_PATH}")

# ====================== 创建输出主目录 ======================
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)
    print(f"已创建输出目录：{OUTPUT_DIR}")

# ====================== 读取原始 JSON ======================
print(f"正在读取：{INPUT_PATH}")
with open(INPUT_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

# 确保是 list[dict]
if not isinstance(data, list):
    raise ValueError("JSON 根节点必须是数组（list），例如：[ {...}, {...} ]")

print(f"共加载 {len(data)} 条记录")

# ====================== 转换函数：键值对格式 ======================
def record_to_kv_text(record: dict) -> str:
    """将单条记录的键值对转换为文本格式"""
    lines = []
    for key, value in record.items():
        if value is None:
            value = ""
        value = str(value).strip()
        # 统一分隔符，提升可读性
        value = value.replace("；", "。").replace(";", "。")
        lines.append(f"{key}：{value}")
    return "\n".join(lines)

# ====================== 主转换逻辑 ======================
result = []
for idx, rec in enumerate(data, start=1):
    if not isinstance(rec, dict):
        print(f"警告：第 {idx} 条记录不是字典，已跳过")
        continue
    content = record_to_kv_text(rec)
    result.append({
        "type": "text",
        "content": content
    })
    print(f"已处理第 {idx} 条")

# ====================== 按块拆分数据并输出 ======================
total_records = len(result)
chunk_count = (total_records + CHUNK_SIZE - 1) // CHUNK_SIZE  # 计算需要的文件夹数

print(f"\n开始拆分输出，每 {CHUNK_SIZE} 条为一个文件夹，共需 {chunk_count} 个文件夹")

for i in range(chunk_count):
    start = i * CHUNK_SIZE
    end = min(start + CHUNK_SIZE, total_records)
    chunk = result[start:end]
    folder_name = os.path.join(OUTPUT_DIR, f"chunk_{i + 1:03d}")
    os.makedirs(folder_name, exist_ok=True)
    chunk_path = os.path.join(folder_name, f"AI能力画像文档_处理后_{i + 1:03d}.json")
    with open(chunk_path, "w", encoding="utf-8") as f:
        json.dump(chunk, f, ensure_ascii=False, indent=2)
    print(f"已生成文件：{chunk_path}（包含 {len(chunk)} 条记录）")

print(f"\n全部拆分完成，共生成 {chunk_count} 个文件夹。")

# ====================== 打印前3条预览 ======================
print("\n=== 输出预览（前3条） ===")
pprint(result[:3])
