"""
Celery 异步任务定义
"""
from celery import Task
from app.worker.celery_app import celery_app
from app.services.db_sync import DatabaseSyncService
from app.services.ai_analyzer import AIAnalyzerService
import logging

logger = logging.getLogger(__name__)


class DatabaseTask(Task):
    """数据库任务基类"""

    _db_sync_service = None
    _ai_analyzer_service = None

    @property
    def db_sync_service(self):
        if self._db_sync_service is None:
            self._db_sync_service = DatabaseSyncService()
        return self._db_sync_service

    @property
    def ai_analyzer_service(self):
        if self._ai_analyzer_service is None:
            self._ai_analyzer_service = AIAnalyzerService()
        return self._ai_analyzer_service


@celery_app.task(base=DatabaseTask, bind=True)
def excel_import_task(self, excel_path: str, region: str = "nantong"):
    """Excel导入任务"""
    try:
        self.update_state(state="PROGRESS", meta={"current": 0, "total": 0})

        count = self.db_sync_service.import_from_excel(excel_path, region)

        return {
            "success": True,
            "message": f"成功导入 {count} 条记录",
            "count": count,
        }
    except Exception as e:
        logger.error(f"Excel导入任务失败: {e}")
        return {"success": False, "error": str(e)}


@celery_app.task(base=DatabaseTask, bind=True)
def db_sync_task(self, from_region: str, to_region: str):
    """数据库间同步任务"""
    try:
        self.update_state(state="PROGRESS", meta={"current": 0, "total": 0})

        count = self.db_sync_service.sync_between_databases(from_region, to_region)

        return {
            "success": True,
            "message": f"成功同步 {count} 条记录",
            "count": count,
        }
    except Exception as e:
        logger.error(f"数据库同步任务失败: {e}")
        return {"success": False, "error": str(e)}


@celery_app.task(base=DatabaseTask, bind=True)
def ai_analyze_task(self, project_ids: list, region: str = "nantong", force_reanalyze: bool = False):
    """AI分析任务"""
    try:
        from app.database import execute_query

        # 获取项目数据
        if project_ids:
            ids_str = ",".join(map(str, project_ids))
            query = f"SELECT * FROM ai_projects WHERE id IN ({ids_str}) AND source_region = %s"
            projects = execute_query(query, (region,), region)
        else:
            query = """
            SELECT * FROM ai_projects
            WHERE (application_scenario IS NULL OR core_functions IS NULL)
            AND source_region = %s
            LIMIT 100
            """
            projects = execute_query(query, (region,), region)

        if not projects:
            return {"success": True, "message": "没有需要分析的项目", "count": 0}

        # 创建分析任务
        task_id = self.ai_analyzer_service.create_analysis_task(region)

        # 异步执行分析
        import asyncio
        asyncio.run(
            self.ai_analyzer_service.analyze_projects_async(
                projects, task_id, force_reanalyze, region
            )
        )

        return {
            "success": True,
            "message": f"完成 {len(projects)} 个项目的AI分析",
            "count": len(projects),
        }

    except Exception as e:
        logger.error(f"AI分析任务失败: {e}")
        return {"success": False, "error": str(e)}


@celery_app.task(base=DatabaseTask, bind=True)
def scheduled_sync(self):
    """定时同步任务（用于Celery Beat）"""
    try:
        # 同步南通到无锡
        nantong_to_wuxi = self.db_sync_service.sync_between_databases("nantong", "wuxi")

        # 同步无锡到南通
        wuxi_to_nantong = self.db_sync_service.sync_between_databases("wuxi", "nantong")

        return {
            "success": True,
            "message": f"定时同步完成: 南通→无锡 {nantong_to_wuxi} 条, 无锡→南通 {wuxi_to_nantong} 条",
        }
    except Exception as e:
        logger.error(f"定时同步任务失败: {e}")
        return {"success": False, "error": str(e)}
