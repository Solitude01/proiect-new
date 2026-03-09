# POST Interface Server

基于 Python + FastAPI 的 HTTP POST 接口服务器，供其他设备访问和提交数据。

## 安装依赖

```bash
pip install -r requirements.txt
```

## 启动服务器

```bash
python server.py
```

服务器将启动并监听 `0.0.0.0:8000`，允许来自任何设备的连接。

## API 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/` | 服务状态检查 |
| GET | `/api/health` | 健康检查 |
| POST | `/api/data` | 接收结构化数据 |
| POST | `/api/echo` | 回显数据（测试用）|
| GET | `/docs` | Swagger UI 文档 |
| GET | `/redoc` | ReDoc 文档 |

## 测试方法

### 1. 使用 curl 测试

```bash
curl -X POST http://localhost:8000/api/data \
  -H "Content-Type: application/json" \
  -d '{"message": "hello", "device": "test"}'
```

### 2. 发送带附加数据的请求

```bash
curl -X POST http://localhost:8000/api/data \
  -H "Content-Type: application/json" \
  -d '{
    "message": "sensor data",
    "device": "temperature-sensor-01",
    "data": {
      "temperature": 25.5,
      "humidity": 60,
      "timestamp": "2024-01-01T12:00:00Z"
    }
  }'
```

### 3. 使用 Echo 接口测试

```bash
curl -X POST http://localhost:8000/api/echo \
  -H "Content-Type: application/json" \
  -d '{"any": "data", "you": "want"}'
```

### 4. 从其他设备访问

将 `<服务器IP>` 替换为运行服务器的机器的实际 IP 地址：

```bash
curl -X POST http://<服务器IP>:8000/api/data \
  -H "Content-Type: application/json" \
  -d '{"message": "from other device", "device": "mobile"}'
```

### 5. 使用浏览器查看文档

访问 http://localhost:8000/docs 查看交互式 API 文档（Swagger UI）。

## 数据格式

### POST /api/data 请求格式

```json
{
  "message": "必填的消息内容",
  "device": "可选的设备标识（默认：unknown）",
  "data": "可选的附加数据（任意类型）"
}
```

### 响应格式

```json
{
  "success": true,
  "message": "Data received successfully",
  "received_at": "2024-01-01T12:00:00.000000",
  "client_info": {
    "ip": "192.168.1.100",
    "user_agent": "curl/7.68.0"
  },
  "received_data": {
    "message": "hello",
    "device": "test",
    "data": null
  }
}
```

## 日志输出

服务器会在控制台输出所有请求的日志信息，包括：
- 请求时间
- 客户端 IP 地址
- 设备标识
- 消息内容
- User-Agent

## 配置

如需修改监听端口或地址，编辑 `server.py` 文件底部的 `uvicorn.run()` 调用：

```python
uvicorn.run(
    "server:app",
    host="0.0.0.0",  # 监听地址
    port=8000,        # 端口号
    reload=True       # 开发模式自动重载
)
```
