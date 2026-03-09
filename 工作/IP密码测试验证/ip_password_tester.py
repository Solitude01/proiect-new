#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IP密码测试验证工具
用于批量测试IP地址的登录密码
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import requests
from requests.auth import HTTPDigestAuth
import pandas as pd
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import queue


class IPTester:
    """负责单个IP的密码测试"""

    def __init__(self, port=80, timeout=5):
        self.port = port
        self.timeout = timeout

    def test_password(self, ip, username, password):
        """测试单个密码"""
        url = f"http://{ip}:{self.port}/ISAPI/System/status"
        try:
            response = requests.get(
                url,
                auth=HTTPDigestAuth(username, password),
                timeout=self.timeout
            )
            if response.status_code == 200:
                return True, "连接成功,密码正确"
            elif response.status_code == 401:
                return False, "认证失败,密码错误"
            else:
                return False, f"HTTP状态码: {response.status_code}"
        except requests.exceptions.Timeout:
            return False, "连接超时"
        except requests.exceptions.ConnectionError:
            return False, "无法连接"
        except Exception as e:
            return False, f"异常: {str(e)}"

    def test_ip_with_dict(self, ip, username, preset_password, password_dict, progress_callback=None, cancel_event=None):
        """使用字典测试IP密码"""
        # 先测试预设密码
        if preset_password and preset_password.strip():
            if progress_callback:
                progress_callback(ip, f"测试预设密码: {preset_password}")

            success, msg = self.test_password(ip, username, preset_password)
            if success:
                return {
                    "ip": ip,
                    "status": "成功",
                    "password": preset_password,
                    "message": msg
                }

        # 遍历密码字典
        for idx, password in enumerate(password_dict):
            if cancel_event and cancel_event.is_set():
                return {
                    "ip": ip,
                    "status": "已取消",
                    "password": "",
                    "message": "测试被取消"
                }

            if progress_callback:
                progress_callback(ip, f"测试密码 ({idx+1}/{len(password_dict)}): {password}")

            success, msg = self.test_password(ip, username, password)
            if success:
                return {
                    "ip": ip,
                    "status": "成功",
                    "password": password,
                    "message": msg
                }

        return {
            "ip": ip,
            "status": "失败",
            "password": "",
            "message": "未找到正确密码"
        }


class PasswordTestWorker:
    """后台执行测试任务的工作线程"""

    def __init__(self, gui, ip_list, password_dict, max_workers=10, port=80, timeout=5):
        self.gui = gui
        self.ip_list = ip_list
        self.password_dict = password_dict
        self.max_workers = max_workers
        self.port = port
        self.timeout = timeout
        self.cancel_event = threading.Event()
        self.thread = None
        self.results = []

    def start(self):
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        self.cancel_event.set()

    def is_running(self):
        return self.thread and self.thread.is_alive()

    def run(self):
        """执行测试任务"""
        tester = IPTester(port=self.port, timeout=self.timeout)
        total = len(self.ip_list)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务并保存索引以保持原始顺序
            futures = []
            for idx, ip_info in enumerate(self.ip_list):
                if self.cancel_event.is_set():
                    break

                future = executor.submit(
                    tester.test_ip_with_dict,
                    ip_info["ip"],
                    ip_info["username"],
                    ip_info["password"],
                    self.password_dict,
                    self._make_progress_callback(ip_info["ip"]),
                    self.cancel_event
                )
                futures.append((idx, future, ip_info))

            # 按照原始顺序处理结果
            for idx, future, ip_info in futures:
                if self.cancel_event.is_set():
                    break

                try:
                    result = future.result()
                    self.results.append(result)
                    self.gui.queue.put({
                        "type": "result",
                        "data": result,
                        "progress": (idx + 1, total)
                    })
                except Exception as e:
                    result = {
                        "ip": ip_info["ip"],
                        "status": "错误",
                        "password": "",
                        "message": str(e)
                    }
                    self.results.append(result)
                    self.gui.queue.put({
                        "type": "result",
                        "data": result,
                        "progress": (idx + 1, total)
                    })

        if not self.cancel_event.is_set():
            self.gui.queue.put({"type": "complete"})

    def _make_progress_callback(self, ip):
        """创建进度回调函数"""
        def callback(ip_addr, message):
            self.gui.queue.put({
                "type": "log",
                "ip": ip_addr,
                "message": message
            })
        return callback


class MainGUI:
    """主窗口类"""

    def __init__(self, root):
        self.root = root
        self.root.title("IP密码测试验证工具")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)

        self.worker = None
        self.queue = queue.Queue()
        self.results_data = []

        self._create_widgets()
        self._load_default_files()
        self._check_queue()

    def _create_widgets(self):
        """创建GUI组件"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(4, weight=1)
        main_frame.rowconfigure(6, weight=1)

        # === 配置区域 ===
        config_frame = ttk.LabelFrame(main_frame, text="配置区域", padding="10")
        config_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        config_frame.columnconfigure(1, weight=1)

        # 待测试文件
        ttk.Label(config_frame, text="待测试文件:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.ip_file_var = tk.StringVar()
        ttk.Entry(config_frame, textvariable=self.ip_file_var).grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        ttk.Button(config_frame, text="浏览...", command=self._browse_ip_file).grid(row=0, column=2, padx=5, pady=5)

        # 密码字典
        ttk.Label(config_frame, text="密码字典:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.pwd_file_var = tk.StringVar()
        ttk.Entry(config_frame, textvariable=self.pwd_file_var).grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        ttk.Button(config_frame, text="浏览...", command=self._browse_pwd_file).grid(row=1, column=2, padx=5, pady=5)

        # 参数配置
        param_frame = ttk.Frame(config_frame)
        param_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)

        ttk.Label(param_frame, text="线程数:").grid(row=0, column=0, padx=5)
        self.thread_var = tk.IntVar(value=10)
        ttk.Spinbox(param_frame, from_=1, to=50, textvariable=self.thread_var, width=5).grid(row=0, column=1, padx=5)

        ttk.Label(param_frame, text="超时时间(秒):").grid(row=0, column=2, padx=5)
        self.timeout_var = tk.IntVar(value=5)
        ttk.Spinbox(param_frame, from_=1, to=30, textvariable=self.timeout_var, width=5).grid(row=0, column=3, padx=5)

        ttk.Label(param_frame, text="端口:").grid(row=0, column=4, padx=5)
        self.port_var = tk.IntVar(value=80)
        ttk.Spinbox(param_frame, from_=1, to=65535, textvariable=self.port_var, width=5).grid(row=0, column=5, padx=5)

        # 按钮区域
        btn_frame = ttk.Frame(config_frame)
        btn_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)

        self.start_btn = ttk.Button(btn_frame, text="开始测试", command=self._start_test, width=15)
        self.start_btn.grid(row=0, column=0, padx=5)

        self.stop_btn = ttk.Button(btn_frame, text="停止测试", command=self._stop_test, width=15, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=1, padx=5)

        self.export_btn = ttk.Button(btn_frame, text="导出结果", command=self._export_results, width=15, state=tk.DISABLED)
        self.export_btn.grid(row=0, column=2, padx=5)

        # === 进度区域 ===
        progress_frame = ttk.LabelFrame(main_frame, text="测试进度", padding="10")
        progress_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        progress_frame.columnconfigure(0, weight=1)

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5)

        self.status_var = tk.StringVar(value="就绪")
        self.status_label = ttk.Label(progress_frame, textvariable=self.status_var)
        self.status_label.grid(row=1, column=0, sticky=tk.W, padx=5, pady=(5, 0))

        # === 结果表格 ===
        result_frame = ttk.LabelFrame(main_frame, text="测试结果", padding="10")
        result_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(0, weight=1)

        # 创建表格
        columns = ("IP地址", "状态", "正确密码", "消息")
        self.tree = ttk.Treeview(result_frame, columns=columns, show="headings", height=10)

        self.tree.heading("IP地址", text="IP地址")
        self.tree.heading("状态", text="状态")
        self.tree.heading("正确密码", text="正确密码")
        self.tree.heading("消息", text="消息")

        self.tree.column("IP地址", width=120)
        self.tree.column("状态", width=60)
        self.tree.column("正确密码", width=100)
        self.tree.column("消息", width=300)

        # 滚动条
        scrollbar_y = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar_x = ttk.Scrollbar(result_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar_y.grid(row=0, column=1, sticky=(tk.N, tk.S))
        scrollbar_x.grid(row=1, column=0, sticky=(tk.W, tk.E))

        # === 日志输出 ===
        log_frame = ttk.LabelFrame(main_frame, text="日志输出", padding="10")
        log_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.log_text.config(state=tk.DISABLED)

        # 统计信息
        self.stats_var = tk.StringVar(value="成功: 0 | 失败: 0 | 总计: 0")
        stats_label = ttk.Label(main_frame, textvariable=self.stats_var, font=("Arial", 10, "bold"))
        stats_label.grid(row=4, column=0, columnspan=3, sticky=tk.W)

    def _load_default_files(self):
        """加载默认文件"""
        default_ip_file = r"D:\proiect\工作\IP密码测试验证\待测试.md"
        default_pwd_file = r"D:\proiect\工作\IP密码测试验证\密码.md"

        if os.path.exists(default_ip_file):
            self.ip_file_var.set(default_ip_file)

        if os.path.exists(default_pwd_file):
            self.pwd_file_var.set(default_pwd_file)

    def _browse_ip_file(self):
        filename = filedialog.askopenfilename(
            title="选择待测试文件",
            filetypes=[("Markdown文件", "*.md"), ("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if filename:
            self.ip_file_var.set(filename)

    def _browse_pwd_file(self):
        filename = filedialog.askopenfilename(
            title="选择密码字典文件",
            filetypes=[("Markdown文件", "*.md"), ("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if filename:
            self.pwd_file_var.set(filename)

    def _read_ip_file(self, filepath):
        """读取IP文件"""
        ip_list = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            for line in lines[1:]:  # 跳过标题行
                line = line.strip()
                if not line:
                    continue

                # 支持制表符或空格分隔
                parts = re.split(r'\t+|\s{2,}', line)
                if len(parts) >= 2:
                    ip = parts[0].strip()
                    username = parts[1].strip() if len(parts) > 1 else "admin"
                    password = parts[2].strip() if len(parts) > 2 else ""

                    # 验证IP格式
                    if re.match(r'^(\d{1,3}\.){3}\d{1,3}$', ip):
                        ip_list.append({
                            "ip": ip,
                            "username": username,
                            "password": password
                        })

            return ip_list
        except Exception as e:
            messagebox.showerror("错误", f"读取IP文件失败: {str(e)}")
            return []

    def _read_pwd_file(self, filepath):
        """读取密码文件"""
        passwords = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    passwords.append(line)

            return list(dict.fromkeys(passwords))  # 去重
        except Exception as e:
            messagebox.showerror("错误", f"读取密码文件失败: {str(e)}")
            return []

    def _add_log(self, message):
        """添加日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _start_test(self):
        """开始测试"""
        ip_file = self.ip_file_var.get()
        pwd_file = self.pwd_file_var.get()

        if not ip_file or not os.path.exists(ip_file):
            messagebox.showerror("错误", "请选择有效的待测试文件")
            return

        if not pwd_file or not os.path.exists(pwd_file):
            messagebox.showerror("错误", "请选择有效的密码字典文件")
            return

        # 读取文件
        ip_list = self._read_ip_file(ip_file)
        password_dict = self._read_pwd_file(pwd_file)

        if not ip_list:
            messagebox.showwarning("警告", "IP列表为空")
            return

        if not password_dict:
            messagebox.showwarning("警告", "密码字典为空")
            return

        # 清空之前的结果
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.results_data = []
        self.progress_var.set(0)

        # 添加日志
        self._add_log(f"开始测试，共 {len(ip_list)} 个IP，密码字典 {len(password_dict)} 个")

        # 创建工作线程
        self.worker = PasswordTestWorker(
            self,
            ip_list,
            password_dict,
            max_workers=self.thread_var.get(),
            port=self.port_var.get(),
            timeout=self.timeout_var.get()
        )

        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.export_btn.config(state=tk.DISABLED)

        self.worker.start()

    def _stop_test(self):
        """停止测试"""
        if self.worker:
            self.worker.stop()
            self._add_log("正在停止测试...")

    def _check_queue(self):
        """检查队列更新UI"""
        try:
            while True:
                msg = self.queue.get_nowait()

                if msg["type"] == "log":
                    self._add_log(f"{msg['ip']} - {msg['message']}")

                elif msg["type"] == "result":
                    data = msg["data"]
                    progress = msg["progress"]

                    # 更新表格
                    self.tree.insert("", tk.END, values=(
                        data["ip"],
                        data["status"],
                        data["password"],
                        data["message"]
                    ))
                    self.results_data.append(data)

                    # 更新进度
                    completed, total = progress
                    percent = (completed / total) * 100
                    self.progress_var.set(percent)

                    # 更新状态
                    success_count = sum(1 for r in self.results_data if r["status"] == "成功")
                    fail_count = sum(1 for r in self.results_data if r["status"] != "成功")
                    self.status_var.set(f"进度: {completed}/{total} ({percent:.1f}%)  成功:{success_count} 失败:{fail_count}")
                    self.stats_var.set(f"成功: {success_count} | 失败: {fail_count} | 总计: {len(self.results_data)}")

                    # 滚动到最新
                    self.tree.see(self.tree.get_children()[-1] if self.tree.get_children() else "")

                elif msg["type"] == "complete":
                    self._add_log("测试完成")
                    self.start_btn.config(state=tk.NORMAL)
                    self.stop_btn.config(state=tk.DISABLED)
                    self.export_btn.config(state=tk.NORMAL)
                    messagebox.showinfo("完成", "测试已完成！")

        except queue.Empty:
            pass

        self.root.after(100, self._check_queue)

    def _export_results(self):
        """导出结果到Excel"""
        if not self.results_data:
            messagebox.showwarning("警告", "没有可导出的结果")
            return

        filename = filedialog.asksaveasfilename(
            title="保存测试结果",
            defaultextension=".xlsx",
            filetypes=[("Excel文件", "*.xlsx"), ("CSV文件", "*.csv")]
        )

        if not filename:
            return

        try:
            df = pd.DataFrame(self.results_data)
            df.columns = ["IP地址", "状态", "正确密码", "消息"]

            if filename.endswith('.csv'):
                df.to_csv(filename, index=False, encoding='utf-8-sig')
            else:
                df.to_excel(filename, index=False, engine='openpyxl')

            self._add_log(f"结果已导出到: {filename}")
            messagebox.showinfo("成功", f"结果已导出到:\n{filename}")
        except Exception as e:
            messagebox.showerror("错误", f"导出失败: {str(e)}")


def main():
    root = tk.Tk()
    app = MainGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
