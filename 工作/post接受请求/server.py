"""
POST Interface Server
提供 HTTP POST 接口供其他设备访问
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Optional
import uvicorn
import json
from datetime import datetime

# 创建 FastAPI 应用实例
app = FastAPI(
    title="POST Interface Server",
    description="提供 HTTP POST 接口供其他设备访问和提交数据",
    version="1.0.0"
)

# 配置 CORS 中间件，允许跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有请求头
)


# 定义请求数据模型
class DataRequest(BaseModel):
    message: str
    device: Optional[str] = "unknown"
    data: Optional[Any] = None


# 定义响应数据模型
class DataResponse(BaseModel):
    success: bool
    message: str
    received_at: str
    client_info: dict
    received_data: Any


@app.get("/")
async def root():
    """服务状态检查端点"""
    return {
        "status": "running",
        "service": "POST Interface Server",
        "timestamp": datetime.now().isoformat(),
        "docs_url": "/docs"
    }


@app.post("/api/data", response_model=DataResponse)
async def receive_data(request: Request, data: DataRequest):
    """
    接收 POST 数据的通用接口

    - **message**: 消息内容（必填）
    - **device**: 设备标识（可选）
    - **data**: 附加数据（可选，任意类型）
    """
    # 获取客户端信息
    client_host = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    # 记录请求日志
    print(f"[{datetime.now().isoformat()}] Received request from {client_host}")
    print(f"  Device: {data.device}")
    print(f"  Message: {data.message}")
    print(f"  User-Agent: {user_agent}")
    if data.data:
        print(f"  Data: {json.dumps(data.data, ensure_ascii=False)}")
    print("-" * 50)

    # 构造响应
    response = DataResponse(
        success=True,
        message="Data received successfully",
        received_at=datetime.now().isoformat(),
        client_info={
            "ip": client_host,
            "user_agent": user_agent
        },
        received_data=data.dict()
    )

    return response


@app.post("/api/echo")
async def echo_data(request: Request):
    """
    回显接口 - 原样返回接收到的数据
    适用于测试和调试
    """
    body = await request.json()

    client_host = request.client.host if request.client else "unknown"

    print(f"[{datetime.now().isoformat()}] Echo request from {client_host}")
    print(f"  Body: {json.dumps(body, ensure_ascii=False)}")
    print("-" * 50)

    return {
        "success": True,
        "echo": body,
        "client_ip": client_host,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    # 启动服务器，监听所有网络接口
    print("=" * 50)
    print("POST Interface Server Starting...")
    print("=" * 50)
    print("API Documentation: http://localhost:8000/docs")
    print("API Endpoints:")
    print("  POST /api/data  - 接收结构化数据")
    print("  POST /api/echo  - 回显数据（测试用）")
    print("  GET  /          - 服务状态")
    print("  GET  /api/health- 健康检查")
    print("=" * 50)

    uvicorn.run(
        "server:app",
        host="0.0.0.0",  # 监听所有网络接口
        port=8000,
        reload=True      # 开发模式自动重载
    )
