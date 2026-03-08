"""
Instance Configuration Manager
Handles CRUD operations for instance configurations using JSON files.
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel


class LAConfig(BaseModel):
    """LogicAgent connection configuration"""
    ip: str
    port: int


class ControlButton(BaseModel):
    """Control button configuration"""
    id: str
    label: str           # 按钮显示名称
    command: str         # 命令标识
    color: str = "blue"  # green, red, blue, orange
    endpoint: str = ""   # 发送端点路径，如 "/api/control"
    method: str = "POST" # HTTP 方法: POST, GET, PUT
    payload: dict = {}   # 发送的数据内容，如 {"action": "start", "value": 1}
    button_type: str = "command"  # command: 普通命令按钮, input: 带输入框的按钮


class AudioFile(BaseModel):
    """Custom audio file configuration"""
    id: str
    name: str
    filename: str
    url: str


class AudioAlert(BaseModel):
    """Audio alert configuration"""
    keyword: str
    sound: str
    audio_file_id: str = ""  # 关联的自定义音频文件ID
    min_interval: int = 0    # 最小报警间隔（分钟），0表示不限制


class MetricsMapping(BaseModel):
    """Metrics key mapping (LA field -> Display name)"""
    la_key: str      # LA发送的字段名
    display_name: str  # 显示名称
    unit: str = ""   # 单位
    data_type: str = "string"  # string, number, boolean
    format: str = ""  # 格式化字符串，如 %.2f


class InstanceConfig(BaseModel):
    """Complete instance configuration"""
    instance_id: str
    name: str
    description: str = ""
    la_config: LAConfig
    view_port: int = 0  # 业务视图专用端口，0表示不启用
    view_uid: str = ""  # 业务视图访问UID
    control_buttons: List[ControlButton] = []
    metrics_mappings: List[MetricsMapping] = []  # 实时指标映射配置
    metrics_mapping: Dict[str, str] = {}  # 兼容旧配置
    audio_alerts: List[AudioAlert] = []
    audio_files: List[AudioFile] = []
    audio_alert_match_enabled: bool = False  # 音频告警关键词匹配开关，默认关闭
    created_at: str = ""
    updated_at: str = ""


class ConfigManager:
    """Manages instance configurations with JSON persistence"""

    def __init__(self, config_dir: str = "configs/instances"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _get_config_path(self, instance_id: str) -> Path:
        """Get the file path for an instance config"""
        return self.config_dir / f"{instance_id}.json"

    def list_instances(self) -> List[Dict]:
        """List all instance configurations"""
        instances = []
        for config_file in self.config_dir.glob("*.json"):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Return summary without full config details
                    instances.append({
                        "instance_id": data.get("instance_id"),
                        "name": data.get("name"),
                        "description": data.get("description", ""),
                        "created_at": data.get("created_at", ""),
                        "la_ip": data.get("la_config", {}).get("ip"),
                        "la_port": data.get("la_config", {}).get("port")
                    })
            except Exception as e:
                print(f"Error loading config {config_file}: {e}")
                continue
        # Sort by created_at descending
        instances.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return instances

    def get_instance(self, instance_id: str) -> Optional[InstanceConfig]:
        """Get full configuration for a specific instance"""
        config_path = self._get_config_path(instance_id)
        if not config_path.exists():
            return None
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return InstanceConfig(**data)
        except Exception as e:
            print(f"Error reading config for {instance_id}: {e}")
            return None

    def create_instance(self, config: InstanceConfig) -> InstanceConfig:
        """Create a new instance configuration"""
        now = datetime.now().isoformat()
        config.created_at = now
        config.updated_at = now

        # Generate view UID if not provided
        if not config.view_uid:
            config.view_uid = str(uuid.uuid4())[:16]

        config_path = self._get_config_path(config.instance_id)
        if config_path.exists():
            raise ValueError(f"Instance {config.instance_id} already exists")

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config.model_dump(), f, indent=2, ensure_ascii=False)

        return config

    def update_instance(self, instance_id: str, updates: Dict) -> Optional[InstanceConfig]:
        """Update an existing instance configuration"""
        config = self.get_instance(instance_id)
        if not config:
            return None

        # Apply updates
        for key, value in updates.items():
            if key in ["instance_id", "created_at"]:
                continue

            if key == "control_buttons" and isinstance(value, list):
                # Convert dict list to ControlButton objects
                config.control_buttons = [ControlButton(**btn) for btn in value]
            elif key == "la_config" and isinstance(value, dict):
                # Update LA config
                config.la_config = LAConfig(**value)
            elif key == "audio_alerts" and isinstance(value, list):
                # Convert dict list to AudioAlert objects
                config.audio_alerts = [AudioAlert(**alert) for alert in value]
            elif key == "audio_files" and isinstance(value, list):
                # Convert dict list to AudioFile objects
                config.audio_files = [AudioFile(**f) for f in value]
            elif key == "metrics_mappings" and isinstance(value, list):
                # Convert dict list to MetricsMapping objects
                config.metrics_mappings = [MetricsMapping(**m) for m in value]
            elif key == "view_port":
                config.view_port = int(value) if value else 0
            elif key == "view_uid":
                config.view_uid = str(value) if value else ""
            elif hasattr(config, key):
                setattr(config, key, value)

        config.updated_at = datetime.now().isoformat()

        config_path = self._get_config_path(instance_id)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config.model_dump(), f, indent=2, ensure_ascii=False)

        return config

    def delete_instance(self, instance_id: str) -> bool:
        """Delete an instance configuration"""
        config_path = self._get_config_path(instance_id)
        if not config_path.exists():
            return False
        try:
            config_path.unlink()
            return True
        except Exception as e:
            print(f"Error deleting config {instance_id}: {e}")
            return False

    def instance_exists(self, instance_id: str) -> bool:
        """Check if an instance exists"""
        return self._get_config_path(instance_id).exists()

    def get_instance_by_view_uid(self, view_uid: str) -> Optional[InstanceConfig]:
        """Find instance configuration by view_uid (for business view access)"""
        if not view_uid:
            return None

        # Search through all instance configs to find matching view_uid
        for config_file in self.config_dir.glob("*.json"):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("view_uid") == view_uid:
                        return InstanceConfig(**data)
            except Exception as e:
                print(f"Error reading config {config_file}: {e}")
                continue
        return None

    def get_instance_id_by_view_uid(self, view_uid: str) -> Optional[str]:
        """Get instance_id by view_uid"""
        config = self.get_instance_by_view_uid(view_uid)
        return config.instance_id if config else None


# Default templates for new instances
DEFAULT_CONTROL_BUTTONS = [
    {"id": "start", "label": "启动生产", "command": "START_PRODUCTION", "color": "green"},
    {"id": "stop", "label": "紧急停止", "command": "EMERGENCY_STOP", "color": "red"},
    {"id": "reset", "label": "复位", "command": "RESET_SYSTEM", "color": "blue"},
    {"id": "pause", "label": "暂停", "command": "PAUSE_PRODUCTION", "color": "orange"}
]

DEFAULT_METRICS_MAPPING = {
    "cycle_time": "当前节拍",
    "total_count": "生产总数",
    "good_count": "良品数",
    "bad_count": "不良品数",
    "oee": "设备综合效率",
    "status": "运行状态"
}

DEFAULT_AUDIO_ALERTS = [
    {"keyword": "ERROR", "sound": "alert_error.mp3"},
    {"keyword": "WARNING", "sound": "alert_warn.mp3"},
    {"keyword": "STOP", "sound": "alert_stop.mp3"}
]
