"""
数据库配置管理模块
"""
import os
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass

from dotenv import load_dotenv

# 加载环境变量
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)


@dataclass
class DatabaseConfig:
    """数据库配置"""
    host: str
    port: int
    user: str
    password: str
    database: str

    @property
    def connection_url(self) -> str:
        """SQLAlchemy连接URL"""
        return f"mysql+pymysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}?charset=utf8mb4"

    @property
    def raw_url(self) -> str:
        """原始连接字符串（用于pymysql）"""
        return f"mysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class Config:
    """应用配置"""

    # 南通数据库
    db_nantong = DatabaseConfig(
        host=os.getenv('DB_NANTONG_HOST', '10.30.5.92'),
        port=int(os.getenv('DB_NANTONG_PORT', '3306')),
        user=os.getenv('DB_NANTONG_USER', 'ai_project_data_read'),
        password=os.getenv('DB_NANTONG_PASSWORD', 'ai_project_data_read'),
        database=os.getenv('DB_NANTONG_DATABASE', 'ai_project_data')
    )

    # 无锡数据库
    db_wuxi = DatabaseConfig(
        host=os.getenv('DB_WUXI_HOST', '10.20.32.165'),
        port=int(os.getenv('DB_WUXI_PORT', '3306')),
        user=os.getenv('DB_WUXI_USER', 'ai_project_data_read'),
        password=os.getenv('DB_WUXI_PASSWORD', 'ai_project_data_read'),
        database=os.getenv('DB_WUXI_DATABASE', 'ai_project_data')
    )

    # 应用配置
    app_env = os.getenv('APP_ENV', 'development')
    secret_key = os.getenv('SECRET_KEY', 'dev-secret-key')

    # Redis配置
    redis_host = os.getenv('REDIS_HOST', 'localhost')
    redis_port = int(os.getenv('REDIS_PORT', '6379'))
    redis_db = int(os.getenv('REDIS_DB', '0'))

    # Gemini API配置
    gemini_api_key = os.getenv('GEMINI_API_KEY', '')
    gemini_api_url = os.getenv('GEMINI_API_URL', 'https://generativelanguage.googleapis.com/v1beta/models')


def get_database_config(region: str = 'nantong') -> DatabaseConfig:
    """获取指定区域的数据库配置"""
    if region == 'wuxi':
        return Config.db_wuxi
    return Config.db_nantong


def get_all_database_configs() -> Dict[str, DatabaseConfig]:
    """获取所有数据库配置"""
    return {
        'nantong': Config.db_nantong,
        'wuxi': Config.db_wuxi
    }
