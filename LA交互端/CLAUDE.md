# CLAUDE.md

本文件为 Claude Code 在此仓库中工作时提供指导。

## 项目概述

LA交互端 是用于 LogicAgent (LA) 工业自动化软件的 IIoT 多实例中间件系统。它通过 Webhook 接收 LA 数据，通过 WebSocket 推送到浏览器，实例间数据完全隔离。

支持通过 **PyInstaller** 打包为独立的 Windows 可执行文件 (LAdmin.exe / LView.exe)，可在没有 Python 环境的机器上部署运行。

## 开发命令

### 启动开发服务器

```bash
# 单服务模式（仅控制台）
python main.py

# 多服务模式（控制台 + 业务视图）
python start_all.py

# 或使用批处理文件
start.bat          # 单控制台服务
start_all.bat      # 两个服务同时启动
```

### 安装依赖

```bash
pip install -r requirements.txt
```

### 单实例模式启动（业务隔离）

```bash
# 格式：python start_instance.py <实例ID> <端口>
python start_instance.py line1 8001
```

### 构建可执行文件

```bash
# 构建 LAdmin.exe（控制台）和 LView.exe（业务视图）
pyinstaller LAdmin.spec
pyinstaller LView.spec

# 或使用批处理文件
build_exe.bat
```

### 释放被占用的端口

```bash
kill-server.bat   # 杀掉占用 8000-8009、6010 端口的进程
```

## 架构

### 多实例数据隔离

系统使用**基于房间的 WebSocket 隔离模式**：

- 每个实例拥有自己的 WebSocket "房间"（`websocket_manager.py`）
- 消息仅广播到同一房间内的连接
- 确保生产线 A 的数据不会出现在生产线 B 的仪表板上

关键文件：
- `websocket_manager.py` — ConnectionManager 类处理房间隔离
- `main.py` — `/ws/{instance_id}` WebSocket 端点将客户端加入房间

### 配置持久化

实例配置以 JSON 文件存储在 `configs/instances/{instance_id}.json`：

```python
# config_manager.py
class InstanceConfig(BaseModel):
    instance_id: str
    name: str
    la_config: LAConfig                # LA 连接配置（IP、端口）
    view_port: int                     # 业务视图端口（0 表示禁用）
    view_uid: str                      # 业务视图访问 UID
    control_buttons: List[ControlButton]   # 支持 button_type: "command" 或 "input"
    metrics_mappings: List[MetricsMapping] # LA 字段 → 显示名称（含单位/格式）
    audio_alerts: List[AudioAlert]     # 支持 name、keyword、sound、audio_file_id、min_interval、enabled
    audio_files: List[AudioFile]
    audio_alert_match_enabled: bool    # 全局音频告警匹配开关（默认关闭）
    audio_alerts_enabled: bool = True  # 全局音频告警总开关（默认开启）
```

### 双端口架构

两个独立的 HTTP 服务运行同一个 FastAPI 应用：

1. **控制台服务（端口 8000）** — 完整的管理访问权限
2. **业务视图服务（端口 6010）** — 面向操作员的只读仪表板

业务视图通过 `/{view_uid}` 访问，继承父控制台的配置。

**注意**：端口 6000-6009 是 Chrome 不安全端口，请使用 6010 及以上端口。

### 单实例模式

通过设置 `INSTANCE_ID` 环境变量，为单个实例在自定义端口上运行专用服务：
- 根路由 `/` 自动重定向到该实例的仪表板
- 访问其他实例 ID 返回 403
- 由 `start_instance.py` 使用，用于按生产线隔离部署

### 告警系统

接收并广播来自 LA 的告警，自动检测格式：
- `POST /api/{id}/alert` — 接受 JSON、form-data、URL-encoded 或查询字符串格式
- `GET /api/{id}/alert?message=...&level=...` — 基于 GET 的简单告警
- 自动从多种字段名变体中提取 level 和 message（level/type/severity、message/msg/content/text）
- `POST /api/{id}/alert-debug` — 调试端点，显示解析后的载荷，用于排查 LA 集成问题

### `{{input}}` 占位符系统

`button_type: "input"` 类型的控制按钮会渲染一个输入框。按钮载荷中的 `{{input}}` 占位符会在转发到 LA 之前被递归替换为用户输入的值。支持字符串、字典和列表类型。

`main.py` 中的 `_replace_input_placeholder()` 函数处理递归替换。

### 通过 UID 访问业务视图

`GET /view/{view_uid}` 路由提供直接访问只读仪表板的功能，无需知道 instance_id。解析逻辑：
- `config_manager.get_instance_by_view_uid()` 扫描所有配置文件，查找匹配的 `view_uid`
- 前端通过 `GET /api/view/{view_uid}` 在启动时获取配置

### 主题系统

CSS 使用 CSS 自定义属性实现暗色/亮色主题切换。`<html>` 元素的 `data-theme` 属性在 `"dark"`（默认）和 `"light"` 之间切换。主题偏好保存在 localStorage 中。

### PyInstaller 构建

spec 文件（`LAdmin.spec`、`LView.spec`）包含了 uvicorn、websockets、starlette、pydantic 及其所有子模块的 `hiddenimports`。新增任何依赖时，两个 spec 文件都需要同步更新。构建时还会打包 `templates/`、`static/` 和 `configs/` 目录作为数据文件。

## 关键 API 端点

```
POST /api/instances                # 创建实例
GET  /api/instances/{id}           # 获取实例配置
PUT  /api/instances/{id}           # 更新实例配置
DELETE /api/instances/{id}         # 删除实例
POST /api/{id}/webhook             # 接收 LA 数据（JSON 或 multipart/form-data）
POST /api/{id}/alert               # 接收 LA 告警（自动检测格式）
GET  /api/{id}/alert               # 简单 GET 告警
POST /api/{id}/metrics             # 接收实时指标数据
POST /api/{id}/control             # 转发命令到 LA（支持自定义端点/方法/载荷）
POST /api/{id}/audio/upload        # 上传音频文件
GET  /api/{id}/audio               # 列出音频文件
DELETE /api/{id}/audio/{file_id}   # 删除音频文件
GET  /api/{id}/logs                # 获取持久化日志
DELETE /api/{id}/logs              # 清除日志
GET  /api/{id}/status              # 获取实时状态（已连接客户端数）
WS   /ws/{id}                      # WebSocket 连接（房间隔离）
GET  /view/{view_uid}              # 通过 UID 访问业务视图
GET  /api/server-info              # 获取服务器 IP 地址
```

## 前端结构

- `templates/index.html` — 实例管理门户（CRUD 模态框）
- `templates/dashboard.html` — 完整控制台（可折叠的设置面板）
- `templates/business_view.html` — 操作员仪表板（与控制台相同，仅只读）
- `static/js/dashboard.js` — 主仪表板逻辑（`DashboardManager` 类，约 700 行）
- `static/js/business_view.js` — 业务视图逻辑（`BusinessViewManager` 类，与 DashboardManager 几乎一致）
- `static/js/portal.js` — 实例管理（CRUD、模态框、消息提示）
- `static/js/audio.js` — 音频解锁和通知系统
- `static/css/dashboard.css` — 工业风格仪表板样式，通过 CSS 变量实现暗色/亮色主题

## 前端模式

### 连接门（Connection Gate）

仪表板加载时显示一个覆盖层（"连接并解锁音频"），要求用户点击后才能连接 WebSocket。这满足了浏览器的自动播放限制——音频上下文在同一个用户手势中创建/恢复。

### 日志批量渲染

`dashboard.js` 使用批量渲染模式处理终端日志：新日志条目被推入 `this.logBatch`，通过 `setInterval` 每 50ms 处理一次，批量插入 DOM 节点以避免布局抖动。

### 指标映射渲染

指标网格支持两种模式：
1. **未映射** — 从 snake_case/camelCase 键名自动生成显示标签
2. **已映射** — 使用 `MetricsMapping` 配置（la_key、display_name、unit、data_type、format）精确控制显示

### 音频告警时间过滤

每个 AudioAlert 有 `min_interval` 字段（分钟）。`dashboard.js` 跟踪 `lastAlertTimes`，跳过距离上次触发时间太近的告警。

## WebSocket 协议

服务端到客户端的消息遵循 `{ type: string, payload?: any, instance_id?: string, timestamp?: string }` 格式。

关键消息类型：
- `"connection"` — 连接成功确认
- `"data"` — Webhook/实时数据载荷
- `"alert"` — 告警信息（payload 中携带 level、message、type）
- `"pong"` — 心跳响应
- `"subscribed"` — 订阅确认
- `"config_sync"` — 配置变更广播到房间（从控制台转发到业务视图）

心跳：前端每 5 秒发送 `{ type: "ping" }`，服务端响应 `{ type: "pong" }`。如果 30 秒内未收到 pong，则认为连接断开（触发指数退避重连，上限 30 秒）。

## 依赖

- **fastapi** + **uvicorn** — Web 框架和 ASGI 服务器
- **jinja2** — 模板引擎
- **aiofiles** — 异步文件 I/O
- **httpx** — 异步 HTTP 客户端（用于转发命令到 LA）
- **python-multipart** — 表单数据解析

## 代码模式

### 添加新的 WebSocket 消息类型

1. 在 `dashboard.js` 或 `business_view.js` 中添加处理：
```javascript
// 在 handleWebSocketMessage() 中
case 'NEW_TYPE':
    this.handleNewType(data.payload);
    break;
```

2. 从 main.py 广播：
```python
await websocket_manager.broadcast_to_room(instance_id, {
    "type": "NEW_TYPE",
    "payload": {...}
})
```

### 配置更新

设置面板使用临时状态，保存时才实际应用：
```javascript
this.tempSettings = { ...this.instanceConfig };  // 打开时克隆
// 用户编辑 tempSettings
// 保存时：POST /api/instances/{id}/config 使用 tempSettings
```

### 新增配置字段

1. 在 `config_manager.py` 的模型中添加（InstanceConfig 或嵌套模型）
2. 在 ConfigManager 的 `update_instance()` 中处理字段转换
3. 如果新字段出现在设置面板中，在 `dashboard.html` 中添加 UI 部分
4. 更新 `dashboard.js` 中的前端渲染方法

### 修改设置面板

设置部分是可折叠的：
- 部分标题具有 `onclick="toggleSettingsSection(this)"`
- 内容包裹在 `.settings-section-content` 中，默认 `display: none`
- 参考 `dashboard.html` 中的现有部分模式
