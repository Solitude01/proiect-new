#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
超脑批量压力测试工具
功能：
1. 批量获取多个设备的通道
2. 批量查询AIOP事件
3. 压力测试（多并发、多请求）
4. 统计结果和性能数据
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
from dataclasses import dataclass
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
    operation: str  # 'get_channels' 或 'query_aiop'
    success: bool
    response_time_ms: float
    data_count: int = 0  # 通道数或事件数
    error_msg: str = ""
    timestamp: str = ""


@dataclass
class DeviceInfo:
    """设备信息"""
    id: str
    ip: str
    password: str
    http_port: int = 80
    scheme: str = "http"
    username: str = "admin"
    channels: List[Dict] = None
    
    def __post_init__(self):
        if self.channels is None:
            self.channels = []
    
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
    
    def get_all_channels(self) -> Tuple[bool, List[Dict], float, str]:
        """获取所有通道，返回(成功, 通道列表, 响应时间, 错误信息)"""
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
                            channels.append({'id': channel_id, 'name': channel_name})
                
                return True, channels, elapsed, ""
            else:
                return False, [], elapsed, f"HTTP {resp.status_code}"
                
        except Exception as e:
            elapsed = (time.time() - start_ts) * 1000
            return False, [], elapsed, str(e)
    
    def ai_intelligent_search(self, channels: List[int], start_time: datetime, 
                              end_time: datetime, max_results: int = 30) -> Tuple[bool, Dict, float, str]:
        """AIOP事件查询，返回(成功, 结果数据, 响应时间, 错误信息)"""
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
        
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        start_ts = time.time()
        try:
            resp = self.session.post(url, json=payload, auth=self.auth, 
                                    headers=headers, timeout=30)
            elapsed = (time.time() - start_ts) * 1000
            
            if resp.status_code == 200:
                data = resp.json()
                result = data.get('SearchResult', {})
                matches = result.get('numOfMatches', 0)
                return True, result, elapsed, ""
            else:
                return False, {}, elapsed, f"HTTP {resp.status_code}"
                
        except Exception as e:
            elapsed = (time.time() - start_ts) * 1000
            return False, {}, elapsed, str(e)


class BatchStressTestTool:
    """批量压力测试工具"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("超脑批量压力测试工具")
        self.root.geometry("1200x800")
        
        # 加载设备
        self.devices: List[DeviceInfo] = []
        self.results: List[TestResult] = []
        self.is_running = False
        self.cancel_event = threading.Event()
        
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
                    scheme=item.get('Scheme', 'http'),
                    username='admin'
                )
                if device.id and device.ip:
                    self.devices.append(device)
            
            self.devices.sort(key=lambda x: int(x.id) if x.id.isdigit() else x.id)
            
        except Exception as e:
            messagebox.showerror("错误", f"加载设备失败: {e}")
    
    def _build_ui(self):
        """构建UI"""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        # ===== 左侧面板：配置 =====
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side="left", fill="y", padx=(0, 10))
        
        # 设备选择
        device_frame = ttk.LabelFrame(left_frame, text="设备选择", padding=10)
        device_frame.pack(fill="x", pady=5)
        
        self.device_listbox = tk.Listbox(device_frame, selectmode=tk.MULTIPLE, height=10, width=35)
        scrollbar = ttk.Scrollbar(device_frame, orient="vertical", command=self.device_listbox.yview)
        self.device_listbox.configure(yscrollcommand=scrollbar.set)
        
        for device in self.devices:
            self.device_listbox.insert(tk.END, f"DM{device.id:>2} - {device.ip}")
        
        self.device_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        btn_frame = ttk.Frame(device_frame)
        btn_frame.pack(fill="x", pady=5)
        ttk.Button(btn_frame, text="全选", command=self._select_all).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="清空", command=self._select_none).pack(side="left", padx=2)
        
        # 测试配置
        config_frame = ttk.LabelFrame(left_frame, text="测试配置", padding=10)
        config_frame.pack(fill="x", pady=5)
        
        # 测试类型
        ttk.Label(config_frame, text="测试类型:").grid(row=0, column=0, sticky="w", pady=3)
        self.test_type_var = tk.StringVar(value="channels")
        ttk.Combobox(config_frame, textvariable=self.test_type_var,
                    values=["channels", "aiop_once", "aiop_stress"],
                    width=25, state="readonly").grid(row=0, column=1, sticky="w")
        ttk.Label(config_frame, text="(channels=获取通道, aiop_once=单次查询, aiop_stress=压力测试)").grid(row=0, column=2, sticky="w", padx=5)
        
        # 并发数
        ttk.Label(config_frame, text="并发线程:").grid(row=1, column=0, sticky="w", pady=3)
        self.workers_var = tk.IntVar(value=5)
        ttk.Spinbox(config_frame, from_=1, to=50, textvariable=self.workers_var, width=10).grid(row=1, column=1, sticky="w")
        
        # 每设备请求数（压力测试用）
        ttk.Label(config_frame, text="每设备请求:").grid(row=2, column=0, sticky="w", pady=3)
        self.requests_var = tk.IntVar(value=10)
        ttk.Spinbox(config_frame, from_=1, to=100, textvariable=self.requests_var, width=10).grid(row=2, column=1, sticky="w")
        ttk.Label(config_frame, text="(仅压力测试有效)").grid(row=2, column=2, sticky="w", padx=5)
        
        # 请求间隔
        ttk.Label(config_frame, text="请求间隔(ms):").grid(row=3, column=0, sticky="w", pady=3)
        self.interval_var = tk.IntVar(value=100)
        ttk.Spinbox(config_frame, from_=0, to=5000, textvariable=self.interval_var, width=10).grid(row=3, column=1, sticky="w")
        
        # 时间范围（AIOP查询用）
        ttk.Label(config_frame, text="开始时间:").grid(row=4, column=0, sticky="w", pady=3)
        self.start_time_var = tk.StringVar(
            value=datetime.now().replace(hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M"))
        ttk.Entry(config_frame, textvariable=self.start_time_var, width=18).grid(row=4, column=1, sticky="w")
        
        ttk.Label(config_frame, text="结束时间:").grid(row=5, column=0, sticky="w", pady=3)
        self.end_time_var = tk.StringVar(
            value=datetime.now().replace(hour=23, minute=59, second=59).strftime("%Y-%m-%d %H:%M"))
        ttk.Entry(config_frame, textvariable=self.end_time_var, width=18).grid(row=5, column=1, sticky="w")
        
        # 控制按钮
        ctrl_frame = ttk.Frame(left_frame)
        ctrl_frame.pack(fill="x", pady=10)
        
        self.start_btn = ttk.Button(ctrl_frame, text="开始测试", command=self._start_test)
        self.start_btn.pack(fill="x", pady=2)
        
        self.stop_btn = ttk.Button(ctrl_frame, text="停止测试", command=self._stop_test, state="disabled")
        self.stop_btn.pack(fill="x", pady=2)
        
        self.export_btn = ttk.Button(ctrl_frame, text="导出结果", command=self._export_results, state="disabled")
        self.export_btn.pack(fill="x", pady=2)
        
        # ===== 右侧面板：日志和统计 =====
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side="left", fill="both", expand=True)
        
        # 统计信息
        stats_frame = ttk.LabelFrame(right_frame, text="统计信息", padding=10)
        stats_frame.pack(fill="x", pady=5)
        
        self.stats_var = tk.StringVar(value="就绪 - 请选择设备和测试类型")
        ttk.Label(stats_frame, textvariable=self.stats_var, font=("Consolas", 10), 
                 wraplength=600, justify="left").pack(anchor="w")
        
        # 进度条
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(right_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x", pady=5)
        
        # 日志
        log_frame = ttk.LabelFrame(right_frame, text="测试日志", padding=5)
        log_frame.pack(fill="both", expand=True, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap="word", font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True)
        self.log_text.tag_configure("success", foreground="green")
        self.log_text.tag_configure("error", foreground="red")
        self.log_text.tag_configure("info", foreground="blue")
        self.log_text.tag_configure("warning", foreground="orange")
    
    def _select_all(self):
        self.device_listbox.select_set(0, tk.END)
    
    def _select_none(self):
        self.device_listbox.selection_clear(0, tk.END)
    
    def _get_selected_devices(self) -> List[DeviceInfo]:
        selected = []
        for i in self.device_listbox.curselection():
            selected.append(self.devices[i])
        return selected
    
    def _parse_time(self, time_str: str) -> datetime:
        try:
            return datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        except:
            try:
                return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            except:
                return datetime.now()
    
    def _log(self, message: str, tag: Optional[str] = None):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
        self.log_text.see(tk.END)
    
    def _update_stats(self, completed: int, success: int, fail: int, avg_time: float = 0):
        total = len(self._get_selected_devices())
        progress = (completed / total * 100) if total > 0 else 0
        
        stats_text = (f"设备: {total} | 完成: {completed}/{total} | 进度: {progress:.0f}%\n"
                     f"成功: {success} | 失败: {fail} | 平均响应: {avg_time:.0f}ms")
        
        self.stats_var.set(stats_text)
        self.progress_var.set(progress)
    
    def _start_test(self):
        devices = self._get_selected_devices()
        if not devices:
            messagebox.showwarning("提示", "请至少选择一个设备")
            return
        
        test_type = self.test_type_var.get()
        
        # 解析时间（AIOP查询用）
        if test_type in ["aiop_once", "aiop_stress"]:
            try:
                start_time = self._parse_time(self.start_time_var.get())
                end_time = self._parse_time(self.end_time_var.get())
            except:
                messagebox.showwarning("提示", "时间格式错误")
                return
        
        self.is_running = True
        self.cancel_event.clear()
        self.results = []
        
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.export_btn.config(state="disabled")
        self.log_text.delete(1.0, tk.END)
        
        self._log(f"开始测试: {test_type}, 设备数: {len(devices)}", "info")
        
        if test_type == "channels":
            thread = threading.Thread(target=self._test_get_channels, args=(devices,), daemon=True)
        elif test_type == "aiop_once":
            thread = threading.Thread(target=self._test_aiop_once, 
                                     args=(devices, start_time, end_time), daemon=True)
        else:  # aiop_stress
            thread = threading.Thread(target=self._test_aiop_stress, 
                                     args=(devices, start_time, end_time), daemon=True)
        
        thread.start()
    
    def _stop_test(self):
        if self.is_running:
            self.cancel_event.set()
            self._log("正在停止测试...", "warning")
    
    def _test_get_channels(self, devices: List[DeviceInfo]):
        """测试获取通道"""
        workers = self.workers_var.get()
        
        completed = 0
        success = 0
        fail = 0
        total_time = 0.0
        total_channels = 0
        
        def test_device(device: DeviceInfo):
            if self.cancel_event.is_set():
                return None
            
            client = DeepmindClient(device)
            ok, channels, elapsed, error = client.get_all_channels()
            
            result = TestResult(
                device_id=device.id,
                device_ip=device.ip,
                operation="get_channels",
                success=ok,
                response_time_ms=elapsed,
                data_count=len(channels),
                error_msg=error,
                timestamp=datetime.now().isoformat()
            )
            
            if ok:
                device.channels = channels
                self._log(f"[OK] DM{device.id}: {len(channels)}个通道 ({elapsed:.0f}ms)", "success")
            else:
                self._log(f"[FAIL] DM{device.id}: {error} ({elapsed:.0f}ms)", "error")
            
            return result
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(test_device, d): d for d in devices}
            
            for future in as_completed(futures):
                result = future.result()
                if result:
                    self.results.append(result)
                    completed += 1
                    total_time += result.response_time_ms
                    if result.success:
                        success += 1
                        total_channels += result.data_count
                    else:
                        fail += 1
                    
                    avg_time = total_time / completed if completed > 0 else 0
                    self.root.after(0, lambda: self._update_stats(completed, success, fail, avg_time))
        
        self.is_running = False
        self.root.after(0, self._finish_test, completed, success, fail, total_channels)
    
    def _test_aiop_once(self, devices: List[DeviceInfo], start_time: datetime, end_time: datetime):
        """单次AIOP查询测试"""
        workers = self.workers_var.get()
        interval = self.interval_var.get() / 1000.0
        
        # 先获取通道
        self._log("步骤1: 获取通道列表...", "info")
        for device in devices:
            if self.cancel_event.is_set():
                break
            client = DeepmindClient(device)
            ok, channels, _, _ = client.get_all_channels()
            if ok:
                device.channels = channels
                self._log(f"  DM{device.id}: {len(channels)}个通道", "info")
        
        # 查询AIOP事件
        self._log("步骤2: 查询AIOP事件...", "info")
        
        completed = 0
        success = 0
        fail = 0
        total_time = 0.0
        total_events = 0
        
        def query_device(device: DeviceInfo):
            if self.cancel_event.is_set():
                return None
            
            if not device.channels:
                return TestResult(
                    device_id=device.id,
                    device_ip=device.ip,
                    operation="query_aiop",
                    success=False,
                    response_time_ms=0,
                    error_msg="无通道信息"
                )
            
            client = DeepmindClient(device)
            channel_ids = [int(ch['id']) for ch in device.channels]
            
            ok, data, elapsed, error = client.ai_intelligent_search(
                channel_ids, start_time, end_time, max_results=30
            )
            
            matches = data.get('numOfMatches', 0) if ok else 0
            
            result = TestResult(
                device_id=device.id,
                device_ip=device.ip,
                operation="query_aiop",
                success=ok,
                response_time_ms=elapsed,
                data_count=matches,
                error_msg=error,
                timestamp=datetime.now().isoformat()
            )
            
            if ok:
                self._log(f"[OK] DM{device.id}: {matches}条事件 ({elapsed:.0f}ms)", "success")
            else:
                self._log(f"[FAIL] DM{device.id}: {error} ({elapsed:.0f}ms)", "error")
            
            if interval > 0:
                time.sleep(interval)
            
            return result
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(query_device, d): d for d in devices}
            
            for future in as_completed(futures):
                result = future.result()
                if result:
                    self.results.append(result)
                    completed += 1
                    total_time += result.response_time_ms
                    if result.success:
                        success += 1
                        total_events += result.data_count
                    else:
                        fail += 1
                    
                    avg_time = total_time / completed if completed > 0 else 0
                    self.root.after(0, lambda: self._update_stats(completed, success, fail, avg_time))
        
        self.is_running = False
        self.root.after(0, self._finish_test, completed, success, fail, total_events)
    
    def _test_aiop_stress(self, devices: List[DeviceInfo], start_time: datetime, end_time: datetime):
        """AIOP压力测试"""
        workers = self.workers_var.get()
        requests_per_device = self.requests_var.get()
        interval = self.interval_var.get() / 1000.0
        
        # 先获取通道
        self._log("步骤1: 获取通道列表...", "info")
        for device in devices:
            if self.cancel_event.is_set():
                break
            client = DeepmindClient(device)
            ok, channels, _, _ = client.get_all_channels()
            if ok:
                device.channels = channels
        
        # 压力测试
        total_requests = len(devices) * requests_per_device
        self._log(f"步骤2: 压力测试 ({total_requests}次请求, {workers}并发)...", "info")
        
        completed = 0
        success = 0
        fail = 0
        total_time = 0.0
        
        def stress_query(device: DeviceInfo, req_index: int):
            if self.cancel_event.is_set():
                return None
            
            client = DeepmindClient(device)
            channel_ids = [int(ch['id']) for ch in device.channels] if device.channels else [1]
            
            ok, data, elapsed, error = client.ai_intelligent_search(
                channel_ids, start_time, end_time, max_results=30
            )
            
            result = TestResult(
                device_id=device.id,
                device_ip=device.ip,
                operation=f"stress_{req_index}",
                success=ok,
                response_time_ms=elapsed,
                error_msg=error,
                timestamp=datetime.now().isoformat()
            )
            
            if interval > 0:
                time.sleep(interval)
            
            return result
        
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
                        self._log(f"进度: {completed}/{total_requests} 完成", "info")
                        self.root.after(0, lambda: self._update_stats(completed, success, fail, avg_time))
        
        self.is_running = False
        self.root.after(0, self._finish_test, completed, success, fail, 0)
    
    def _finish_test(self, total: int, success: int, fail: int, data_count: int):
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.export_btn.config(state="normal")
        
        # 计算统计信息
        if self.results:
            times = [r.response_time_ms for r in self.results]
            min_time = min(times)
            max_time = max(times)
            avg_time = mean(times)
            median_time = median(times)
        else:
            min_time = max_time = avg_time = median_time = 0
        
        self._log("=" * 60, "info")
        self._log(f"测试完成!", "info")
        self._log(f"总请求: {total}", "info")
        self._log(f"成功: {success} ({success/total*100:.1f}%)", "success" if fail == 0 else "info")
        self._log(f"失败: {fail} ({fail/total*100:.1f}%)", "error" if fail > 0 else "info")
        if data_count > 0:
            self._log(f"数据总数: {data_count}", "info")
        self._log(f"响应时间 - 最小: {min_time:.0f}ms, 最大: {max_time:.0f}ms, 平均: {avg_time:.0f}ms, 中位数: {median_time:.0f}ms", "info")
        self._log("=" * 60, "info")
    
    def _export_results(self):
        """导出测试结果"""
        if not self.results:
            messagebox.showinfo("提示", "没有可导出的结果")
            return
        
        try:
            filename = f"stress_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
            
            # 计算统计信息
            times = [r.response_time_ms for r in self.results]
            
            export_data = {
                'export_time': datetime.now().isoformat(),
                'config': {
                    'test_type': self.test_type_var.get(),
                    'workers': self.workers_var.get(),
                    'requests_per_device': self.requests_var.get(),
                    'interval_ms': self.interval_var.get(),
                },
                'summary': {
                    'total_requests': len(self.results),
                    'success': sum(1 for r in self.results if r.success),
                    'fail': sum(1 for r in self.results if not r.success),
                    'min_time_ms': min(times) if times else 0,
                    'max_time_ms': max(times) if times else 0,
                    'avg_time_ms': mean(times) if times else 0,
                    'median_time_ms': median(times) if times else 0,
                },
                'results': [
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
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            self._log(f"结果已导出: {filename}", "success")
            messagebox.showinfo("导出成功", f"结果已保存:\n{filepath}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))


def main():
    root = tk.Tk()
    app = BatchStressTestTool(root)
    root.mainloop()


if __name__ == "__main__":
    main()
