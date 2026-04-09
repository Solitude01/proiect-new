"""
数据库同步脚本
功能：
1. 从Excel文件导入数据到数据库
2. 从数据库导出数据到Excel
3. 双数据库同步
4. 定时自动同步
"""

import pandas as pd
import pymysql
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging
from db_config import get_all_database_configs, get_database_config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseSync:
    """数据库同步服务"""

    # Excel列名映射
    COLUMN_MAPPING = {
        'C': '项目名称',
        'D': '工厂名称',
        'E': '项目目标',
        'F': '收益描述',
        'G': 'OK图片描述',
        'H': 'NG图片描述',
        'I': '应用场景简述',
        'J': '处理对象(输入)',
        'K': '核心功能',
        'L': '输出形式/接口'
    }

    # 数据库字段映射
    DB_COLUMNS = [
        'project_name', 'factory_name', 'project_goal', 'benefit_desc',
        'ok_image_desc', 'ng_image_desc', 'application_scenario',
        'processing_object', 'core_functions', 'output_interface'
    ]

    def __init__(self, region: str = 'nantong'):
        """初始化数据库连接"""
        self.region = region
        self.config = get_database_config(region)
        self.connection = None

    def connect(self) -> pymysql.Connection:
        """建立数据库连接"""
        try:
            self.connection = pymysql.connect(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                database=self.config.database,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            logger.info(f"成功连接到 {self.region} 数据库")
            return self.connection
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            raise

    def disconnect(self):
        """断开数据库连接"""
        if self.connection:
            self.connection.close()
            logger.info(f"已断开 {self.region} 数据库连接")

    def create_tables(self):
        """创建数据库表结构"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS ai_projects (
            id INT PRIMARY KEY AUTO_INCREMENT,
            project_name VARCHAR(255) NOT NULL COMMENT '项目名称',
            factory_name VARCHAR(100) COMMENT '工厂名称',
            project_goal TEXT COMMENT '项目目标',
            benefit_desc TEXT COMMENT '收益描述',
            ok_image_desc TEXT COMMENT 'OK图片描述',
            ng_image_desc TEXT COMMENT 'NG图片描述',
            application_scenario TEXT COMMENT '应用场景简述',
            processing_object TEXT COMMENT '处理对象(输入)',
            core_functions JSON COMMENT '核心功能',
            output_interface TEXT COMMENT '输出形式/接口',
            deployment_method TEXT COMMENT '部署方式',
            sync_status ENUM('pending','synced','failed') DEFAULT 'pending' COMMENT '同步状态',
            source_region VARCHAR(50) DEFAULT 'nantong' COMMENT '数据来源区域',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            INDEX idx_project_name (project_name),
            INDEX idx_factory (factory_name),
            INDEX idx_sync_status (sync_status),
            INDEX idx_created (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI项目数据表';

        CREATE TABLE IF NOT EXISTS sync_tasks (
            id INT PRIMARY KEY AUTO_INCREMENT,
            task_type ENUM('excel_import','ai_analyze','db_sync','export_excel') NOT NULL COMMENT '任务类型',
            status ENUM('pending','running','completed','failed') DEFAULT 'pending' COMMENT '任务状态',
            total_count INT DEFAULT 0 COMMENT '总数量',
            processed_count INT DEFAULT 0 COMMENT '已处理数量',
            error_message TEXT COMMENT '错误信息',
            source_file VARCHAR(500) COMMENT '源文件路径',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            completed_at TIMESTAMP NULL COMMENT '完成时间',
            INDEX idx_status (status),
            INDEX idx_created (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='同步任务表';

        CREATE TABLE IF NOT EXISTS sync_logs (
            id INT PRIMARY KEY AUTO_INCREMENT,
            task_id INT COMMENT '关联的sync_tasks.id',
            log_level ENUM('info','warning','error') DEFAULT 'info' COMMENT '日志级别',
            message TEXT COMMENT '日志消息',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            INDEX idx_task (task_id),
            INDEX idx_created (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='同步日志表';
        """

        try:
            with self.connection.cursor() as cursor:
                for statement in create_table_sql.split(';'):
                    if statement.strip():
                        cursor.execute(statement)
            self.connection.commit()
            logger.info("数据库表结构创建成功")
        except Exception as e:
            logger.error(f"创建表结构失败: {e}")
            raise

    def import_from_excel(self, excel_path: str, selected_columns: List[str] = None) -> int:
        """
        从Excel文件导入数据

        Args:
            excel_path: Excel文件路径
            selected_columns: 选中的列名列表，如果为None则使用所有列

        Returns:
            导入的记录数
        """
        try:
            # 读取Excel文件
            df = pd.read_excel(excel_path, engine='openpyxl')

            # 如果没有指定列，使用默认映射
            if selected_columns is None:
                selected_columns = list(self.COLUMN_MAPPING.values())

            # 筛选需要的列
            available_columns = [col for col in selected_columns if col in df.columns]
            df = df[available_columns]

            # 重命名列以匹配数据库字段
            column_rename = {v: k for k, v in self.COLUMN_MAPPING.items() if v in available_columns}
            df.rename(columns=column_rename, inplace=True)

            # 插入数据库
            count = 0
            with self.connection.cursor() as cursor:
                for _, row in df.iterrows():
                    try:
                        # 构建INSERT语句
                        columns = []
                        values = []
                        for col_name, col_db in self.COLUMN_MAPPING.items():
                            if col_db in available_columns:
                                columns.append(col_db)
                                value = row[col_db] if pd.notna(row[col_db]) else None
                                values.append(value)

                        if not columns:
                            continue

                        sql = f"""
                        INSERT INTO ai_projects ({', '.join(columns)}, source_region, sync_status)
                        VALUES ({', '.join(['%s'] * len(columns))}, %s, 'synced')
                        """
                        cursor.execute(sql, values + [self.region])
                        count += 1
                    except Exception as e:
                        logger.warning(f"插入行失败: {e}")
                        continue

            self.connection.commit()
            logger.info(f"从Excel导入 {count} 条记录到 {self.region} 数据库")
            return count

        except Exception as e:
            logger.error(f"从Excel导入失败: {e}")
            raise

    def export_to_excel(self, output_path: str, conditions: Dict = None) -> int:
        """
        导出数据到Excel

        Args:
            output_path: 输出Excel文件路径
            conditions: 查询条件

        Returns:
            导出的记录数
        """
        try:
            # 构建查询
            sql = "SELECT * FROM ai_projects WHERE 1=1"
            params = []

            if conditions:
                for key, value in conditions.items():
                    sql += f" AND {key} = %s"
                    params.append(value)

            df = pd.read_sql(sql, self.connection, params=params)

            # 重命名列以显示中文
            reverse_mapping = {k: v for k, v in self.COLUMN_MAPPING.items()}
            df.rename(columns=reverse_mapping, inplace=True)

            # 保存到Excel
            df.to_excel(output_path, index=False, engine='openpyxl')

            count = len(df)
            logger.info(f"导出 {count} 条记录到Excel: {output_path}")
            return count

        except Exception as e:
            logger.error(f"导出到Excel失败: {e}")
            raise

    def sync_between_databases(self, target_region: str = 'wuxi') -> int:
        """
        在两个数据库之间同步数据

        Args:
            target_region: 目标区域

        Returns:
            同步的记录数
        """
        try:
            # 获取目标数据库配置
            target_config = get_database_config(target_region)
            target_connection = pymysql.connect(
                host=target_config.host,
                port=target_config.port,
                user=target_config.user,
                password=target_config.password,
                database=target_config.database,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )

            # 从源数据库获取所有数据
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM ai_projects WHERE sync_status = 'synced'")
                source_data = cursor.fetchall()

            count = 0
            with target_connection.cursor() as target_cursor:
                for row in source_data:
                    try:
                        # 检查是否已存在
                        target_cursor.execute(
                            "SELECT id FROM ai_projects WHERE project_name = %s AND factory_name = %s",
                            (row['project_name'], row['factory_name'])
                        )
                        existing = target_cursor.fetchone()

                        if existing:
                            # 更新现有记录
                            update_sql = """
                            UPDATE ai_projects SET
                                project_goal=%s, benefit_desc=%s, ok_image_desc=%s, ng_image_desc=%s,
                                application_scenario=%s, processing_object=%s, core_functions=%s,
                                output_interface=%s, deployment_method=%s, sync_status='synced',
                                updated_at=CURRENT_TIMESTAMP
                            WHERE id=%s
                            """
                            target_cursor.execute(update_sql, (
                                row['project_goal'], row['benefit_desc'], row['ok_image_desc'],
                                row['ng_image_desc'], row['application_scenario'], row['processing_object'],
                                row['core_functions'], row['output_interface'], row.get('deployment_method'),
                                existing['id']
                            ))
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
                            target_cursor.execute(insert_sql, (
                                row['project_name'], row['factory_name'], row['project_goal'],
                                row['benefit_desc'], row['ok_image_desc'], row['ng_image_desc'],
                                row['application_scenario'], row['processing_object'], row['core_functions'],
                                row['output_interface'], row.get('deployment_method'), target_region
                            ))

                        count += 1
                    except Exception as e:
                        logger.warning(f"同步记录失败: {e}")
                        continue

            target_connection.commit()
            target_connection.close()
            logger.info(f"同步 {count} 条记录到 {target_region} 数据库")
            return count

        except Exception as e:
            logger.error(f"数据库间同步失败: {e}")
            raise

    def get_projects(self, limit: int = 100, offset: int = 0,
                     factory: str = None, status: str = None) -> Tuple[List[Dict], int]:
        """
        获取项目列表

        Returns:
            (项目列表, 总数)
        """
        try:
            with self.connection.cursor() as cursor:
                # 计数查询
                count_sql = "SELECT COUNT(*) as total FROM ai_projects WHERE 1=1"
                count_params = []

                if factory:
                    count_sql += " AND factory_name = %s"
                    count_params.append(factory)
                if status:
                    count_sql += " AND sync_status = %s"
                    count_params.append(status)

                cursor.execute(count_sql, count_params)
                total = cursor.fetchone()['total']

                # 数据查询
                data_sql = """
                SELECT * FROM ai_projects WHERE 1=1
                """
                params = []

                if factory:
                    data_sql += " AND factory_name = %s"
                    params.append(factory)
                if status:
                    data_sql += " AND sync_status = %s"
                    params.append(status)

                data_sql += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])

                cursor.execute(data_sql, params)
                projects = cursor.fetchall()

                return projects, total

        except Exception as e:
            logger.error(f"查询项目列表失败: {e}")
            raise

    def create_sync_task(self, task_type: str, total_count: int = 0) -> int:
        """创建同步任务记录"""
        try:
            with self.connection.cursor() as cursor:
                sql = """
                INSERT INTO sync_tasks (task_type, status, total_count, processed_count)
                VALUES (%s, 'running', %s, 0)
                """
                cursor.execute(sql, (task_type, total_count))
                self.connection.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"创建同步任务失败: {e}")
            raise

    def update_sync_task(self, task_id: int, status: str = None,
                        processed_count: int = None, error_message: str = None):
        """更新同步任务状态"""
        try:
            with self.connection.cursor() as cursor:
                updates = []
                params = []

                if status:
                    updates.append("status = %s")
                    params.append(status)
                if processed_count is not None:
                    updates.append("processed_count = %s")
                    params.append(processed_count)
                if error_message:
                    updates.append("error_message = %s")
                    params.append(error_message)
                if status in ['completed', 'failed']:
                    updates.append("completed_at = CURRENT_TIMESTAMP")

                if updates:
                    params.append(task_id)
                    sql = f"UPDATE sync_tasks SET {', '.join(updates)} WHERE id = %s"
                    cursor.execute(sql, params)
                    self.connection.commit()
        except Exception as e:
            logger.error(f"更新同步任务失败: {e}")

    def add_sync_log(self, task_id: int, message: str, level: str = 'info'):
        """添加同步日志"""
        try:
            with self.connection.cursor() as cursor:
                sql = "INSERT INTO sync_logs (task_id, log_level, message) VALUES (%s, %s, %s)"
                cursor.execute(sql, (task_id, level, message))
                self.connection.commit()
        except Exception as e:
            logger.error(f"添加同步日志失败: {e}")


def test_connection():
    """测试数据库连接"""
    logger.info("开始测试数据库连接...")

    configs = get_all_database_configs()
    for region, config in configs.items():
        try:
            sync = DatabaseSync(region)
            sync.connect()
            sync.disconnect()
            logger.info(f"✓ {region} 数据库连接成功")
        except Exception as e:
            logger.error(f"✗ {region} 数据库连接失败: {e}")


if __name__ == "__main__":
    # 测试数据库连接
    test_connection()
