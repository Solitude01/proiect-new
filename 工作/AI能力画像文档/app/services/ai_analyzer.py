"""
AI分析服务
"""
import json
import asyncio
import aiohttp
from typing import List, Dict, Optional
from datetime import datetime
from app.database import execute_update
from app.schemas import AIAnalysisResult, TaskStatusEnum
from app.config import settings


class AIAnalyzerService:
    """AI分析服务类"""

    def __init__(self):
        self.api_key = settings.gemini_api_key
        self.api_url = settings.gemini_api_url
        self.model = "gemini-1.5-flash"  # 可配置

    def create_analysis_task(self, region: str) -> int:
        """创建分析任务记录"""
        from app.database import get_db_cursor

        with get_db_cursor(region) as cursor:
            query = """
            INSERT INTO sync_tasks (task_type, status, total_count, processed_count)
            VALUES ('ai_analyze', 'running', 0, 0)
            """
            cursor.execute(query)
            return cursor.lastrowid

    async def analyze_single_project(self, project: Dict) -> AIAnalysisResult:
        """分析单个项目"""
        # 构建prompt
        prompt = self._build_prompt(project)

        # 调用Gemini API
        result = await self._call_gemini_api(prompt)

        # 解析结果
        return self._parse_result(result)

    async def analyze_projects_async(
        self,
        projects: List[Dict],
        task_id: int,
        force_reanalyze: bool,
        region: str,
    ):
        """异步批量分析项目"""
        total = len(projects)
        processed = 0
        errors = []

        for project in projects:
            try:
                result = await self.analyze_single_project(project)

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
                        json.dumps(result.core_functions, ensure_ascii=False),
                        result.output_format,
                        result.deployment_method,
                        project["id"],
                    ),
                    region,
                )

                processed += 1

                # 更新任务进度
                self._update_task_progress(task_id, processed, total, region)

                # 避免API限流
                await asyncio.sleep(1)

            except Exception as e:
                errors.append(f"项目 {project.get('project_name')}: {str(e)}")
                print(f"分析项目失败: {e}")

        # 完成任务
        if errors:
            self._complete_task(task_id, processed, total, "; ".join(errors), region)
        else:
            self._complete_task(task_id, processed, total, None, region)

    def _build_prompt(self, project: Dict) -> str:
        """构建AI分析prompt"""
        return f"""
你是一名专业的AI能力文档整理助手。请根据以下项目信息，输出客观、中立、描述性的AI能力画像分析：

项目名称：{project.get('project_name', '')}
工厂名称：{project.get('factory_name', '')}
项目目标：{project.get('project_goal', '')}
收益描述：{project.get('benefit_desc', '')}
OK图片描述：{project.get('ok_image_desc', '')}
NG图片描述：{project.get('ng_image_desc', '')}

请分析并输出以下五个字段的详细描述（JSON格式）：

{{
    "application_scenario": "一句话总结该项目的实际应用场景，突出业务背景但避免价值评估",
    "processing_object": "说明该AI项目接收的图像或视频来源",
    "core_functions": ["功能点1", "功能点2", ...],
    "output_format": "说明系统输出的形式，包括数据格式、接口协议、联动设备等",
    "deployment_method": "描述部署形态和硬件依赖（可选）"
}}

注意：
1. 内容需符合"图像AI能力画像"的客观、中立、描述性风格
2. core_functions字段为数组格式
3. 直接输出JSON，不要包含其他说明文字
"""

    async def _call_gemini_api(self, prompt: str) -> str:
        """调用Gemini API"""
        if not self.api_key:
            # 如果没有配置API密钥，返回模拟数据
            return self._mock_response()

        url = f"{self.api_url}/{self.model}:generateContent?key={self.api_key}"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 2048,
            },
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    raise Exception(f"Gemini API调用失败: {response.status}")

    def _mock_response(self) -> str:
        """模拟API响应（用于测试）"""
        return json.dumps(
            {
                "application_scenario": "工业生产线上的产品质量检测场景",
                "processing_object": "工业相机拍摄的产品静态图像",
                "core_functions": ["缺陷检测", "尺寸测量", "外观检查"],
                "output_format": "JSON格式检测结果，通过REST API输出，支持PLC联动",
                "deployment_method": "工控机部署，依赖GPU加速",
            },
            ensure_ascii=False,
        )

    def _parse_result(self, result_text: str) -> AIAnalysisResult:
        """解析AI分析结果"""
        try:
            # 清理JSON字符串（移除markdown标记）
            result_text = result_text.strip()
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]

            data = json.loads(result_text.strip())

            return AIAnalysisResult(
                application_scenario=data.get("application_scenario", ""),
                processing_object=data.get("processing_object", ""),
                core_functions=data.get("core_functions", []),
                output_format=data.get("output_format", ""),
                deployment_method=data.get("deployment_method"),
            )
        except Exception as e:
            # 解析失败时返回默认值
            return AIAnalysisResult(
                application_scenario="AI分析结果解析失败",
                processing_object="未知",
                core_functions=["功能分析失败"],
                output_format="未知",
                deployment_method=None,
            )

    def _update_task_progress(
        self, task_id: int, processed: int, total: int, region: str
    ):
        """更新任务进度"""
        from app.database import get_db_cursor

        with get_db_cursor(region) as cursor:
            query = """
            UPDATE sync_tasks
            SET processed_count = %s, total_count = %s
            WHERE id = %s
            """
            cursor.execute(query, (processed, total, task_id))

    def _complete_task(
        self, task_id: int, processed: int, total: int, error_message: str, region: str
    ):
        """完成任务"""
        from app.database import get_db_cursor

        with get_db_cursor(region) as cursor:
            query = """
            UPDATE sync_tasks
            SET status = %s, processed_count = %s, total_count = %s,
                error_message = %s, completed_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """
            cursor.execute(
                query,
                (
                    TaskStatusEnum.completed.value
                    if not error_message
                    else TaskStatusEnum.failed.value,
                    processed,
                    total,
                    error_message,
                    task_id,
                ),
            )
