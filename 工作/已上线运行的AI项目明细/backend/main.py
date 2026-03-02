"""
AI项目展示系统 - 后端 API
FastAPI + SQLAlchemy + MySQL
"""
import os
import uuid
import shutil
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
import pandas as pd

from database import engine, get_db, Base
from models import Project

# 创建数据库表
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Projects API")

# 上传目录
UPLOAD_DIR = "/app/uploads/images"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/api/health")
def health_check():
    """健康检查"""
    return {"status": "ok", "message": "AI Projects API is running"}


@app.get("/api/projects")
def get_projects(
    factory: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取项目列表"""
    query = db.query(Project)

    if factory:
        query = query.filter(Project.factory_name == factory)
    if status:
        query = query.filter(Project.status == status)

    projects = query.order_by(Project.id.desc()).all()

    result = []
    for p in projects:
        result.append({
            "id": p.id,
            "project_name": p.project_name,
            "project_goal": p.project_goal,
            "benefit_desc": p.benefit_desc,
            "money_benefit": float(p.money_benefit) if p.money_benefit else 0,
            "time_saved": float(p.time_saved) if p.time_saved else 0,
            "factory_name": p.factory_name,
            "applicant": p.applicant,
            "create_time": str(p.create_time) if p.create_time else None,
            "submit_time": str(p.submit_time) if p.submit_time else None,
            "developer": p.developer,
            "audit_time": str(p.audit_time) if p.audit_time else None,
            "online_time": str(p.online_time) if p.online_time else None,
            "cancel_time": str(p.cancel_time) if p.cancel_time else None,
            "status": p.status,
            "alarm_image": p.alarm_image
        })

    return result


@app.get("/api/projects/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db)):
    """获取单个项目"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return {
        "id": project.id,
        "project_name": project.project_name,
        "project_goal": project.project_goal,
        "benefit_desc": project.benefit_desc,
        "money_benefit": float(project.money_benefit) if project.money_benefit else 0,
        "time_saved": float(project.time_saved) if project.time_saved else 0,
        "factory_name": project.factory_name,
        "applicant": project.applicant,
        "create_time": str(project.create_time) if project.create_time else None,
        "submit_time": str(project.submit_time) if project.submit_time else None,
        "developer": project.developer,
        "audit_time": str(project.audit_time) if project.audit_time else None,
        "online_time": str(project.online_time) if project.online_time else None,
        "cancel_time": str(project.cancel_time) if project.cancel_time else None,
        "status": project.status,
        "alarm_image": project.alarm_image
    }


@app.post("/api/projects/upload")
async def upload_excel(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """上传 Excel 文件并导入数据"""

    # 检查文件类型
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="请上传 Excel 文件 (.xlsx 或 .xls)")

    # 保存临时文件
    temp_path = f"/tmp/{uuid.uuid4()}_{file.filename}"
    try:
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # 读取 Excel
        df = pd.read_excel(temp_path)

        # 清空旧数据（可选，根据需求决定是否保留）
        db.query(Project).delete()
        db.commit()

        imported_count = 0

        for _, row in df.iterrows():
            # 跳过空行
            if pd.isna(row.iloc[0]) or str(row.iloc[0]).strip() == '':
                continue

            project = Project(
                project_name=safe_str(row.iloc[0] if len(row) > 0 else None),
                factory_name=safe_str(row.iloc[1] if len(row) > 1 else None),
                project_goal=safe_str(row.iloc[2] if len(row) > 2 else None),
                benefit_desc=safe_str(row.iloc[3] if len(row) > 3 else None),
                money_benefit=safe_float(row.iloc[4] if len(row) > 4 else None),
                time_saved=safe_float(row.iloc[5] if len(row) > 5 else None),
                applicant=safe_str(row.iloc[6] if len(row) > 6 else None),
                create_time=safe_date(row.iloc[7] if len(row) > 7 else None),
                submit_time=safe_date(row.iloc[8] if len(row) > 8 else None),
                developer=safe_str(row.iloc[9] if len(row) > 9 else None),
                audit_time=safe_date(row.iloc[10] if len(row) > 10 else None),
                online_time=safe_date(row.iloc[11] if len(row) > 11 else None),
                cancel_time=safe_date(row.iloc[12] if len(row) > 12 else None),
                status=safe_str(row.iloc[13] if len(row) > 13 else None),
                alarm_image=None  # 图片需要单独处理
            )
            db.add(project)
            imported_count += 1

        db.commit()

        return {"message": "导入成功", "imported_count": imported_count}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")
    finally:
        # 清理临时文件
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    """获取统计数据"""
    total = db.query(func.count(Project.id)).scalar() or 0

    # 已上线项目数
    online_count = db.query(func.count(Project.id)).filter(
        Project.status.ilike('%上线%') |
        Project.status.ilike('%已完成%') |
        Project.status.ilike('%运行中%')
    ).scalar() or 0

    # 总收益
    total_revenue = db.query(func.sum(Project.money_benefit)).scalar() or 0

    # 总节省时间
    total_time_saved = db.query(func.sum(Project.time_saved)).scalar() or 0

    # 按工厂统计
    factory_stats = db.query(
        Project.factory_name,
        func.count(Project.id).label('count')
    ).group_by(Project.factory_name).all()

    return {
        "total": total,
        "online": online_count,
        "total_revenue": float(total_revenue),
        "total_time_saved": float(total_time_saved),
        "by_factory": [{"factory": f[0], "count": f[1]} for f in factory_stats if f[0]]
    }


@app.get("/api/filters")
def get_filters(db: Session = Depends(get_db)):
    """获取筛选选项"""
    factories = db.query(Project.factory_name).distinct().filter(
        Project.factory_name.isnot(None),
        Project.factory_name != ''
    ).all()

    statuses = db.query(Project.status).distinct().filter(
        Project.status.isnot(None),
        Project.status != ''
    ).all()

    return {
        "factories": sorted([f[0] for f in factories]),
        "statuses": sorted([s[0] for s in statuses])
    }


# ==================
# 工具函数
# ==================

def safe_str(value) -> Optional[str]:
    """安全转换为字符串"""
    if pd.isna(value):
        return None
    return str(value).strip() if value else None


def safe_float(value) -> float:
    """安全转换为浮点数"""
    if pd.isna(value):
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def safe_date(value):
    """安全转换为日期"""
    if pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            try:
                return datetime.strptime(value, "%Y/%m/%d").date()
            except ValueError:
                return None
    return None
