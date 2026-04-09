"""
数据库同步服务
"""
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional
from app.database import execute_query, execute_update, get_db_cursor
from app.config import settings
from app.schemas import TaskTypeEnum, TaskStatusEnum


class DatabaseSyncService:
    """数据库同步服务类"""

    # Excel列名映射
    COLUMN_MAPPING = {
        "C": "项目名称",
        "D": "工厂名称",
        "E": "项目目标",
        "F": "收益描述",
        "G": "OK图片描述",
        "H": "NG图片描述",
        "I": "应用场景简述",
        "J": "处理对象(输入)",
        "K": "核心功能",
        "L": "输出形式/接口",
    }

    def import_from_excel(self, excel_path: str, region: str = "nantong") -> int:
        """
        从Excel文件导入数据

        Args:
            excel_path: Excel文件路径
            region: 目标数据库区域

        Returns:
            导入的记录数
        """
        try:
            # 读取Excel文件
            df = pd.read_excel(excel_path, engine="openpyxl")

            # 筛选需要的列
            available_columns = [
                col for col in self.COLUMN_MAPPING.values() if col in df.columns
            ]
            df = df[available_columns]

            # 插入数据库
            count = 0
            with get_db_cursor(region) as cursor:
                for _, row in df.iterrows():
                    try:
                        # 构建插入语句
                        columns = []
                        values = []
                        for col_name, col_cn in self.COLUMN_MAPPING.items():
                            if col_cn in available_columns:
                                columns.append(col_cn)
                                value = row[col_cn] if pd.notna(row[col_cn]) else None
                                values.append(value)

                        if not columns:
                            continue

                        # 检查是否已存在（基于项目名称+工厂名称）
                        check_query = """
                        SELECT id FROM ai_projects
                        WHERE project_name = %s AND factory_name = %s
                        """
                        cursor.execute(
                            check_query,
                            (
                                row.get("项目名称"),
                                row.get("工厂名称"),
                            ),
                        )
                        existing = cursor.fetchone()

                        if existing:
                            # 更新现有记录
                            update_sql = f"""
                            UPDATE ai_projects SET
                                {", ".join([f"{col} = %s" for col in columns])},
                                sync_status = 'synced',
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                            """
                            cursor.execute(
                                update_sql,
                                tuple(values) + (existing["id"],),
                            )
                        else:
                            # 插入新记录
                            insert_sql = f"""
                            INSERT INTO ai_projects ({", ".join(columns)}, sync_status, source_region)
                            VALUES ({", ".join(["%s"] * len(columns))}, 'synced', %s)
                            """
                            cursor.execute(insert_sql, tuple(values) + (region,))

                        count += 1
                    except Exception as e:
                        print(f"导入行失败: {e}")
                        continue

            return count

        except Exception as e:
            raise Exception(f"Excel导入失败: {e}")

    def export_to_excel(self, output_path: str, region: str = "nantong") -> int:
        """
        导出数据到Excel

        Args:
            output_path: 输出文件路径
            region: 数据区域

        Returns:
            导出的记录数
        """
        try:
            # 查询所有项目
            query = "SELECT * FROM ai_projects WHERE source_region = %s"
            projects = execute_query(query, (region,), region)

            # 转换为DataFrame
            df = pd.DataFrame(projects)

            # 重命名列以显示中文
            reverse_mapping = {v: k for k, v in self.COLUMN_MAPPING.items()}
            df.rename(columns=reverse_mapping, inplace=True)

            # 保存到Excel
            df.to_excel(output_path, index=False, engine="openpyxl")

            return len(df)

        except Exception as e:
            raise Exception(f"Excel导出失败: {e}")

    def sync_between_databases(
        self, from_region: str, to_region: str
    ) -> int:
        """
        在两个数据库之间同步数据

        Args:
            from_region: 源区域
            to_region: 目标区域

        Returns:
            同步的记录数
        """
        try:
            # 从源数据库获取所有已同步的数据
            query = """
            SELECT * FROM ai_projects
            WHERE source_region = %s AND sync_status = 'synced'
            """
            source_data = execute_query(query, (from_region,), from_region)

            count = 0
            with get_db_cursor(to_region) as cursor:
                for row in source_data:
                    try:
                        # 检查目标数据库中是否存在
                        check_query = """
                        SELECT id FROM ai_projects
                        WHERE project_name = %s AND factory_name = %s AND source_region = %s
                        """
                        cursor.execute(
                            check_query,
                            (
                                row["project_name"],
                                row["factory_name"],
                                to_region,
                            ),
                        )
                        existing = cursor.fetchone()

                        if existing:
                            # 更新现有记录
                            update_sql = """
                            UPDATE ai_projects SET
                                project_goal = %s, benefit_desc = %s,
                                ok_image_desc = %s, ng_image_desc = %s,
                                application_scenario = %s, processing_object = %s,
                                core_functions = %s, output_interface = %s,
                                deployment_method = %s, sync_status = 'synced',
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                            """
                            cursor.execute(
                                update_sql,
                                (
                                    row.get("project_goal"),
                                    row.get("benefit_desc"),
                                    row.get("ok_image_desc"),
                                    row.get("ng_image_desc"),
                                    row.get("application_scenario"),
                                    row.get("processing_object"),
                                    row.get("core_functions"),
                                    row.get("output_interface"),
                                    row.get("deployment_method"),
                                    existing["id"],
                                ),
                            )
                        else:
                            # 插入新记录
                            insert_sql = """
                            INSERT INTO ai_projects (
                                project_name, factory_name, project_goal, benefit_desc,
                                ok_image_desc, ng_image_desc, application_scenario,
                                processing_object, core_functions, output_interface,
                                deployment_method, sync_status, source_region
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'synced', %s)
                            """
                            cursor.execute(
                                insert_sql,
                                (
                                    row["project_name"],
                                    row["factory_name"],
                                    row.get("project_goal"),
                                    row.get("benefit_desc"),
                                    row.get("ok_image_desc"),
                                    row.get("ng_image_desc"),
                                    row.get("application_scenario"),
                                    row.get("processing_object"),
                                    row.get("core_functions"),
                                    row.get("output_interface"),
                                    row.get("deployment_method"),
                                    to_region,
                                ),
                            )

                        count += 1
                    except Exception as e:
                        print(f"同步记录失败: {e}")
                        continue

            return count

        except Exception as e:
            raise Exception(f"数据库间同步失败: {e}")

    def create_task(self, task_type: str, source_file: str = None) -> int:
        """创建同步任务记录"""
        query = """
        INSERT INTO sync_tasks (task_type, status, total_count, processed_count, source_file)
        VALUES (%s, 'running', 0, 0, %s)
        """
        return execute_update(query, (task_type, source_file))

    def update_task(
        self,
        task_id: int,
        status: str,
        processed_count: int,
        error_message: str = None,
    ):
        """更新同步任务状态"""
        updates = ["status = %s", "processed_count = %s"]
        params = [status, processed_count]

        if error_message:
            updates.append("error_message = %s")
            params.append(error_message)

        if status in [TaskStatusEnum.completed.value, TaskStatusEnum.failed.value]:
            updates.append("completed_at = CURRENT_TIMESTAMP")

        params.append(task_id)
        query = f"UPDATE sync_tasks SET {', '.join(updates)} WHERE id = %s"
        execute_update(query, tuple(params))
