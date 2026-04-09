"""
应用配置管理
"""
import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置"""

    # 应用基础配置
    app_name: str = "AI能力画像文档系统"
    app_env: str = os.getenv("APP_ENV", "development")
    debug: bool = os.getenv("DEBUG", "True").lower() == "true"
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

    # 服务配置
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    workers: int = int(os.getenv("WORKERS", "1"))

    # CORS配置
    allow_origins: List[str] = ["*"] if os.getenv("APP_ENV") == "development" else [
        os.getenv("FRONTEND_URL", "http://localhost:3000")
    ]

    # 数据库配置
    db_nantong_host: str = os.getenv("DB_NANTONG_HOST", "10.30.5.92")
    db_nantong_port: int = int(os.getenv("DB_NANTONG_PORT", "3306"))
    db_nantong_user: str = os.getenv("DB_NANTONG_USER", "ai_project_data_read")
    db_nantong_password: str = os.getenv("DB_NANTONG_PASSWORD", "ai_project_data_read")
    db_nantong_database: str = os.getenv("DB_NANTONG_DATABASE", "ai_project_data")

    db_wuxi_host: str = os.getenv("DB_WUXI_HOST", "10.20.32.165")
    db_wuxi_port: int = int(os.getenv("DB_WUXI_PORT", "3306"))
    db_wuxi_user: str = os.getenv("DB_WUXI_USER", "ai_project_data_read")
    db_wuxi_password: str = os.getenv("DB_WUXI_PASSWORD", "ai_project_data_read")
    db_wuxi_database: str = os.getenv("DB_WUXI_DATABASE", "ai_project_data")

    # Redis配置
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_db: int = int(os.getenv("REDIS_DB", "0"))
    redis_password: str = os.getenv("REDIS_PASSWORD", "")

    # 文件上传配置
    upload_dir: str = os.getenv("UPLOAD_DIR", "uploads")
    max_upload_size: int = int(os.getenv("MAX_UPLOAD_SIZE", "52428800"))  # 50MB

    # AI分析配置
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_api_url: str = os.getenv("GEMINI_API_URL", "https://generativelanguage.googleapis.com/v1beta/models")

    # 分页配置
    default_page_size: int = int(os.getenv("DEFAULT_PAGE_SIZE", "20"))
    max_page_size: int = int(os.getenv("MAX_PAGE_SIZE", "100"))

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
