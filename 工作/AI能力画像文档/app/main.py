"""
FastAPI 应用主入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import uvicorn

from app.config import settings
from app.database import init_db
from app.routes import projects, sync, analyze

# 创建FastAPI应用
app = FastAPI(
    title="AI能力画像文档系统",
    description="AI项目数据管理、同步和分析平台",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录（HTML页面）
static_path = Path(__file__).parent.parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=static_path), name="static")

# 注册路由
app.include_router(projects.router, prefix="/api/projects", tags=["项目管理"])
app.include_router(sync.router, prefix="/api/sync", tags=["数据同步"])
app.include_router(analyze.router, prefix="/api/analyze", tags=["AI分析"])


@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    # 初始化数据库连接
    init_db()
    print("🚀 AI能力画像文档系统启动成功")


@app.get("/")
async def root():
    """根路径，返回HTML页面"""
    # 优先返回Pro版本
    pro_html = Path(__file__).parent.parent / "AI能力画像助手 (Pro).html"
    if pro_html.exists():
        return FileResponse(pro_html)

    # 回退到基础版本
    basic_html = Path(__file__).parent.parent / "AI能力画像.html"
    if basic_html.exists():
        return FileResponse(basic_html)

    return {"message": "AI能力画像文档系统 API", "docs": "/docs"}


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "version": "1.0.0"}


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True if settings.app_env == "development" else False
    )
