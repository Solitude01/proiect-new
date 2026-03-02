#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能文件夹清理器 - 根据修改时间删除文件
作者: Claude Code
功能: 可视化界面选择文件夹，根据时间条件删除旧文件
"""

import os
import time
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from datetime import datetime, timedelta
from pathlib import Path
import fnmatch

# 尝试导入send2trash库，用于安全删除（移动到回收站）
try:
    from send2trash import send2trash
    SEND2TRASH_AVAILABLE = True
except ImportError:
    SEND2TRASH_AVAILABLE = False


class FileCleanerApp:
    """智能文件夹清理器主应用类"""

    def __init__(self, root):
        """初始化应用程序"""
        self.root = root
        self.root.title("智能文件夹清理器")
        self.root.geometry("800x800")
        self.root.resizable(True, True)

        # 应用程序变量
        self.folder_path = tk.StringVar()  # 选择的文件夹路径
        self.time_value = tk.IntVar(value=30)  # 时间值（默认30）
        self.time_unit = tk.StringVar(value='天')  # 时间单位（默认天）
        self.time_mode = tk.StringVar(value="relative")  # 时间模式: relative 或 custom
        self.custom_timestamp = tk.StringVar(value="")  # 自定义时间节点
        self.include_subfolders = tk.BooleanVar(value=True)  # 是否包含子文件夹（默认开启）
        self.deletion_mode = tk.StringVar(value="")  # 删除方式：'recycle'(回收站) 或 'permanent'(永久删除)，默认为空
        self.file_filter = tk.StringVar(value="*.*")  # 文件类型过滤
        self.delete_files_var = tk.BooleanVar(value=False)  # 是否删除文件（默认不选中）
        self.delete_folders = tk.BooleanVar(value=False)  # 是否删除文件夹（默认不选中）
        self.delete_empty_folders = tk.BooleanVar(value=True)  # 是否删除空文件夹
        self._initializing = True  # 标记是否在初始化阶段

        # 自定义时间节点的各个部分
        self.custom_year = tk.StringVar(value=datetime.now().strftime('%Y'))
        self.custom_month = tk.StringVar(value=datetime.now().strftime('%m'))
        self.custom_day = tk.StringVar(value=datetime.now().strftime('%d'))
        self.custom_hour = tk.StringVar(value="00")
        self.custom_minute = tk.StringVar(value="00")
        self.custom_second = tk.StringVar(value="00")

        # 创建界面
        self.create_widgets()
        self._initializing = False  # 初始化完成
        self.update_status("准备就绪")

        # 如果send2trash不可用，警告用户
        if not SEND2TRASH_AVAILABLE:
            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 警告：未安装send2trash库，无法使用回收站功能。")
            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 提示：运行 'pip install send2trash' 安装此库。")

        self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 智能文件夹清理器初始化完成")
        self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 提示：可以直接点击「执行清理」，预览不是必要步骤")

    def create_widgets(self):
        """创建所有GUI组件"""
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 配置网格权重，使界面可以自适应调整大小
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        current_row = 0

        # ========== 文件夹选择区域 ==========
        ttk.Label(main_frame, text="目标文件夹:", font=('Arial', 10, 'bold')).grid(
            row=current_row, column=0, sticky=tk.W, pady=5
        )
        current_row += 1

        # 文件夹路径显示框
        folder_frame = ttk.Frame(main_frame)
        folder_frame.grid(row=current_row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        folder_frame.columnconfigure(0, weight=1)

        self.folder_entry = ttk.Entry(folder_frame, textvariable=self.folder_path, state='readonly')
        self.folder_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))

        ttk.Button(folder_frame, text="浏览...", command=self.browse_folder).grid(row=0, column=1)
        current_row += 1

        # 分隔线
        ttk.Separator(main_frame, orient='horizontal').grid(
            row=current_row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10
        )
        current_row += 1

        # ========== 时间条件设置区域 ==========
        time_label = ttk.Label(main_frame, text="⏰ 时间条件", font=('Arial', 10, 'bold'))
        time_label.grid(row=current_row, column=0, sticky=tk.W, pady=(5, 0))
        current_row += 1

        # 快捷时间预设
        preset_frame = ttk.Frame(main_frame)
        preset_frame.grid(row=current_row, column=0, columnspan=3, sticky=tk.W, pady=5)

        ttk.Label(preset_frame, text="快捷预设:").pack(side=tk.LEFT, padx=(0, 5))

        presets = [
            ("1小时前", 1, "小时"),
            ("1天前", 1, "天"),
            ("1周前", 7, "天"),
            ("1月前", 1, "月"),
            ("3月前", 3, "月"),
            ("1年前", 1, "年")
        ]

        for text, value, unit in presets:
            ttk.Button(
                preset_frame,
                text=text,
                command=lambda v=value, u=unit: self.set_time_preset(v, u),
                width=8
            ).pack(side=tk.LEFT, padx=2)

        current_row += 1

        # 自定义时间设置
        time_frame = ttk.Frame(main_frame)
        time_frame.grid(row=current_row, column=0, columnspan=3, sticky=tk.W, pady=5)

        ttk.Label(time_frame, text="或自定义:", font=('Arial', 9)).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(time_frame, text="删除", font=('Arial', 10)).pack(side=tk.LEFT, padx=(0, 5))

        # 时间值输入框（使用Spinbox）
        self.time_value_spinbox = ttk.Spinbox(
            time_frame,
            from_=1,
            to=3650,
            textvariable=self.time_value,
            width=10
        )
        self.time_value_spinbox.pack(side=tk.LEFT, padx=(0, 5))

        # 时间单位选择
        self.time_unit_combo = ttk.Combobox(
            time_frame,
            textvariable=self.time_unit,
            values=['天', '小时', '分钟', '月', '年'],
            width=8,
            state='readonly'
        )
        self.time_unit_combo.pack(side=tk.LEFT, padx=(0, 5))
        self.time_unit_combo.bind('<<ComboboxSelected>>', self.on_time_unit_change)

        ttk.Label(time_frame, text="前修改过的文件", font=('Arial', 10)).pack(side=tk.LEFT)
        current_row += 1

        # 时间模式选择
        mode_frame = ttk.Frame(main_frame)
        mode_frame.grid(row=current_row, column=0, columnspan=3, sticky=tk.W, pady=5)
        
        ttk.Label(mode_frame, text="时间模式:", font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=(0, 10))
        
        self.time_mode = tk.StringVar(value="relative")  # relative 或 custom
        
        # 相对时间模式
        self.relative_radio = ttk.Radiobutton(
            mode_frame,
            text="相对时间",
            variable=self.time_mode,
            value="relative",
            command=self.on_time_mode_change
        )
        self.relative_radio.pack(side=tk.LEFT, padx=(0, 15))
        
        # 自定义时间节点模式
        self.custom_radio = ttk.Radiobutton(
            mode_frame,
            text="自定义时间节点",
            variable=self.time_mode,
            value="custom",
            command=self.on_time_mode_change
        )
        self.custom_radio.pack(side=tk.LEFT, padx=(0, 15))
        
        current_row += 1

        # 自定义时间节点输入区域
        custom_time_frame = ttk.Frame(main_frame)
        custom_time_frame.grid(row=current_row, column=0, columnspan=3, sticky=tk.W, pady=5)

        ttk.Label(custom_time_frame, text="时间节点:").pack(side=tk.LEFT, padx=(0, 5))

        # 年月日
        self.custom_year_entry = ttk.Entry(custom_time_frame, textvariable=self.custom_year, width=6)
        self.custom_year_entry.pack(side=tk.LEFT, padx=(0, 2))
        ttk.Label(custom_time_frame, text="年").pack(side=tk.LEFT, padx=(0, 5))

        self.custom_month_entry = ttk.Entry(custom_time_frame, textvariable=self.custom_month, width=4)
        self.custom_month_entry.pack(side=tk.LEFT, padx=(0, 2))
        ttk.Label(custom_time_frame, text="月").pack(side=tk.LEFT, padx=(0, 5))

        self.custom_day_entry = ttk.Entry(custom_time_frame, textvariable=self.custom_day, width=4)
        self.custom_day_entry.pack(side=tk.LEFT, padx=(0, 2))
        ttk.Label(custom_time_frame, text="日").pack(side=tk.LEFT, padx=(0, 10))

        # 时分秒
        self.custom_hour_entry = ttk.Entry(custom_time_frame, textvariable=self.custom_hour, width=4)
        self.custom_hour_entry.pack(side=tk.LEFT, padx=(0, 2))
        ttk.Label(custom_time_frame, text=":").pack(side=tk.LEFT)

        self.custom_minute_entry = ttk.Entry(custom_time_frame, textvariable=self.custom_minute, width=4)
        self.custom_minute_entry.pack(side=tk.LEFT, padx=(0, 2))
        ttk.Label(custom_time_frame, text=":").pack(side=tk.LEFT)

        self.custom_second_entry = ttk.Entry(custom_time_frame, textvariable=self.custom_second, width=4)
        self.custom_second_entry.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            custom_time_frame,
            text="当前时间",
            command=self.set_current_time,
            width=10
        ).pack(side=tk.LEFT, padx=(0, 5))

        current_row += 1

        # ========== 配置选项区域 ==========

        # 扫描范围设置
        scan_frame = ttk.LabelFrame(main_frame, text="📁 扫描范围", padding="10")
        scan_frame.grid(row=current_row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        current_row += 1

        self.include_subfolders_check = ttk.Checkbutton(
            scan_frame,
            text="递归扫描子文件夹",
            variable=self.include_subfolders
        )
        self.include_subfolders_check.grid(row=0, column=0, sticky=tk.W, pady=2)

        # 文件过滤
        filter_frame = ttk.Frame(scan_frame)
        filter_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        ttk.Label(filter_frame, text="文件类型:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Entry(filter_frame, textvariable=self.file_filter, width=20).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(filter_frame, text="(*.log, *.tmp 或留空表示所有)").pack(side=tk.LEFT)

        # 删除策略设置
        strategy_frame = ttk.LabelFrame(main_frame, text="🗑️ 删除策略", padding="10")
        strategy_frame.grid(row=current_row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        current_row += 1

        # 删除目标选择
        target_frame = ttk.Frame(strategy_frame)
        target_frame.grid(row=0, column=0, sticky=tk.W, pady=2)

        ttk.Label(target_frame, text="删除目标:", font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 10))

        self.delete_files_var = tk.BooleanVar(value=True)
        self.delete_files_check = ttk.Checkbutton(
            target_frame,
            text="文件",
            variable=self.delete_files_var,
            command=self.on_delete_strategy_change
        )
        self.delete_files_check.pack(side=tk.LEFT, padx=(0, 15))

        self.delete_folders_check = ttk.Checkbutton(
            target_frame,
            text="文件夹（包含所有内容）",
            variable=self.delete_folders,
            command=self.on_delete_strategy_change
        )
        self.delete_folders_check.pack(side=tk.LEFT)

        # 空文件夹清理
        self.delete_empty_folders_check = ttk.Checkbutton(
            strategy_frame,
            text="清理空文件夹（删除文件后自动清理产生的空文件夹）",
            variable=self.delete_empty_folders
        )
        self.delete_empty_folders_check.grid(row=1, column=0, sticky=tk.W, pady=2, padx=(20, 0))

        # 删除方式设置
        method_frame = ttk.LabelFrame(main_frame, text="⚙️ 删除方式（必选其一）", padding="10")
        method_frame.grid(row=current_row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        current_row += 1

        # 单选按钮组
        button_frame = ttk.Frame(method_frame)
        button_frame.grid(row=0, column=0, sticky=tk.W, pady=5)

        ttk.Label(button_frame, text="选择删除方式:", font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 10))

        self.recycle_radio = ttk.Radiobutton(
            button_frame,
            text="🔄 移动到回收站（安全，可恢复）",
            variable=self.deletion_mode,
            value="recycle"
        )
        self.recycle_radio.pack(side=tk.LEFT, padx=(0, 20))

        self.permanent_radio = ttk.Radiobutton(
            button_frame,
            text="⚠️ 永久删除（无法恢复）",
            variable=self.deletion_mode,
            value="permanent"
        )
        self.permanent_radio.pack(side=tk.LEFT)

        # 提示信息
        ttk.Label(
            method_frame,
            text="💡 提示：执行清理前必须选择一种删除方式",
            foreground='blue',
            font=('Arial', 8)
        ).grid(row=1, column=0, sticky=tk.W, pady=2, padx=(20, 0))

        if not SEND2TRASH_AVAILABLE:
            self.recycle_radio.config(state='disabled')
            ttk.Label(
                method_frame,
                text="ℹ️ 未安装 send2trash 库，无法使用回收站功能。运行: pip install send2trash",
                foreground='orange',
                font=('Arial', 8)
            ).grid(row=2, column=0, sticky=tk.W, pady=2, padx=(20, 0))

        # ========== 操作按钮区域 ==========
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=current_row, column=0, columnspan=3, pady=10)
        current_row += 1

        self.preview_button = ttk.Button(
            button_frame,
            text="🔍 预览",
            command=self.preview_files,
            width=18
        )
        self.preview_button.pack(side=tk.LEFT, padx=5)

        self.execute_button = ttk.Button(
            button_frame,
            text="🗑️ 执行清理",
            command=self.execute_cleanup,
            width=18
        )
        self.execute_button.pack(side=tk.LEFT, padx=5)

        ttk.Button(
            button_frame,
            text="🔄 重置设置",
            command=self.reset_settings,
            width=18
        ).pack(side=tk.LEFT, padx=5)

        # ========== 进度条 ==========
        progress_frame = ttk.Frame(main_frame)
        progress_frame.grid(row=current_row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        progress_frame.columnconfigure(0, weight=1)
        current_row += 1

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100,
            mode='determinate'
        )
        self.progress_bar.grid(row=0, column=0, sticky=(tk.W, tk.E))

        self.progress_label = ttk.Label(progress_frame, text="", font=('Arial', 8))
        self.progress_label.grid(row=1, column=0, sticky=tk.W)

        # ========== 日志区域 ==========
        log_frame = ttk.LabelFrame(main_frame, text="日志", padding="5")
        log_frame.grid(row=current_row, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(current_row, weight=1)
        current_row += 1

        # 使用ScrolledText控件显示日志
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=15,
            width=80,
            wrap=tk.WORD,
            font=('Consolas', 9)
        )
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 清空日志按钮
        ttk.Button(log_frame, text="清空日志", command=self.clear_log).grid(
            row=1, column=0, sticky=tk.E, pady=(5, 0)
        )

        # ========== 状态栏 ==========
        self.status_label = ttk.Label(
            main_frame,
            text="准备就绪",
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        self.status_label.grid(row=current_row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(5, 0))

    def on_time_unit_change(self, event=None):
        """时间单位改变时的处理"""
        unit = self.time_unit.get()
        # 根据单位调整输入范围
        if unit == '分钟':
            self.time_value_spinbox.config(from_=1, to=525600)  # 最多1年分钟数
        elif unit == '小时':
            self.time_value_spinbox.config(from_=1, to=8760)   # 最多1年小时数
        elif unit == '天':
            self.time_value_spinbox.config(from_=1, to=3650)   # 最多10年天数
        elif unit == '月':
            self.time_value_spinbox.config(from_=1, to=120)    # 最多10年月数
        elif unit == '年':
            self.time_value_spinbox.config(from_=1, to=10)     # 最多10年

    def on_time_mode_change(self):
        """时间模式改变时的处理"""
        if self.time_mode.get() == "custom":
            # 自定义时间节点模式
            self.time_value_spinbox.config(state='disabled')
            self.time_unit_combo.config(state='disabled')
            # 启用所有自定义时间输入框
            self.custom_year_entry.config(state='normal')
            self.custom_month_entry.config(state='normal')
            self.custom_day_entry.config(state='normal')
            self.custom_hour_entry.config(state='normal')
            self.custom_minute_entry.config(state='normal')
            self.custom_second_entry.config(state='normal')
        else:
            # 相对时间模式
            self.time_value_spinbox.config(state='normal')
            self.time_unit_combo.config(state='readonly')
            # 禁用所有自定义时间输入框
            self.custom_year_entry.config(state='disabled')
            self.custom_month_entry.config(state='disabled')
            self.custom_day_entry.config(state='disabled')
            self.custom_hour_entry.config(state='disabled')
            self.custom_minute_entry.config(state='disabled')
            self.custom_second_entry.config(state='disabled')

    def set_current_time(self):
        """设置当前时间为自定义时间节点"""
        now = datetime.now()
        self.custom_year.set(now.strftime('%Y'))
        self.custom_month.set(now.strftime('%m'))
        self.custom_day.set(now.strftime('%d'))
        self.custom_hour.set(now.strftime('%H'))
        self.custom_minute.set(now.strftime('%M'))
        self.custom_second.set(now.strftime('%S'))

    def set_time_preset(self, value, unit):
        """设置时间快捷预设"""
        self.time_mode.set("relative")
        self.time_value.set(value)
        self.time_unit.set(unit)
        self.on_time_mode_change()
        self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 已设置时间预设: {value}{unit}前")

    def reset_settings(self):
        """重置所有设置到默认值"""
        self.time_value.set(30)
        self.time_unit.set('天')
        self.time_mode.set("relative")
        self.include_subfolders.set(True)  # 默认打开递归扫描
        self.delete_files_var.set(False)  # 默认不选中
        self.delete_folders.set(False)  # 默认不选中
        self.delete_empty_folders.set(True)
        self.deletion_mode.set("")  # 默认不选中任何删除方式
        self.file_filter.set("*.*")

        # 重置自定义时间
        now = datetime.now()
        self.custom_year.set(now.strftime('%Y'))
        self.custom_month.set(now.strftime('%m'))
        self.custom_day.set(now.strftime('%d'))
        self.custom_hour.set("00")
        self.custom_minute.set("00")
        self.custom_second.set("00")

        self.on_time_mode_change()
        self.on_delete_strategy_change()
        self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 已重置所有设置到默认值")

    def update_progress(self, current, total, message=""):
        """更新进度条和进度消息"""
        if total > 0:
            progress = (current / total) * 100
            self.progress_var.set(progress)
            self.progress_label.config(text=f"{message} ({current}/{total}) - {progress:.1f}%")
        else:
            self.progress_var.set(0)
            self.progress_label.config(text=message)
        self.root.update()

    def clear_progress(self):
        """清除进度条"""
        self.progress_var.set(0)
        self.progress_label.config(text="")

    def on_delete_strategy_change(self):
        """删除策略改变时的处理 - 管理选项之间的逻辑关系"""
        delete_files = self.delete_files_var.get()
        delete_folders = self.delete_folders.get()

        # 初始化阶段不检查，避免启动时弹窗
        if self._initializing:
            return

        # 如果两个都不选中，禁用"清理空文件夹"选项
        if not delete_files and not delete_folders:
            self.delete_empty_folders.set(False)
            self.delete_empty_folders_check.config(state='disabled')
            # 给出友好提示，而不是强制恢复
            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 提示：请选择至少一个删除目标（文件或文件夹）")
            return

        # 只有删除文件时，"清理空文件夹"选项才有意义
        if delete_files and not delete_folders:
            self.delete_empty_folders_check.config(state='normal')
        elif delete_folders and not delete_files:
            # 只删除文件夹时，空文件夹清理没有意义
            self.delete_empty_folders.set(False)
            self.delete_empty_folders_check.config(state='disabled')
        else:
            # 两者都删除时，空文件夹清理可选
            self.delete_empty_folders_check.config(state='normal')

    def browse_folder(self):
        """浏览并选择文件夹"""
        folder = filedialog.askdirectory(title="选择要清理的文件夹")
        if folder:
            self.folder_path.set(folder)
            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 已选择文件夹: {folder}")

    def get_items_to_delete(self):
        """
        获取符合条件的文件和文件夹列表
        返回: (文件列表, 文件夹列表)
        """
        start_time = time.time()
        folder = self.folder_path.get()

        # 验证文件夹路径
        if not folder:
            messagebox.showerror("错误", "请先选择一个文件夹！")
            return None, None

        if not os.path.exists(folder):
            messagebox.showerror("错误", f"文件夹不存在: {folder}")
            return None, None

        if not os.path.isdir(folder):
            messagebox.showerror("错误", f"选择的路径不是文件夹: {folder}")
            return None, None

        # 检查是否选择了删除方式
        deletion_mode = self.deletion_mode.get()
        if not deletion_mode:
            messagebox.showwarning(
                "提示",
                "请选择删除方式：\n\n🔄 移动到回收站（可恢复）\n⚠️ 永久删除（不可恢复）\n\n在「删除方式」区域选择一种方式。"
            )
            return None, None

        # 检查是否至少选择了一个删除目标
        delete_files = self.delete_files_var.get()
        delete_folders_enabled = self.delete_folders.get()

        if not delete_files and not delete_folders_enabled:
            messagebox.showwarning(
                "提示",
                "请至少选择一个删除目标：\n\n☑ 文件\n☑ 文件夹\n\n在「删除策略」区域勾选要删除的目标类型。"
            )
            return None, None

        # 计算时间阈值
        try:
            if self.time_mode.get() == "custom":
                # 自定义时间节点模式 - 从分开的输入框获取值
                try:
                    year = self.custom_year.get().strip()
                    month = self.custom_month.get().strip()
                    day = self.custom_day.get().strip()
                    hour = self.custom_hour.get().strip()
                    minute = self.custom_minute.get().strip()
                    second = self.custom_second.get().strip()

                    if not all([year, month, day, hour, minute, second]):
                        messagebox.showerror("错误", "请填写完整的自定义时间节点！")
                        return None, None

                    custom_time_str = f"{year}-{month}-{day} {hour}:{minute}:{second}"
                    custom_dt = datetime.strptime(custom_time_str, '%Y-%m-%d %H:%M:%S')
                    cutoff_time = custom_dt.timestamp()
                    cutoff_date = custom_dt
                except ValueError as e:
                    messagebox.showerror("错误", f"自定义时间节点格式错误！\n请检查年月日时分秒的值是否正确。\n错误信息: {e}")
                    return None, None
            else:
                # 相对时间模式 - 删除N个时间单位前的文件
                time_value = self.time_value.get()
                if time_value < 1:
                    messagebox.showerror("错误", "时间值必须大于0！")
                    return None, None
                
                unit = self.time_unit.get()
                seconds_per_unit = {
                    '分钟': 60,
                    '小时': 60 * 60,
                    '天': 24 * 60 * 60,
                    '月': 30 * 24 * 60 * 60,  # 近似值
                    '年': 365 * 24 * 60 * 60  # 近似值
                }
                
                cutoff_time = time.time() - (time_value * seconds_per_unit[unit])
                cutoff_date = datetime.fromtimestamp(cutoff_time)

        except tk.TclError:
            messagebox.showerror("错误", "请输入有效的时间值！")
            return None, None

        self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始扫描文件夹: {folder}")
        if self.time_mode.get() == "custom":
            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 使用自定义时间节点: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")
            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 将删除该时间节点之前修改的项目")
        else:
            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 时间阈值: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')} ({time_value}{unit}前)")
            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 将删除{time_value}{unit}前修改的项目")
        self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 包含子文件夹: {'是' if self.include_subfolders.get() else '否'}")

        # 检查删除目标
        delete_files = self.delete_files_var.get()
        delete_folders_enabled = self.delete_folders.get()
        self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 删除目标: {'文件 ' if delete_files else ''}{'文件夹' if delete_folders_enabled else ''}")

        # 获取文件过滤模式（仅对文件有效）
        filter_patterns = self.file_filter.get().strip()
        if not filter_patterns or filter_patterns == "":
            filter_patterns = "*.*"

        patterns = [p.strip() for p in filter_patterns.split(',')]
        if delete_files:
            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 文件过滤: {', '.join(patterns)}")


        files_to_delete = []
        folders_to_delete = []

        try:
            # 遍历文件夹
            if self.include_subfolders.get():
                # 递归遍历所有子文件夹
                scan_start = time.time()
                for root, dirs, files in os.walk(folder):
                    # 收集文件（如果启用）
                    if delete_files:
                        for filename in files:
                            file_path = os.path.join(root, filename)
                            if self._should_delete_file(file_path, cutoff_time, patterns):
                                files_to_delete.append(file_path)

                    # 收集文件夹（如果启用）
                    if delete_folders_enabled:
                        for dirname in dirs:
                            dir_path = os.path.join(root, dirname)
                            if self._should_delete_folder(dir_path, cutoff_time):
                                folders_to_delete.append(dir_path)

                scan_end = time.time()
                self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 扫描完成，耗时: {scan_end - scan_start:.2f}秒")
            else:
                # 只遍历当前文件夹
                scan_start = time.time()
                try:
                    for item in os.listdir(folder):
                        item_path = os.path.join(folder, item)
                        if os.path.isfile(item_path) and delete_files:
                            if self._should_delete_file(item_path, cutoff_time, patterns):
                                files_to_delete.append(item_path)
                        elif os.path.isdir(item_path) and delete_folders_enabled:
                            if self._should_delete_folder(item_path, cutoff_time):
                                folders_to_delete.append(item_path)
                    scan_end = time.time()
                    self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 扫描完成，耗时: {scan_end - scan_start:.2f}秒")
                except PermissionError as e:
                    self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误：无权限访问文件夹 {folder}: {e}")
                    messagebox.showerror("权限错误", f"无法访问文件夹: {e}")
                    return None, None

        except Exception as e:
            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 扫描文件时发生错误: {e}")
            messagebox.showerror("错误", f"扫描文件时发生错误: {e}")
            return None, None

        total_time = time.time() - start_time
        self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 文件扫描总耗时: {total_time:.2f}秒")
        self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 找到 {len(files_to_delete)} 个文件, {len(folders_to_delete)} 个文件夹")
        return files_to_delete, folders_to_delete

    def _should_delete_file(self, file_path, cutoff_time, patterns):
        """
        判断文件是否应该被删除
        参数:
            file_path: 文件路径
            cutoff_time: 时间阈值（时间戳）
            patterns: 文件名匹配模式列表
        返回: True/False
        """
        try:
            # 检查文件修改时间
            mtime = os.path.getmtime(file_path)
            if mtime >= cutoff_time:
                return False

            # 检查文件名是否匹配过滤模式
            filename = os.path.basename(file_path)
            for pattern in patterns:
                if fnmatch.fnmatch(filename, pattern):
                    return True

            return False

        except PermissionError:
            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 警告：无权限访问文件 {file_path}")
            return False
        except Exception as e:
            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 警告：检查文件时出错 {file_path}: {e}")
            return False

    def _should_delete_folder(self, folder_path, cutoff_time):
        """
        判断文件夹是否应该被删除
        参数:
            folder_path: 文件夹路径
            cutoff_time: 时间阈值（时间戳）
        返回: True/False
        """
        try:
            # 检查文件夹修改时间
            mtime = os.path.getmtime(folder_path)
            return mtime < cutoff_time

        except PermissionError:
            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 警告：无权限访问文件夹 {folder_path}")
            return False
        except Exception as e:
            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 警告：检查文件夹时出错 {folder_path}: {e}")
            return False

    def _get_folder_size(self, folder_path):
        """
        计算文件夹的总大小
        参数:
            folder_path: 文件夹路径
        返回: 文件夹大小（字节）
        """
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(folder_path):
                for filename in filenames:
                    file_path = os.path.join(dirpath, filename)
                    try:
                        total_size += os.path.getsize(file_path)
                    except:
                        pass
        except:
            pass
        return total_size

    def _remove_empty_folders(self, root_folder, use_recycle_mode=False):
        """
        递归删除空文件夹
        参数:
            root_folder: 根文件夹路径
            use_recycle_mode: 是否使用回收站模式
        返回: 删除的空文件夹数量
        """
        if not self.delete_empty_folders.get():
            return 0

        deleted_count = 0
        use_recycle = use_recycle_mode and SEND2TRASH_AVAILABLE

        # 从最深层开始，向上删除空文件夹
        for dirpath, dirnames, filenames in os.walk(root_folder, topdown=False):
            # 跳过根文件夹本身
            if dirpath == root_folder:
                continue

            try:
                # 检查文件夹是否为空
                if not os.listdir(dirpath):
                    if use_recycle:
                        send2trash(dirpath)
                        self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [✓] 已删除空文件夹（回收站）: {dirpath}")
                    else:
                        os.rmdir(dirpath)
                        self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [✓] 已删除空文件夹（永久）: {dirpath}")
                    deleted_count += 1
            except PermissionError:
                self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [✗] 无权限删除空文件夹: {dirpath}")
            except Exception as e:
                # 忽略非空文件夹或其他错误
                pass

        return deleted_count

    def preview_files(self):
        """预览将要删除的文件和文件夹（不执行删除）"""
        preview_start = time.time()
        self.clear_log()
        self.clear_progress()
        self.update_status("预览中...")
        self.log_message("=" * 80)
        self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始预览...")
        self.log_message("=" * 80)

        # 暂时禁用按钮
        self.preview_button.config(state='disabled')
        self.execute_button.config(state='disabled')
        self.root.update()

        try:
            files_to_delete, folders_to_delete = self.get_items_to_delete()

            if files_to_delete is None or folders_to_delete is None:
                return

            total_items = len(files_to_delete) + len(folders_to_delete)

            if total_items == 0:
                self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] \n没有找到符合条件的项目。")
                self.update_status("预览完成 - 无项目")
                self.clear_progress()
            else:
                self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] \n找到 {len(files_to_delete)} 个文件和 {len(folders_to_delete)} 个文件夹:\n")

                # 计算总大小
                total_size = 0
                item_count = 0

                # 显示文件
                if files_to_delete:
                    self.log_message("--- 文件列表 ---")
                    for i, file_path in enumerate(files_to_delete, 1):
                        try:
                            file_size = os.path.getsize(file_path)
                            total_size += file_size
                            mtime = os.path.getmtime(file_path)
                            mtime_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                            size_str = self._format_size(file_size)

                            self.log_message(f"{i}. [{mtime_str}] [{size_str}] {file_path}")
                            item_count += 1

                            # 性能优化：每100项更新一次UI和进度条
                            if item_count % 100 == 0:
                                self.update_progress(item_count, total_items, "预览文件")
                        except Exception as e:
                            self.log_message(f"{i}. [错误] {file_path} - {e}")

                # 显示文件夹
                if folders_to_delete:
                    self.log_message("\n--- 文件夹列表 ---")
                    for i, folder_path in enumerate(folders_to_delete, 1):
                        try:
                            folder_size = self._get_folder_size(folder_path)
                            total_size += folder_size
                            mtime = os.path.getmtime(folder_path)
                            mtime_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                            size_str = self._format_size(folder_size)

                            self.log_message(f"{i}. [{mtime_str}] [{size_str}] {folder_path}")
                            item_count += 1

                            # 性能优化：每100项更新一次UI和进度条
                            if item_count % 100 == 0:
                                self.update_progress(item_count, total_items, "预览文件夹")
                        except Exception as e:
                            self.log_message(f"{i}. [错误] {folder_path} - {e}")

                preview_end = time.time()
                self.log_message(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 总计: {len(files_to_delete)} 个文件, {len(folders_to_delete)} 个文件夹, 总大小: {self._format_size(total_size)}")
                self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 预览完成，耗时: {preview_end - preview_start:.2f}秒")
                self.update_status(f"预览完成 - 找到 {total_items} 个项目")
                self.update_progress(total_items, total_items, "预览完成")

        finally:
            # 重新启用按钮
            self.preview_button.config(state='normal')
            self.execute_button.config(state='normal')

    def execute_cleanup(self):
        """执行文件和文件夹清理操作"""
        cleanup_start = time.time()
        self.clear_log()
        self.clear_progress()
        self.update_status("准备执行清理...")
        self.log_message("=" * 80)
        self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始执行清理...")
        self.log_message("=" * 80)

        # 获取要删除的文件和文件夹列表
        files_to_delete, folders_to_delete = self.get_items_to_delete()

        if files_to_delete is None or folders_to_delete is None:
            return

        total_items = len(files_to_delete) + len(folders_to_delete)

        if total_items == 0:
            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] \n没有找到符合条件的项目。")
            messagebox.showinfo("提示", "没有找到符合条件的项目。")
            self.update_status("就绪")
            return

        # 确认对话框
        deletion_mode = self.deletion_mode.get()
        use_recycle = (deletion_mode == "recycle" and SEND2TRASH_AVAILABLE)
        deletion_type = "移动到回收站" if use_recycle else "永久删除"

        confirm_message = (
            f"您确定要{deletion_type}以下项目吗？\n\n"
            f"文件: {len(files_to_delete)} 个\n"
            f"文件夹: {len(folders_to_delete)} 个\n\n"
            f"{'文件将被移动到回收站，可以恢复。' if use_recycle else '警告：此操作将永久删除，无法恢复！'}"
        )

        response = messagebox.askyesno(
            "确认删除",
            confirm_message,
            icon='warning' if not use_recycle else 'question'
        )

        if not response:
            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] \n用户取消了操作。")
            self.update_status("操作已取消")
            return

        # 执行删除
        self.log_message(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始{deletion_type}...\n")

        # 禁用按钮
        self.preview_button.config(state='disabled')
        self.execute_button.config(state='disabled')

        file_success_count = 0
        file_error_count = 0
        folder_success_count = 0
        folder_error_count = 0
        delete_start = time.time()
        processed_count = 0

        try:
            # 先删除文件
            if files_to_delete:
                self.log_message("--- 删除文件 ---")
                for i, file_path in enumerate(files_to_delete, 1):
                    try:
                        if use_recycle:
                            # 移动到回收站
                            send2trash(file_path)
                            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [✓] 已移动到回收站: {file_path}")
                        else:
                            # 永久删除
                            os.remove(file_path)
                            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [✓] 已永久删除: {file_path}")

                        file_success_count += 1

                    except PermissionError:
                        self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [✗] 权限不足，无法删除: {file_path}")
                        file_error_count += 1

                    except Exception as e:
                        self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [✗] 删除失败: {file_path} - {e}")
                        file_error_count += 1

                    processed_count += 1
                    # 性能优化：每50项更新一次UI和进度条
                    if i % 50 == 0:
                        self.update_progress(processed_count, total_items, "删除文件")

            # 再删除文件夹
            if folders_to_delete:
                self.log_message("\n--- 删除文件夹 ---")
                for i, folder_path in enumerate(folders_to_delete, 1):
                    try:
                        if use_recycle:
                            # 移动到回收站
                            send2trash(folder_path)
                            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [✓] 已移动到回收站: {folder_path}")
                        else:
                            # 永久删除（使用shutil.rmtree递归删除）
                            shutil.rmtree(folder_path)
                            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [✓] 已永久删除: {folder_path}")

                        folder_success_count += 1

                    except PermissionError:
                        self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [✗] 权限不足，无法删除: {folder_path}")
                        folder_error_count += 1

                    except Exception as e:
                        self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [✗] 删除失败: {folder_path} - {e}")
                        folder_error_count += 1

                    processed_count += 1
                    # 性能优化：每10个文件夹更新一次UI和进度条
                    if i % 10 == 0:
                        self.update_progress(processed_count, total_items, "删除文件夹")

            # 清理空文件夹
            empty_folder_count = 0
            if self.delete_empty_folders.get():
                self.log_message(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始清理空文件夹...")
                self.update_progress(processed_count, total_items, "清理空文件夹")

                root_folder = self.folder_path.get()
                empty_folder_count = self._remove_empty_folders(root_folder, use_recycle)

                if empty_folder_count > 0:
                    self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 清理了 {empty_folder_count} 个空文件夹")

        finally:
            # 重新启用按钮
            self.preview_button.config(state='normal')
            self.execute_button.config(state='normal')

        delete_end = time.time()
        # 显示结果
        self.log_message("\n" + "=" * 80)
        self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 清理完成！")
        self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 文件 - 成功: {file_success_count}, 失败: {file_error_count}")
        self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 文件夹 - 成功: {folder_success_count}, 失败: {folder_error_count}")
        if empty_folder_count > 0:
            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 空文件夹 - 已清理: {empty_folder_count}")
        self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 删除操作耗时: {delete_end - delete_start:.2f}秒")
        self.log_message("=" * 80)

        total_time = time.time() - cleanup_start
        total_success = file_success_count + folder_success_count
        total_error = file_error_count + folder_error_count

        self.update_status(f"清理完成 - 成功: {total_success}, 失败: {total_error}, 空文件夹: {empty_folder_count}, 总耗时: {total_time:.2f}秒")
        self.update_progress(100, 100, "清理完成")

        # 显示完成消息
        result_message = (
            f"清理完成！\n\n"
            f"文件:\n  成功: {file_success_count}\n  失败: {file_error_count}\n\n"
            f"文件夹:\n  成功: {folder_success_count}\n  失败: {folder_error_count}\n"
        )
        if empty_folder_count > 0:
            result_message += f"\n空文件夹: {empty_folder_count}"
        result_message += f"\n\n总耗时: {total_time:.2f}秒"

        # 自动保存日志到本地文件
        self.save_log_to_file()

        messagebox.showinfo("完成", result_message)

    def save_log_to_file(self):
        """保存日志到本地文件"""
        try:
            # 创建logs文件夹（如果不存在）
            log_dir = "logs"
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)

            # 生成日志文件名（带时间戳）
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_filename = os.path.join(log_dir, f"清理日志_{timestamp}.txt")

            # 获取日志内容
            log_content = self.log_text.get(1.0, tk.END)

            # 写入文件
            with open(log_filename, 'w', encoding='utf-8') as f:
                f.write(log_content)

            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 日志已保存到: {log_filename}")

        except Exception as e:
            self.log_message(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 保存日志失败: {e}")

    def _format_size(self, size_bytes):
        """格式化文件大小显示"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"

    def log_message(self, message):
        """在日志区域添加消息"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)  # 自动滚动到底部
        self.root.update()

    def clear_log(self):
        """清空日志区域"""
        self.log_text.delete(1.0, tk.END)

    def update_status(self, status):
        """更新状态栏"""
        self.status_label.config(text=status)
        self.root.update()

    def get_processing_summary(self):
        """获取处理时间汇总信息"""
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return f"[{current_time}] 处理时间戳已记录"


def main():
    """主函数"""
    root = tk.Tk()
    app = FileCleanerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
