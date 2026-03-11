"""
IIoT Multi-Instance Middleware for LogicAgent (LA)
FastAPI backend with WebSocket room isolation.
"""

import json
import os
import socket
import uuid
import shutil
import base64
import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config_manager import (
    ConfigManager,
    InstanceConfig,
    LAConfig,
    ControlButton,
    AudioFile,
    DEFAULT_CONTROL_BUTTONS,
    DEFAULT_METRICS_MAPPING,
    DEFAULT_AUDIO_ALERTS
)
from websocket_manager import ConnectionManager


def decode_rfc2047_header(header: str) -> str:
    """
    Decode RFC 2047 encoded header string.
    Supports both UTF-8 and GBK encodings (LA sends GBK but claims UTF-8).
    Format: =?charset?B?base64?=
    Example: =?utf-8?B?5b2T5YmN5L2c5Lia5a2U5pWw?= -> 当前作业孔数
    """
    if not header or not header.startswith('=?'):
        return header

    try:
        # Pattern: =?charset?B?base64?=
        pattern = r'=\?([^?]+)\?B\?([^?]+)\?='
        match = re.match(pattern, header, re.IGNORECASE)

        if match:
            declared_charset = match.group(1).lower()
            encoded_text = match.group(2)
            decoded_bytes = base64.b64decode(encoded_text)

            # Try declared charset first, then GBK, then UTF-8
            for charset in [declared_charset, 'gbk', 'utf-8']:
                try:
                    result = decoded_bytes.decode(charset)
                    print(f"[RFC2047] Decoded '{header}' using {charset}: '{result}'")
                    return result
                except UnicodeDecodeError:
                    continue

            # Fallback
            return decoded_bytes.decode('utf-8', errors='ignore')

        return header
    except Exception as e:
        print(f"[RFC2047 Decode Error] Failed to decode '{header}': {e}")
        return header


# Initialize managers
config_manager = ConfigManager()
websocket_manager = ConnectionManager()

# HTTP client for forwarding to LA
http_client = httpx.AsyncClient(timeout=30.0)

# Logs storage directory
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)


class LogsManager:
    """Manages persistent logs for each instance"""

    def __init__(self, logs_dir: Path = LOGS_DIR):
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(exist_ok=True)
        # Cache for in-memory logs
        self._cache: Dict[str, List[Dict]] = {}
        self._max_cache_size = 1000

    def _get_log_file(self, instance_id: str) -> Path:
        return self.logs_dir / f"{instance_id}.jsonl"

    def add_log(self, instance_id: str, log_entry: Dict):
        """Add a log entry for an instance"""
        log_file = self._get_log_file(instance_id)

        # Add timestamp if not present
        if "timestamp" not in log_entry:
            log_entry["timestamp"] = datetime.now().isoformat()

        # Append to file
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        # Update cache
        if instance_id not in self._cache:
            self._cache[instance_id] = []
        self._cache[instance_id].append(log_entry)

        # Trim cache if too large
        if len(self._cache[instance_id]) > self._max_cache_size:
            self._cache[instance_id] = self._cache[instance_id][-self._max_cache_size:]

    def get_logs(self, instance_id: str, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Get logs for an instance"""
        log_file = self._get_log_file(instance_id)

        if not log_file.exists():
            return []

        logs = []
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            logs.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            print(f"[LogsManager] Error reading logs for {instance_id}: {e}")

        # Return paginated results (newest first)
        logs.reverse()
        start = offset
        end = offset + limit
        return logs[start:end]

    def clear_logs(self, instance_id: str):
        """Clear logs for an instance"""
        log_file = self._get_log_file(instance_id)
        if log_file.exists():
            log_file.unlink()
        if instance_id in self._cache:
            del self._cache[instance_id]


logs_manager = LogsManager()

# Single-instance mode configuration
# If INSTANCE_ID is set, this service only serves that specific instance
SINGLE_INSTANCE_ID = os.getenv("INSTANCE_ID", None)
SINGLE_INSTANCE_MODE = SINGLE_INSTANCE_ID is not None
if SINGLE_INSTANCE_MODE:
    print(f"[Config] Running in SINGLE-INSTANCE mode for: {SINGLE_INSTANCE_ID}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    print("[Startup] IIoT Multi-Instance Middleware starting...")
    yield
    # Shutdown
    print("[Shutdown] Closing WebSocket connections...")
    await websocket_manager.close_all_connections()
    await http_client.aclose()
    print("[Shutdown] Complete.")


# Create FastAPI app
app = FastAPI(
    title="LA IIoT Middleware",
    description="Multi-instance WebSocket middleware for LogicAgent",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")


# ============================================================================
# Frontend Routes
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Instance management portal (or single instance dashboard)"""
    # In single-instance mode, redirect to the dedicated dashboard
    if SINGLE_INSTANCE_MODE:
        if not config_manager.instance_exists(SINGLE_INSTANCE_ID):
            raise HTTPException(status_code=404, detail=f"Instance {SINGLE_INSTANCE_ID} not found")

        instance = config_manager.get_instance(SINGLE_INSTANCE_ID)
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "instance_id": SINGLE_INSTANCE_ID,
                "instance": instance.model_dump() if instance else {},
                "single_instance_mode": True
            }
        )

    # Multi-instance mode: show portal
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/{instance_id}/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, instance_id: str):
    """Instance control console"""
    # In single-instance mode, only allow access to the configured instance
    if SINGLE_INSTANCE_MODE and instance_id != SINGLE_INSTANCE_ID:
        raise HTTPException(status_code=403, detail="Access denied: this instance is not served on this port")

    # Verify instance exists
    if not config_manager.instance_exists(instance_id):
        raise HTTPException(status_code=404, detail="Instance not found")

    instance = config_manager.get_instance(instance_id)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "instance_id": instance_id,
            "instance": instance.model_dump() if instance else {},
            "single_instance_mode": SINGLE_INSTANCE_MODE and instance_id == SINGLE_INSTANCE_ID
        }
    )


@app.get("/view/{view_uid}", response_class=HTMLResponse)
async def business_view_by_uid(request: Request, view_uid: str):
    """
    Business view accessed directly by UID (format: http://host:port/view/uid).
    This is a read-only view without control panel.
    """
    # Find instance by view_uid
    instance = None
    instance_id = None

    # Use the new method to find instance by view_uid
    instance = config_manager.get_instance_by_view_uid(view_uid)

    if not instance:
        raise HTTPException(status_code=404, detail="Invalid access key")

    instance_id = instance.instance_id

    # If in single-instance mode, verify this instance matches
    if SINGLE_INSTANCE_MODE and instance_id != SINGLE_INSTANCE_ID:
        raise HTTPException(status_code=403, detail="Access denied")

    return templates.TemplateResponse(
        "business_view.html",
        {
            "request": request,
            "instance_id": instance_id,
            "instance": instance.model_dump(),
            "view_uid": view_uid,
            "view_url": f"/view/{view_uid}"
        }
    )


# ============================================================================
# API Routes - Instance Management
# ============================================================================

@app.get("/api/server-info")
async def get_server_info():
    """获取服务器信息，包括IP地址"""
    try:
        # 获取本机IP地址
        hostname = socket.gethostname()
        # 尝试获取外部可达的IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # 连接一个公共DNS服务器来确定本机IP
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()

        return {
            "ip": ip,
            "hostname": hostname,
            "port": 8000  # 主服务端口
        }
    except Exception as e:
        return {"ip": "127.0.0.1", "hostname": "localhost", "port": 8000}


@app.get("/api/instances")
async def list_instances():
    """List all instances"""
    return {"instances": config_manager.list_instances()}


@app.post("/api/instances")
async def create_instance(data: Dict[str, Any]):
    """Create a new instance"""
    try:
        # Build instance config
        instance_id = data.get("instance_id", "").strip()
        if not instance_id:
            raise HTTPException(status_code=400, detail="instance_id is required")

        # Check if exists
        if config_manager.instance_exists(instance_id):
            raise HTTPException(status_code=409, detail=f"Instance '{instance_id}' already exists")

        # Build control buttons from form or use defaults
        control_buttons = []
        if data.get("control_buttons"):
            for btn in data["control_buttons"]:
                control_buttons.append(ControlButton(**btn))
        else:
            control_buttons = [ControlButton(**btn) for btn in DEFAULT_CONTROL_BUTTONS]

        config = InstanceConfig(
            instance_id=instance_id,
            name=data.get("name", instance_id),
            description=data.get("description", ""),
            la_config=LAConfig(
                ip=data.get("la_ip", "127.0.0.1"),
                port=data.get("la_port", 8080)
            ),
            control_buttons=control_buttons,
            metrics_mapping=data.get("metrics_mapping", DEFAULT_METRICS_MAPPING),
            audio_alerts=[{"keyword": k, "sound": s} for k, s in DEFAULT_AUDIO_ALERTS]
        )

        created = config_manager.create_instance(config)
        instance_data = created.model_dump()
        # Include view_url in response
        instance_data["view_url"] = f"/view/{created.view_uid}" if created.view_uid else None
        return {"success": True, "instance": instance_data}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/instances/{instance_id}")
async def get_instance(instance_id: str):
    """Get instance details"""
    instance = config_manager.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    instance_data = instance.model_dump()
    # Include view_url in response
    instance_data["view_url"] = f"/view/{instance.view_uid}" if instance.view_uid else None
    return {"instance": instance_data}


@app.get("/api/view/{view_uid}")
async def get_instance_by_view_uid(view_uid: str):
    """Get instance details by view_uid (for business view access)

    Business views use this endpoint to fetch the parent instance configuration.
    This ensures business views always reflect the console's current settings.
    """
    instance = config_manager.get_instance_by_view_uid(view_uid)
    if not instance:
        raise HTTPException(status_code=404, detail="Invalid view key")

    instance_data = instance.model_dump()
    instance_data["view_url"] = f"/view/{view_uid}"
    return {"instance": instance_data}


@app.delete("/api/instances/{instance_id}")
async def delete_instance(instance_id: str):
    """Delete an instance"""
    if not config_manager.instance_exists(instance_id):
        raise HTTPException(status_code=404, detail="Instance not found")

    success = config_manager.delete_instance(instance_id)
    return {"success": success}


@app.put("/api/instances/{instance_id}")
async def update_instance(instance_id: str, data: Dict[str, Any]):
    """Update instance configuration"""
    if not config_manager.instance_exists(instance_id):
        raise HTTPException(status_code=404, detail="Instance not found")

    updated = config_manager.update_instance(instance_id, data)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update instance")

    return {"success": True, "instance": updated.model_dump()}


@app.get("/api/{instance_id}/logs")
async def get_instance_logs(instance_id: str, limit: int = 100, offset: int = 0):
    """Get persistent logs for an instance"""
    if not config_manager.instance_exists(instance_id):
        raise HTTPException(status_code=404, detail="Instance not found")

    logs = logs_manager.get_logs(instance_id, limit=limit, offset=offset)
    return {"logs": logs, "total": len(logs)}


@app.post("/api/{instance_id}/logs")
async def add_instance_log(instance_id: str, log_data: Dict[str, Any]):
    """Add a log entry for an instance"""
    if not config_manager.instance_exists(instance_id):
        raise HTTPException(status_code=404, detail="Instance not found")

    logs_manager.add_log(instance_id, log_data)
    return {"success": True}


@app.delete("/api/{instance_id}/logs")
async def clear_instance_logs(instance_id: str):
    """Clear all logs for an instance"""
    if not config_manager.instance_exists(instance_id):
        raise HTTPException(status_code=404, detail="Instance not found")

    logs_manager.clear_logs(instance_id)
    return {"success": True}


# ============================================================================
# WebSocket Endpoint - Room Isolation
# ============================================================================

@app.websocket("/ws/{instance_id}")
async def websocket_endpoint(websocket: WebSocket, instance_id: str):
    """
    WebSocket endpoint with room isolation.
    Each instance has its own room - data never crosses between instances.
    """
    # Verify instance exists
    if not config_manager.instance_exists(instance_id):
        await websocket.close(code=4004, reason="Instance not found")
        return

    # Accept connection
    connected = await websocket_manager.connect(websocket, instance_id)
    if not connected:
        return

    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "connection",
            "status": "connected",
            "instance_id": instance_id,
            "timestamp": datetime.now().isoformat()
        })

        # Keep connection alive and handle client messages
        while True:
            try:
                # Receive message (can be used for ping/keepalive or commands)
                message = await websocket.receive_json()

                # Handle ping
                if message.get("type") == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.now().isoformat()
                    })

                # Handle subscription requests or other client commands
                elif message.get("type") == "subscribe":
                    await websocket.send_json({
                        "type": "subscribed",
                        "instance_id": instance_id
                    })

                # Handle config sync from dashboard to business view
                elif message.get("type") == "config_sync":
                    # Broadcast config to all clients in the room (including business views)
                    await websocket_manager.broadcast_to_room(instance_id, message)
                    print(f"[WebSocket] Config sync broadcasted to room '{instance_id}'")

            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"[WebSocket] Error in room '{instance_id}': {e}")
                break

    except WebSocketDisconnect:
        pass
    finally:
        websocket_manager.disconnect(websocket, instance_id)


# ============================================================================
# Webhook Receiver - Real-time Data Relay
# ============================================================================

@app.post("/api/{instance_id}/webhook")
async def receive_webhook(instance_id: str, request: Request):
    """
    Receive data from LogicAgent via webhook.
    Supports JSON and multipart/form-data formats.
    Broadcasts to all WebSocket clients in the instance's room.
    """
    # Verify instance exists
    if not config_manager.instance_exists(instance_id):
        raise HTTPException(status_code=404, detail="Instance not found")

    try:
        content_type = request.headers.get("content-type", "").lower()
        print(f"[Webhook] Content-Type: {content_type}")
        payload = {}

        # Handle multipart/form-data
        if "multipart/form-data" in content_type:
            print("[Webhook] Processing as multipart/form-data")
            try:
                form_data = await request.form()
                payload = {}
                print(f"[Webhook] Parsed form data fields: {list(form_data.keys())}")
                for key in form_data.keys():
                    value = form_data[key]
                    # Decode base64 encoded field names (RFC 2047 format: =?charset?B?base64?=)
                    decoded_key = decode_rfc2047_header(key)
                    print(f"[Webhook] Field: '{key}' -> '{decoded_key}' = '{value}'")
                    payload[decoded_key] = value
            except Exception as form_error:
                print(f"[Webhook] Form parsing error: {form_error}")
                # Fallback to raw body
                body = await request.body()
                payload = {"raw": body.decode("utf-8", errors="ignore")}
        else:
            print(f"[Webhook] Not multipart, trying JSON")
            # Try JSON parsing
            try:
                payload = await request.json()
                print(f"[Webhook] JSON parsed: {payload}")
            except json.JSONDecodeError as e:
                print(f"[Webhook] JSON decode error: {e}")
                # Handle plain text or other formats
                body = await request.body()
                payload = {"raw": body.decode("utf-8", errors="ignore")}

        # Add metadata
        message = {
            "type": "data",
            "instance_id": instance_id,
            "timestamp": datetime.now().isoformat(),
            "payload": payload
        }

        # Broadcast to instance room
        recipient_count = await websocket_manager.broadcast_to_room(instance_id, message)

        return {
            "success": True,
            "broadcast_to": recipient_count,
            "instance_id": instance_id,
            "payload": payload
        }

    except Exception as e:
        print(f"[Webhook Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Alert Receiver - From LogicAgent
# ============================================================================

@app.post("/api/{instance_id}/alert")
async def receive_alert(instance_id: str, request: Request):
    """
    Receive alert/notification from LogicAgent.
    Supports both JSON and form-data requests.
    Broadcasts to WebSocket clients and triggers audio alerts.
    """
    if not config_manager.instance_exists(instance_id):
        raise HTTPException(status_code=404, detail="Instance not found")

    try:
        print(f"\n[Alert] ========== 收到来自 {instance_id} 的告警请求 ==========")

        content_type = request.headers.get("content-type", "").lower()
        body = await request.body()
        body_text = body.decode("utf-8", errors="ignore")

        # 详细日志记录
        print(f"[Alert] Method: {request.method}")
        print(f"[Alert] Content-Type: {content_type}")
        print(f"[Alert] Raw body: {body_text[:1000]}")
        print(f"[Alert] Query params: {dict(request.query_params)}")

        payload = {}

        # Try to parse based on content type
        if "application/json" in content_type:
            try:
                payload = json.loads(body_text) if body_text.strip() else {}
                print(f"[Alert] Parsed as JSON: {payload}")
            except json.JSONDecodeError as e:
                print(f"[Alert] JSON parse error: {e}, trying form parse...")
                # Fallback to form parsing
                from urllib.parse import parse_qs
                parsed = parse_qs(body_text)
                payload = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
                print(f"[Alert] Parsed as query string: {payload}")
        elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            # Handle form data
            form_data = await request.form()
            payload = dict(form_data)
            print(f"[Alert] Parsed as form data: {payload}")
        else:
            # Try JSON first
            try:
                payload = json.loads(body_text) if body_text.strip() else {}
                print(f"[Alert] Parsed as JSON (fallback): {payload}")
            except:
                # Try to parse as query string
                from urllib.parse import parse_qs
                parsed = parse_qs(body_text)
                payload = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
                print(f"[Alert] Parsed as query string (fallback): {payload}")

        # If still empty, try to get from query params
        if not payload:
            payload = dict(request.query_params)
            print(f"[Alert] Using query params as payload: {payload}")

        print(f"[Alert] Final payload from {instance_id}: {payload}")

        # Determine alert level and message - 支持多种字段名
        # level: level, type, alert_type, severity
        level = (
            payload.get("level")
            or payload.get("type")
            or payload.get("alert_type")
            or payload.get("severity")
            or "info"
        )

        # message: message, msg, content, text, info, description
        message = (
            payload.get("message")
            or payload.get("msg")
            or payload.get("content")
            or payload.get("text")
            or payload.get("info")
            or payload.get("description")
            or ""
        )

        alert_type = payload.get("alert_type") or payload.get("alertType") or "ALERT"

        if not message:
            message = str(payload)

        print(f"[Alert] Extracted -> level: {level}, message: {message}, type: {alert_type}")

        # Build alert message
        alert_data = {
            "type": "alert",
            "instance_id": instance_id,
            "timestamp": datetime.now().isoformat(),
            "payload": {
                "level": level,
                "message": message,
                "type": alert_type,
                **{k: v for k, v in payload.items() if k not in ["level", "message", "type"]}
            }
        }

        # Broadcast to instance room
        recipient_count = await websocket_manager.broadcast_to_room(instance_id, alert_data)
        print(f"[Alert] Broadcasted to {recipient_count} clients")

        return {
            "success": True,
            "broadcast_to": recipient_count,
            "instance_id": instance_id,
            "level": level,
            "message": message
        }

    except Exception as e:
        print(f"[Alert] Error processing alert: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/{instance_id}/alert")
async def receive_alert_get(instance_id: str, message: str = "", level: str = "info"):
    """
    Simple GET endpoint for receiving alerts from LA.
    Usage: /api/line1/alert?message=设备故障&level=error
    """
    if not config_manager.instance_exists(instance_id):
        raise HTTPException(status_code=404, detail="Instance not found")

    print(f"\n[Alert] ========== GET 请求来自 {instance_id} ==========")
    print(f"[Alert] message: {message}, level: {level}")

    alert_data = {
        "type": "alert",
        "instance_id": instance_id,
        "timestamp": datetime.now().isoformat(),
        "payload": {
            "level": level,
            "message": message,
            "type": "ALERT"
        }
    }

    recipient_count = await websocket_manager.broadcast_to_room(instance_id, alert_data)
    print(f"[Alert] Broadcasted to {recipient_count} clients")

    return {
        "success": True,
        "broadcast_to": recipient_count,
        "instance_id": instance_id
    }


@app.post("/api/{instance_id}/alert-debug")
async def alert_debug(instance_id: str, request: Request):
    """
    调试端点：返回解析后的请求数据，用于诊断LA表单提交问题
    """
    if not config_manager.instance_exists(instance_id):
        raise HTTPException(status_code=404, detail="Instance not found")

    content_type = request.headers.get("content-type", "").lower()
    headers = dict(request.headers)
    query_params = dict(request.query_params)

    # 读取原始body
    body = await request.body()
    body_text = body.decode("utf-8", errors="ignore")

    result = {
        "instance_id": instance_id,
        "content_type": content_type,
        "headers": {k: v for k, v in headers.items() if k.lower() not in ["authorization", "cookie"]},
        "query_params": query_params,
        "raw_body": body_text,
        "parsed_payload": {},
        "extraction": {
            "level_candidates": {},
            "message_candidates": {}
        }
    }

    # 尝试各种解析方式
    payload = {}

    # JSON解析
    if "application/json" in content_type:
        try:
            payload = json.loads(body_text) if body_text.strip() else {}
            result["parsed_method"] = "json"
        except:
            from urllib.parse import parse_qs
            parsed = parse_qs(body_text)
            payload = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
            result["parsed_method"] = "query_string_fallback"
    elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form_data = await request.form()
        payload = dict(form_data)
        result["parsed_method"] = "form_data"
    else:
        try:
            payload = json.loads(body_text) if body_text.strip() else {}
            result["parsed_method"] = "json_fallback"
        except:
            from urllib.parse import parse_qs
            parsed = parse_qs(body_text)
            payload = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
            result["parsed_method"] = "query_string"

    if not payload:
        payload = query_params
        result["parsed_method"] = "query_params"

    result["parsed_payload"] = payload

    # 尝试提取各种可能的字段
    level_fields = ["level", "type", "alert_type", "severity", "alertType", "alert_level"]
    for field in level_fields:
        if field in payload:
            result["extraction"]["level_candidates"][field] = payload[field]

    message_fields = ["message", "msg", "content", "text", "info", "description", "body", "data"]
    for field in message_fields:
        if field in payload:
            result["extraction"]["message_candidates"][field] = payload[field]

    # 建议
    suggestions = []
    if not result["extraction"]["message_candidates"]:
        suggestions.append("LA 表单中没有找到 message/msg/content/text 等字段，请检查LA发送的字段名")
    if not result["extraction"]["level_candidates"]:
        suggestions.append("LA 表单中没有找到 level/type/severity 等字段，将使用默认值 'info'")

    result["suggestions"] = suggestions

    print(f"\n[Alert-Debug] Debug request from {instance_id}:")
    print(f"[Alert-Debug] Content-Type: {content_type}")
    print(f"[Alert-Debug] Parsed: {payload}")

    return result


def _replace_input_placeholder(obj: Any, input_value: Any) -> Any:
    """
    递归替换 payload 中的 {{input}} 占位符为用户输入的值。
    支持字符串、字典、列表等各种类型。
    """
    if isinstance(obj, str):
        if obj == "{{input}}":
            return input_value
        return obj.replace("{{input}}", str(input_value))
    elif isinstance(obj, dict):
        return {k: _replace_input_placeholder(v, input_value) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_replace_input_placeholder(item, input_value) for item in obj]
    return obj


# ============================================================================
# Control Forwarder - Frontend to LA
# ============================================================================

@app.post("/api/{instance_id}/control")
async def forward_control(instance_id: str, data: Dict[str, Any]):
    """
    Forward control commands from frontend to LogicAgent.
    Supports button-specific configuration for endpoint, method, and payload.
    Returns LA response to frontend.
    """
    # Get instance config
    instance = config_manager.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    # Get button configuration if button_id is provided
    button_id = data.get("button_id")
    button_config = None
    if button_id:
        for btn in instance.control_buttons:
            if btn.id == button_id:
                button_config = btn
                break

    try:
        # Determine target URL and method
        if button_config and button_config.endpoint:
            # Use button-specific endpoint
            endpoint = button_config.endpoint
            if not endpoint.startswith("/"):
                endpoint = "/" + endpoint
            la_url = f"http://{instance.la_config.ip}:{instance.la_config.port}{endpoint}"
        else:
            # Default endpoint
            la_url = f"http://{instance.la_config.ip}:{instance.la_config.port}/api/control"

        # Determine HTTP method
        method = "POST"
        if button_config and button_config.method:
            method = button_config.method.upper()

        # Build payload
        if button_config and button_config.payload:
            # Use button-specific payload as base
            command_data = {
                **button_config.payload,
                "_middleware": {
                    "instance_id": instance_id,
                    "button_id": button_id,
                    "forwarded_at": datetime.now().isoformat()
                }
            }
            # 处理输入按钮的值替换
            # 支持在 payload 中使用 {{input}} 占位符，会被替换为用户输入的值
            input_value = data.get("extra_data", {}).get("input_value")
            print(f"[Control] Received input_value: {input_value}, type: {type(input_value)}")
            print(f"[Control] Before replace: {command_data}")
            if input_value is not None:
                command_data = _replace_input_placeholder(command_data, input_value)
                print(f"[Control] After replace: {command_data}")
        else:
            # Use frontend data
            command_data = {
                **{k: v for k, v in data.items() if k not in ["button_id", "extra_data"]},
                "_middleware": {
                    "instance_id": instance_id,
                    "forwarded_at": datetime.now().isoformat()
                }
            }

        # Forward to LA with appropriate method
        print(f"[Control] Sending to LA: {method} {la_url}")
        print(f"[Control] Request data: {command_data}")

        try:
            if method == "GET":
                response = await http_client.get(la_url, params=command_data)
            elif method == "PUT":
                response = await http_client.put(la_url, json=command_data)
            else:  # POST
                response = await http_client.post(la_url, json=command_data)

            print(f"[Control] Raw response: status={response.status_code}, headers={dict(response.headers)}")
        except httpx.TimeoutException as e:
            print(f"[Control] Timeout error: {e}")
            return {
                "success": True,  # 超时视为成功
                "status_code": 504,
                "method": method,
                "url": la_url,
                "la_response": {},
                "warning": "LA响应超时(30s)，但命令可能已执行"
            }
        except Exception as e:
            print(f"[Control] Request error: {type(e).__name__}: {e}")
            raise

        # Return LA response
        try:
            response_data = response.json()
        except:
            response_data = {"raw_response": response.text}

        print(f"[Control] LA response: status={response.status_code}, data={response_data}")

        # 504 超时特殊处理 - LA可能已收到命令但响应超时
        is_success = response.status_code < 400
        error_msg = None
        if response.status_code == 504:
            is_success = True  # 视为成功，因为LA可能已收到
            error_msg = "LA响应超时，但命令可能已执行"

        return {
            "success": is_success,
            "status_code": response.status_code,
            "method": method,
            "url": la_url,
            "la_response": response_data,
            "warning": error_msg
        }

    except httpx.ConnectError:
        return {
            "success": False,
            "error": f"Cannot connect to LogicAgent at {instance.la_config.ip}:{instance.la_config.port}",
            "la_unreachable": True
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================================
# Audio File Management
# ============================================================================

AUDIO_DIR = Path("static/audio")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


@app.post("/api/{instance_id}/audio/upload")
async def upload_audio(instance_id: str, file: UploadFile = File(...), name: str = ""):
    """
    Upload custom audio file for an instance.
    Supports mp3, wav, ogg formats.
    """
    if not config_manager.instance_exists(instance_id):
        raise HTTPException(status_code=404, detail="Instance not found")

    # Validate file extension
    allowed_extensions = {'.mp3', '.wav', '.ogg', '.m4a'}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Unsupported file format. Allowed: {allowed_extensions}")

    # Generate unique filename
    file_id = str(uuid.uuid4())[:8]
    safe_filename = f"{instance_id}_{file_id}{file_ext}"
    file_path = AUDIO_DIR / safe_filename

    try:
        # Save file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Add to instance config
        instance = config_manager.get_instance(instance_id)
        audio_file = AudioFile(
            id=file_id,
            name=name or file.filename,
            filename=safe_filename,
            url=f"/static/audio/{safe_filename}"
        )

        if not instance.audio_files:
            instance.audio_files = []
        instance.audio_files.append(audio_file)

        # Update instance
        config_manager.update_instance(instance_id, {
            "audio_files": [f.model_dump() for f in instance.audio_files]
        })

        return {
            "success": True,
            "file": audio_file.model_dump(),
            "message": "Audio file uploaded successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")


@app.get("/api/{instance_id}/audio")
async def list_audio_files(instance_id: str):
    """List all audio files for an instance"""
    if not config_manager.instance_exists(instance_id):
        raise HTTPException(status_code=404, detail="Instance not found")

    instance = config_manager.get_instance(instance_id)
    return {
        "audio_files": [f.model_dump() for f in (instance.audio_files or [])]
    }


@app.delete("/api/{instance_id}/audio/{file_id}")
async def delete_audio_file(instance_id: str, file_id: str):
    """Delete an audio file"""
    if not config_manager.instance_exists(instance_id):
        raise HTTPException(status_code=404, detail="Instance not found")

    instance = config_manager.get_instance(instance_id)
    if not instance.audio_files:
        raise HTTPException(status_code=404, detail="No audio files found")

    # Find file
    audio_file = None
    for f in instance.audio_files:
        if f.id == file_id:
            audio_file = f
            break

    if not audio_file:
        raise HTTPException(status_code=404, detail="Audio file not found")

    try:
        # Delete physical file
        file_path = AUDIO_DIR / audio_file.filename
        if file_path.exists():
            file_path.unlink()

        # Remove from config
        instance.audio_files = [f for f in instance.audio_files if f.id != file_id]
        config_manager.update_instance(instance_id, {
            "audio_files": [f.model_dump() for f in instance.audio_files]
        })

        return {"success": True, "message": "Audio file deleted"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")


# ============================================================================
# Health & Status
# ============================================================================

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "websocket_rooms": websocket_manager.get_all_rooms(),
        "instances": len(config_manager.list_instances())
    }


@app.get("/api/{instance_id}/status")
async def instance_status(instance_id: str):
    """Get real-time status for an instance"""
    if not config_manager.instance_exists(instance_id):
        raise HTTPException(status_code=404, detail="Instance not found")

    return {
        "instance_id": instance_id,
        "connected_clients": websocket_manager.get_room_size(instance_id),
        "timestamp": datetime.now().isoformat()
    }


@app.post("/api/{instance_id}/metrics")
async def receive_metrics(instance_id: str, request: Request):
    """
    Receive real-time metrics data from LogicAgent.
    Similar to webhook but specifically for metrics data.
    Broadcasts to all WebSocket clients in the instance's room.

    Expected payload format:
    {
        "cycle_time": 12.5,
        "total_count": 1000,
        "good_count": 995,
        "bad_count": 5,
        "oee": 85.5,
        "status": "running"
    }
    """
    if not config_manager.instance_exists(instance_id):
        raise HTTPException(status_code=404, detail="Instance not found")

    try:
        content_type = request.headers.get("content-type", "").lower()

        # Parse JSON payload
        if "application/json" in content_type:
            payload = await request.json()
        else:
            # Try to parse as JSON anyway
            body = await request.body()
            payload = json.loads(body.decode("utf-8", errors="ignore"))

        # Add metadata
        message = {
            "type": "data",
            "instance_id": instance_id,
            "timestamp": datetime.now().isoformat(),
            "payload": payload
        }

        # Broadcast to instance room
        recipient_count = await websocket_manager.broadcast_to_room(instance_id, message)

        return {
            "success": True,
            "broadcast_to": recipient_count,
            "instance_id": instance_id,
            "metrics_received": list(payload.keys()) if isinstance(payload, dict) else []
        }

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process metrics: {str(e)}")


# ============================================================================
# Read-Only View Routes
# ============================================================================

@app.get("/{instance_id}/view", response_class=HTMLResponse)
async def readonly_view(request: Request, instance_id: str):
    """
    Read-only view for business users.
    Shows real-time metrics and logs, but no control panel.
    """
    if not config_manager.instance_exists(instance_id):
        raise HTTPException(status_code=404, detail="Instance not found")

    instance = config_manager.get_instance(instance_id)

    return templates.TemplateResponse("readonly.html", {
        "request": request,
        "instance_id": instance_id,
        "instance": instance.model_dump()
    })


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    import logging
    import sys

    # 修复 PyInstaller 打包后的 isatty 问题
    # 强制创建有效的 stdout/stderr
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w')

    # 配置简单日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    # Get configuration from environment
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    reload = os.getenv("RELOAD", "false").lower() == "true"

    if SINGLE_INSTANCE_MODE:
        print(f"""
    ╔══════════════════════════════════════════════════════════════╗
    ║           LA IIoT Single-Instance Service                    ║
    ╠══════════════════════════════════════════════════════════════╣
    ║  Instance:   {SINGLE_INSTANCE_ID:<46} ║
    ║  Server:     http://{host}:{port}{' ' * (27 - len(str(port)))} ║
    ║  Direct URL: http://{host}:{port}/                          ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    else:
        print(f"""
    ╔══════════════════════════════════════════════════════════════╗
    ║           LA IIoT Multi-Instance Middleware                  ║
    ╠══════════════════════════════════════════════════════════════╣
    ║  Server: http://{host}:{port}                               ║
    ║  API Docs: http://{host}:{port}/docs                        ║
    ╚══════════════════════════════════════════════════════════════╝
    """)

    # 使用自定义日志配置
    try:
        uvicorn.run(
            app,
            host=host,
            port=port,
            reload=reload,
            log_level="info",
            access_log=True
        )
    except Exception as e:
        print(f"\n[错误] 服务启动失败: {e}")
        import traceback
        traceback.print_exc()
        print("\n按任意键退出...")
        input()
        sys.exit(1)
