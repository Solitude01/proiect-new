"""
AI分析API路由
"""
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import Optional, List
from app.database import execute_query, execute_update, get_db_cursor
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    MessageResponse,
    TaskTypeEnum,
    TaskStatusEnum,
)
from app.services.ai_analyzer import AIAnalyzerService

router = APIRouter()


@router.post("/batch", response_model=AnalyzeResponse)
async def batch_analyze(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    region: str = Query("nantong", description="数据区域"),
):
    """批量触发AI分析"""
    try:
        analyzer = AIAnalyzerService()

        # 创建分析任务
        task_id = analyzer.create_analysis_task(region)

        # 获取需要分析的项目
        if request.project_ids:
            # 分析指定项目
            project_ids = ",".join(map(str, request.project_ids))
            query = f"""
            SELECT * FROM ai_projects
            WHERE id IN ({project_ids}) AND source_region = %s
            """
            projects = execute_query(query, (region,), region)
        else:
            # 分析所有待分析的项目
            query = """
            SELECT * FROM ai_projects
            WHERE (application_scenario IS NULL OR core_functions IS NULL)
            AND source_region = %s
            LIMIT 100
            """
            projects = execute_query(query, (region,), region)

        if not projects:
            return AnalyzeResponse(
                task_id=task_id,
                message="没有需要分析的项目",
                total_count=0,
            )

        # 在后台执行分析任务
        background_tasks.add_task(
            analyzer.analyze_projects_async,
            projects,
            task_id,
            request.force_reanalyze,
            region,
        )

        return AnalyzeResponse(
            task_id=task_id,
            message=f"已启动分析任务，共 {len(projects)} 个项目",
            total_count=len(projects),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析任务启动失败: {str(e)}")


@router.post("/{project_id}", response_model=MessageResponse)
async def analyze_project(
    project_id: int,
    force_reanalyze: bool = Query(False, description="是否强制重新分析"),
    region: str = Query("nantong", description="数据区域"),
):
    """分析单个项目"""
    try:
        # 获取项目数据
        query = "SELECT * FROM ai_projects WHERE id = %s AND source_region = %s"
        projects = execute_query(query, (project_id, region), region)

        if not projects:
            raise HTTPException(status_code=404, detail="项目不存在")

        project = projects[0]

        # 检查是否已有分析结果
        if not force_reanalyze and (
            project.get("application_scenario") or project.get("core_functions")
        ):
            return MessageResponse(message="该项目已有分析结果，如需重新分析请设置 force_reanalyze=true", success=False)

        # 执行分析
        analyzer = AIAnalyzerService()
        result = await analyzer.analyze_single_project(project)

        # 更新数据库
        update_query = """
        UPDATE ai_projects SET
            application_scenario = %s,
            processing_object = %s,
            core_functions = %s,
            output_interface = %s,
            deployment_method = %s,
            sync_status = 'synced'
        WHERE id = %s
        """
        execute_update(
            update_query,
            (
                result.application_scenario,
                result.processing_object,
                result.core_functions,
                result.output_format,
                result.deployment_method,
                project_id,
            ),
            region,
        )

        return MessageResponse(message="项目分析完成", success=True)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@router.get("/status/{task_id}")
async def get_analysis_status(
    task_id: int, region: str = Query("nantong", description="数据区域")
):
    """获取分析任务状态"""
    query = "SELECT * FROM sync_tasks WHERE id = %s AND task_type = 'ai_analyze'"
    results = execute_query(query, (task_id,), region)

    if not results:
        raise HTTPException(status_code=404, detail="分析任务不存在")

    task = results[0]
    return {
        "task_id": task["id"],
        "status": task["status"],
        "total_count": task["total_count"],
        "processed_count": task["processed_count"],
        "error_message": task.get("error_message"),
        "completed_at": task.get("completed_at"),
    }


@router.get("/queue", response_model=list)
async def get_analysis_queue(
    region: str = Query("nantong", description="数据区域"),
):
    """获取待分析项目队列"""
    query = """
    SELECT id, project_name, factory_name, created_at
    FROM ai_projects
    WHERE (application_scenario IS NULL OR core_functions IS NULL)
    AND source_region = %s
    ORDER BY created_at ASC
    LIMIT 50
    """
    return execute_query(query, (region,), region)
