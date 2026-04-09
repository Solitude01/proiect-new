"""
数据同步API路由
"""
from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from typing import Optional
from datetime import datetime
from app.database import execute_query, execute_update, get_db_cursor
from app.schemas import (
    SyncTaskCreate,
    SyncTaskResponse,
    MessageResponse,
    TaskTypeEnum,
    TaskStatusEnum,
)
from app.services.db_sync import DatabaseSyncService

router = APIRouter()


@router.post("/trigger", response_model=SyncTaskResponse)
async def trigger_sync(
    task_type: TaskTypeEnum = Query(..., description="同步任务类型"),
    source_file: Optional[str] = Query(None, description="源文件路径"),
    region: str = Query("nantong", description="目标数据区域"),
):
    """触发数据同步任务"""
    try:
        sync_service = DatabaseSyncService()

        # 创建任务记录
        task_id = sync_service.create_task(task_type.value, source_file)

        # 根据任务类型执行不同的同步逻辑
        if task_type == TaskTypeEnum.excel_import:
            if not source_file:
                raise HTTPException(status_code=400, detail="Excel导入需要指定源文件路径")
            count = sync_service.import_from_excel(source_file, region)
        elif task_type == TaskTypeEnum.db_sync:
            count = sync_service.sync_between_databases("wuxi" if region == "nantong" else "nantong", region)
        elif task_type == TaskTypeEnum.export_excel:
            if not source_file:
                raise HTTPException(status_code=400, detail="导出Excel需要指定目标文件路径")
            count = sync_service.export_to_excel(source_file, region)
        else:
            raise HTTPException(status_code=400, detail=f"不支持的任务类型: {task_type}")

        # 更新任务状态
        sync_service.update_task(task_id, TaskStatusEnum.completed.value, count)

        return SyncTaskResponse(
            id=task_id,
            task_type=task_type,
            status=TaskStatusEnum.completed,
            total_count=count,
            processed_count=count,
            source_file=source_file,
            created_at=datetime.now(),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步失败: {str(e)}")


@router.get("/tasks", response_model=list)
async def get_sync_tasks(
    status: Optional[str] = Query(None, description="任务状态筛选"),
    task_type: Optional[str] = Query(None, description="任务类型筛选"),
    limit: int = Query(50, ge=1, le=200, description="返回数量限制"),
    region: str = Query("nantong", description="数据区域"),
):
    """获取同步任务列表"""
    conditions = []
    params = []

    if status:
        conditions.append("status = %s")
        params.append(status)
    if task_type:
        conditions.append("task_type = %s")
        params.append(task_type)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    query = f"""
    SELECT * FROM sync_tasks
    WHERE {where_clause}
    ORDER BY created_at DESC
    LIMIT %s
    """
    params.append(limit)

    return execute_query(query, tuple(params), region)


@router.get("/tasks/{task_id}", response_model=SyncTaskResponse)
async def get_sync_task(task_id: int, region: str = Query("nantong", description="数据区域")):
    """获取同步任务详情"""
    query = "SELECT * FROM sync_tasks WHERE id = %s"
    results = execute_query(query, (task_id,), region)

    if not results:
        raise HTTPException(status_code=404, detail="任务不存在")

    return SyncTaskResponse(**results[0])


@router.post("/upload", response_model=MessageResponse)
async def upload_excel(
    file: UploadFile = File(..., description="Excel文件"),
    region: str = Query("nantong", description="目标数据区域"),
):
    """上传Excel文件并导入数据"""
    try:
        # 保存上传的文件
        import os
        from pathlib import Path

        upload_dir = Path("uploads")
        upload_dir.mkdir(exist_ok=True)

        file_path = upload_dir / file.filename
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # 触发导入任务
        sync_service = DatabaseSyncService()
        task_id = sync_service.create_task(TaskTypeEnum.excel_import.value, str(file_path))

        try:
            count = sync_service.import_from_excel(str(file_path), region)
            sync_service.update_task(task_id, TaskStatusEnum.completed.value, count)
            return MessageResponse(message=f"成功导入 {count} 条记录", success=True)
        except Exception as e:
            sync_service.update_task(task_id, TaskStatusEnum.failed.value, 0, str(e))
            raise e

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@router.get("/status", response_model=dict)
async def get_sync_status(region: str = Query("nantong", description="数据区域")):
    """获取同步状态概览"""
    # 最近任务状态
    recent_tasks_query = """
    SELECT status, COUNT(*) as count
    FROM sync_tasks
    WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
    GROUP BY status
    """
    recent_tasks = execute_query(recent_tasks_query, (), region)

    # 待同步项目数
    pending_query = """
    SELECT COUNT(*) as pending_count
    FROM ai_projects
    WHERE sync_status = 'pending'
    """
    pending = execute_query(pending_query, (), region)

    # 最后同步时间
    last_sync_query = """
    SELECT MAX(completed_at) as last_sync_at
    FROM sync_tasks
    WHERE status = 'completed'
    """
    last_sync = execute_query(last_sync_query, (), region)

    return {
        "recent_tasks": {task["status"]: task["count"] for task in recent_tasks},
        "pending_projects": pending[0]["pending_count"] if pending else 0,
        "last_sync_at": last_sync[0]["last_sync_at"] if last_sync and last_sync[0]["last_sync_at"] else None,
    }


@router.post("/sync-all", response_model=MessageResponse)
async def sync_all_projects(
    from_region: str = Query("nantong", description="源数据区域"),
    to_region: str = Query("wuxi", description="目标数据区域"),
):
    """同步所有项目数据到另一个数据库"""
    try:
        sync_service = DatabaseSyncService()
        task_id = sync_service.create_task(TaskTypeEnum.db_sync.value)

        count = sync_service.sync_between_databases(from_region, to_region)
        sync_service.update_task(task_id, TaskStatusEnum.completed.value, count)

        return MessageResponse(message=f"成功同步 {count} 条记录到 {to_region} 数据库", success=True)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步失败: {str(e)}")
