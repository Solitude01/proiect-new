"""
项目管理API路由
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.database import execute_query, execute_update, get_db_cursor
from app.schemas import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ProjectListResponse,
    MessageResponse,
)

router = APIRouter()


@router.get("", response_model=ProjectListResponse)
async def get_projects(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    factory: Optional[str] = Query(None, description="工厂名称筛选"),
    status: Optional[str] = Query(None, description="同步状态筛选"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    region: str = Query("nantong", description="数据区域"),
):
    """获取项目列表（支持分页、筛选、搜索）"""
    offset = (page - 1) * page_size

    # 构建查询条件
    conditions = []
    params = []

    if factory:
        conditions.append("factory_name = %s")
        params.append(factory)
    if status:
        conditions.append("sync_status = %s")
        params.append(status)
    if keyword:
        conditions.append("(project_name LIKE %s OR project_goal LIKE %s)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # 计数查询
    count_query = f"SELECT COUNT(*) as total FROM ai_projects WHERE {where_clause}"
    count_result = execute_query(count_query, tuple(params), region)
    total = count_result[0]["total"] if count_result else 0

    # 数据查询
    data_query = f"""
    SELECT * FROM ai_projects
    WHERE {where_clause}
    ORDER BY created_at DESC
    LIMIT %s OFFSET %s
    """
    query_params = tuple(params) + (page_size, offset)
    projects = execute_query(data_query, query_params, region)

    # 计算总页数
    total_pages = (total + page_size - 1) // page_size

    return ProjectListResponse(
        items=[ProjectResponse(**project) for project in projects],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: int, region: str = Query("nantong", description="数据区域")):
    """获取单个项目详情"""
    query = "SELECT * FROM ai_projects WHERE id = %s"
    results = execute_query(query, (project_id,), region)

    if not results:
        raise HTTPException(status_code=404, detail="项目不存在")

    return ProjectResponse(**results[0])


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(project: ProjectCreate, region: str = Query("nantong", description="数据区域")):
    """创建新项目"""
    query = """
    INSERT INTO ai_projects (
        project_name, factory_name, project_goal, benefit_desc,
        ok_image_desc, ng_image_desc, application_scenario,
        processing_object, core_functions, output_interface,
        deployment_method, sync_status, source_region
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'synced', %s)
    """

    params = (
        project.project_name,
        project.factory_name,
        project.project_goal,
        project.benefit_desc,
        project.ok_image_desc,
        project.ng_image_desc,
        project.application_scenario,
        project.processing_object,
        project.core_functions,
        project.output_interface,
        project.deployment_method,
        region,
    )

    with get_db_cursor(region) as cursor:
        cursor.execute(query, params)
        project_id = cursor.lastrowid

    # 重新查询返回完整数据
    return await get_project(project_id, region)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    project: ProjectUpdate,
    region: str = Query("nantong", description="数据区域"),
):
    """更新项目"""
    # 检查项目是否存在
    existing = await get_project(project_id, region)
    if not existing:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 构建更新字段
    updates = []
    params = []

    for field, value in project.model_dump(exclude_unset=True).items():
        if value is not None:
            updates.append(f"{field} = %s")
            params.append(value)

    if not updates:
        raise HTTPException(status_code=400, detail="没有提供要更新的字段")

    params.append(project_id)
    query = f"UPDATE ai_projects SET {', '.join(updates)} WHERE id = %s"

    execute_update(query, tuple(params), region)

    return await get_project(project_id, region)


@router.delete("/{project_id}", response_model=MessageResponse)
async def delete_project(
    project_id: int, region: str = Query("nantong", description="数据区域")
):
    """删除项目"""
    # 检查项目是否存在
    existing = await get_project(project_id, region)
    if not existing:
        raise HTTPException(status_code=404, detail="项目不存在")

    query = "DELETE FROM ai_projects WHERE id = %s"
    execute_update(query, (project_id,), region)

    return MessageResponse(message="项目已删除", success=True)


@router.get("/stats/factories", response_model=list)
async def get_factory_stats(region: str = Query("nantong", description="数据区域")):
    """获取工厂统计信息"""
    query = """
    SELECT
        factory_name,
        COUNT(*) as project_count,
        SUM(CASE WHEN sync_status = 'synced' THEN 1 ELSE 0 END) as synced_count,
        SUM(CASE WHEN sync_status = 'pending' THEN 1 ELSE 0 END) as pending_count,
        SUM(CASE WHEN sync_status = 'failed' THEN 1 ELSE 0 END) as failed_count
    FROM ai_projects
    WHERE factory_name IS NOT NULL
    GROUP BY factory_name
    ORDER BY project_count DESC
    """
    return execute_query(query, (), region)


@router.get("/stats/summary", response_model=dict)
async def get_summary_stats(region: str = Query("nantong", description="数据区域")):
    """获取总体统计信息"""
    stats_query = """
    SELECT
        COUNT(*) as total_projects,
        SUM(CASE WHEN sync_status = 'synced' THEN 1 ELSE 0 END) as synced_projects,
        SUM(CASE WHEN sync_status = 'pending' THEN 1 ELSE 0 END) as pending_projects,
        SUM(CASE WHEN sync_status = 'failed' THEN 1 ELSE 0 END) as failed_projects,
        COUNT(DISTINCT factory_name) as factory_count
    FROM ai_projects
    """
    stats = execute_query(stats_query, (), region)

    # 最近7天新增项目
    recent_query = """
    SELECT COUNT(*) as recent_projects
    FROM ai_projects
    WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
    """
    recent = execute_query(recent_query, (), region)

    return {
        **stats[0] if stats else {},
        **recent[0] if recent else {},
    }
