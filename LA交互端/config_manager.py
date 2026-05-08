"""
Instance Configuration Manager
Handles CRUD operations for instance configurations using JSON files.
"""

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


def _get_config_base_dir() -> str:
    """Return the base directory for config storage.

    In development, resolves relative to CWD.
    When packaged by PyInstaller, resolves relative to the directory
    containing the EXE so that configs persist across runs.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(".")


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
    filename: str = ""  # 默认为空字符串，兼容旧数据
    url: str


class AudioAlert(BaseModel):
    """Audio alert configuration"""
    name: str = ""           # 规则自定义名称
    keyword: str
    sound: str
    audio_file_id: str = ""  # 关联的自定义音频文件ID
    min_interval: int = 0    # 最小报警间隔（分钟），0表示不限制
    enabled: bool = True     # 启用/禁用开关


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
    enabled: bool = True  # 实例启用/禁用开关，默认启用
    la_config: LAConfig
    view_port: int = 0  # 业务视图专用端口，0表示不启用
    view_uid: str = ""  # 业务视图访问UID
    control_buttons: List[ControlButton] = []
    metrics_mappings: List[MetricsMapping] = []  # 实时指标映射配置
    metrics_mapping: Dict[str, str] = {}  # 兼容旧配置
    audio_alerts: List[AudioAlert] = []
    audio_files: List[AudioFile] = []
    audio_alert_match_enabled: bool = False  # 音频告警关键词匹配开关，默认关闭
    audio_alerts_enabled: bool = True  # 全局音频告警开关，默认开启
    deleted_at: str = ""    # 软删除时间戳，空串表示未删除
    created_at: str = ""
    updated_at: str = ""


class ConfigManager:
    """Manages instance configurations with JSON persistence"""

    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = os.path.join(_get_config_base_dir(), "configs", "instances")
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _get_config_path(self, instance_id: str) -> Path:
        """Get the file path for an instance config"""
        return self.config_dir / f"{instance_id}.json"

    def list_instances(self, include_deleted: bool = False) -> List[Dict]:
        """List instance configurations.
        Args:
            include_deleted: If True, return only trashed instances.
                             If False (default), return only active instances.
        """
        instances = []
        for config_file in self.config_dir.glob("*.json"):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    is_deleted = bool(data.get("deleted_at", ""))
                    # Filter based on include_deleted flag
                    if include_deleted and not is_deleted:
                        continue
                    if not include_deleted and is_deleted:
                        continue
                    # Return summary without full config details
                    instances.append({
                        "instance_id": data.get("instance_id"),
                        "name": data.get("name"),
                        "description": data.get("description", ""),
                        "enabled": data.get("enabled", True),
                        "deleted_at": data.get("deleted_at", ""),
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
            # If the existing instance is soft-deleted, auto-clean it
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if existing.get("deleted_at", ""):
                    config_path.unlink()  # Clean up old trashed file
                else:
                    raise ValueError(f"Instance {config.instance_id} already exists")
            except ValueError:
                raise
            except Exception:
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

    def delete_instance(self, instance_id: str) -> Optional[str]:
        """Soft-delete: mark instance as deleted. Returns deleted_at timestamp or None."""
        config_path = self._get_config_path(instance_id)
        if not config_path.exists():
            return None
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            now = datetime.now().isoformat()
            data["deleted_at"] = now
            data["enabled"] = False
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return now
        except Exception as e:
            print(f"Error soft-deleting config {instance_id}: {e}")
            return None

    def restore_instance(self, instance_id: str) -> bool:
        """Restore a soft-deleted instance."""
        config_path = self._get_config_path(instance_id)
        if not config_path.exists():
            return False
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not data.get("deleted_at"):
                return False  # Not deleted
            data["deleted_at"] = ""
            data["enabled"] = True
            data["updated_at"] = datetime.now().isoformat()
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error restoring config {instance_id}: {e}")
            return False

    def permanently_delete_instance(self, instance_id: str) -> bool:
        """Permanently remove an instance configuration from disk."""
        config_path = self._get_config_path(instance_id)
        if not config_path.exists():
            return False
        try:
            config_path.unlink()
            return True
        except Exception as e:
            print(f"Error permanently deleting config {instance_id}: {e}")
            return False

    def instance_exists(self, instance_id: str) -> bool:
        """Check if an instance exists (not soft-deleted)."""
        config_path = self._get_config_path(instance_id)
        if not config_path.exists():
            return False
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return not bool(data.get("deleted_at", ""))
        except Exception:
            return config_path.exists()  # fallback

    def is_instance_enabled(self, instance_id: str) -> bool:
        """Return False for disabled or soft-deleted instances.
        Returns True for non-existent instances (caller should check existence separately)."""
        config_path = self._get_config_path(instance_id)
        if not config_path.exists():
            return True
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("deleted_at", ""):
                return False
            return data.get("enabled", True)
        except Exception:
            return True

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
