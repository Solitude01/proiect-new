# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LA交互端 is an IIoT multi-instance middleware system for LogicAgent (LA) industrial automation software. It receives webhook data from LA and pushes it to browsers via WebSocket, with complete data isolation between instances.

## Development Commands

### Run Development Server

```bash
# Single service mode (console only)
python main.py

# Multi-service mode (console + business view)
python start_all.py

# Or using batch files
start.bat          # Single console service
start_all.bat      # Both services
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run Single Instance Mode (for business isolation)

```bash
# Format: python start_instance.py <instance_id> <port>
python start_instance.py line1 8001
```

### Build Executables

```bash
# Build LAdmin.exe (console) and LView.exe (business view)
pyinstaller LAdmin.spec
pyinstaller LView.spec

# Or use the batch file
build_exe.bat
```

### Testing

This project has no automated test suite. Test manually via the API endpoints or browser.

## Architecture

### Multi-Instance Data Isolation

The system uses a **room-based WebSocket isolation** pattern:

- Each instance has its own WebSocket "room" (`websocket_manager.py`)
- Messages are broadcast only to connections in the same room
- This ensures production data from Line A never appears on Line B's dashboard

Key files:
- `websocket_manager.py` - ConnectionManager class handles room isolation
- `main.py` - WebSocket endpoint at `/ws/{instance_id}` joins clients to rooms

### Configuration Persistence

Instance configs are stored as JSON files in `configs/instances/{instance_id}.json`:

```python
# config_manager.py
class InstanceConfig(BaseModel):
    instance_id: str
    name: str
    la_config: LAConfig          # LA connection (IP, port)
    view_port: int               # Business view port (0 = disabled)
    view_uid: str                # Business view access UID
    control_buttons: List[ControlButton]
    metrics_mappings: List[MetricsMapping]
    audio_alerts: List[AudioAlert]
    audio_files: List[AudioFile]
```

### Dual-Port Architecture

Two separate HTTP services run the same FastAPI app:

1. **Console Service (port 8000)** - Full management access
2. **Business View Service (port 6010)** - Read-only dashboard for operators

Business views are accessed via `/{view_uid}` and inherit parent console configuration.

**Important**: Port 6000-6009 are Chrome unsafe ports - use 6010+ instead.

### Key API Endpoints

```
POST /api/instances              # Create instance
GET  /api/instances/{id}         # Get instance config
POST /api/{id}/webhook           # Receive LA data
WS   /ws/{id}                    # WebSocket connection
POST /api/{id}/control           # Forward command to LA
GET  /api/{id}/logs              # Get persistent logs
GET  /view/{view_uid}            # Business view access
```

### Frontend Structure

- `templates/index.html` - Instance management portal
- `templates/dashboard.html` - Full console with settings
- `templates/business_view.html` - Operator dashboard (inherits config)
- `static/js/dashboard.js` - Main dashboard logic (75KB, uses class-based architecture)
- `static/js/business_view.js` - Business view logic
- `static/js/audio.js` - Audio unlock and notification system

### Logs Persistence

Logs are stored in JSONL format (`logs/{instance_id}.jsonl`):

```python
# main.py - LogsManager class
logs_manager.add_log(instance_id, {
    "type": "system|webhook|control|alert",
    "message": "...",
    "timestamp": "..."
})
```

## Dependencies

- **fastapi** + **uvicorn** - Web framework and ASGI server
- **jinja2** - Template engine
- **aiofiles** - Async file I/O
- **httpx** - Async HTTP client (for forwarding commands to LA)
- **python-multipart** - Form data parsing

## Key Implementation Details

### Webhook Decoding

LA sends data with RFC 2047 encoded headers (GBK charset but may claim UTF-8). The webhook handler in `main.py` decodes these headers before broadcasting.

### WebSocket Heartbeat

The frontend sends a ping every 5 seconds; if no pong is received within 30 seconds, it reconnects with exponential backoff (capped at 30s). This keeps connections alive through network middleware that drops idle TCP connections.

## Code Patterns

### Adding New WebSocket Message Type

1. Add handler in `dashboard.js` or `business_view.js`:
```javascript
// In dashboard.js handleWebSocketMessage()
case 'NEW_TYPE':
    this.handleNewType(data.payload);
    break;
```

2. Broadcast from main.py:
```python
await websocket_manager.broadcast_to_room(instance_id, {
    "type": "NEW_TYPE",
    "payload": {...}
})
```

### Configuration Updates

Settings panel uses temporary state that applies on save:

```javascript
// dashboard.js pattern
this.tempSettings = { ...this.instanceConfig };  // Clone on open
// User edits tempSettings
// On save: POST /api/instances/{id}/config with tempSettings
```

### Audio Alert System

Audio alerts trigger based on WebSocket message keywords:

```javascript
// Check alerts in message handler
this.config.audio_alerts.forEach(alert => {
    if (message.includes(alert.keyword)) {
        this.audioManager.playAlert(alert.sound);
    }
});
```

## File Structure

```
LA交互端/
├── main.py                    # FastAPI app, webhook handlers, logs
├── config_manager.py          # Pydantic models + ConfigManager
├── websocket_manager.py       # Room-based WebSocket isolation
├── start_all.py              # Launches both console + business services
├── start_instance.py         # Single-instance mode launcher
├── configs/instances/*.json  # Instance configurations
├── logs/*.jsonl              # Persistent logs per instance
├── static/audio/             # Custom audio uploads
├── templates/
│   ├── index.html           # Portal page
│   ├── dashboard.html       # Full console
│   └── business_view.html   # Operator view
└── static/js/
    ├── dashboard.js         # Main console (class Dashboard)
    ├── business_view.js     # Business view
    ├── portal.js            # Instance management
    └── audio.js             # Audio unlock/notifications
```

## Common Tasks

### Add New Config Field

1. Add to `config_manager.py` model (InstanceConfig or nested model)
2. Update `update_instance()` in ConfigManager to handle field conversion
3. Update UI rendering in `dashboard.js` render methods
4. Update template in `dashboard.html` if needed

### Modify Settings Panel

Settings sections are collapsible:
- Section headers have `onclick="toggleSettingsSection(this)"`
- Content is wrapped in `.settings-section-content` with `display: none` default
- See existing sections in `dashboard.html` for pattern

### Test WebSocket Isolation

```bash
# Create two instances
curl -X POST http://localhost:8000/api/instances \
  -H "Content-Type: application/json" \
  -d '{"instance_id":"test_a","name":"A","la_ip":"127.0.0.1","la_port":8080}'

# Send to A only
curl -X POST http://localhost:8000/api/test_a/webhook \
  -d '{"message":"Only A should see this"}'
```
