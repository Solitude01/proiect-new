#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TXT文件同步工具 v3.0
功能：批量同步所有TXT文件到本地，支持系统托盘
特点：
1. 最小化到桌面（点击最小化按钮）
2. 点击叉号直接缩小到系统托盘
3. 只有在系统托盘才能退出程序
4. 复制所有txt文件，不创建文件夹结构
版本：3.0
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import sys
import threading
import time
import logging
import configparser
import shutil
from pathlib import Path
from datetime import datetime
import tempfile
import base64

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False
    print("警告: 未安装pystray库，请运行: pip install pystray pillow")

try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False


class SystemTrayIcon:
    """系统托盘图标管理类"""

    def __init__(self, app):
        self.app = app
        self.icon = None
        self.menu = None
        self.create_icon()

    def create_icon(self):
        """创建系统托盘图标"""
        # 创建简单的图标
        width, height = 64, 64
        image = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(image)

        # 绘制文件夹图标
        draw.rectangle([10, 20, 54, 54], fill='blue', outline='black', width=2)
        draw.rectangle([15, 15, 45, 25], fill='yellow', outline='black', width=1)

        # 创建菜单
        self.menu = pystray.Menu(
            pystray.MenuItem('📂 打开主界面', self.show_window),
            pystray.MenuItem('🚀 开始同步', self.start_sync),
            pystray.MenuItem('⏸️ 停止同步', self.stop_sync),
            pystray.MenuItem('📊 显示状态', self.show_status),
            pystray.MenuItem('💾 保存配置', self.save_config),
            pystray.MenuItem('❌ 退出程序', self.quit_app)
        )

        self.icon = pystray.Icon(
            "txt_sync",
            image,
            "TXT文件同步工具 v3.0",
            self.menu
        )

    def show_window(self, icon, item):
        """显示主窗口"""
        self.app.show_window()

    def start_sync(self, icon, item):
        """开始同步"""
        self.app.start_sync()

    def stop_sync(self, icon, item):
        """停止同步"""
        self.app.stop_sync()

    def show_status(self, icon, item):
        """显示状态"""
        self.app.show_status()

    def save_config(self, icon, item):
        """保存配置"""
        self.app.save_config()

    def quit_app(self, icon, item):
        """退出应用"""
        self.app.force_exit()

    def run(self):
        """运行托盘图标"""
        if self.icon:
            self.icon.run()

    def stop(self):
        """停止托盘图标"""
        if self.icon:
            self.icon.stop()

    def update_tooltip(self, text):
        """更新托盘图标提示"""
        if self.icon:
            self.icon.title = text


def get_app_path():
    """获取应用程序所在目录（支持打包后的exe）"""
    if getattr(sys, 'frozen', False):
        # 打包后的exe运行
        return os.path.dirname(sys.executable)
    else:
        # 脚本直接运行
        return os.path.dirname(os.path.abspath(__file__))


class TXTFileSyncApp:
    """
    TXT文件同步应用程序类 v3.0
    """

    def __init__(self, root):
        """初始化应用程序"""
        self.root = root
        self.root.title("TXT文件同步工具 v3.0")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)

        # 获取应用程序目录，确保配置文件保存在exe同目录
        app_path = get_app_path()

        # 应用程序状态
        self.sync_thread = None
        self.running = False
        self.config_file = os.path.join(app_path, "sync_config.ini")
        self.log_file = os.path.join(app_path, "sync_log.log")
        self.tray_icon = None
        self.tray_thread = None

        # 初始化变量
        self.shared_path_var = tk.StringVar()
        self.local_path_var = tk.StringVar()
        self.interval_var = tk.StringVar(value="5")
        self.extensions_var = tk.StringVar(value=".txt")
        self.exclude_var = tk.StringVar(value="temp,cache,.tmp,Thumbs.db,desktop.ini")
        self.status_var = tk.StringVar(value="🔧 准备就绪 - 请配置参数并点击开始")
        self.stats_var = tk.StringVar(value="📊 统计: 0个文件 | 0字节 | 运行时间: 00:00:00")

        # 创建GUI组件
        self.create_widgets()
        self.load_config()
        self.setup_logging()

        # 创建系统托盘图标
        if HAS_TRAY:
            self.create_tray_icon()

        # 绑定窗口事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 显示欢迎信息
        self.log_message("=== TXT文件同步工具 v3.0 启动 ===")
        self.log_message("✅ 支持批量同步所有TXT文件")
        self.log_message("✅ 最小化到桌面，叉号缩小到托盘")
        self.log_message("✅ 只有在托盘才能退出程序")

    def create_tray_icon(self):
        """创建系统托盘图标"""
        try:
            self.tray_icon = SystemTrayIcon(self)
            # 在后台线程中运行托盘图标
            self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
            self.tray_thread.start()
            self.log_message("✅ 系统托盘图标已创建")
        except Exception as e:
            self.log_message(f"❌ 创建托盘图标失败: {e}")

    def show_window(self):
        """显示窗口"""
        self.root.deiconify()  # 显示窗口
        self.root.lift()  # 置于顶层
        self.root.focus_force()  # 获取焦点

    def start_sync(self):
        """开始同步"""
        if not self.running:
            self.root.after(0, self._start_sync_internal)

    def _start_sync_internal(self):
        """内部开始同步方法"""
        if self.validate_config():
            self.running = True
            self.update_ui_state()
            self.log_message("🚀 开始批量TXT文件同步...")
            self.log_message(f"📁 源文件夹: {self.shared_path_var.get()}")
            self.log_message(f"💾 目标文件夹: {self.local_path_var.get()}")
            self.log_message(f"⏰ 轮询间隔: {self.interval_var.get()} 秒")

            # 启动同步线程
            self.sync_thread = threading.Thread(target=self.sync_worker, daemon=True)
            self.sync_thread.start()

            # 更新托盘图标提示
            if self.tray_icon:
                self.tray_icon.update_tooltip("TXT同步运行中...")

    def stop_sync(self):
        """停止同步"""
        self.root.after(0, self._stop_sync_internal)

    def _stop_sync_internal(self):
        """内部停止同步方法"""
        self.running = False
        self.log_message("🛑 正在停止文件同步...")
        self.update_ui_state()

        # 更新托盘图标提示
        if self.tray_icon:
            self.tray_icon.update_tooltip("TXT同步已停止")

    def sync_worker(self):
        """同步工作线程 - 批量同步所有新文件"""
        start_time = time.time()
        file_count = 0
        total_size = 0

        try:
            while self.running:
                # 更新状态
                self.root.after(0, self.update_status, "🔍 正在检查新文件...")
                time.sleep(0.1)

                # 执行同步检查
                result = self.perform_sync_check()

                if result['success']:
                    if result['new_file']:
                        file_count += 1
                        total_size += result['file_size']
                        self.log_message(f"✅ {result['new_file']}")
                    else:
                        self.log_message("ℹ️ 当前没有新文件或更新需要同步")
                else:
                    self.log_message(f"❌ 同步失败: {result['error']}")

                # 更新统计信息
                elapsed = time.time() - start_time
                self.root.after(0, self.update_stats, file_count, total_size, elapsed)

                # 等待下次轮询
                if self.running:
                    interval = float(self.interval_var.get())
                    self.root.after(0, self.update_status, f"⏳ 等待下次检查 ({interval}s)")
                    time.sleep(interval)

        except Exception as e:
            self.root.after(0, self.log_message, f"❌ 同步过程中发生严重错误: {e}")
        finally:
            self.root.after(0, self.finalize_stop)

    def perform_sync_check(self):
        """执行同步检查 - 批量同步所有新文件和更新的文件"""
        try:
            shared_path = self.shared_path_var.get().strip()

            # 检查共享文件夹是否存在
            if not os.path.exists(shared_path):
                return {'success': False, 'error': f"源文件夹不存在: {shared_path}"}

            # 获取所有需要同步的文件（包含同步类型）
            files_to_sync = self.get_files_to_sync()

            if not files_to_sync:
                return {'success': True, 'new_file': None}

            synced_files = []
            total_size = 0
            new_count = 0
            update_count = 0

            # 依次复制文件
            for file_path, sync_type in files_to_sync:
                try:
                    file_size = os.path.getsize(file_path)
                    copy_success = self.copy_file_to_local(file_path)

                    if copy_success:
                        file_name = os.path.basename(file_path)
                        synced_files.append(file_name)
                        total_size += file_size

                        # 根据同步类型显示不同的日志
                        if sync_type == 'new':
                            new_count += 1
                            self.log_message(f"📄 新增: {file_name} ({self.format_size(file_size)})")
                        else:  # update
                            update_count += 1
                            self.log_message(f"🔄 更新: {file_name} ({self.format_size(file_size)})")
                    else:
                        self.log_message(f"❌ 文件复制失败: {file_path}")

                except Exception as e:
                    self.log_message(f"❌ 处理文件失败 {file_path}: {e}")
                    continue

            if synced_files:
                # 生成汇总信息
                summary_parts = []
                if new_count > 0:
                    summary_parts.append(f"新增{new_count}个")
                if update_count > 0:
                    summary_parts.append(f"更新{update_count}个")
                summary = "，".join(summary_parts)
                return {'success': True, 'new_file': f"批量同步完成! {summary}", 'file_size': total_size}
            else:
                return {'success': True, 'new_file': None}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_files_to_sync(self):
        """获取所有需要同步的文件（新文件或更新的文件）
        返回: [(file_path, sync_type), ...] 其中 sync_type 为 'new' 或 'update'
        """
        shared_path = self.shared_path_var.get().strip()
        files_to_sync = []

        try:
            exclude_items = [item.strip() for item in self.exclude_var.get().split(',') if item.strip()]
            file_extensions = [ext.strip().lower() for ext in self.extensions_var.get().split(',') if ext.strip()]

            # 获取已同步的文件列表（包含修改时间）
            synced_files = self.get_synced_files()

            # 递归搜索所有子目录
            for root, dirs, files in os.walk(shared_path):
                for file in files:
                    if not self.is_file_allowed(file, exclude_items, file_extensions):
                        continue

                    file_path = os.path.join(root, file)
                    file_name = os.path.basename(file_path)

                    try:
                        # 获取源文件的修改时间
                        src_mtime = os.path.getmtime(file_path)

                        if file_name not in synced_files:
                            # 新文件
                            files_to_sync.append((file_path, 'new'))
                        elif src_mtime > synced_files[file_name]:
                            # 源文件更新了，需要覆盖
                            files_to_sync.append((file_path, 'update'))
                        # 否则文件已存在且没有更新，跳过
                    except (OSError, IOError):
                        continue

            return files_to_sync

        except Exception as e:
            self.log_message(f"❌ 获取文件列表失败: {e}")
            return []

    def get_synced_files(self):
        """获取已同步的文件列表，返回 {文件名: 修改时间} 字典"""
        local_path = self.local_path_var.get().strip()
        synced_files = {}  # 改为字典存储文件名和修改时间

        try:
            if os.path.exists(local_path):
                for item in os.listdir(local_path):
                    item_path = os.path.join(local_path, item)
                    if os.path.isfile(item_path):
                        synced_files[item] = os.path.getmtime(item_path)  # 存储修改时间
        except Exception:
            pass

        return synced_files

    def is_file_allowed(self, filename, exclude_items, file_extensions):
        """检查文件是否允许同步"""
        # 检查排除列表
        for exclude_item in exclude_items:
            if exclude_item.lower() in filename.lower():
                return False

        # 检查文件扩展名
        if file_extensions:
            file_ext = os.path.splitext(filename)[1].lower()
            return file_ext in file_extensions

        return True

    def copy_file_to_local(self, src_path):
        """复制文件到本地目标文件夹（不创建文件夹结构）"""
        try:
            local_path = self.local_path_var.get().strip()

            # 确保本地目标文件夹存在
            if not os.path.exists(local_path):
                os.makedirs(local_path)
                self.log_message(f"📁 创建本地目标文件夹: {local_path}")

            # 只复制文件到根目录，不保持目录结构
            dst_path = os.path.join(local_path, os.path.basename(src_path))

            # 复制文件
            shutil.copy2(src_path, dst_path)
            return True

        except Exception as e:
            self.log_message(f"❌ 复制文件失败 {src_path}: {e}")
            return False

    def update_stats(self, file_count, total_size, elapsed):
        """更新统计信息"""
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        stats_text = f"📊 统计: {file_count}个文件 | {self.format_size(total_size)} | 运行时间: {time_str}"
        self.root.after(0, self.stats_var.set, stats_text)

    def finalize_stop(self):
        """最终停止处理"""
        self.running = False
        self.update_ui_state()
        self.log_message("🛑 文件同步已停止")

    def format_size(self, size_bytes):
        """格式化文件大小"""
        if size_bytes == 0:
            return "0 B"

        size_names = ["B", "KB", "MB", "GB", "TB"]
        import math
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_names[i]}"

    def show_status(self):
        """显示状态"""
        if hasattr(self, 'stats_var'):
            status = self.stats_var.get()
            messagebox.showinfo("同步状态", status)
        else:
            messagebox.showinfo("同步状态", "同步未运行")

    def save_config(self):
        """保存配置"""
        self.root.after(0, self.save_config_internal)

    def save_config_internal(self):
        """内部保存配置方法"""
        try:
            config = configparser.ConfigParser()

            config['PATHS'] = {
                'SHARED_FOLDER_PATH': self.shared_path_var.get(),
                'LOCAL_TARGET_PATH': self.local_path_var.get(),
                'LOG_FILE_PATH': self.log_file
            }

            config['SYNC'] = {
                'POLLING_INTERVAL_SECONDS': self.interval_var.get(),
                'RECURSIVE_SYNC': 'True',
                'REMOVE_EXTRA_FILES': 'false'
            }

            config['FILTER'] = {
                'FILE_EXTENSIONS': self.extensions_var.get(),
                'EXCLUDE_ITEMS': self.exclude_var.get()
            }

            config['TRAY'] = {
                'SHOW_TRAY_ICON': 'True',
                'MINIMIZE_TO_TRAY': 'True'
            }

            with open(self.config_file, 'w', encoding='utf-8') as f:
                config.write(f)

            self.log_message(f"💾 配置已保存到: {self.config_file}")

        except Exception as e:
            messagebox.showerror("❌ 错误", f"保存配置时出错: {e}")

    def force_exit(self):
        """强制退出应用程序"""
        if self.running:
            if messagebox.askokcancel("确认", "同步正在运行，确定要退出吗？"):
                self.stop_sync_internal()
                # 等待线程结束
                if self.sync_thread and self.sync_thread.is_alive():
                    self.sync_thread.join(timeout=2)
                self.cleanup()
                self.root.destroy()
        else:
            self.cleanup()
            self.root.destroy()

    def create_widgets(self):
        """创建GUI组件"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # 标题
        title_label = ttk.Label(main_frame, text="📁 TXT文件同步工具 v3.0", font=("微软雅黑", 16, "bold"))
        title_label.grid(row=0, column=0, pady=(0, 10))

        # 配置区域
        config_frame = ttk.LabelFrame(main_frame, text="⚙️ 配置设置", padding="10")
        config_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        config_frame.columnconfigure(1, weight=1)

        # 第一行：共享文件夹路径
        ttk.Label(config_frame, text="📁 源文件夹路径:", font=("微软雅黑", 10)).grid(
            row=0, column=0, sticky=tk.W, pady=5
        )
        shared_path_entry = ttk.Entry(
            config_frame, textvariable=self.shared_path_var, width=50, font=("Consolas", 9)
        )
        shared_path_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(10, 5), pady=5)
        ttk.Button(config_frame, text="📁 浏览", command=self.browse_shared_path, width=10).grid(
            row=0, column=2, padx=5, pady=5
        )

        # 第二行：本地目标路径
        ttk.Label(config_frame, text="💾 目标文件夹路径:", font=("微软雅黑", 10)).grid(
            row=1, column=0, sticky=tk.W, pady=5
        )
        local_path_entry = ttk.Entry(
            config_frame, textvariable=self.local_path_var, width=50, font=("Consolas", 9)
        )
        local_path_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(10, 5), pady=5)
        ttk.Button(config_frame, text="📁 浏览", command=self.browse_local_path, width=10).grid(
            row=1, column=2, padx=5, pady=5
        )

        # 第三行：轮询间隔
        ttk.Label(config_frame, text="⏰ 轮询间隔(秒):", font=("微软雅黑", 10)).grid(
            row=2, column=0, sticky=tk.W, pady=5
        )
        interval_entry = ttk.Entry(config_frame, textvariable=self.interval_var, width=10, font=("Consolas", 9))
        interval_entry.grid(row=2, column=1, sticky=tk.W, padx=(10, 5), pady=5)
        ttk.Label(config_frame, text="例: 5 (每5秒检查一次)", font=("微软雅黑", 8)).grid(
            row=2, column=2, padx=5, pady=5, sticky=tk.W
        )

        # 第四行：文件扩展名过滤
        ttk.Label(config_frame, text="📄 文件扩展名:", font=("微软雅黑", 10)).grid(
            row=3, column=0, sticky=tk.W, pady=5
        )
        extensions_entry = ttk.Entry(
            config_frame, textvariable=self.extensions_var, width=30, font=("Consolas", 9)
        )
        extensions_entry.grid(row=3, column=1, sticky=(tk.W, tk.E), padx=(10, 5), pady=5)
        ttk.Label(config_frame, text="例: .txt (只处理txt文件)", font=("微软雅黑", 8)).grid(
            row=3, column=2, padx=5, pady=5, sticky=tk.W
        )

        # 第五行：排除文件
        ttk.Label(config_frame, text="🚫 排除文件:", font=("微软雅黑", 10)).grid(
            row=4, column=0, sticky=tk.W, pady=5
        )
        exclude_entry = ttk.Entry(
            config_frame, textvariable=self.exclude_var, width=30, font=("Consolas", 9)
        )
        exclude_entry.grid(row=4, column=1, sticky=(tk.W, tk.E), padx=(10, 5), pady=5)
        ttk.Label(config_frame, text="例: temp,cache,.tmp", font=("微软雅黑", 8)).grid(
            row=4, column=2, padx=5, pady=5, sticky=tk.W
        )

        # 控制按钮区域
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, pady=(0, 10), sticky=tk.W)

        self.start_btn = ttk.Button(
            button_frame, text="▶️ 开始同步", command=self.start_sync, width=15,
            style='Accent.TButton'
        )
        self.start_btn.grid(row=0, column=0, padx=5)

        self.stop_btn = ttk.Button(
            button_frame, text="⏸️ 停止同步", command=self.stop_sync, state=tk.DISABLED, width=15
        )
        self.stop_btn.grid(row=0, column=1, padx=5)

        self.save_btn = ttk.Button(
            button_frame, text="💾 保存配置", command=self.save_config_internal, width=12
        )
        self.save_btn.grid(row=0, column=2, padx=5)

        self.hide_btn = ttk.Button(
            button_frame, text="🎯 最小化到托盘(叉号也可)", command=self.minimize_to_tray, width=22
        )
        self.hide_btn.grid(row=0, column=3, padx=5)

        # 状态显示区域
        status_frame = ttk.LabelFrame(main_frame, text="📊 同步状态", padding="10")
        status_frame.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        status_frame.columnconfigure(0, weight=1)
        status_frame.rowconfigure(0, weight=1)

        self.status_text = scrolledtext.ScrolledText(
            status_frame, height=20, width=80, font=("Consolas", 9),
            wrap=tk.WORD, state='disabled'
        )
        self.status_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 进度条和状态标签
        progress_frame = ttk.Frame(main_frame)
        progress_frame.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        progress_frame.columnconfigure(0, weight=1)

        status_label = ttk.Label(
            progress_frame, textvariable=self.status_var, font=("微软雅黑", 10),
            foreground="#2E86AB"
        )
        status_label.grid(row=0, column=0, sticky=tk.W)

        self.progress_bar = ttk.Progressbar(progress_frame, mode='indeterminate', length=300)
        self.progress_bar.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)

        # 统计信息
        stats_frame = ttk.Frame(main_frame)
        stats_frame.grid(row=5, column=0, sticky=(tk.W, tk.E), pady=(0, 5))

        stats_label = ttk.Label(
            stats_frame, textvariable=self.stats_var, font=("Consolas", 9),
            foreground="#A7A7A7"
        )
        stats_label.grid(row=0, column=0, sticky=tk.W)

        # 设置列权重
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)

    def minimize_to_tray(self):
        """最小化窗口到系统托盘"""
        if self.tray_icon:
            self.root.withdraw()  # 隐藏窗口到托盘
            self.log_message("窗口已最小化到系统托盘")

    def on_closing(self):
        """
        窗口关闭事件处理 - 默认最小化到托盘
        """
        self.minimize_to_tray()

    def cleanup(self):
        """清理资源"""
        if self.tray_icon:
            self.tray_icon.stop()
        self.log_message("✅ 应用程序已退出")

    def validate_config(self):
        """验证配置是否有效"""
        shared_path = self.shared_path_var.get().strip()
        local_path = self.local_path_var.get().strip()

        if not shared_path:
            messagebox.showwarning("⚠️ 警告", "请输入源文件夹路径")
            return False

        if not local_path:
            messagebox.showwarning("⚠️ 警告", "请输入目标文件夹路径")
            return False

        try:
            interval = float(self.interval_var.get())
            if interval <= 0:
                raise ValueError("间隔时间必须大于0")
        except ValueError as e:
            messagebox.showwarning("⚠️ 警告", f"轮询间隔必须是正数: {e}")
            return False

        return True

    def browse_shared_path(self):
        """浏览源文件夹路径"""
        path = filedialog.askdirectory(title="选择源文件夹路径")
        if path:
            self.shared_path_var.set(path)
            self.log_message(f"设置源文件夹路径: {path}")

    def browse_local_path(self):
        """浏览目标文件夹路径"""
        path = filedialog.askdirectory(title="选择目标文件夹路径")
        if path:
            self.local_path_var.set(path)
            self.log_message(f"设置目标文件夹路径: {path}")

    def load_config(self):
        """从文件加载配置"""
        try:
            if not os.path.exists(self.config_file):
                self.log_message(f"配置文件 {self.config_file} 不存在，使用默认配置")
                return

            config = configparser.ConfigParser()
            config.read(self.config_file, encoding='utf-8')

            # 加载路径配置
            if 'PATHS' in config:
                paths = config['PATHS']
                self.shared_path_var.set(paths.get('SHARED_FOLDER_PATH', ''))
                self.local_path_var.set(paths.get('LOCAL_TARGET_PATH', ''))

            # 加载同步配置
            if 'SYNC' in config:
                sync = config['SYNC']
                self.interval_var.set(sync.get('POLLING_INTERVAL_SECONDS', '5'))

            # 加载过滤配置
            if 'FILTER' in config:
                filter_config = config['FILTER']
                self.extensions_var.set(filter_config.get('FILE_EXTENSIONS', '.txt'))
                self.exclude_var.set(filter_config.get('EXCLUDE_ITEMS', 'temp,cache,.tmp,Thumbs.db,desktop.ini'))

            self.log_message(f"📂 配置已从 {self.config_file} 加载")

        except Exception as e:
            self.log_message(f"❌ 加载配置时出错: {e}")

    def setup_logging(self):
        """设置日志"""
        # 配置日志格式
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_file, encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )

    def log_message(self, message):
        """在状态框中添加日志消息"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        formatted_message = f"[{timestamp}] {message}\n"

        self.status_text.configure(state='normal')
        self.status_text.insert(tk.END, formatted_message)
        self.status_text.see(tk.END)
        self.status_text.configure(state='disabled')

        # 同时输出到控制台
        print(formatted_message.strip())

    def update_ui_state(self):
        """更新UI状态"""
        if self.running:
            self.start_btn.configure(state=tk.DISABLED)
            self.stop_btn.configure(state=tk.NORMAL)
            self.progress_bar.start()
            self.update_status("🔄 TXT文件同步进行中...")
        else:
            self.start_btn.configure(state=tk.NORMAL)
            self.stop_btn.configure(state=tk.DISABLED)
            self.progress_bar.stop()
            self.update_status("🔧 准备就绪 - 请配置参数并点击开始")

    def update_status(self, message):
        """更新状态信息"""
        self.status_var.set(message)


def main():
    """主函数"""
    # 设置DPI感知
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass

    # 创建主窗口
    root = tk.Tk()

    # 启动应用
    app = TXTFileSyncApp(root)

    # 如果没有托盘图标，显示主窗口
    if not app.tray_icon:
        app.show_window()

    root.mainloop()


if __name__ == "__main__":
    main()