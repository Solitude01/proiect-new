#!/usr/bin/env python3
"""
AI项目数据导入脚本 v3
- 修复中文乱码（DROP 重建表）
- 修复日期时间格式
- 支持提取 WPS/Excel 嵌入图片

使用方法:
    python import_excel.py your_file.xlsx
"""

import sys
import os
import uuid
import pandas as pd
import pymysql
from datetime import datetime
from openpyxl import load_workbook

# ==================
# 数据库配置
# ==================
DB_CONFIG = {
    'host': '10.30.43.199',
    'port': 3306,
    'user': 'aiprojects',
    'password': 'user_password',
    'database': 'ai_projects',
    'charset': 'utf8mb4',
    'use_unicode': True,
}

# 图片保存到本地，之后手动复制到 NAS
IMAGE_LOCAL_DIR = r"D:\proiect\工作\已上线运行的AI项目明细\images"


def safe_str(value):
    if pd.isna(value):
        return None
    s = str(value).strip()
    return s if s else None


def safe_float(value):
    if pd.isna(value):
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def safe_date(value):
    if pd.isna(value):
        return None
    # pandas Timestamp
    if hasattr(value, 'date'):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, str):
        value = value.strip()
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d %H:%M:%S', '%Y/%m/%d', '%Y.%m.%d']:
            try:
                return datetime.strptime(value, fmt).strftime('%Y-%m-%d')
            except ValueError:
                continue
    return None


def extract_images_from_excel(filepath):
    """从 Excel 提取嵌入图片，返回 {行号: 图片文件名}"""
    print("正在提取 Excel 中的图片...")

    save_dir = IMAGE_LOCAL_DIR
    os.makedirs(save_dir, exist_ok=True)

    wb = load_workbook(filepath)
    ws = wb.active

    image_map = {}

    for image in ws._images:
        try:
            anchor = image.anchor
            if hasattr(anchor, '_from'):
                row = anchor._from.row  # 0-indexed
            elif hasattr(anchor, 'row'):
                row = anchor.row
            else:
                continue

            filename = f"project_{row}_{uuid.uuid4().hex[:8]}.png"
            filepath_save = os.path.join(save_dir, filename)

            img_data = image._data()
            with open(filepath_save, 'wb') as f:
                f.write(img_data)

            # 同一行多张图片只保留最后一张
            image_map[row] = filename

        except Exception as e:
            print(f"  提取图片失败: {e}")

    print(f"共提取 {len(image_map)} 张图片到 {save_dir}")
    return image_map


def import_excel(filepath):
    """导入 Excel 数据到数据库"""

    print(f"正在读取文件: {filepath}")

    # 提取图片
    image_map = extract_images_from_excel(filepath)

    # 读取数据
    df = pd.read_excel(filepath)
    print(f"读取到 {len(df)} 行数据")
    print(f"Excel 列名: {list(df.columns)}")

    # 打印第一行数据帮助确认
    if len(df) > 0:
        print(f"第一行数据预览:")
        for i, col in enumerate(df.columns):
            val = df.iloc[0, i]
            print(f"  [{i}] {col}: {val}")

    # 连接数据库
    print(f"\n连接数据库: {DB_CONFIG['host']}:{DB_CONFIG['port']}")
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    cursor.execute("SET NAMES utf8mb4")

    try:
        # 删除旧表并重建（解决字符集问题）
        print("删除旧表并重建...")
        cursor.execute("DROP TABLE IF EXISTS projects")
        cursor.execute("""
        CREATE TABLE projects (
            id INT AUTO_INCREMENT PRIMARY KEY,
            project_name VARCHAR(255) NOT NULL,
            project_goal TEXT,
            benefit_desc TEXT,
            money_benefit DECIMAL(10,2) DEFAULT 0,
            time_saved DECIMAL(10,2) DEFAULT 0,
            factory_name VARCHAR(100),
            applicant VARCHAR(100),
            create_time DATE,
            submit_time DATE,
            developer VARCHAR(100),
            audit_time DATE,
            online_time DATE,
            cancel_time DATE,
            status VARCHAR(50),
            alarm_image VARCHAR(500),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        conn.commit()
        print("表已重建")

        # 插入数据
        insert_sql = """
        INSERT INTO projects
        (project_name, factory_name, project_goal, benefit_desc,
         money_benefit, time_saved, applicant, create_time, submit_time,
         developer, audit_time, online_time, cancel_time, status, alarm_image)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        imported = 0
        skipped = 0

        for idx, row in df.iterrows():
            # 跳过空行
            first_val = row.iloc[0]
            if pd.isna(first_val) or str(first_val).strip() == '':
                skipped += 1
                continue

            # 图片映射：idx 是 dataframe 行号(0-based)，图片 row 是 Excel 行号(0-based，含标题行)
            # 所以图片的 row = idx + 1 (因为第0行是标题)
            image_filename = image_map.get(idx + 1)

            project_name = safe_str(row.iloc[0])
            factory_name = safe_str(row.iloc[1]) if len(row) > 1 else None
            project_goal = safe_str(row.iloc[2]) if len(row) > 2 else None
            benefit_desc = safe_str(row.iloc[3]) if len(row) > 3 else None
            money_benefit = safe_float(row.iloc[4]) if len(row) > 4 else 0
            time_saved = safe_float(row.iloc[5]) if len(row) > 5 else 0
            applicant = safe_str(row.iloc[6]) if len(row) > 6 else None
            create_time = safe_date(row.iloc[7]) if len(row) > 7 else None
            submit_time = safe_date(row.iloc[8]) if len(row) > 8 else None
            developer = safe_str(row.iloc[9]) if len(row) > 9 else None
            audit_time = safe_date(row.iloc[10]) if len(row) > 10 else None
            online_time = safe_date(row.iloc[11]) if len(row) > 11 else None
            cancel_time = safe_date(row.iloc[12]) if len(row) > 12 else None
            status = safe_str(row.iloc[13]) if len(row) > 13 else None

            data = (
                project_name, factory_name, project_goal, benefit_desc,
                money_benefit, time_saved, applicant, create_time, submit_time,
                developer, audit_time, online_time, cancel_time, status,
                image_filename
            )

            cursor.execute(insert_sql, data)
            imported += 1

        conn.commit()

        # 验证数据
        cursor.execute("SELECT id, project_name, applicant, developer, status FROM projects LIMIT 3")
        rows = cursor.fetchall()
        print(f"\n验证数据（前3条）:")
        for r in rows:
            print(f"  id={r[0]}, 项目={r[1]}, 申请人={r[2]}, 开发人={r[3]}, 状态={r[4]}")

        cursor.execute("SELECT COUNT(*) FROM projects WHERE alarm_image IS NOT NULL")
        img_count = cursor.fetchone()[0]

        print(f"\n导入完成！")
        print(f"  - 成功导入: {imported} 条")
        print(f"  - 跳过空行: {skipped} 条")
        print(f"  - 有图片的: {img_count} 条")

        if image_map:
            print(f"\n图片已保存到: {IMAGE_LOCAL_DIR}")
            print(f"请将图片复制到 NAS: /vol1/1000/webdemo/uploads/images/")

    except Exception as e:
        conn.rollback()
        print(f"导入失败: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        cursor.close()
        conn.close()


def main():
    if len(sys.argv) < 2:
        print("用法: python import_excel.py <Excel文件路径>")
        print("示例: python import_excel.py AI项目明细.xlsx")
        sys.exit(1)

    filepath = sys.argv[1]
    import_excel(filepath)


if __name__ == '__main__':
    main()
