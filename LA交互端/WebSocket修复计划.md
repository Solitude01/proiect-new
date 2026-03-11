# WebSocket 频繁断开重连问题修复计划

## 问题描述

WebSocket 连接出现频繁断开重连现象（约每10秒一次）：
- 17:00:42 - WebSocket 已连接
- 17:00:41 - WebSocket 连接已断开
- 17:00:31 - WebSocket 已连接

## 根本原因分析

### 状态感知实现原理（回答用户问题）

用户问"状态感知是如何实现的？我好像没有在LA配置响应"。

**答案**: 状态感知完全由**前端自动实现**，不需要LA配置：

1. **前端状态检测** (`dashboard.js:220-253`):
   - `ws.onopen` → 显示"已连接"（绿色）
   - `ws.onclose` → 显示"已断开"（红色），触发重连
   - `updateConnectionStatus()` 更新UI状态

2. **日志持久化** (`dashboard.js:addLog`):
   - 连接事件自动记录到浏览器终端
   - 通过 `POST /api/{id}/logs` 保存到服务器
   - 存储在 `logs/W8LA.jsonl` 文件中
   - 页面刷新后从历史日志恢复显示

### 频繁断开原因

网络中间件（代理/NAT/防火墙）在连接**空闲约10秒后**强制断开TCP连接。

**当前心跳机制的问题**:
- 前端每5秒发送应用层ping (`dashboard.js:296-307`)
- 后端 `receive_json()` 是**阻塞调用**，一直等待消息
- 某些网络设备在TCP空闲10秒后静默断开连接
- 前端30秒pong超时太长，无法及时感知断开

## 修复方案

### 方案 1: 优化心跳参数（推荐）

**前端** (`dashboard.js`):
```javascript
// 缩短ping间隔：5秒 → 2秒
startPingInterval() {
    this.pingInterval = setInterval(() => {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'ping' }));
            // 缩短pong超时：30秒 → 8秒
            if (Date.now() - this.lastPongTime > 8000) {
                console.log('[WebSocket] Pong timeout, reconnecting...');
                this.ws.close();
            }
        }
    }, 2000);  // 每2秒发送一次心跳
}
```

### 方案 2: 后端主动保活

**后端** (`main.py:429-458`):
```python
import asyncio

@app.websocket("/ws/{instance_id}")
async def websocket_endpoint(websocket: WebSocket, instance_id: str):
    ...
    # 启动心跳任务
    heartbeat_task = asyncio.create_task(send_heartbeat(websocket))

    try:
        while True:
            try:
                # 设置接收超时，避免永久阻塞
                message = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=10.0
                )
                # 处理消息...
            except asyncio.TimeoutError:
                # 超时继续循环，让心跳保持连接
                continue
    finally:
        heartbeat_task.cancel()
        ...

async def send_heartbeat(websocket: WebSocket):
    """每5秒发送一次心跳保持连接"""
    while True:
        try:
            await asyncio.sleep(5)
            await websocket.send_json({"type": "heartbeat"})
        except:
            break
```

### 方案 3: WebSocket原生ping/pong

使用WebSocket协议级的ping/pong（而非应用层），更可靠：
```python
# 在websocket连接建立后启用原生心跳
websocket.ping_interval = 5.0
websocket.ping_timeout = 10.0
```

## 实施步骤

1. **实施前端优化**（方案1）- 最快见效
   - 修改 `dashboard.js` ping间隔和超时时间
   - 重启服务验证效果

2. **如仍有问题，实施后端的接收超时**（方案2）
   - 修改 `main.py` WebSocket端点
   - 添加主动心跳或接收超时

3. **监控验证**
   - 观察日志，确认连接稳定
   - 检查浏览器控制台网络面板

## 关键文件

| 文件 | 位置 | 说明 |
|------|------|------|
| dashboard.js | L296-314 | 前端心跳ping/pong逻辑 |
| main.py | L403-463 | WebSocket端点处理 |
| websocket_manager.py | L23-55 | 连接管理 |

## 新增：LA心跳端点实施方案

### 新增端点

**后端** (`main.py`):
```python
# LA心跳上报端点
@app.post("/api/{instance_id}/heartbeat")
async def receive_heartbeat(instance_id: str, request: Request):
    """
    接收LA客户端心跳，用于检测LA软件存活状态
    """
    if not config_manager.instance_exists(instance_id):
        raise HTTPException(status_code=404, detail="Instance not found")

    try:
        data = await request.json()
    except:
        data = {}

    # 记录LA心跳时间
    la_status = {
        "type": "la_heartbeat",
        "instance_id": instance_id,
        "timestamp": datetime.now().isoformat(),
        "la_timestamp": data.get("timestamp"),
        "status": data.get("status", "alive"),
        "client_ip": request.client.host if request.client else None
    }

    # 存储到内存或临时存储
    # 广播给前端显示LA在线状态
    await websocket_manager.broadcast_to_room(instance_id, {
        "type": "LA_STATUS",
        "payload": {
            "online": True,
            "last_heartbeat": datetime.now().isoformat()
        }
    })

    return {"status": "ok", "received": True}

# 查询LA状态端点
@app.get("/api/{instance_id}/la-status")
async def get_la_status(instance_id: str):
    """获取LA客户端当前状态"""
    if not config_manager.instance_exists(instance_id):
        raise HTTPException(status_code=404, detail="Instance not found")

    # 从内存中获取最后心跳时间
    last_heartbeat = get_last_heartbeat(instance_id)  # 需要实现
    is_online = last_heartbeat and (datetime.now() - last_heartbeat).seconds < 30

    return {
        "instance_id": instance_id,
        "la_online": is_online,
        "last_heartbeat": last_heartbeat,
        "websocket_clients": websocket_manager.get_room_size(instance_id)
    }
```

### LA客户端配置示例

在LA软件中配置定时HTTP请求：

```
URL: http://10.30.44.154:8000/api/W8LA/heartbeat
方法: POST
Content-Type: application/json
请求体: {"status": "alive", "timestamp": "{SystemTime:yyyy-MM-dd HH:mm:ss}"}
频率: 每10秒
```

### 前端状态显示更新

**前端** (`dashboard.js`):
```javascript
// 在 handleMessage 中添加LA状态处理
case 'LA_STATUS':
    this.updateLAStatus(data.payload.online, data.payload.last_heartbeat);
    break;

// 新增LA状态显示方法
updateLAStatus(online, lastHeartbeat) {
    const laStatusEl = document.getElementById('laStatus');
    if (laStatusEl) {
        laStatusEl.textContent = online ? 'LA在线' : 'LA离线';
        laStatusEl.className = online ? 'status-online' : 'status-offline';
    }
}
```

## 实施步骤（更新）

1. **快速修复WebSocket断开**（5分钟）
   - 修改 `dashboard.js` L296-314: ping间隔5秒→2秒，超时30秒→8秒
   - 重启服务验证效果

2. **添加LA心跳端点**（15分钟）
   - 修改 `main.py`: 添加 `/api/{id}/heartbeat` POST端点
   - 添加 `/api/{id}/la-status` GET端点
   - 添加内存存储记录最后心跳时间

3. **前端显示LA状态**（10分钟）
   - 修改 `dashboard.js`: 添加LA状态消息处理
   - 修改 `dashboard.html`: 添加LA状态指示器

4. **LA客户端配置**（用户自行配置）
   - 按上述示例配置LA定时HTTP请求

## LA配置指导

### LogicAgent配置步骤

1. 打开LA配置界面
2. 找到"定时任务"或"循环执行"配置
3. 添加HTTP POST动作：
   - **URL**: `http://<中间件IP>:8000/api/<instance_id>/heartbeat`
   - **方法**: POST
   - **Content-Type**: application/json
   - **Body**: `{"status":"alive","timestamp":"{SystemTime}"}`
   - **频率**: 10秒

4. 测试发送一次，观察中间件控制台是否收到日志

## 关键文件（更新）

| 文件 | 位置 | 说明 |
|------|------|------|
| dashboard.js | L296-314 | 前端心跳ping/pong逻辑（需修改） |
| dashboard.js | L317+ | 添加LA状态消息处理 |
| main.py | 新增 | `/api/{id}/heartbeat` 端点 |
| main.py | 新增 | `/api/{id}/la-status` 端点 |
| dashboard.html | 新增 | LA状态显示UI |
| websocket_manager.py | 无需修改 | 复用现有广播功能 |

## 验证方法

1. **WebSocket稳定性验证**
   - 修改后重启服务
   - 打开浏览器开发者工具 → Network → WS
   - 观察WebSocket连接是否稳定（Messages不再频繁出现close/open）
   - 终端日志不再频繁出现"WebSocket 已连接/已断开"

2. **LA心跳验证**
   - 配置LA定时任务
   - 查看中间件控制台是否收到 `[WebSocket] LA heartbeat from W8LA`
   - 前端显示LA在线状态
   - 关闭LA软件，观察30秒后前端显示LA离线
