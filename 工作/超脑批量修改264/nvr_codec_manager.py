#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
超脑设备编码格式批量修改工具
功能：加载 Deepmind.json，自动发现通道，检查编码格式，批量修改为 H.264
新增功能：显示监控点名称、搜索、导出监控点、单个设备扫描
"""

import json
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading
import requests
from requests.auth import HTTPDigestAuth
import xml.etree.ElementTree as ET
from datetime import datetime
import csv


class NvrDevice:
    """NVR设备类"""
    def __init__(self, deepmind_id, ip, password, http_port=80, rtsp_port=554, scheme="http"):
        self.deepmind_id = deepmind_id
        self.ip = ip
        self.password = password
        self.http_port = http_port
        self.rtsp_port = rtsp_port
        self.scheme = scheme
        self.auth = HTTPDigestAuth('admin', password)
        self.channels = []  # 发现的通道列表 [{id, stream_id, codec, name, enabled}, ...]
        self.status = "未连接"
        self.error_msg = ""

    def get_base_url(self):
        return f"{self.scheme}://{self.ip}:{self.http_port}"


class NvrCodecManager:
    """NVR编码管理器主类"""

    def __init__(self, root):
        self.root = root
        self.root.title("超脑设备编码格式批量修改工具")
        self.root.geometry("1400x800")
        self.root.minsize(1200, 700)

        self.devices = []  # 设备列表
        self.search_text = ""  # 搜索文本
        self.setup_ui()
        self.load_devices()

    def setup_ui(self):
        """设置UI界面"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 配置行列权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # 标题
        title_label = ttk.Label(
            main_frame,
            text="超脑设备编码格式批量修改工具",
            font=("Microsoft YaHei", 16, "bold")
        )
        title_label.grid(row=0, column=0, pady=(0, 10), sticky=tk.W)

        # 主内容区 - 左右分栏
        content_frame = ttk.Frame(main_frame)
        content_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        content_frame.columnconfigure(0, weight=3)
        content_frame.columnconfigure(1, weight=1)
        content_frame.rowconfigure(0, weight=1)

        # ===== 左侧：设备列表 =====
        left_frame = ttk.LabelFrame(content_frame, text="设备列表（勾选要修改的通道）", padding="10")
        left_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(1, weight=1)

        # 工具栏
        toolbar = ttk.Frame(left_frame)
        toolbar.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Button(toolbar, text="🔄 刷新设备", command=self.load_devices).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="🔍 扫描所有设备", command=self.check_codecs).pack(side=tk.LEFT, padx=5)
        
        # 单个设备扫描区域
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=10, fill=tk.Y)
        ttk.Label(toolbar, text="扫描指定设备:").pack(side=tk.LEFT, padx=(5, 0))
        
        # 设备选择下拉框
        self.device_combo = ttk.Combobox(toolbar, width=20, state="readonly")
        self.device_combo.pack(side=tk.LEFT, padx=5)
        self.device_combo.bind("<<ComboboxSelected>>", self.on_device_selected)
        
        ttk.Button(toolbar, text="🔍 扫描该设备", command=self.scan_selected_device).pack(side=tk.LEFT, padx=5)
        
        # 搜索和导出区域
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=10, fill=tk.Y)
        ttk.Label(toolbar, text="搜索:").pack(side=tk.LEFT, padx=(5, 0))
        
        self.search_entry = ttk.Entry(toolbar, width=25)
        self.search_entry.pack(side=tk.LEFT, padx=5)
        self.search_entry.bind("<KeyRelease>", self.on_search)
        
        ttk.Button(toolbar, text="📥 导出监控点", command=self.export_channels).pack(side=tk.LEFT, padx=5)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=10, fill=tk.Y)
        ttk.Button(toolbar, text="✓ 全选H.265", command=self.select_all_h265).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="✗ 取消全选", command=self.deselect_all).pack(side=tk.LEFT, padx=5)

        # 创建Canvas用于滚动
        self.canvas = tk.Canvas(left_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor=tk.NW, width=750)
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=1, column=1, sticky=(tk.N, tk.S))

        # 绑定鼠标滚轮
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # ===== 右侧：日志 =====
        right_frame = ttk.LabelFrame(content_frame, text="操作日志", padding="10")
        right_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)

        # 日志文本框
        self.log_text = scrolledtext.ScrolledText(
            right_frame,
            wrap=tk.WORD,
            width=45,
            height=35,
            font=("Consolas", 10)
        )
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 日志按钮区
        log_btn_frame = ttk.Frame(right_frame)
        log_btn_frame.grid(row=1, column=0, pady=(10, 0), sticky=(tk.W, tk.E))
        ttk.Button(log_btn_frame, text="清空日志", command=self.clear_log).pack(side=tk.RIGHT)

        # ===== 底部操作区 =====
        bottom_frame = ttk.LabelFrame(main_frame, text="批量操作", padding="10")
        bottom_frame.grid(row=2, column=0, pady=15, sticky=(tk.W, tk.E))

        # 统计信息
        self.stats_label = ttk.Label(bottom_frame, text="就绪 | 已选: 0 个通道", font=("Microsoft YaHei", 11))
        self.stats_label.pack(side=tk.LEFT, padx=10)

        # 进度条
        self.progress = ttk.Progressbar(bottom_frame, length=300, mode='determinate')
        self.progress.pack(side=tk.LEFT, padx=20)
        self.progress_label = ttk.Label(bottom_frame, text="0/0", font=("Microsoft YaHei", 10))
        self.progress_label.pack(side=tk.LEFT, padx=5)

        # 执行按钮
        execute_btn = tk.Button(
            bottom_frame,
            text="▶ 执行修改",
            command=self.execute_modify,
            bg="#4CAF50",
            fg="white",
            font=("Microsoft YaHei", 12, "bold"),
            padx=20,
            pady=8,
            cursor="hand2"
        )
        execute_btn.pack(side=tk.RIGHT, padx=10)

        # 存储UI引用
        self.device_frames = {}  # device -> frame
        self.device_check_vars = {}  # device -> var
        self.channel_check_vars = {}  # (device, channel_id) -> var
        self.channel_labels = {}  # (device, channel_id) -> label
        self.channel_frames = {}  # (device, channel_id) -> frame 用于搜索隐藏/显示

    def _on_mousewheel(self, event):
        """处理鼠标滚轮"""
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def log(self, message):
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def clear_log(self):
        """清空日志"""
        self.log_text.delete(1.0, tk.END)

    def update_device_combo(self):
        """更新设备选择下拉框"""
        device_list = [f"{d.ip} (Deepmind: {d.deepmind_id})" for d in self.devices]
        self.device_combo['values'] = device_list
        if device_list:
            self.device_combo.set("选择设备...")

    def on_device_selected(self, event=None):
        """设备选择事件"""
        pass

    def scan_selected_device(self):
        """扫描选中的单个设备"""
        selection = self.device_combo.get()
        if selection == "选择设备..." or not selection:
            messagebox.showinfo("提示", "请先选择一个设备")
            return
        
        # 查找对应的设备
        selected_ip = selection.split(" ")[0]
        for device in self.devices:
            if device.ip == selected_ip:
                self.check_single_device(device)
                return

    def on_search(self, event=None):
        """搜索事件"""
        self.search_text = self.search_entry.get().lower().strip()
        self.filter_channels()

    def filter_channels(self):
        """根据搜索文本过滤通道显示"""
        search = self.search_text
        
        for (device, channel_id), frame in self.channel_frames.items():
            if not frame:
                continue
                
            # 查找通道信息
            channel = None
            for ch in device.channels:
                if ch['id'] == channel_id:
                    channel = ch
                    break
            
            if not channel:
                continue
            
            # 检查是否匹配搜索条件
            if not search:
                frame.pack(fill=tk.X, pady=2)
            else:
                # 按监控点名称、通道ID、IP地址搜索
                name_match = search in channel.get('name', '').lower()
                id_match = search in str(channel_id).lower()
                ip_match = search in device.ip.lower()
                
                if name_match or id_match or ip_match:
                    frame.pack(fill=tk.X, pady=2)
                else:
                    frame.pack_forget()

    def export_channels(self):
        """导出所有监控点信息"""
        if not any(d.channels for d in self.devices):
            messagebox.showinfo("提示", "没有可导出的监控点数据，请先扫描设备")
            return
        
        # 选择保存路径
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV文件", "*.csv"), ("所有文件", "*.*")],
            initialfile=f"监控点列表_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                # 写入表头
                writer.writerow(['序号', '设备IP', 'Deepmind ID', '通道ID', '监控点名称', 
                               '码流ID', '当前编码', '状态'])
                
                row_num = 1
                for device in self.devices:
                    for ch in device.channels:
                        writer.writerow([
                            row_num,
                            device.ip,
                            device.deepmind_id,
                            ch['id'],
                            ch.get('name', '未知'),
                            ch['stream_id'],
                            ch.get('codec', '未知'),
                            device.status
                        ])
                        row_num += 1
            
            self.log(f"✓ 成功导出 {row_num - 1} 个监控点到: {file_path}")
            messagebox.showinfo("成功", f"已导出 {row_num - 1} 个监控点到:\n{file_path}")
        except Exception as e:
            messagebox.showerror("错误", f"导出失败: {e}")
            self.log(f"✗ 导出失败: {e}")

    def load_devices(self):
        """从 Deepmind.json 加载设备列表"""
        try:
            with open('Deepmind.json', 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.devices = []
            for item in data:
                device = NvrDevice(
                    deepmind_id=item.get('Deepmind', ''),
                    ip=item.get('IP', ''),
                    password=item.get('Password', ''),
                    http_port=item.get('HttpPort', 80),
                    rtsp_port=item.get('RtspPort', 554),
                    scheme=item.get('Scheme', 'http')
                )
                self.devices.append(device)

            self.refresh_device_list()
            self.update_device_combo()
            self.log(f"✓ 成功加载 {len(self.devices)} 台设备")

        except Exception as e:
            messagebox.showerror("错误", f"加载 Deepmind.json 失败: {e}")
            self.log(f"✗ 加载失败: {e}")

    def refresh_device_list(self):
        """刷新设备列表显示"""
        # 清空现有内容
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        self.device_frames = {}
        self.device_check_vars = {}
        self.channel_check_vars = {}
        self.channel_labels = {}
        self.channel_frames = {}

        # 为每个设备创建卡片
        for i, device in enumerate(self.devices):
            self.create_device_card(device, i)

        # 更新统计
        self.update_stats()

    def create_device_card(self, device, index):
        """创建设备卡片"""
        # 设备框架
        card = ttk.LabelFrame(
            self.scrollable_frame,
            text=f"",
            padding="10"
        )
        card.pack(fill=tk.X, pady=5, padx=5)

        # 设备标题行
        header = ttk.Frame(card)
        header.pack(fill=tk.X)

        # 设备复选框
        device_var = tk.BooleanVar(value=False)
        self.device_check_vars[device] = device_var

        device_check = ttk.Checkbutton(
            header,
            text=f"📹 {device.ip} (Deepmind: {device.deepmind_id})",
            variable=device_var,
            command=lambda d=device: self.on_device_toggle(d)
        )
        device_check.pack(side=tk.LEFT)

        # 设备状态标签
        status_text = device.status if device.status != "未连接" else "点击扫描获取通道"
        status_label = ttk.Label(header, text=status_text, foreground="gray")
        status_label.pack(side=tk.RIGHT)
        self.device_frames[device] = {'card': card, 'status_label': status_label, 'channels_frame': None}

        # 通道容器（初始隐藏，扫描后显示）
        if device.channels:
            self.show_channels(device)

    def show_channels(self, device):
        """显示设备的通道列表"""
        card_info = self.device_frames.get(device)
        if not card_info:
            return

        # 如果已存在通道框架，先销毁
        if card_info['channels_frame']:
            card_info['channels_frame'].destroy()

        # 创建通道框架
        channels_frame = ttk.Frame(card_info['card'])
        channels_frame.pack(fill=tk.X, pady=(10, 0), padx=(20, 0))
        card_info['channels_frame'] = channels_frame

        # 通道标题
        ttk.Label(
            channels_frame,
            text="通道列表（勾选要修改为 H.264 的通道）：",
            font=("Microsoft YaHei", 9, "bold")
        ).pack(anchor=tk.W, pady=(0, 5))

        # 为每个通道创建行
        for ch in device.channels:
            ch_frame = ttk.Frame(channels_frame)
            ch_frame.pack(fill=tk.X, pady=2)
            self.channel_frames[(device, ch['id'])] = ch_frame

            # 通道复选框
            ch_var = tk.BooleanVar(value=ch.get('codec') == 'H.265')
            self.channel_check_vars[(device, ch['id'])] = ch_var

            # 显示通道ID、监控点名称
            channel_name = ch.get('name', '未知')
            display_text = f"通道 {ch['id']} - {channel_name} (码流 {ch['stream_id']})"
            
            ch_check = ttk.Checkbutton(
                ch_frame,
                text=display_text,
                variable=ch_var,
                command=lambda: self.update_stats()
            )
            ch_check.pack(side=tk.LEFT)

            # 编码格式标签
            codec = ch.get('codec', '未知')
            if codec == 'H.264':
                color = "green"
                symbol = "✓"
            elif codec == 'H.265':
                color = "red"
                symbol = "✗"
            else:
                color = "gray"
                symbol = "?"

            ch_label = tk.Label(
                ch_frame,
                text=f"{symbol} {codec}",
                fg=color,
                font=("Microsoft YaHei", 9, "bold")
            )
            ch_label.pack(side=tk.RIGHT, padx=10)
            self.channel_labels[(device, ch['id'])] = ch_label

        # 设备操作按钮
        btn_frame = ttk.Frame(channels_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(
            btn_frame,
            text="✓ 全选本设备",
            command=lambda d=device: self.select_device_channels(d, True)
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            btn_frame,
            text="✗ 取消全选",
            command=lambda d=device: self.select_device_channels(d, False)
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            btn_frame,
            text="🔍 仅扫描本设备",
            command=lambda d=device: self.check_single_device(d)
        ).pack(side=tk.RIGHT, padx=5)

    def on_device_toggle(self, device):
        """设备复选框切换"""
        var = self.device_check_vars.get(device)
        if var:
            self.select_device_channels(device, var.get())
        self.update_stats()

    def select_device_channels(self, device, select):
        """选择/取消选择设备的所有通道"""
        for ch in device.channels:
            ch_var = self.channel_check_vars.get((device, ch['id']))
            if ch_var:
                ch_var.set(select)

        # 更新设备复选框状态
        device_var = self.device_check_vars.get(device)
        if device_var:
            device_var.set(select)

        self.update_stats()

    def select_all_h265(self):
        """选中所有 H.265 通道"""
        for device in self.devices:
            for ch in device.channels:
                ch_var = self.channel_check_vars.get((device, ch['id']))
                if ch_var:
                    ch_var.set(ch.get('codec') == 'H.265')

            # 更新设备复选框
            has_h265 = any(ch.get('codec') == 'H.265' for ch in device.channels)
            device_var = self.device_check_vars.get(device)
            if device_var:
                device_var.set(has_h265)

        self.update_stats()
        self.log("已自动选中所有 H.265 通道")

    def deselect_all(self):
        """取消全选"""
        for var in self.device_check_vars.values():
            var.set(False)
        for var in self.channel_check_vars.values():
            var.set(False)
        self.update_stats()

    def update_stats(self):
        """更新统计信息"""
        selected_count = sum(1 for var in self.channel_check_vars.values() if var.get())
        self.stats_label.config(text=f"就绪 | 已选: {selected_count} 个通道")

    def get_codec_from_xml(self, xml_text):
        """从XML中提取编码类型"""
        try:
            root = ET.fromstring(xml_text)
            for elem in root.iter():
                if elem.tag.endswith('videoCodecType'):
                    return elem.text
            return None
        except Exception as e:
            return f"解析错误"

    def set_codec_in_xml(self, xml_text, new_codec="H.264"):
        """在XML中设置编码类型"""
        try:
            root = ET.fromstring(xml_text)
            for elem in root.iter():
                if elem.tag.endswith('videoCodecType'):
                    elem.text = new_codec
                    return ET.tostring(root, encoding='unicode')
            return None
        except Exception as e:
            return None

    def discover_channels(self, device):
        """发现设备通道"""
        url = f"{device.get_base_url()}/ISAPI/ContentMgmt/InputProxy/channels"
        try:
            response = requests.get(url, auth=device.auth, timeout=10)
            if response.status_code == 200:
                # 解析XML获取通道列表
                root = ET.fromstring(response.text)
                channels = []

                # 查找所有 InputProxyChannel
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
                            stream_id = f"{channel_id}01"  # 主码流
                            channels.append({
                                'id': channel_id,
                                'stream_id': stream_id,
                                'codec': '未知',
                                'name': channel_name,
                                'enabled': True
                            })

                device.channels = channels
                device.status = "已连接"
                return True
            else:
                device.status = "连接失败"
                device.error_msg = f"HTTP {response.status_code}"
                return False
        except requests.exceptions.Timeout:
            device.status = "超时"
            device.error_msg = "连接超时"
            return False
        except Exception as e:
            device.status = "错误"
            device.error_msg = str(e)
            return False

    def get_channel_config(self, device, stream_id):
        """获取通道配置"""
        url = f"{device.get_base_url()}/ISAPI/ContentMgmt/StreamingProxy/channels/{stream_id}"
        try:
            response = requests.get(url, auth=device.auth, timeout=10)
            if response.status_code == 200:
                return response.text
            else:
                return None
        except Exception as e:
            return None

    def check_single_device(self, device):
        """扫描单个设备"""
        def task():
            self.log(f"[{device.ip}] 正在扫描...")

            # 发现通道
            if not self.discover_channels(device):
                self.log(f"  ✗ 连接失败: {device.error_msg}")
                self.root.after(0, lambda: self.update_device_status(device))
                return

            self.log(f"  ✓ 发现 {len(device.channels)} 个通道")

            # 获取每个通道的配置
            for ch in device.channels:
                config_xml = self.get_channel_config(device, ch['stream_id'])
                if config_xml:
                    codec = self.get_codec_from_xml(config_xml)
                    ch['codec'] = codec or "未知"
                    ch['xml_config'] = config_xml
                    status = "✓" if ch['codec'] == 'H.264' else "✗"
                    self.log(f"    {status} 通道{ch['id']}({ch['name']}): {ch['codec']}")
                else:
                    ch['codec'] = "获取失败"
                    self.log(f"    ✗ 通道{ch['id']}({ch['name']}): 获取配置失败")

            # 刷新显示
            self.root.after(0, lambda: self.refresh_after_scan(device))

        threading.Thread(target=task, daemon=True).start()

    def check_codecs(self):
        """检查所有设备的编码格式"""
        def task():
            self.log("="*50)
            self.log("开始扫描所有设备...")
            total = len(self.devices)
            processed = 0

            for device in self.devices:
                self.log(f"[{device.ip}] 正在连接...")

                # 发现通道
                if not self.discover_channels(device):
                    self.log(f"  ✗ 连接失败: {device.error_msg}")
                    processed += 1
                    self.update_progress(processed, total)
                    self.root.after(0, lambda d=device: self.update_device_status(d))
                    continue

                self.log(f"  ✓ 发现 {len(device.channels)} 个通道")

                # 获取每个通道的配置
                for ch in device.channels:
                    config_xml = self.get_channel_config(device, ch['stream_id'])
                    if config_xml:
                        codec = self.get_codec_from_xml(config_xml)
                        ch['codec'] = codec or "未知"
                        ch['xml_config'] = config_xml
                        status = "✓" if ch['codec'] == 'H.264' else "✗"
                        self.log(f"    {status} 通道{ch['id']}({ch['name']}): {ch['codec']}")
                    else:
                        ch['codec'] = "获取失败"
                        self.log(f"    ✗ 通道{ch['id']}({ch['name']}): 获取配置失败")

                processed += 1
                self.update_progress(processed, total)

            self.log("="*50)
            self.log("扫描完成！")
            self.root.after(0, self.refresh_device_list)
            self.root.after(0, self.select_all_h265)

        threading.Thread(target=task, daemon=True).start()

    def update_device_status(self, device):
        """更新设备状态显示"""
        card_info = self.device_frames.get(device)
        if card_info and card_info['status_label']:
            card_info['status_label'].config(text=device.status, foreground="red")

    def refresh_after_scan(self, device):
        """扫描后刷新设备显示"""
        self.refresh_device_list()
        # 自动选中该设备的H.265通道
        for ch in device.channels:
            if ch.get('codec') == 'H.265':
                ch_var = self.channel_check_vars.get((device, ch['id']))
                if ch_var:
                    ch_var.set(True)
        self.update_stats()

    def modify_channel_codec(self, device, channel):
        """修改通道编码格式"""
        if 'xml_config' not in channel:
            return False, "没有配置数据"

        xml_config = channel['xml_config']
        new_xml = self.set_codec_in_xml(xml_config, "H.264")

        if not new_xml:
            return False, "XML修改失败"

        url = f"{device.get_base_url()}/ISAPI/ContentMgmt/StreamingProxy/channels/{channel['stream_id']}"
        headers = {'Content-Type': 'application/xml'}

        try:
            response = requests.put(
                url,
                data=new_xml.encode('utf-8'),
                headers=headers,
                auth=device.auth,
                timeout=10
            )

            if response.status_code == 200:
                channel['codec'] = 'H.264'
                return True, "成功"
            else:
                return False, f"HTTP {response.status_code}"
        except Exception as e:
            return False, str(e)

    def execute_modify(self):
        """执行批量修改"""
        # 统计要修改的通道
        to_modify = []
        for device in self.devices:
            for ch in device.channels:
                ch_var = self.channel_check_vars.get((device, ch['id']))
                if ch_var and ch_var.get() and ch.get('codec') == 'H.265':
                    to_modify.append((device, ch))

        if not to_modify:
            messagebox.showinfo("提示", "没有需要修改的通道（请选择编码为 H.265 的通道）")
            return

        if not messagebox.askyesno(
            "确认",
            f"确定要将 {len(to_modify)} 个通道的编码格式修改为 H.264 吗？\n\n注意：修改过程中视频流会短暂中断。"
        ):
            return

        def task():
            self.log("="*50)
            self.log(f"开始批量修改，共 {len(to_modify)} 个通道...")
            total = len(to_modify)
            success_count = 0

            for i, (device, ch) in enumerate(to_modify):
                self.log(f"[{i+1}/{total}] {device.ip} 通道{ch['id']}({ch['name']})...")

                success, msg = self.modify_channel_codec(device, ch)
                if success:
                    self.log(f"  ✓ 修改成功")
                    success_count += 1
                else:
                    self.log(f"  ✗ 修改失败: {msg}")

                self.update_progress(i + 1, total)

            self.log("="*50)
            self.log(f"批量修改完成: {success_count}/{total} 成功")
            self.root.after(0, self.refresh_device_list)

        threading.Thread(target=task, daemon=True).start()

    def update_progress(self, current, total):
        """更新进度条"""
        def update():
            if total > 0:
                self.progress['value'] = (current / total) * 100
                self.progress_label['text'] = f"{current}/{total}"
        self.root.after(0, update)


def main():
    root = tk.Tk()
    app = NvrCodecManager(root)
    root.mainloop()


if __name__ == "__main__":
    main()
