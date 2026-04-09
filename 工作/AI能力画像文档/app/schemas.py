"""
Pydantic 数据模式定义
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime
from enum import Enum


class SyncStatusEnum(str, Enum):
    """同步状态枚举"""
    pending = "pending"
    synced = "synced"
    failed = "failed"


class TaskStatusEnum(str, Enum):
    """任务状态枚举"""
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class TaskTypeEnum(str, Enum):
    """任务类型枚举"""
    excel_import = "excel_import"
    ai_analyze = "ai_analyze"
    db_sync = "db_sync"
    export_excel = "export_excel"


# ============ 项目相关模式 ============

class ProjectBase(BaseModel):
    """项目基础模式"""
    project_name: str = Field(..., description="项目名称", min_length=1, max_length=255)
    factory_name: Optional[str] = Field(None, description="工厂名称", max_length=100)
    project_goal: Optional[str] = Field(None, description="项目目标")
    benefit_desc: Optional[str] = Field(None, description="收益描述")
    ok_image_desc: Optional[str] = Field(None, description="OK图片描述")
    ng_image_desc: Optional[str] = Field(None, description="NG图片描述")
    application_scenario: Optional[str] = Field(None, description="应用场景简述")
    processing_object: Optional[str] = Field(None, description="处理对象(输入)")
    core_functions: Optional[Any] = Field(None, description="核心功能")
    output_interface: Optional[str] = Field(None, description="输出形式/接口")
    deployment_method: Optional[str] = Field(None, description="部署方式")


class ProjectCreate(ProjectBase):
    """创建项目请求模式"""
    pass


class ProjectUpdate(BaseModel):
    """更新项目请求模式"""
    factory_name: Optional[str] = None
    project_goal: Optional[str] = None
    benefit_desc: Optional[str] = None
    ok_image_desc: Optional[str] = None
    ng_image_desc: Optional[str] = None
    application_scenario: Optional[str] = None
    processing_object: Optional[str] = None
    core_functions: Optional[Any] = None
    output_interface: Optional[str] = None
    deployment_method: Optional[str] = None


class ProjectResponse(ProjectBase):
    """项目响应模式"""
    id: int
    sync_status: SyncStatusEnum
    source_region: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectListResponse(BaseModel):
    """项目列表响应模式"""
    items: List[ProjectResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============ 同步任务相关模式 ============

class SyncTaskBase(BaseModel):
    """同步任务基础模式"""
    task_type: TaskTypeEnum
    source_file: Optional[str] = None


class SyncTaskCreate(SyncTaskBase):
    """创建同步任务请求"""
    total_count: int = 0


class SyncTaskResponse(BaseModel):
    """同步任务响应模式"""
    id: int
    task_type: TaskTypeEnum
    status: TaskStatusEnum
    total_count: int
    processed_count: int
    error_message: Optional[str] = None
    source_file: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============ AI分析相关模式 ============

class AnalyzeRequest(BaseModel):
    """AI分析请求模式"""
    project_ids: Optional[List[int]] = None  # 指定项目ID，为空则分析所有pending状态的项目
    force_reanalyze: bool = False  # 是否强制重新分析


class AnalyzeResponse(BaseModel):
    """AI分析响应模式"""
    task_id: int
    message: str
    total_count: int


class AIAnalysisResult(BaseModel):
    """AI分析结果模式"""
    application_scenario: str = Field(..., description="应用场景简述")
    processing_object: str = Field(..., description="处理对象(输入)")
    core_functions: List[str] = Field(..., description="核心功能列表")
    output_format: str = Field(..., description="输出形式/接口")
    deployment_method: Optional[str] = Field(None, description="部署方式")


# ============ 通用响应模式 ============

class MessageResponse(BaseModel):
    """消息响应模式"""
    message: str
    success: bool = True


class PaginatedResponse(BaseModel):
    """分页响应基础模式"""
    page: int
    page_size: int
    total: int
    total_pages: int
