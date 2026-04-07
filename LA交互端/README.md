# LA IIoT 多实例中间件

为 LogicAgent (LA) 工业自动化软件设计的轻量级 Windows Web 中间件。支持多实例隔离架构，为不同生产线提供独立的数据通道。

## 功能特性

- **多实例架构** — 每个实例拥有独立的数据通道，数据完全隔离
- **FastAPI 后端** — 基于 WebSocket 房间隔离模式
- **工业级仪表板** — 现代化、响应式、深色主题
- **实时更新** — 基于 WebSocket 的数据中继
- **音频通知** — 符合浏览器规范的音频解锁系统
- **Windows 防火墙** — 自动化防火墙配置

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

或使用提供的批处理脚本：

```bash
start.bat
```

### 2. 启动服务器

```bash
python main.py
```

或直接双击 `start.bat`（建议以管理员身份运行以配置防火墙）。

### 3. 访问门户

打开浏览器访问：`http://localhost:8000`

## API 端点

### 实例管理

- `GET /api/instances` — 列出所有实例
- `POST /api/instances` — 创建新实例
- `GET /api/instances/{instance_id}` — 获取实例详情
- `DELETE /api/instances/{instance_id}` — 删除实例

### WebSocket

- `WS /ws/{instance_id}` — 实时数据连接（房间隔离）

### Webhook

- `POST /api/{instance_id}/webhook` — 接收来自 LogicAgent 的数据

### 控制

- `POST /api/{instance_id}/control` — 向 LogicAgent 转发控制命令

## 配置

实例配置以 JSON 文件形式存储在 `configs/instances/` 目录中。

示例配置：

```json
{
  "instance_id": "workshop_01",
  "name": "一车间实例",
  "description": "A 生产线",
  "la_config": {
    "ip": "192.168.1.100",
    "port": 8080
  },
  "control_buttons": [
    {"id": "start", "label": "启动生产", "command": "START_PRODUCTION", "color": "green"}
  ],
  "metrics_mapping": {
    "cycle_time": "当前节拍",
    "total_count": "生产总数"
  },
  "audio_alerts": [
    {"keyword": "ERROR", "sound": "alert_error"}
  ]
}
```

## 测试

### 多实例隔离测试

```bash
# 创建两个实例
curl -X POST http://localhost:8000/api/instances \
  -H "Content-Type: application/json" \
  -d '{"instance_id":"test_a","name":"测试 A","la_ip":"127.0.0.1","la_port":8080}'

curl -X POST http://localhost:8000/api/instances \
  -H "Content-Type: application/json" \
  -d '{"instance_id":"test_b","name":"测试 B","la_ip":"127.0.0.1","la_port":8081}'

# 向 A 发送 webhook（只有 A 会收到）
curl -X POST http://localhost:8000/api/test_a/webhook \
  -H "Content-Type: application/json" \
  -d '{"message":"仅 A 可见的数据"}'
```

## 项目结构

```
LA交互端/
├── main.py                 # FastAPI 应用程序
├── config_manager.py       # 实例配置管理
├── websocket_manager.py    # WebSocket 连接池
├── requirements.txt        # Python 依赖
├── start.bat              # Windows 启动脚本
├── static/
│   ├── css/dashboard.css   # 工业仪表板样式
│   └── js/
│       ├── portal.js       # 实例门户逻辑
│       ├── dashboard.js    # 仪表板交互逻辑
│       └── audio.js        # 音频解锁与通知
└── templates/
    ├── index.html         # 实例管理门户
    └── dashboard.html     # 实例控制终端
```

## 许可证

MIT
