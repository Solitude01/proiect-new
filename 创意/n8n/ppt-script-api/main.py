import sqlite3
import json
import os
import uuid
import urllib.request
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

app = FastAPI()

# ===============================
# 配置区域
# ===============================

# 1. 数据库文件路径 (对应 docker-compose.yml 挂载的 /data)
DB_PATH = '/data/tasks.db'

# 2. n8n Webhook 地址
# 你的 n8n 运行在宿主机的 5678 端口
# 如果 n8n 和这个 API 在同一个 Docker 网络，也可以用 http://n8n:5678/...
# 这里为了稳妥，使用宿主机 IP。请确保你的 Webhook ID (4a5aa046...) 是正确的
N8N_WEBHOOK_URL = "http://10.30.43.199:5678/webhook/4a5aa046-b6df-48f2-91f5-79ec15627052"

# 3. 允许跨域 (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===============================
# 数据库初始化
# ===============================
def init_db():
    # 1. 确保 /data 目录存在 (防止本地运行或挂载异常时报错)
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir)
            print(f"已创建数据库目录: {db_dir}")
        except Exception as e:
            print(f"创建目录失败 (如果是 Docker 挂载请忽略): {e}")

    # 2. 连接数据库
    print(f"正在连接数据库: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 3. 创建表
    # status: 任务状态 (uploaded, processing, completed, error 等)
    # data: 存储 JSON 格式的详细进度数据 (如页码、脚本内容等)
    c.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            status TEXT,
            data TEXT,
            updated_at TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    print("数据库初始化完成。")

# 启动时立即初始化
init_db()

# ===============================
# 数据模型
# ===============================
class StatusUpdate(BaseModel):
    task_id: str
    status: str
    msg: Optional[str] = ""
    data: Optional[Dict[str, Any]] = {}

# ===============================
# 核心接口
# ===============================

# --- 接口 1: 接收 n8n 的状态汇报 ---
# n8n 每处理完一步，就会调用这个接口更新数据库
@app.post("/api/update_status")
async def update_status(update: StatusUpdate):
    print(f"收到汇报: [{update.task_id}] -> {update.status} | Msg: {update.msg}")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        current_time = datetime.now()
        
        # 检查任务是否存在
        c.execute("SELECT data FROM tasks WHERE id=?", (update.task_id,))
        row = c.fetchone()
        
        final_data = update.data
        
        if row:
            # 如果已有数据，尝试合并 JSON (保留之前的字段)
            try:
                old_data = json.loads(row[0]) if row[0] else {}
                if update.data:
                    old_data.update(update.data)
                final_data = old_data
            except Exception as e:
                print(f"JSON Merge Error: {e}")
                pass
                
            c.execute('''
                UPDATE tasks 
                SET status=?, data=?, updated_at=? 
                WHERE id=?
            ''', (update.status, json.dumps(final_data), current_time, update.task_id))
        else:
            # 如果任务不存在（理论上不应该，因为 /upload 已经创建了），则插入新记录
            c.execute('''
                INSERT INTO tasks (id, status, data, updated_at) 
                VALUES (?, ?, ?, ?)
            ''', (update.task_id, update.status, json.dumps(final_data), current_time))
            
        conn.commit()
        conn.close()
        return {"msg": "Status updated"}
        
    except Exception as e:
        print(f"Database Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- 接口 2: 前端轮询状态 ---
# 网页通过这个接口查询任务进度
@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT status, data, updated_at FROM tasks WHERE id=?", (task_id,))
    row = c.fetchone()
    conn.close()
    
    if row:
        return {
            "task_id": task_id,
            "status": row[0],
            "data": json.loads(row[1]) if row[1] else {},
            "updated_at": row[2]
        }
    else:
        return {"task_id": task_id, "status": "unknown", "data": {}}

# --- 接口 3: 前端上传文件并触发 n8n ---
@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    # 1. 生成唯一任务 ID
    task_id = str(uuid.uuid4())
    
    # 2. 保存文件到 /data 目录 (容器内路径)
    # 这里的 /data 对应宿主机挂载的 ./data 目录，n8n 也能通过某种方式访问(如果挂载了相同目录)
    # 或者 n8n 通过后续的 HTTP 请求下载
    save_filename = f"{task_id}_{file.filename}"
    file_location = f"/data/{save_filename}"
    
    try:
        with open(file_location, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        print(f"文件已保存: {file_location}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {e}")
    
    # 3. 初始化数据库状态为 'uploaded'
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        current_time = datetime.now()
        initial_data = json.dumps({
            "filename": file.filename, 
            "path": file_location,
            "original_name": file.filename
        })
        c.execute("INSERT INTO tasks (id, status, data, updated_at) VALUES (?, ?, ?, ?)", 
                  (task_id, "uploaded", initial_data, current_time))
        conn.commit()
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据库初始化失败: {e}")

    # 4. 主动呼叫 n8n Webhook
    # 这一步是为了让 n8n 开始干活。我们将 task_id 和文件路径传给它。
    payload = {
        "query": { # 保持和你 n8n 结构一致，或者直接放在根目录
             "task_id": task_id,
             "file_path": file_location,
             "filename": file.filename
        },
        # 也可以放在根目录，看你 n8n 怎么取
        "task_id": task_id,
        "file_path": file_location
    }
    
    try:
        # 使用标准库发送请求，避免引入 requests 依赖
        req = urllib.request.Request(
            N8N_WEBHOOK_URL, 
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        # 设置 3 秒超时，因为只需要触发，不需要等 n8n 执行完
        with urllib.request.urlopen(req, timeout=3) as response:
            print(f"n8n 触发成功，状态码: {response.status}")
            
    except Exception as e:
        print(f"触发 n8n 失败 (但文件已保存): {e}")
        # 这里不抛出异常，否则前端会以为失败了。我们返回一个警告。
        return {
            "task_id": task_id, 
            "status": "uploaded", 
            "warning": "Trigger n8n failed, please check network.",
            "error_detail": str(e)
        }

    # 5. 返回 task_id 给前端，前端开始轮询
    return {
        "task_id": task_id, 
        "message": "Task started", 
        "status": "uploaded"
    }

# --- 接口 4: (调试用) 查看所有任务 ---
@app.get("/api/all_tasks")
async def get_all_tasks(limit: int = 10):
    conn = sqlite3.connect(DB_PATH)
    # 以字典形式返回结果，方便查看
    conn.row_factory = sqlite3.Row 
    c = conn.cursor()
    
    # 按时间倒序，只看最近的 limit 条
    c.execute("SELECT * FROM tasks ORDER BY updated_at DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        # 把 row 对象转成字典，并解析 data 里的 JSON 字符串
        item = dict(row)
        try:
            item['data'] = json.loads(item['data']) if item['data'] else {}
        except:
            pass
        results.append(item)
        
    return results

if __name__ == "__main__":
    # 本地调试入口
    uvicorn.run(app, host="0.0.0.0", port=8080)