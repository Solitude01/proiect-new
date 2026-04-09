"""
数据库连接管理
"""
import pymysql
from typing import Dict, Optional
from contextlib import contextmanager
from app.config import settings


class DatabaseManager:
    """数据库管理器"""

    def __init__(self):
        self.connections: Dict[str, pymysql.Connection] = {}

    def get_connection(self, region: str = "nantong") -> pymysql.Connection:
        """获取指定区域的数据库连接"""
        if region not in self.connections or not self._is_connection_valid(region):
            self.connections[region] = self._create_connection(region)
        return self.connections[region]

    def _create_connection(self, region: str) -> pymysql.Connection:
        """创建新的数据库连接"""
        config = self._get_db_config(region)
        try:
            connection = pymysql.connect(
                host=config["host"],
                port=config["port"],
                user=config["user"],
                password=config["password"],
                database=config["database"],
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=10
            )
            return connection
        except Exception as e:
            raise ConnectionError(f"无法连接到 {region} 数据库: {e}")

    def _get_db_config(self, region: str) -> Dict:
        """获取数据库配置"""
        if region == "wuxi":
            return {
                "host": settings.db_wuxi_host,
                "port": settings.db_wuxi_port,
                "user": settings.db_wuxi_user,
                "password": settings.db_wuxi_password,
                "database": settings.db_wuxi_database,
            }
        else:  # nantong
            return {
                "host": settings.db_nantong_host,
                "port": settings.db_nantong_port,
                "user": settings.db_nantong_user,
                "password": settings.db_nantong_password,
                "database": settings.db_nantong_database,
            }

    def _is_connection_valid(self, region: str) -> bool:
        """检查连接是否有效"""
        try:
            connection = self.connections.get(region)
            if connection:
                connection.ping(reconnect=False)
                return True
        except:
            pass
        return False

    def close_all(self):
        """关闭所有连接"""
        for connection in self.connections.values():
            try:
                connection.close()
            except:
                pass
        self.connections.clear()


# 全局数据库管理器实例
db_manager = DatabaseManager()


def init_db():
    """初始化数据库连接"""
    # 预创建连接
    try:
        db_manager.get_connection("nantong")
        db_manager.get_connection("wuxi")
    except Exception as e:
        print(f"⚠️ 数据库初始化警告: {e}")


@contextmanager
def get_db_cursor(region: str = "nantong"):
    """获取数据库游标的上下文管理器"""
    connection = db_manager.get_connection(region)
    cursor = connection.cursor()
    try:
        yield cursor
        connection.commit()
    except Exception as e:
        connection.rollback()
        raise e
    finally:
        cursor.close()


def execute_query(query: str, params: tuple = None, region: str = "nantong") -> list:
    """执行查询并返回结果"""
    with get_db_cursor(region) as cursor:
        cursor.execute(query, params or ())
        return cursor.fetchall()


def execute_update(query: str, params: tuple = None, region: str = "nantong") -> int:
    """执行更新并返回影响行数"""
    with get_db_cursor(region) as cursor:
        return cursor.execute(query, params or ())
