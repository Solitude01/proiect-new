# LA IIoT 多实例中间件

为 LogicAgent (LA) 工业自动化软件设计的轻量级 Windows Web 中间件。支持多实例隔离架构，为不同生产线提供独立的数据通道。

## 功能特性

- **多实例架构** — 每个实例拥有独立数据通道，WebSocket 房间隔离
- **FastAPI 后端** — 基于 WebSocket 的实时数据中继
- **工业级仪表板** — HUD 风格控制面板，暗色/亮色主题切换
- **音频告警系统** — 关键词匹配触发、自定义音频上传、全局开关
- **实例回收站** — 软删除 + 恢复机制，防止误删
- **在线连接数** — 门户实时显示每个实例的客户端连接数
- **操作确认** — 删除/禁用需输入实例名称确认，禁止粘贴
- **控制按钮** — 支持 6 种颜色、自定义端点/方法/载荷
- **单实例模式** — 按生产线独立端口部署
- **PyInstaller 打包** — 生成独立 Windows 可执行文件

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动服务器

```bash
python main.py
# 或指定端口
python main.py --port 8002
# 或使用批处理（含防火墙配置）
start.bat
```

### 3. 访问门户

打开浏览器访问：`http://localhost:8000`

## 启动方式

| 命令 | 说明 |
|------|------|
| `python main.py` | 单控制台服务（默认端口 8000） |
| `python main.py --port 8002` | 指定端口启动 |
| `python start_all.py` | 控制台 + 业务视图双服务 |
| `python start_instance.py <id> <port>` | 单实例模式 |
| `start.bat` | Windows 一键启动（含防火墙） |
| `kill-server.bat` | 释放被占用的端口 |
| `build_exe.bat` | 构建独立 EXE |

## API 端点

### 实例管理

| 端点 | 说明 |
|------|------|
| `GET /api/instances?type=active\|trash` | 列出实例（active=活跃，trash=回收站） |
| `POST /api/instances` | 创建新实例 |
| `GET /api/instances/{id}` | 获取实例详情 |
| `PUT /api/instances/{id}` | 更新实例配置 |
| `DELETE /api/instances/{id}` | 软删除（移入回收站） |
| `POST /api/instances/{id}/restore` | 从回收站恢复 |
| `DELETE /api/instances/{id}/permanent` | 永久删除 |

### 数据与告警

| 端点 | 说明 |
|------|------|
| `POST /api/{id}/webhook` | 接收 LA 数据（JSON/multipart） |
| `POST /api/{id}/metrics` | 接收实时指标数据 |
| `POST /api/{id}/alert` | 接收告警（自动检测格式） |
| `GET /api/{id}/alert?message=&level=` | 简单 GET 告警 |
| `POST /api/{id}/alert-debug` | 告警调试端点 |

### 控制与音频

| 端点 | 说明 |
|------|------|
| `POST /api/{id}/control` | 转发命令到 LA（支持自定义端点/方法/载荷） |
| `POST /api/{id}/audio/upload` | 上传自定义音频文件 |
| `GET /api/{id}/audio` | 列出音频文件 |
| `DELETE /api/{id}/audio/{file_id}` | 删除音频文件 |

### 实时通信与状态

| 端点 | 说明 |
|------|------|
| `WS /ws/{id}` | WebSocket 连接（房间隔离） |
| `GET /api/{id}/status` | 实时状态（连接数） |
| `GET /api/{id}/logs` | 获取持久化日志 |
| `DELETE /api/{id}/logs` | 清除日志 |
| `GET /api/server-info` | 获取服务器 IP |
| `GET /api/health` | 健康检查 |

## 配置

实例配置以 JSON 文件形式存储在 `configs/instances/` 目录中。

```json
{
  "instance_id": "workshop_01",
  "name": "一车间实例",
  "description": "A 生产线",
  "enabled": true,
  "la_config": {
    "ip": "192.168.1.100",
    "port": 8080
  },
  "control_buttons": [
    {"id": "start", "label": "启动生产", "command": "START_PRODUCTION", "color": "green", "button_type": "command"},
    {"id": "set_speed", "label": "设置速度", "command": "SET_SPEED", "color": "blue", "button_type": "input", "payload": {"action": "set_speed", "value": "{{input}}"}
  ],
  "metrics_mappings": [
    {"la_key": "cycle_time", "display_name": "当前节拍", "unit": "s", "data_type": "number"}
  ],
  "audio_alerts": [
    {"name": "故障告警", "keyword": "ERROR", "sound": "error", "min_interval": 5, "enabled": true}
  ],
  "audio_alert_match_enabled": false,
  "audio_alerts_enabled": true
}
```

### 控制按钮颜色

| 值 | 颜色 | 用途示例 |
|------|------|------|
| `green` | 绿色 | 启动/开始 |
| `red` | 红色 | 停止/紧急 |
| `blue` | 青色 | 复位/通用 |
| `orange` | 橙色 | 暂停/警告 |
| `yellow` | 黄色 | 提示/通知 |
| `purple` | 紫色 | 特殊操作 |

### 按钮类型

| 类型 | 说明 |
|------|------|
| `command` | 普通按钮，点击直接发送载荷 |
| `input` | 带输入框按钮，`{{input}}` 占位符被替换为用户输入值 |

## 测试

### 基本测试

```bash
# 创建实例
curl -X POST http://localhost:8000/api/instances \
  -H "Content-Type: application/json" \
  -d '{"instance_id":"line1","name":"一号线","la_ip":"127.0.0.1","la_port":8080}'

# 发送 webhook
curl -X POST http://localhost:8000/api/line1/webhook \
  -H "Content-Type: application/json" \
  -d '{"message":"测试数据"}'

# 发送告警
curl "http://localhost:8000/api/line1/alert?message=设备故障&level=error"

# 软删除
curl -X DELETE http://localhost:8000/api/instances/line1

# 恢复
curl -X POST http://localhost:8000/api/instances/line1/restore
```

### 多实例隔离测试

```bash
# 创建两个实例，向 A 发送数据
curl -X POST http://localhost:8000/api/instances \
  -d '{"instance_id":"test_a","name":"测试 A","la_ip":"127.0.0.1","la_port":8080}'
curl -X POST http://localhost:8000/api/test_a/webhook \
  -d '{"message":"仅 A 可见"}'
# 连接到 /ws/test_b 的客户端不会收到此消息
```

## 项目结构

```
LA交互端/
├── main.py                    # FastAPI 应用入口
├── config_manager.py          # 实例配置管理（Pydantic 模型）
├── websocket_manager.py       # WebSocket 房间隔离连接池
├── start_all.py               # 多服务启动器
├── start_instance.py          # 单实例启动器
├── requirements.txt           # Python 依赖
├── start.bat                  # Windows 一键启动（含防火墙）
├── kill-server.bat            # 端口释放工具
├── build_exe.bat              # 构建独立 EXE
├── LAdmin.spec / LView.spec   # PyInstaller 配置
├── configs/instances/*.json   # 实例配置文件
├── logs/*.jsonl               # 持久化日志
├── static/
│   ├── css/dashboard.css      # 工业 HUD 仪表板样式
│   ├── js/
│   │   ├── portal.js          # 门户管理（实例 CRUD + 回收站）
│   │   ├── dashboard.js       # 控制台交互逻辑
│   │   ├── business_view.js   # 业务视图逻辑
│   │   └── audio.js           # 音频解锁与通知
│   └── audio/                 # 自定义音频文件
└── templates/
    ├── index.html             # 实例管理门户
    ├── dashboard.html         # 实例控制终端
    └── business_view.html     # 业务视图（只读）
```

## 许可证

MIT
