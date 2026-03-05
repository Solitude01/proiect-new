#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
超脑批量查询工具 - 终极整合版
功能：
1. 设备选择优化（搜索、分组、快速选择）
2. 批量获取通道 + 可视化通道选择
3. AIOP事件查询 / 全部事件查询
4. 压力测试（多并发、多请求）
5. 实时统计和结果导出

整合自：
- super_brain_query_tool.py (3栏布局、通道可视化)
- batch_stress_test.py (压力测试、统计分析)
- batch_search_all_channels.py (基础批量查询)
"""

import os
import sys
import json
import time
import uuid
import threading
import requests
import xml.etree.ElementTree as ET
import re
from requests.auth import HTTPDigestAuth
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from statistics import mean, median
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# 禁用SSL警告
from urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


@dataclass
class TestResult:
    """测试结果数据类"""
    device_id: str
    device_ip: str
    operation: str
    success: bool
    response_time_ms: float
    data_count: int = 0
    error_msg: str = ""
    timestamp: str = ""


@dataclass
class ChannelInfo:
    """通道信息类"""
    id: str
    name: str = "未知"
    selected: bool = True


@dataclass
class DeviceInfo:
    """设备信息类"""
    id: str
    ip: str
    password: str
    http_port: int = 80
    rtsp_port: int = 554
    scheme: str = "http"
    username: str = "admin"
    channels: List[ChannelInfo] = field(default_factory=list)
    status: str = "未连接"
    selected: bool = False
    
    def get_base_url(self):
        return f"{self.scheme}://{self.ip}:{self.http_port}"
    
    @property
    def display_name(self):
        return f"DM{self.id:>2} - {self.ip}"


class DeepmindClient:
    """超脑设备客户端"""
    
    def __init__(self, device: DeviceInfo):
        self.device = device
        self.session = requests.Session()
        self.session.verify = False
        self.session.trust_env = False
        self.auth = HTTPDigestAuth(device.username, device.password)
    
    def get_all_channels(self) -> Tuple[bool, List[ChannelInfo], float, str]:
        """获取所有通道"""
        url = f"{self.device.get_base_url()}/ISAPI/ContentMgmt/InputProxy/channels"
        
        start_ts = time.time()
        try:
            resp = self.session.get(url, auth=self.auth, timeout=10)
            elapsed = (time.time() - start_ts) * 1000
            
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                channels = []
                
                for channel in root.iter():
                    if channel.tag.endswith('InputProxyChannel'):
                        channel_id = None
                        channel_name = "未知"
                        
                        for child in channel.iter():
                            if child.tag.endswith('id'):
                                channel_id = child.text
                            elif child.tag.endswith('name'):
                                channel_name = child.text or "未知"
                        
                        if channel_id:
                            channels.append(ChannelInfo(id=channel_id, name=channel_name))
                
                return True, channels, elapsed, ""
            else:
                return False, [], elapsed, f"HTTP {resp.status_code}"
                
        except Exception as e:
            elapsed = (time.time() - start_ts) * 1000
            return False, [], elapsed, str(e)
    
    def _get_headers(self):
        return {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Content-Type': 'application/json',
            'Origin': self.device.get_base_url(),
            'Referer': f"{self.device.get_base_url()}/doc/index.html",
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'X-Requested-With': 'XMLHttpRequest'
        }
    
    def ai_intelligent_search(self, channels: List[int], start_time: datetime,
                              end_time: datetime, max_results: int = 30) -> Dict:
        """AIOP事件查询"""
        url = f"{self.device.get_base_url()}/ISAPI/Intelligent/AIOpenPlatform/AIIntelligentSearch?format=json"
        
        payload = {
            "SearchCondition": {
                "searchID": str(uuid.uuid4()).upper(),
                "searchResultPosition": 0,
                "maxResults": max_results,
                "startTime": start_time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                "endTime": end_time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                "engine": [],
                "taskType": "videoTask",
                "minConfidence": 0,
                "secondVerifyAlarmEnabled": False,
                "AIOPDataUrlEnabled": True,
                "channelID": channels,
                "secondVerifyAlarmType": "succ"
            }
        }
        
        start_ts = time.time()
        try:
            resp = self.session.post(url, json=payload, auth=self.auth,
                                    headers=self._get_headers(), timeout=30)
            elapsed = (time.time() - start_ts) * 1000
            
            return {
                'success': resp.status_code == 200,
                'status_code': resp.status_code,
                'response_time_ms': elapsed,
                'response': resp.json() if resp.status_code == 200 else None,
                'raw_response': resp.text[:500] if resp.status_code != 200 else None,
                'error': None
            }
        except Exception as e:
            return {
                'success': False,
                'status_code': None,
                'response_time_ms': (time.time() - start_ts) * 1000,
                'response': None,
                'error': str(e)
            }
    
    def event_record_search(self, channels: List[int], start_time: datetime,
                           end_time: datetime, max_results: int = 30) -> Dict:
        """全部事件查询"""
        url = f"{self.device.get_base_url()}/ISAPI/ContentMgmt/eventRecordSearch?format=json"
        
        payload = {
            "EventSearchDescription": {
                "searchID": str(uuid.uuid4()).upper(),
                "searchResultPosition": 0,
                "maxResults": max_results,
                "timeSpanList": [
                    {
                        "startTime": start_time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                        "endTime": end_time.strftime("%Y-%m-%dT%H:%M:%S+08:00")
                    }
                ],
                "type": "all",
                "eventType": "all",
                "channels": channels
            }
        }
        
        start_ts = time.time()
        try:
            resp = self.session.post(url, json=payload, auth=self.auth,
                                    headers=self._get_headers(), timeout=30)
            elapsed = (time.time() - start_ts) * 1000
            
            return {
                'success': resp.status_code == 200,
                'status_code': resp.status_code,
                'response_time_ms': elapsed,
                'response': resp.json() if resp.status_code == 200 else None,
                'error': None
            }
        except Exception as e:
            return {
                'success': False,
                'status_code': None,
                'response_time_ms': (time.time() - start_ts) * 1000,
                'response': None,
                'error': str(e)
            }


class UnifiedSuperBrainTool:
    """超脑统一查询工具 - 整合所有功能"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("超脑批量查询工具 - 终极整合版")
        self.root.geometry("1450x900")
        self.root.minsize(1400, 800)
        
        # 数据
        self.devices: List[DeviceInfo] = []
        self.filtered_devices: List[DeviceInfo] = []
        self.selected_device: Optional[DeviceInfo] = None
        self.results: List[TestResult] = []
        self.query_results: List[Dict] = []
        self.is_running = False
        self.cancel_event = threading.Event()
        
        # UI引用
        self.channel_vars = {}  # channel_id -> BooleanVar
        self.device_checkboxes = {}  # device_id -> BooleanVar
        
        self._load_devices()
        self._build_ui()
    
    def _load_devices(self):
        """加载设备配置"""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(script_dir)
            json_path = os.path.join(parent_dir, "Deepmind.json")
            
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for item in data:
                device = DeviceInfo(
                    id=str(item.get('Deepmind', '')),
                    ip=item.get('IP', ''),
                    password=item.get('Password', ''),
                    http_port=int(item.get('HttpPort', 80)),
                    rtsp_port=int(item.get('RtspPort', 554)),
                    scheme=item.get('Scheme', 'http'),
                    username='admin'
                )
                if device.id and device.ip:
                    self.devices.append(device)
            
            self.devices.sort(key=lambda x: int(x.id) if x.id.isdigit() else x.id)
            self.filtered_devices = self.devices.copy()
            
        except Exception as e:
            messagebox.showerror("错误", f"加载设备失败: {e}")
    
    def _build_ui(self):
        """构建UI - 4栏布局"""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        # 配置grid权重
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.columnconfigure(2, weight=1)
        main_frame.columnconfigure(3, weight=2)
        main_frame.rowconfigure(1, weight=1)
        
        # ===== 顶部：标题和模式切换 =====
        top_frame = ttk.Frame(main_frame)
        top_frame.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        
        ttk.Label(top_frame, text="超脑批量查询工具 - 终极整合版",
                 font=("Microsoft YaHei", 16, "bold")).pack(side="left")
        
        # 操作模式选择
        mode_frame = ttk.Frame(top_frame)
        mode_frame.pack(side="right")
        
        ttk.Label(mode_frame, text="操作模式:").pack(side="left", padx=(0, 5))
        self.mode_var = tk.StringVar(value="single")
        ttk.Combobox(mode_frame, textvariable=self.mode_var,
                    values=["single", "batch", "stress"],
                    width=15, state="readonly").pack(side="left")
        ttk.Label(mode_frame, text="(single=单设备, batch=批量, stress=压力测试)",
                 font=("Consolas", 9)).pack(side="left", padx=(5, 0))
        
        # ===== 第1栏：设备选择（优化版） =====
        device_frame = ttk.LabelFrame(main_frame, text="1. 设备选择", padding=10)
        device_frame.grid(row=1, column=0, sticky="nsew", padx=5)
        device_frame.rowconfigure(3, weight=1)
        
        # 搜索框
        search_frame = ttk.Frame(device_frame)
        search_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        
        ttk.Label(search_frame, text="搜索:").pack(side="left")
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=20)
        search_entry.pack(side="left", padx=5)
        search_entry.bind('<KeyRelease>', self._on_search)
        
        # 快速选择按钮
        quick_frame = ttk.Frame(device_frame)
        quick_frame.grid(row=1, column=0, sticky="ew", pady=2)
        
        ttk.Button(quick_frame, text="全选", command=self._select_all_devices, width=8).pack(side="left", padx=2)
        ttk.Button(quick_frame, text="清空", command=self._select_none_devices, width=8).pack(side="left", padx=2)
        ttk.Button(quick_frame, text="反选", command=self._invert_selection, width=8).pack(side="left", padx=2)
        
        # IP范围选择
        range_frame = ttk.Frame(device_frame)
        range_frame.grid(row=2, column=0, sticky="ew", pady=2)
        
        ttk.Button(range_frame, text="10.30.x.x", command=lambda: self._select_by_ip("10.30."), width=10).pack(side="left", padx=2)
        ttk.Button(range_frame, text="10.152.x.x", command=lambda: self._select_by_ip("10.152."), width=10).pack(side="left", padx=2)
        ttk.Button(range_frame, text="DM10-20", command=lambda: self._select_by_id_range(10, 20), width=10).pack(side="left", padx=2)
        
        # 设备列表（带复选框）
        list_frame = ttk.Frame(device_frame)
        list_frame.grid(row=3, column=0, sticky="nsew", pady=5)
        list_frame.rowconfigure(0, weight=1)
        
        self.device_canvas = tk.Canvas(list_frame, highlightthickness=0, width=220)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.device_canvas.yview)
        self.device_list_inner = ttk.Frame(self.device_canvas)
        
        self.device_list_inner.bind(
            "<Configure>",
            lambda e: self.device_canvas.configure(scrollregion=self.device_canvas.bbox("all"))
        )
        
        self.device_canvas.create_window((0, 0), window=self.device_list_inner, anchor="nw", width=200)
        self.device_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.device_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        # 统计（先创建变量）
        self.device_stats_var = tk.StringVar(value=f"共 {len(self.devices)} 个设备")
        ttk.Label(device_frame, textvariable=self.device_stats_var, font=("Consolas", 9)).grid(row=4, column=0, sticky="w")
        
        self._populate_device_list()
        
        # ===== 第2栏：通道选择 =====
        channel_frame = ttk.LabelFrame(main_frame, text="2. 通道选择", padding=10)
        channel_frame.grid(row=1, column=1, sticky="nsew", padx=5)
        channel_frame.rowconfigure(1, weight=1)
        
        # 通道操作按钮
        ch_btn_frame = ttk.Frame(channel_frame)
        ch_btn_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        
        ttk.Button(ch_btn_frame, text="获取通道", command=self._fetch_channels, width=10).pack(side="left", padx=2)
        ttk.Button(ch_btn_frame, text="全选", command=self._select_all_channels, width=8).pack(side="left", padx=2)
        ttk.Button(ch_btn_frame, text="清空", command=self._deselect_all_channels, width=8).pack(side="left", padx=2)
        
        # 通道列表
        ch_list_frame = ttk.Frame(channel_frame)
        ch_list_frame.grid(row=1, column=0, sticky="nsew")
        ch_list_frame.rowconfigure(0, weight=1)
        
        self.channel_canvas = tk.Canvas(ch_list_frame, highlightthickness=0, width=250)
        ch_scrollbar = ttk.Scrollbar(ch_list_frame, orient="vertical", command=self.channel_canvas.yview)
        self.channel_inner_frame = ttk.Frame(self.channel_canvas)
        
        self.channel_inner_frame.bind(
            "<Configure>",
            lambda e: self.channel_canvas.configure(scrollregion=self.channel_canvas.bbox("all"))
        )
        
        self.channel_canvas.create_window((0, 0), window=self.channel_inner_frame, anchor="nw", width=230)
        self.channel_canvas.configure(yscrollcommand=ch_scrollbar.set)
        
        self.channel_canvas.grid(row=0, column=0, sticky="nsew")
        ch_scrollbar.grid(row=0, column=1, sticky="ns")
        
        # 通道统计
        self.channel_stats_var = tk.StringVar(value="未获取通道")
        ttk.Label(channel_frame, textvariable=self.channel_stats_var, font=("Consolas", 9)).grid(row=2, column=0, sticky="w", pady=(5, 0))
        
        # ===== 第3栏：查询配置 =====
        config_frame = ttk.LabelFrame(main_frame, text="3. 查询配置", padding=10)
        config_frame.grid(row=1, column=2, sticky="nsew", padx=5)
        
        # 查询类型
        ttk.Label(config_frame, text="查询类型:").grid(row=0, column=0, sticky="w", pady=5)
        self.query_type_var = tk.StringVar(value="aiop")
        ttk.Combobox(config_frame, textvariable=self.query_type_var,
                    values=["aiop", "event"], width=20, state="readonly").grid(row=0, column=1, sticky="w")
        
        # 时间范围
        ttk.Label(config_frame, text="开始时间:").grid(row=1, column=0, sticky="w", pady=5)
        self.start_time_var = tk.StringVar(
            value=datetime.now().replace(hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M"))
        ttk.Entry(config_frame, textvariable=self.start_time_var, width=20).grid(row=1, column=1, sticky="w")
        
        ttk.Label(config_frame, text="结束时间:").grid(row=2, column=0, sticky="w", pady=5)
        self.end_time_var = tk.StringVar(
            value=datetime.now().replace(hour=23, minute=59, second=59).strftime("%Y-%m-%d %H:%M"))
        ttk.Entry(config_frame, textvariable=self.end_time_var, width=20).grid(row=2, column=1, sticky="w")
        
        # 最大结果
        ttk.Label(config_frame, text="最大结果:").grid(row=3, column=0, sticky="w", pady=5)
        self.max_results_var = tk.IntVar(value=30)
        ttk.Spinbox(config_frame, from_=1, to=1000, textvariable=self.max_results_var, width=10).grid(row=3, column=1, sticky="w")
        
        # 并发设置
        ttk.Separator(config_frame, orient="horizontal").grid(row=4, column=0, columnspan=2, sticky="ew", pady=10)
        
        ttk.Label(config_frame, text="并发线程:").grid(row=5, column=0, sticky="w", pady=5)
        self.workers_var = tk.IntVar(value=5)
        ttk.Spinbox(config_frame, from_=1, to=50, textvariable=self.workers_var, width=10).grid(row=5, column=1, sticky="w")
        
        # 压力测试专用
        ttk.Label(config_frame, text="每设备请求:").grid(row=6, column=0, sticky="w", pady=5)
        self.requests_var = tk.IntVar(value=10)
        ttk.Spinbox(config_frame, from_=1, to=100, textvariable=self.requests_var, width=10).grid(row=6, column=1, sticky="w")
        
        ttk.Label(config_frame, text="请求间隔(ms):").grid(row=7, column=0, sticky="w", pady=5)
        self.interval_var = tk.IntVar(value=100)
        ttk.Spinbox(config_frame, from_=0, to=5000, textvariable=self.interval_var, width=10).grid(row=7, column=1, sticky="w")
        
        # 控制按钮
        btn_frame = ttk.Frame(config_frame)
        btn_frame.grid(row=8, column=0, columnspan=2, pady=20, sticky="ew")
        
        self.start_btn = tk.Button(btn_frame, text="开始查询", command=self._start_operation,
                                  bg="#4CAF50", fg="white", font=("Microsoft YaHei", 11, "bold"))
        self.start_btn.pack(fill="x", pady=2)
        
        self.stop_btn = tk.Button(btn_frame, text="停止", command=self._stop_operation,
                                 bg="#f44336", fg="white", state="disabled")
        self.stop_btn.pack(fill="x", pady=2)
        
        self.export_btn = tk.Button(btn_frame, text="导出结果", command=self._export_results,
                                   state="disabled")
        self.export_btn.pack(fill="x", pady=2)
        
        # ===== 第4栏：日志和统计 =====
        right_frame = ttk.LabelFrame(main_frame, text="4. 日志与统计", padding=10)
        right_frame.grid(row=1, column=3, sticky="nsew", padx=5)
        right_frame.rowconfigure(1, weight=1)
        right_frame.columnconfigure(0, weight=1)
        
        # 统计信息
        stats_frame = ttk.Frame(right_frame)
        stats_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        
        self.stats_var = tk.StringVar(value="就绪 - 请选择设备和配置参数")
        ttk.Label(stats_frame, textvariable=self.stats_var, font=("Consolas", 10),
                 justify="left", wraplength=400).pack(anchor="w")
        
        # 进度条
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(right_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=0, column=0, sticky="ew", pady=(60, 0))
        
        # 日志
        self.log_text = scrolledtext.ScrolledText(right_frame, wrap="word", font=("Consolas", 9))
        self.log_text.grid(row=1, column=0, sticky="nsew", pady=5)
        
        self.log_text.tag_configure("success", foreground="green")
        self.log_text.tag_configure("error", foreground="red")
        self.log_text.tag_configure("info", foreground="blue")
        self.log_text.tag_configure("warning", foreground="orange")
        self.log_text.tag_configure("highlight", foreground="purple", font=("Consolas", 9, "bold"))
    
    def _populate_device_list(self):
        """填充设备列表"""
        # 清空现有
        for widget in self.device_list_inner.winfo_children():
            widget.destroy()
        self.device_checkboxes.clear()
        
        # 创建复选框
        for device in self.filtered_devices:
            var = tk.BooleanVar(value=device.selected)
            self.device_checkboxes[device.id] = var
            
            cb = ttk.Checkbutton(
                self.device_list_inner,
                text=device.display_name,
                variable=var,
                command=lambda d=device, v=var: self._on_device_toggle(d, v)
            )
            cb.pack(anchor="w", pady=1)
        
        self.device_list_inner.update_idletasks()
        self.device_canvas.configure(scrollregion=self.device_canvas.bbox("all"))
        self.device_stats_var.set(f"显示 {len(self.filtered_devices)}/{len(self.devices)} 个设备, 已选 {self._get_selected_device_count()}")
    
    def _on_search(self, event=None):
        """搜索设备"""
        query = self.search_var.get().lower().strip()
        
        if not query:
            self.filtered_devices = self.devices.copy()
        else:
            self.filtered_devices = [
                d for d in self.devices
                if query in d.id.lower() or query in d.ip.lower() or f"dm{d.id}".lower() == query
            ]
        
        self._populate_device_list()
    
    def _on_device_toggle(self, device: DeviceInfo, var: tk.BooleanVar):
        """设备选择切换"""
        device.selected = var.get()
        if device.selected:
            self.selected_device = device
        self.device_stats_var.set(f"显示 {len(self.filtered_devices)}/{len(self.devices)} 个设备, 已选 {self._get_selected_device_count()}")
    
    def _get_selected_devices(self) -> List[DeviceInfo]:
        """获取选中的设备列表"""
        return [d for d in self.devices if d.selected]
    
    def _get_selected_device_count(self) -> int:
        """获取选中设备数量"""
        return sum(1 for d in self.devices if d.selected)
    
    def _select_all_devices(self):
        """全选设备"""
        for device in self.filtered_devices:
            device.selected = True
            if device.id in self.device_checkboxes:
                self.device_checkboxes[device.id].set(True)
        self.device_stats_var.set(f"显示 {len(self.filtered_devices)}/{len(self.devices)} 个设备, 已选 {self._get_selected_device_count()}")
    
    def _select_none_devices(self):
        """清空设备选择"""
        for device in self.devices:
            device.selected = False
        for var in self.device_checkboxes.values():
            var.set(False)
        self.device_stats_var.set(f"显示 {len(self.filtered_devices)}/{len(self.devices)} 个设备, 已选 0")
    
    def _invert_selection(self):
        """反选设备"""
        for device in self.filtered_devices:
            device.selected = not device.selected
            if device.id in self.device_checkboxes:
                self.device_checkboxes[device.id].set(device.selected)
        self.device_stats_var.set(f"显示 {len(self.filtered_devices)}/{len(self.devices)} 个设备, 已选 {self._get_selected_device_count()}")
    
    def _select_by_ip(self, prefix: str):
        """按IP前缀选择"""
        for device in self.devices:
            if device.ip.startswith(prefix):
                device.selected = True
                if device.id in self.device_checkboxes:
                    self.device_checkboxes[device.id].set(True)
        self._populate_device_list()
    
    def _select_by_id_range(self, start: int, end: int):
        """按ID范围选择"""
        for device in self.devices:
            try:
                did = int(device.id)
                if start <= did <= end:
                    device.selected = True
                    if device.id in self.device_checkboxes:
                        self.device_checkboxes[device.id].set(True)
            except:
                pass
        self.device_stats_var.set(f"显示 {len(self.filtered_devices)}/{len(self.devices)} 个设备, 已选 {self._get_selected_device_count()}")
    
    def _fetch_channels(self):
        """获取选中设备的通道"""
        devices = self._get_selected_devices()
        if not devices:
            messagebox.showwarning("提示", "请至少选择一个设备")
            return
        
        if len(devices) == 1:
            # 单设备模式 - 显示复选框
            self._fetch_single_device_channels(devices[0])
        else:
            # 多设备模式 - 批量获取
            self._fetch_multiple_device_channels(devices)
    
    def _fetch_single_device_channels(self, device: DeviceInfo):
        """获取单个设备的通道并显示"""
        def task():
            self._log(f"[{device.ip}] 正在获取通道列表...")
            
            client = DeepmindClient(device)
            ok, channels, elapsed, error = client.get_all_channels()
            
            if ok:
                device.channels = channels
                device.status = "已连接"
                self._log(f"  [OK] 发现 {len(channels)} 个通道 ({elapsed:.0f}ms)", "success")
                self.root.after(0, lambda: self._display_channels(device))
            else:
                device.status = f"失败: {error}"
                self._log(f"  [FAIL] {error} ({elapsed:.0f}ms)", "error")
        
        threading.Thread(target=task, daemon=True).start()
    
    def _fetch_multiple_device_channels(self, devices: List[DeviceInfo]):
        """批量获取多个设备的通道"""
        def task():
            self._log(f"批量获取 {len(devices)} 个设备的通道...", "info")
            
            success_count = 0
            total_channels = 0
            
            with ThreadPoolExecutor(max_workers=self.workers_var.get()) as executor:
                def fetch_one(device):
                    client = DeepmindClient(device)
                    return device, client.get_all_channels()
                
                futures = [executor.submit(fetch_one, d) for d in devices]
                
                for future in as_completed(futures):
                    device, (ok, channels, elapsed, error) = future.result()
                    
                    if ok:
                        device.channels = channels
                        device.status = "已连接"
                        success_count += 1
                        total_channels += len(channels)
                        self._log(f"  [OK] DM{device.id}: {len(channels)}个通道", "success")
                    else:
                        device.status = f"失败"
                        self._log(f"  [FAIL] DM{device.id}: {error}", "error")
            
            self._log(f"通道获取完成: {success_count}/{len(devices)} 成功, 共 {total_channels} 个通道", "highlight")
            self.root.after(0, lambda: self._display_summary_channels(devices))
        
        threading.Thread(target=task, daemon=True).start()
    
    def _display_channels(self, device: DeviceInfo):
        """显示单个设备的通道（复选框形式）"""
        # 清空
        for widget in self.channel_inner_frame.winfo_children():
            widget.destroy()
        self.channel_vars.clear()
        
        if not device.channels:
            ttk.Label(self.channel_inner_frame, text="无通道数据").pack(pady=20)
            self.channel_stats_var.set("无通道")
            return
        
        # 标题
        ttk.Label(self.channel_inner_frame, text=f"DM{device.id} - {len(device.channels)}个通道",
                 font=("Microsoft YaHei", 10, "bold")).pack(anchor="w", pady=(0, 10))
        
        # 复选框
        for ch in device.channels:
            var = tk.BooleanVar(value=ch.selected)
            self.channel_vars[ch.id] = var
            
            cb = ttk.Checkbutton(
                self.channel_inner_frame,
                text=f"通道{ch.id}: {ch.name}",
                variable=var,
                command=lambda c=ch, v=var: self._on_channel_toggle(c, v)
            )
            cb.pack(anchor="w", pady=1)
        
        self.channel_inner_frame.update_idletasks()
        self.channel_canvas.configure(scrollregion=self.channel_canvas.bbox("all"))
        self.channel_stats_var.set(f"DM{device.id}: {len(device.channels)} 个通道, 已选 {sum(1 for c in device.channels if c.selected)}")
    
    def _display_summary_channels(self, devices: List[DeviceInfo]):
        """显示多个设备的通道摘要"""
        for widget in self.channel_inner_frame.winfo_children():
            widget.destroy()
        self.channel_vars.clear()
        
        total = sum(len(d.channels) for d in devices if d.channels)
        
        ttk.Label(self.channel_inner_frame, text=f"批量通道摘要", font=("Microsoft YaHei", 10, "bold")).pack(anchor="w", pady=(0, 10))
        
        for device in devices:
            if device.channels:
                ch_str = ", ".join([c.id for c in device.channels[:5]])
                if len(device.channels) > 5:
                    ch_str += f"... 等{len(device.channels)}个"
                ttk.Label(self.channel_inner_frame, text=f"DM{device.id}: {ch_str}", font=("Consolas", 9)).pack(anchor="w", pady=1)
        
        self.channel_inner_frame.update_idletasks()
        self.channel_canvas.configure(scrollregion=self.channel_canvas.bbox("all"))
        self.channel_stats_var.set(f"{len([d for d in devices if d.channels])} 个设备共 {total} 个通道")
    
    def _on_channel_toggle(self, channel: ChannelInfo, var: tk.BooleanVar):
        """通道选择切换"""
        channel.selected = var.get()
        if self.selected_device:
            selected_count = sum(1 for c in self.selected_device.channels if c.selected)
            self.channel_stats_var.set(f"DM{self.selected_device.id}: {len(self.selected_device.channels)} 个通道, 已选 {selected_count}")
    
    def _select_all_channels(self):
        """全选通道"""
        for var in self.channel_vars.values():
            var.set(True)
        if self.selected_device:
            for c in self.selected_device.channels:
                c.selected = True
            self.channel_stats_var.set(f"DM{self.selected_device.id}: {len(self.selected_device.channels)} 个通道, 已选 {len(self.selected_device.channels)}")
    
    def _deselect_all_channels(self):
        """取消全选通道"""
        for var in self.channel_vars.values():
            var.set(False)
        if self.selected_device:
            for c in self.selected_device.channels:
                c.selected = False
            self.channel_stats_var.set(f"DM{self.selected_device.id}: {len(self.selected_device.channels)} 个通道, 已选 0")
    
    def _get_selected_channels_for_device(self, device: DeviceInfo) -> List[int]:
        """获取指定设备的选中通道"""
        if not device.channels:
            return [1]  # 默认
        selected = [int(c.id) for c in device.channels if c.selected]
        return selected if selected else [1]
    
    def _parse_time(self, time_str: str) -> datetime:
        """解析时间"""
        try:
            return datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        except:
            try:
                return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            except:
                return datetime.now()
    
    def _log(self, message: str, tag: Optional[str] = None):
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
        self.log_text.see(tk.END)
    
    def _update_stats(self, completed: int, total: int, success: int, fail: int, avg_time: float = 0):
        """更新统计"""
        progress = (completed / total * 100) if total > 0 else 0
        
        stats_text = (f"进度: {completed}/{total} ({progress:.0f}%)\n"
                     f"成功: {success} | 失败: {fail}")
        if avg_time > 0:
            stats_text += f"\n平均响应: {avg_time:.0f}ms"
        
        self.stats_var.set(stats_text)
        self.progress_var.set(progress)
    
    def _start_operation(self):
        """开始操作"""
        mode = self.mode_var.get()
        
        if mode == "single":
            self._start_single_query()
        elif mode == "batch":
            self._start_batch_query()
        else:
            self._start_stress_test()
    
    def _start_single_query(self):
        """单设备查询"""
        devices = self._get_selected_devices()
        if len(devices) != 1:
            messagebox.showwarning("提示", "单设备模式请选择一个设备")
            return
        
        device = devices[0]
        
        if not device.channels:
            messagebox.showwarning("提示", "请先获取通道列表")
            return
        
        try:
            start_time = self._parse_time(self.start_time_var.get())
            end_time = self._parse_time(self.end_time_var.get())
        except:
            messagebox.showwarning("提示", "时间格式错误")
            return
        
        channels = self._get_selected_channels_for_device(device)
        if not channels:
            messagebox.showwarning("提示", "请至少选择一个通道")
            return
        
        self.is_running = True
        self.cancel_event.clear()
        self._set_ui_running(True)
        self.log_text.delete(1.0, tk.END)
        
        def task():
            query_type = self.query_type_var.get()
            max_results = self.max_results_var.get()
            
            self._log("=" * 60, "highlight")
            self._log(f"单设备查询: DM{device.id}")
            self._log(f"通道: {channels}")
            self._log(f"时间: {start_time} ~ {end_time}")
            self._log(f"类型: {query_type}")
            self._log("-" * 60)
            
            client = DeepmindClient(device)
            
            if query_type == "aiop":
                result = client.ai_intelligent_search(channels, start_time, end_time, max_results)
            else:
                result = client.event_record_search(channels, start_time, end_time, max_results)
            
            self._process_single_result(device, result, query_type)
            
            self.is_running = False
            self.root.after(0, lambda: self._set_ui_running(False))
        
        threading.Thread(target=task, daemon=True).start()
    
    def _start_batch_query(self):
        """批量查询"""
        devices = self._get_selected_devices()
        if not devices:
            messagebox.showwarning("提示", "请至少选择一个设备")
            return
        
        try:
            start_time = self._parse_time(self.start_time_var.get())
            end_time = self._parse_time(self.end_time_var.get())
        except:
            messagebox.showwarning("提示", "时间格式错误")
            return
        
        self.is_running = True
        self.cancel_event.clear()
        self._set_ui_running(True)
        self.log_text.delete(1.0, tk.END)
        self.results.clear()
        self.query_results.clear()
        
        def task():
            query_type = self.query_type_var.get()
            max_results = self.max_results_var.get()
            workers = self.workers_var.get()
            interval = self.interval_var.get() / 1000.0
            
            self._log(f"批量查询: {len(devices)}个设备, 类型={query_type}", "highlight")
            
            # 先获取通道（如果没有）
            need_channels = any(not d.channels for d in devices)
            if need_channels:
                self._log("自动获取通道列表...")
                for device in devices:
                    if self.cancel_event.is_set():
                        break
                    if not device.channels:
                        client = DeepmindClient(device)
                        ok, channels, _, _ = client.get_all_channels()
                        if ok:
                            device.channels = channels
                            for c in channels:
                                c.selected = True
                            self._log(f"  [OK] DM{device.id}: {len(channels)}个通道", "success")
                        else:
                            self._log(f"  [FAIL] DM{device.id}: 获取通道失败", "error")
            
            # 执行查询
            completed = 0
            success = 0
            fail = 0
            total_time = 0.0
            
            def do_query(device):
                if self.cancel_event.is_set():
                    return None
                
                channels = self._get_selected_channels_for_device(device)
                client = DeepmindClient(device)
                
                if query_type == "aiop":
                    result = client.ai_intelligent_search(channels, start_time, end_time, max_results)
                else:
                    result = client.event_record_search(channels, start_time, end_time, max_results)
                
                if interval > 0:
                    time.sleep(interval)
                
                return device, result
            
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(do_query, d): d for d in devices}
                
                for future in as_completed(futures):
                    if self.cancel_event.is_set():
                        break
                    
                    result = future.result()
                    if result:
                        device, res = result
                        self.query_results.append(res)
                        completed += 1
                        total_time += res.get('response_time_ms', 0)
                        
                        if res.get('success'):
                            success += 1
                            matches = self._extract_matches(res, query_type)
                            self._log(f"[OK] DM{device.id}: {matches}条记录 ({res['response_time_ms']:.0f}ms)", "success")
                        else:
                            fail += 1
                            error = res.get('error') or f"HTTP {res.get('status_code', 'N/A')}"
                            self._log(f"[FAIL] DM{device.id}: {error[:50]}", "error")
                        
                        avg_time = total_time / completed if completed > 0 else 0
                        self.root.after(0, lambda: self._update_stats(completed, len(devices), success, fail, avg_time))
            
            self.is_running = False
            self.root.after(0, lambda: self._finish_operation(completed, success, fail))
        
        threading.Thread(target=task, daemon=True).start()
    
    def _start_stress_test(self):
        """压力测试"""
        devices = self._get_selected_devices()
        if not devices:
            messagebox.showwarning("提示", "请至少选择一个设备")
            return
        
        try:
            start_time = self._parse_time(self.start_time_var.get())
            end_time = self._parse_time(self.end_time_var.get())
        except:
            messagebox.showwarning("提示", "时间格式错误")
            return
        
        workers = self.workers_var.get()
        requests_per_device = self.requests_var.get()
        interval = self.interval_var.get() / 1000.0
        total_requests = len(devices) * requests_per_device
        
        if not messagebox.askyesno("确认", f"压力测试将发送 {total_requests} 次请求\n并发: {workers}, 间隔: {interval*1000:.0f}ms\n\n确认开始?"):
            return
        
        self.is_running = True
        self.cancel_event.clear()
        self._set_ui_running(True)
        self.log_text.delete(1.0, tk.END)
        self.results.clear()
        
        def task():
            query_type = self.query_type_var.get()
            
            self._log(f"压力测试: {len(devices)}设备 x {requests_per_device}请求 = {total_requests}次", "highlight")
            
            # 先获取通道
            self._log("获取通道列表...")
            for device in devices:
                if self.cancel_event.is_set():
                    break
                if not device.channels:
                    client = DeepmindClient(device)
                    ok, channels, _, _ = client.get_all_channels()
                    if ok:
                        device.channels = channels
            
            # 压力测试
            completed = 0
            success = 0
            fail = 0
            total_time = 0.0
            
            def stress_query(device, req_index):
                if self.cancel_event.is_set():
                    return None
                
                channels = self._get_selected_channels_for_device(device)
                client = DeepmindClient(device)
                
                if query_type == "aiop":
                    result = client.ai_intelligent_search(channels, start_time, end_time, 30)
                else:
                    result = client.event_record_search(channels, start_time, end_time, 30)
                
                elapsed = result.get('response_time_ms', 0)
                ok = result.get('success', False)
                error = result.get('error', '')
                
                test_result = TestResult(
                    device_id=device.id,
                    device_ip=device.ip,
                    operation=f"stress_{req_index}",
                    success=ok,
                    response_time_ms=elapsed,
                    data_count=self._extract_matches(result, query_type) if ok else 0,
                    error_msg=error or '',
                    timestamp=datetime.now().isoformat()
                )
                
                if interval > 0:
                    time.sleep(interval)
                
                return test_result
            
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = []
                for device in devices:
                    for i in range(requests_per_device):
                        if self.cancel_event.is_set():
                            break
                        future = executor.submit(stress_query, device, i)
                        futures.append(future)
                
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        self.results.append(result)
                        completed += 1
                        total_time += result.response_time_ms
                        
                        if result.success:
                            success += 1
                        else:
                            fail += 1
                        
                        if completed % 10 == 0 or completed == total_requests:
                            avg_time = total_time / completed if completed > 0 else 0
                            self._log(f"进度: {completed}/{total_requests} 完成")
                            self.root.after(0, lambda: self._update_stats(completed, total_requests, success, fail, avg_time))
            
            self.is_running = False
            self.root.after(0, lambda: self._finish_stress_test(completed, success, fail))
        
        threading.Thread(target=task, daemon=True).start()
    
    def _process_single_result(self, device: DeviceInfo, result: Dict, query_type: str):
        """处理单设备查询结果"""
        if result['success']:
            self._log(f"[SUCCESS] 查询成功! ({result['response_time_ms']:.1f}ms)", "success")
            
            response = result.get('response', {})
            if query_type == "aiop" and 'SearchResult' in response:
                sr = response['SearchResult']
                matches = sr.get('numOfMatches', 0)
                status = sr.get('responseStatusStrg', 'N/A')
                self._log(f"状态: {status}")
                self._log(f"匹配数: {matches}")
                
                ai_alarms = sr.get('AIAlarmInfo', [])
                if ai_alarms:
                    self._log(f"\nAI告警列表 (前5条):", "highlight")
                    for i, alarm in enumerate(ai_alarms[:5]):
                        time_str = alarm.get('dateTime', 'N/A')[:19].replace('T', ' ')
                        ch = alarm.get('channelID', 'N/A')
                        conf = alarm.get('confidence', 'N/A')
                        rule = alarm.get('ruleName', 'N/A')
                        self._log(f"  [{i+1}] 通道{ch} {time_str} 置信度{conf}% 规则:{rule}")
                else:
                    self._log("无AI告警记录")
                    
            elif query_type == "event" and 'EventSearchResult' in response:
                esr = response['EventSearchResult']
                matches = esr.get('numOfMatches', 0)
                status = esr.get('responseStatusStrg', 'N/A')
                self._log(f"状态: {status}")
                self._log(f"匹配数: {matches}")
                
                match_list = esr.get('matchList', [])
                if match_list:
                    self._log(f"\n事件列表 (前5条):", "highlight")
                    for i, event in enumerate(match_list[:5]):
                        self._log(f"  [{i+1}] 通道{event.get('channel', 'N/A')} - {event.get('time', 'N/A')} - {event.get('eventType', 'N/A')}")
                else:
                    self._log("无事件记录")
        else:
            self._log(f"[FAILED] 查询失败: {result.get('status_code', 'N/A')}", "error")
            if result.get('error'):
                self._log(f"错误: {result['error']}", "error")
        
        self._log("=" * 60, "highlight")
    
    def _extract_matches(self, result: Dict, query_type: str) -> int:
        """提取匹配数"""
        if not result.get('success'):
            return 0
        
        response = result.get('response', {})
        if query_type == "aiop":
            return response.get('SearchResult', {}).get('numOfMatches', 0)
        else:
            return response.get('EventSearchResult', {}).get('numOfMatches', 0)
    
    def _finish_operation(self, total: int, success: int, fail: int):
        """完成操作"""
        self._set_ui_running(False)
        self._log("-" * 60, "highlight")
        self._log(f"查询完成! 总计: {total}, 成功: {success}, 失败: {fail}", "highlight")
        
        if self.results or self.query_results:
            self.export_btn.config(state="normal")
    
    def _finish_stress_test(self, total: int, success: int, fail: int):
        """完成压力测试"""
        self._set_ui_running(False)
        
        if self.results:
            times = [r.response_time_ms for r in self.results]
            min_time = min(times)
            max_time = max(times)
            avg_time = mean(times)
            med_time = median(times)
        else:
            min_time = max_time = avg_time = med_time = 0
        
        self._log("=" * 60, "highlight")
        self._log("压力测试完成!", "highlight")
        self._log(f"总请求: {total}", "info")
        self._log(f"成功: {success} ({success/total*100:.1f}%)", "success" if fail == 0 else "info")
        self._log(f"失败: {fail} ({fail/total*100:.1f}%)", "error" if fail > 0 else "info")
        self._log(f"响应时间 - 最小: {min_time:.0f}ms, 最大: {max_time:.0f}ms, 平均: {avg_time:.0f}ms, 中位数: {med_time:.0f}ms", "info")
        self._log("=" * 60, "highlight")
        
        self.export_btn.config(state="normal")
    
    def _set_ui_running(self, running: bool):
        """设置UI运行状态"""
        if running:
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
            self.export_btn.config(state="disabled")
        else:
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            self.export_btn.config(state="normal")
    
    def _stop_operation(self):
        """停止操作"""
        if self.is_running:
            self.cancel_event.set()
            self._log("正在停止...", "warning")
    
    def _export_results(self):
        """导出结果"""
        mode = self.mode_var.get()
        
        try:
            filename = f"results_{mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
            
            export_data = {
                'export_time': datetime.now().isoformat(),
                'mode': mode,
                'config': {
                    'query_type': self.query_type_var.get(),
                    'start_time': self.start_time_var.get(),
                    'end_time': self.end_time_var.get(),
                    'workers': self.workers_var.get(),
                    'interval_ms': self.interval_var.get(),
                }
            }
            
            if mode == "stress" and self.results:
                times = [r.response_time_ms for r in self.results]
                export_data['summary'] = {
                    'total': len(self.results),
                    'success': sum(1 for r in self.results if r.success),
                    'fail': sum(1 for r in self.results if not r.success),
                    'min_time_ms': min(times) if times else 0,
                    'max_time_ms': max(times) if times else 0,
                    'avg_time_ms': mean(times) if times else 0,
                    'median_time_ms': median(times) if times else 0,
                }
                export_data['results'] = [
                    {
                        'device_id': r.device_id,
                        'device_ip': r.device_ip,
                        'operation': r.operation,
                        'success': r.success,
                        'response_time_ms': r.response_time_ms,
                        'data_count': r.data_count,
                        'error_msg': r.error_msg,
                        'timestamp': r.timestamp
                    }
                    for r in self.results
                ]
            elif self.query_results:
                export_data['summary'] = {
                    'total': len(self.query_results),
                    'success': sum(1 for r in self.query_results if r.get('success')),
                    'fail': sum(1 for r in self.query_results if not r.get('success')),
                }
                export_data['results'] = self.query_results
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            self._log(f"结果已导出: {filename}", "success")
            messagebox.showinfo("导出成功", f"结果已保存:\n{filepath}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))


def main():
    root = tk.Tk()
    app = UnifiedSuperBrainTool(root)
    root.mainloop()


if __name__ == "__main__":
    main()
