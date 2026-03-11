# LA IIoT Multi-Instance Middleware

A lightweight Windows-based Web middleware for LogicAgent (LA) industrial automation software. Supports multiple isolated instances for different production lines.

## Features

- **Multi-instance architecture** - Isolated data channels per instance
- **FastAPI backend** - WebSocket room isolation
- **Industrial dashboard** - Modern, responsive, dark theme
- **Real-time updates** - WebSocket-based data relay
- **Audio notifications** - Browser-compliant audio unlock system
- **Windows firewall** - Automated configuration

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Or use the provided batch script:

```bash
start.bat
```

### 2. Run the Server

```bash
python main.py
```

Or simply double-click `start.bat` (run as Administrator for firewall configuration).

### 3. Access the Portal

Open your browser and navigate to: `http://localhost:8000`

## API Endpoints

### Instance Management

- `GET /api/instances` - List all instances
- `POST /api/instances` - Create new instance
- `GET /api/instances/{instance_id}` - Get instance details
- `DELETE /api/instances/{instance_id}` - Remove instance

### WebSocket

- `WS /ws/{instance_id}` - Real-time data connection (room-isolated)

### Webhook

- `POST /api/{instance_id}/webhook` - Receive data from LogicAgent

### Control

- `POST /api/{instance_id}/control` - Forward commands to LogicAgent

## Configuration

Instance configurations are stored as JSON files in `configs/instances/`.

Example instance config:

```json
{
  "instance_id": "workshop_01",
  "name": "一车间实例",
  "description": "Production line A",
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

## Testing

### Multi-instance Isolation Test

```bash
# Create two instances
curl -X POST http://localhost:8000/api/instances \
  -H "Content-Type: application/json" \
  -d '{"instance_id":"test_a","name":"Test A","la_ip":"127.0.0.1","la_port":8080}'

curl -X POST http://localhost:8000/api/instances \
  -H "Content-Type: application/json" \
  -d '{"instance_id":"test_b","name":"Test B","la_ip":"127.0.0.1","la_port":8081}'

# Send webhook to A (only A should receive)
curl -X POST http://localhost:8000/api/test_a/webhook \
  -H "Content-Type: application/json" \
  -d '{"message":"Data for A"}'
```

## Project Structure

```
LA交互端/
├── main.py                 # FastAPI application
├── config_manager.py       # Instance configuration management
├── websocket_manager.py    # WebSocket connection pool
├── requirements.txt        # Python dependencies
├── start.bat              # Windows startup script
├── static/
│   ├── css/dashboard.css   # Industrial dashboard styles
│   └── js/
│       ├── portal.js       # Instance portal logic
│       ├── dashboard.js    # Dashboard interactivity
│       └── audio.js        # Audio unlock & notifications
└── templates/
    ├── index.html         # Instance management portal
    └── dashboard.html     # Instance control console
```

## License

MIT
