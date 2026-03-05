#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
超脑查询工具 - 完整版
功能：
1. 自动获取设备所有通道
2. 可视化选择通道
3. 查询AIOP事件/全部事件
4. 批量设备查询
"""

import os
import sys
import json
import time
import uuid
import threading
import requests
import xml.etree.ElementTree as ET
from requests.auth import HTTPDigestAuth
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# 禁用SSL警告
from urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


class ChannelInfo:
    """通道信息类"""
    def __init__(self, channel_id: str, name: str = "未知"):
        self.id = channel_id
        self.name = name
        self.selected = True  # 默认选中


class DeviceInfo:
    """设备信息类"""
    def __init__(self, device_dict: Dict):
        self.id = device_dict['id']
        self.ip = device_dict['ip']
        self.password = device_dict['password']
        self.http_port = device_dict['http_port']
        self.scheme = device_dict['scheme']
        self.username = device_dict['username']
        self.channels: List[ChannelInfo] = []
        self.status = "未连接"
        
    def get_base_url(self):
        return f"{self.scheme}://{self.ip}:{self.http_port}"


class DeepmindClient:
    """超脑设备客户端"""
    
    def __init__(self, device: DeviceInfo):
        self.device = device
        self.session = requests.Session()
        self.session.verify = False
        self.session.trust_env = False
        self.auth = HTTPDigestAuth(device.username, device.password)
    
    def get_all_channels(self) -> List[ChannelInfo]:
        """获取设备所有通道"""
        url = f"{self.device.get_base_url()}/ISAPI/ContentMgmt/InputProxy/channels"
        
        try:
            resp = self.session.get(url, auth=self.auth, timeout=10)
            
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
                            channels.append(ChannelInfo(channel_id, channel_name))
                
                return channels
            else:
                return []
        except Exception as e:
            print(f"获取通道异常: {e}")
            return []
    
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
                'error': None
            }
        except Exception as e:
            return {
                'success': False,
                'status_code': None,
                'response_time_ms': 0,
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
                "timeSpanList": [{"startTime": start_time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                                "endTime": end_time.strftime("%Y-%m-%dT%H:%M:%S+08:00")}],
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
                'response_time_ms': 0,
                'response': None,
                'error': str(e)
            }


class SuperBrainQueryTool:
    """超脑查询工具主类"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("超脑查询工具 - 完整版")
        self.root.geometry("1400x900")
        self.root.minsize(1200, 800)
        
        # 加载设备
        self.devices: List[DeviceInfo] = []
        self.selected_device: Optional[DeviceInfo] = None
        self.query_results = []
        
        self._load_devices()
        self._build_ui()
    
    def _load_devices(self):
        """从Deepmind.json加载设备"""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(script_dir)
            json_path = os.path.join(parent_dir, "Deepmind.json")
            
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for item in data:
                device_dict = {
                    'id': str(item.get('Deepmind', '')),
                    'ip': item.get('IP', ''),
                    'password': item.get('Password', ''),
                    'http_port': int(item.get('HttpPort', 80)),
                    'rtsp_port': int(item.get('RtspPort', 554)),
                    'scheme': item.get('Scheme', 'http'),
                    'username': 'admin',
                }
                if device_dict['id'] and device_dict['ip']:
                    self.devices.append(DeviceInfo(device_dict))
            
            # 排序
            self.devices.sort(key=lambda x: int(x.id) if x.id.isdigit() else x.id)
            
        except Exception as e:
            messagebox.showerror("错误", f"加载设备失败: {e}")
    
    def _build_ui(self):
        """构建UI"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # ===== 顶部：标题 =====
        title_label = ttk.Label(
            main_frame,
            text="超脑查询工具 - 获取通道 + 查询AIOP事件",
            font=("Microsoft YaHei", 16, "bold")
        )
        title_label.grid(row=0, column=0, pady=(0, 10), sticky=tk.W)
        
        # ===== 主内容区 - 三栏布局 =====
        content_frame = ttk.Frame(main_frame)
        content_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        content_frame.columnconfigure(0, weight=1)
        content_frame.columnconfigure(1, weight=1)
        content_frame.columnconfigure(2, weight=1)
        content_frame.rowconfigure(0, weight=1)
        
        # ===== 左栏：设备列表 =====
        left_frame = ttk.LabelFrame(content_frame, text="1. 选择设备", padding=10)
        left_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5)
        left_frame.rowconfigure(1, weight=1)
        
        # 设备列表
        self.device_listbox = tk.Listbox(left_frame, selectmode=tk.SINGLE, height=15, width=30)
        scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=self.device_listbox.yview)
        self.device_listbox.configure(yscrollcommand=scrollbar.set)
        
        for device in self.devices:
            self.device_listbox.insert(tk.END, f"DM{device.id:>2} - {device.ip}")
        
        self.device_listbox.bind('<<ListboxSelect>>', self._on_device_selected)
        self.device_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # 获取通道按钮
        ttk.Button(left_frame, text="获取通道列表", command=self._fetch_channels).grid(row=1, column=0, pady=10, sticky=tk.EW)
        
        # ===== 中栏：通道列表 =====
        middle_frame = ttk.LabelFrame(content_frame, text="2. 选择通道", padding=10)
        middle_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5)
        middle_frame.rowconfigure(0, weight=1)
        middle_frame.columnconfigure(0, weight=1)
        
        # 通道列表容器（带滚动条）
        self.channel_canvas = tk.Canvas(middle_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(middle_frame, orient="vertical", command=self.channel_canvas.yview)
        self.channel_frame = ttk.Frame(self.channel_canvas)
        
        self.channel_frame.bind(
            "<Configure>",
            lambda e: self.channel_canvas.configure(scrollregion=self.channel_canvas.bbox("all"))
        )
        
        self.channel_canvas.create_window((0, 0), window=self.channel_frame, anchor="nw", width=350)
        self.channel_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.channel_canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # 通道操作按钮
        btn_frame = ttk.Frame(middle_frame)
        btn_frame.grid(row=1, column=0, pady=10, sticky=tk.EW)
        
        ttk.Button(btn_frame, text="全选", command=self._select_all_channels).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="取消全选", command=self._deselect_all_channels).pack(side=tk.LEFT, padx=2)
        
        # ===== 右栏：查询参数 =====
        right_frame = ttk.LabelFrame(content_frame, text="3. 查询参数", padding=10)
        right_frame.grid(row=0, column=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5)
        
        # 查询类型
        ttk.Label(right_frame, text="查询类型:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.query_type_var = tk.StringVar(value="aiop")
        ttk.Combobox(right_frame, textvariable=self.query_type_var,
                    values=["aiop", "event"], width=20, state="readonly").grid(row=0, column=1, sticky=tk.W)
        
        # 时间范围
        ttk.Label(right_frame, text="开始时间:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.start_time_var = tk.StringVar(
            value=datetime.now().replace(hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M"))
        ttk.Entry(right_frame, textvariable=self.start_time_var, width=20).grid(row=1, column=1, sticky=tk.W)
        
        ttk.Label(right_frame, text="结束时间:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.end_time_var = tk.StringVar(
            value=datetime.now().replace(hour=23, minute=59, second=59).strftime("%Y-%m-%d %H:%M"))
        ttk.Entry(right_frame, textvariable=self.end_time_var, width=20).grid(row=2, column=1, sticky=tk.W)
        
        # 最大结果
        ttk.Label(right_frame, text="最大结果:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.max_results_var = tk.IntVar(value=30)
        ttk.Spinbox(right_frame, from_=1, to=100, textvariable=self.max_results_var, width=10).grid(row=3, column=1, sticky=tk.W)
        
        # 执行按钮
        execute_btn = tk.Button(
            right_frame,
            text="执行查询",
            command=self._execute_query,
            bg="#4CAF50",
            fg="white",
            font=("Microsoft YaHei", 12, "bold"),
            padx=20,
            pady=10
        )
        execute_btn.grid(row=4, column=0, columnspan=2, pady=20, sticky=tk.EW)
        
        # ===== 底部：日志和结果 =====
        bottom_frame = ttk.LabelFrame(main_frame, text="查询日志", padding=10)
        bottom_frame.grid(row=2, column=0, pady=10, sticky=(tk.W, tk.E, tk.N, tk.S))
        bottom_frame.columnconfigure(0, weight=1)
        bottom_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(bottom_frame, wrap=tk.WORD, height=12, font=("Consolas", 10))
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.log_text.tag_configure("success", foreground="green")
        self.log_text.tag_configure("error", foreground="red")
        self.log_text.tag_configure("info", foreground="blue")
        
        # 存储引用
        self.channel_vars = {}  # channel_id -> BooleanVar
        self.channel_checkboxes = []
    
    def _on_device_selected(self, event=None):
        """设备选择事件"""
        selection = self.device_listbox.curselection()
        if selection:
            index = selection[0]
            self.selected_device = self.devices[index]
            self._log(f"选择设备: DM{self.selected_device.id} ({self.selected_device.ip})")
            
            # 如果已有通道，显示它们
            if self.selected_device.channels:
                self._display_channels()
            else:
                self._clear_channel_display()
                self._log("点击'获取通道列表'按钮获取通道")
    
    def _clear_channel_display(self):
        """清空通道显示"""
        for widget in self.channel_frame.winfo_children():
            widget.destroy()
        self.channel_vars = {}
        self.channel_checkboxes = []
    
    def _display_channels(self):
        """显示通道列表"""
        if not self.selected_device or not self.selected_device.channels:
            return
        
        self._clear_channel_display()
        
        # 添加标题
        ttk.Label(self.channel_frame, text=f"共 {len(self.selected_device.channels)} 个通道",
                 font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=(0, 10))
        
        # 为每个通道创建复选框
        for channel in self.selected_device.channels:
            var = tk.BooleanVar(value=channel.selected)
            self.channel_vars[channel.id] = var
            
            cb = ttk.Checkbutton(
                self.channel_frame,
                text=f"通道 {channel.id}: {channel.name}",
                variable=var,
                command=lambda cid=channel.id: self._on_channel_toggle(cid)
            )
            cb.pack(anchor=tk.W, pady=2)
            self.channel_checkboxes.append(cb)
        
        # 更新滚动区域
        self.channel_frame.update_idletasks()
        self.channel_canvas.configure(scrollregion=self.channel_canvas.bbox("all"))
    
    def _on_channel_toggle(self, channel_id):
        """通道选择切换"""
        if self.selected_device:
            for ch in self.selected_device.channels:
                if ch.id == channel_id:
                    ch.selected = self.channel_vars[channel_id].get()
                    break
    
    def _select_all_channels(self):
        """全选通道"""
        for var in self.channel_vars.values():
            var.set(True)
        if self.selected_device:
            for ch in self.selected_device.channels:
                ch.selected = True
    
    def _deselect_all_channels(self):
        """取消全选通道"""
        for var in self.channel_vars.values():
            var.set(False)
        if self.selected_device:
            for ch in self.selected_device.channels:
                ch.selected = False
    
    def _fetch_channels(self):
        """获取通道列表"""
        if not self.selected_device:
            messagebox.showwarning("提示", "请先选择一个设备")
            return
        
        def task():
            self._log(f"[{self.selected_device.ip}] 正在获取通道列表...")
            
            client = DeepmindClient(self.selected_device)
            channels = client.get_all_channels()
            
            if channels:
                self.selected_device.channels = channels
                self.selected_device.status = "已连接"
                self._log(f"  ✓ 发现 {len(channels)} 个通道")
                
                # 在主线程更新UI
                self.root.after(0, self._display_channels)
            else:
                self.selected_device.status = "获取失败"
                self._log(f"  ✗ 无法获取通道列表")
        
        threading.Thread(target=task, daemon=True).start()
    
    def _get_selected_channels(self) -> List[int]:
        """获取选中的通道ID列表"""
        selected = []
        if self.selected_device:
            for ch in self.selected_device.channels:
                if ch.selected:
                    selected.append(int(ch.id))
        return selected
    
    def _parse_time(self, time_str: str) -> datetime:
        """解析时间字符串"""
        try:
            return datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        except:
            try:
                return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            except:
                return datetime.now()
    
    def _execute_query(self):
        """执行查询"""
        if not self.selected_device:
            messagebox.showwarning("提示", "请先选择一个设备")
            return
        
        if not self.selected_device.channels:
            messagebox.showwarning("提示", "请先获取通道列表")
            return
        
        selected_channels = self._get_selected_channels()
        if not selected_channels:
            messagebox.showwarning("提示", "请至少选择一个通道")
            return
        
        # 解析时间
        try:
            start_time = self._parse_time(self.start_time_var.get())
            end_time = self._parse_time(self.end_time_var.get())
        except:
            messagebox.showwarning("提示", "时间格式错误")
            return
        
        # 执行查询
        def task():
            query_type = self.query_type_var.get()
            max_results = self.max_results_var.get()
            
            self._log("=" * 60)
            self._log(f"开始查询: DM{self.selected_device.id}")
            self._log(f"通道: {selected_channels}")
            self._log(f"时间: {start_time} ~ {end_time}")
            self._log(f"类型: {query_type}")
            self._log("-" * 60)
            
            client = DeepmindClient(self.selected_device)
            
            if query_type == "aiop":
                result = client.ai_intelligent_search(selected_channels, start_time, end_time, max_results)
            else:
                result = client.event_record_search(selected_channels, start_time, end_time, max_results)
            
            # 处理结果
            if result['success']:
                self._log(f"[SUCCESS] 查询成功! ({result['response_time_ms']:.1f}ms)")
                
                response = result.get('response', {})
                if query_type == "aiop" and 'SearchResult' in response:
                    sr = response['SearchResult']
                    matches = sr.get('numOfMatches', 0)
                    status = sr.get('responseStatusStrg', 'N/A')
                    self._log(f"状态: {status}")
                    self._log(f"匹配数: {matches}")
                    
                    # 显示AI告警
                    ai_alarms = sr.get('AIAlarmInfo', [])
                    if ai_alarms:
                        self._log(f"\nAI告警列表 (显示前5条):")
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
                        self._log(f"\n事件列表 (显示前5条):")
                        for i, event in enumerate(match_list[:5]):
                            self._log(f"  [{i+1}] 通道{event.get('channel', 'N/A')} - {event.get('time', 'N/A')} - {event.get('eventType', 'N/A')}")
                    else:
                        self._log("无事件记录")
            else:
                self._log(f"[FAILED] 查询失败: {result.get('status_code', 'N/A')}")
                if result.get('error'):
                    self._log(f"错误: {result['error']}")
            
            self._log("=" * 60)
        
        threading.Thread(target=task, daemon=True).start()
    
    def _log(self, message: str, tag: Optional[str] = None):
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
        self.log_text.see(tk.END)


def main():
    root = tk.Tk()
    app = SuperBrainQueryTool(root)
    root.mainloop()


if __name__ == "__main__":
    main()
