#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
COCO数据集验证GUI工具
用于验证COCO格式的JSON标注文件是否符合标准
"""

import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox, ttk
import json
import os
from pathlib import Path
from typing import List, Set, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import queue
import time


class COCOValidatorGUI:
    """COCO数据集验证器GUI应用"""

    def __init__(self, root):
        self.root = root
        self.root.title("COCO数据集验证工具")
        self.root.geometry("1400x850")

        # 存储选择的文件路径
        self.selected_files = []

        # 存储验证结果统计
        self.validation_stats = {}  # {filename: {"total_errors": int, "error_types": {type: count}}}

        # 多线程相关
        self.use_multithreading = tk.BooleanVar(value=False)
        self.thread_count = tk.IntVar(value=4)
        self.validation_lock = threading.Lock()
        self.is_validating = False

        # 进度跟踪
        self.total_files_to_validate = 0
        self.files_validated = 0

        # 核查项开关（默认全部开启）
        self.validation_checks = {
            'json_format': tk.BooleanVar(value=True),  # JSON格式检查
            'top_level_keys': tk.BooleanVar(value=True),  # 顶级键检查
            'image_id_unique': tk.BooleanVar(value=True),  # Image ID唯一性
            'category_id_unique': tk.BooleanVar(value=True),  # Category ID唯一性
            'annotation_id_unique': tk.BooleanVar(value=True),  # Annotation ID唯一性
            'image_required_keys': tk.BooleanVar(value=True),  # Image必需键
            'image_dimensions': tk.BooleanVar(value=True),  # Image尺寸验证
            'category_required_keys': tk.BooleanVar(value=True),  # Category必需键
            'annotation_required_keys': tk.BooleanVar(value=True),  # Annotation必需键
            'image_id_exists': tk.BooleanVar(value=True),  # image_id存在性
            'category_id_exists': tk.BooleanVar(value=True),  # category_id存在性
            'iscrowd_valid': tk.BooleanVar(value=True),  # iscrowd值验证
            'bbox_format': tk.BooleanVar(value=True),  # BBox格式
            'bbox_bounds': tk.BooleanVar(value=True),  # BBox边界
            'area_valid': tk.BooleanVar(value=True),  # Area值验证
            'segmentation_format': tk.BooleanVar(value=True),  # Segmentation格式
            'segmentation_rectangle': tk.BooleanVar(value=True),  # 矩形标注8值检查
        }

        # 创建GUI组件
        self.create_widgets()

    def create_widgets(self):
        """创建GUI界面组件"""
        # 设置整体样式
        style = ttk.Style()
        style.theme_use('clam')

        # 主容器：左中右三栏布局
        main_container = tk.Frame(self.root, bg="#f0f0f0")
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 左侧区域：核查选项
        left_frame = tk.Frame(main_container, relief=tk.RAISED, borderwidth=2, width=220, bg="white")
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        left_frame.pack_propagate(False)

        # 核查选项标题
        tk.Label(
            left_frame,
            text="📋 核查选项",
            font=("Arial", 11, "bold"),
            bg="#2196F3",
            fg="white",
            pady=10
        ).pack(fill=tk.X)

        # 核查选项按钮区
        btn_frame = tk.Frame(left_frame, pady=8, bg="white")
        btn_frame.pack(fill=tk.X, padx=8)

        tk.Button(
            btn_frame,
            text="✓ 全选",
            command=self.select_all_checks,
            width=9,
            bg="#4CAF50",
            fg="white",
            font=("Arial", 8, "bold"),
            relief=tk.FLAT,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            btn_frame,
            text="✗ 全不选",
            command=self.deselect_all_checks,
            width=9,
            bg="#FF5722",
            fg="white",
            font=("Arial", 8, "bold"),
            relief=tk.FLAT,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=2)

        # 核查项列表（添加滚动条）
        checks_canvas_frame = tk.Frame(left_frame, bg="white")
        checks_canvas_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=5)

        checks_canvas = tk.Canvas(checks_canvas_frame, highlightthickness=0, bg="white")
        checks_scrollbar = tk.Scrollbar(checks_canvas_frame, orient="vertical", command=checks_canvas.yview)
        checks_frame = tk.Frame(checks_canvas, bg="white")

        checks_frame.bind(
            "<Configure>",
            lambda e: checks_canvas.configure(scrollregion=checks_canvas.bbox("all"))
        )

        checks_canvas.create_window((0, 0), window=checks_frame, anchor="nw")
        checks_canvas.configure(yscrollcommand=checks_scrollbar.set)

        checks_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        checks_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        check_labels = {
            'json_format': 'JSON格式检查',
            'top_level_keys': '顶级键检查',
            'image_id_unique': 'Image ID唯一性',
            'category_id_unique': 'Category ID唯一性',
            'annotation_id_unique': 'Annotation ID唯一性',
            'image_required_keys': 'Image必需键',
            'image_dimensions': 'Image尺寸验证',
            'category_required_keys': 'Category必需键',
            'annotation_required_keys': 'Annotation必需键',
            'image_id_exists': 'image_id存在性',
            'category_id_exists': 'category_id存在性',
            'iscrowd_valid': 'iscrowd值验证',
            'bbox_format': 'BBox格式检查',
            'bbox_bounds': 'BBox边界检查',
            'area_valid': 'Area值验证',
            'segmentation_format': 'Segmentation格式',
            'segmentation_rectangle': '矩形标注8值检查',
        }

        for key, label in check_labels.items():
            cb = tk.Checkbutton(
                checks_frame,
                text=label,
                variable=self.validation_checks[key],
                font=("Arial", 9),
                anchor="w",
                bg="white",
                activebackground="#e3f2fd",
                cursor="hand2"
            )
            cb.pack(fill=tk.X, pady=3, padx=2)

        # 中间区域：文件列表和错误统计
        middle_frame = tk.Frame(main_container, relief=tk.RAISED, borderwidth=2, width=360, bg="white")
        middle_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 8))
        middle_frame.pack_propagate(False)

        # 中间区域标题
        tk.Label(
            middle_frame,
            text="📁 文件列表与错误统计",
            font=("Arial", 11, "bold"),
            bg="#FF9800",
            fg="white",
            pady=10
        ).pack(fill=tk.X)

        # 已选择文件信息区域
        file_info_frame = tk.Frame(middle_frame, relief=tk.SUNKEN, borderwidth=1, bg="#e3f2fd")
        file_info_frame.pack(fill=tk.X, padx=5, pady=5)

        tk.Label(
            file_info_frame,
            text="已选择文件信息",
            font=("Arial", 9, "bold"),
            bg="#e3f2fd",
            fg="#1976d2"
        ).pack(anchor="w", padx=5, pady=2)

        self.file_info_text = tk.Text(
            file_info_frame,
            wrap=tk.WORD,
            width=40,
            height=3,
            font=("Consolas", 8),
            bg="#e3f2fd",
            relief=tk.FLAT,
            state=tk.DISABLED
        )
        self.file_info_text.pack(fill=tk.X, padx=5, pady=2)

        # 文件操作按钮
        file_btn_frame = tk.Frame(middle_frame, pady=8, bg="white")
        file_btn_frame.pack(fill=tk.X, padx=8)

        tk.Button(
            file_btn_frame,
            text="📄 选择文件",
            command=self.select_files,
            width=11,
            bg="#4CAF50",
            fg="white",
            font=("Arial", 9, "bold"),
            relief=tk.FLAT,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            file_btn_frame,
            text="📂 选择文件夹",
            command=self.select_folder,
            width=11,
            bg="#2196F3",
            fg="white",
            font=("Arial", 9, "bold"),
            relief=tk.FLAT,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            file_btn_frame,
            text="🗑 清空列表",
            command=self.clear_file_list,
            width=10,
            bg="#f44336",
            fg="white",
            font=("Arial", 9, "bold"),
            relief=tk.FLAT,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=2)

        # 文件列表（带滚动条）
        list_frame = tk.Frame(middle_frame, bg="white")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=5)

        list_scrollbar = tk.Scrollbar(list_frame)
        list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.file_listbox = tk.Listbox(
            list_frame,
            yscrollcommand=list_scrollbar.set,
            font=("Consolas", 9),
            selectmode=tk.SINGLE,
            bg="#fafafa",
            selectbackground="#2196F3",
            selectforeground="white",
            relief=tk.FLAT,
            borderwidth=1
        )
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_scrollbar.config(command=self.file_listbox.yview)

        # 绑定选择事件
        self.file_listbox.bind('<<ListboxSelect>>', self.on_file_select)

        # 错误统计区域
        stats_frame = tk.Frame(middle_frame, relief=tk.GROOVE, borderwidth=1, bg="white")
        stats_frame.pack(fill=tk.X, padx=8, pady=5)

        tk.Label(
            stats_frame,
            text="📊 错误统计",
            font=("Arial", 10, "bold"),
            fg="#d32f2f",
            bg="white"
        ).pack(anchor="w", padx=5, pady=5)

        self.stats_text = scrolledtext.ScrolledText(
            stats_frame,
            wrap=tk.WORD,
            width=40,
            height=8,
            font=("Consolas", 8),
            bg="#fff3e0",
            state=tk.DISABLED
        )
        self.stats_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 右侧区域：核查结果详情
        right_frame = tk.Frame(main_container, bg="#f0f0f0")
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 顶部操作按钮和多线程选项
        top_frame = tk.Frame(right_frame, pady=8, bg="#f0f0f0")
        top_frame.pack(side=tk.TOP, fill=tk.X)

        # 按钮区域
        btn_container = tk.Frame(top_frame, bg="#f0f0f0")
        btn_container.pack(side=tk.LEFT)

        tk.Button(
            btn_container,
            text="▶ 开始核查",
            command=self.start_validation,
            width=15,
            bg="#FF9800",
            fg="white",
            font=("Arial", 10, "bold"),
            relief=tk.FLAT,
            cursor="hand2",
            padx=10,
            pady=8
        ).pack(side=tk.LEFT, padx=5)
        # 保存按钮引用以便控制状态
        self.start_button = btn_container.winfo_children()[0]

        tk.Button(
            btn_container,
            text="🗑 清空结果",
            command=self.clear_results,
            width=15,
            bg="#9E9E9E",
            fg="white",
            font=("Arial", 10, "bold"),
            relief=tk.FLAT,
            cursor="hand2",
            padx=10,
            pady=8
        ).pack(side=tk.LEFT, padx=5)
        # 保存按钮引用以便控制状态
        self.clear_button = btn_container.winfo_children()[1]

        # 多线程选项区域
        mt_frame = tk.Frame(top_frame, relief=tk.RAISED, borderwidth=2, padx=12, pady=8, bg="white")
        mt_frame.pack(side=tk.LEFT, padx=20)

        tk.Checkbutton(
            mt_frame,
            text="⚡ 启用多线程",
            variable=self.use_multithreading,
            font=("Arial", 9, "bold"),
            fg="#1976D2",
            bg="white",
            activebackground="white",
            command=self.toggle_multithreading,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=5)

        tk.Label(
            mt_frame,
            text="线程数:",
            font=("Arial", 9),
            bg="white"
        ).pack(side=tk.LEFT, padx=(10, 5))

        self.thread_spinbox = tk.Spinbox(
            mt_frame,
            from_=1,
            to=16,
            textvariable=self.thread_count,
            width=5,
            font=("Arial", 9),
            state=tk.DISABLED
        )
        self.thread_spinbox.pack(side=tk.LEFT)

        # 进度条区域（优化布局）
        progress_container = tk.Frame(right_frame, relief=tk.RAISED, borderwidth=2, pady=10, padx=15, bg="white")
        progress_container.pack(side=tk.TOP, fill=tk.X, pady=(0, 8))

        tk.Label(
            progress_container,
            text="🔄 核查进度：",
            font=("Arial", 9, "bold"),
            fg="#1976D2",
            bg="white"
        ).pack(side=tk.LEFT, padx=5)

        self.progress_bar = ttk.Progressbar(
            progress_container,
            mode='determinate',
            length=350
        )
        self.progress_bar.pack(side=tk.LEFT, padx=8)

        self.progress_label = tk.Label(
            progress_container,
            text="0/0 (0%)",
            font=("Arial", 9, "bold"),
            fg="#FF5722",
            bg="white",
            width=15
        )
        self.progress_label.pack(side=tk.LEFT, padx=5)

        # 结果显示区域
        result_frame = tk.Frame(right_frame, bg="#f0f0f0", pady=5)
        result_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # 结果标题栏
        result_header = tk.Frame(result_frame, bg="#4CAF50", pady=8)
        result_header.pack(side=tk.TOP, fill=tk.X)

        tk.Label(
            result_header,
            text="📝 核查结果详情",
            font=("Arial", 10, "bold"),
            bg="#4CAF50",
            fg="white"
        ).pack(side=tk.LEFT, padx=10)

        # 带滚动条的文本框
        self.result_text = scrolledtext.ScrolledText(
            result_frame,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg="#f5f5f5",
            relief=tk.FLAT,
            borderwidth=0
        )
        self.result_text.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=5, padx=2)

    def select_all_checks(self):
        """全选所有核查项"""
        for var in self.validation_checks.values():
            var.set(True)

    def deselect_all_checks(self):
        """取消所有核查项"""
        for var in self.validation_checks.values():
            var.set(False)

    def toggle_multithreading(self):
        """切换多线程状态"""
        if self.use_multithreading.get():
            self.thread_spinbox.config(state=tk.NORMAL)
        else:
            self.thread_spinbox.config(state=tk.DISABLED)

    def select_files(self):
        """选择JSON文件（可多选）"""
        files = filedialog.askopenfilenames(
            title="选择JSON文件",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if files:
            self.selected_files = list(files)
            self.update_file_list()

    def select_folder(self):
        """选择文件夹并自动扫描所有JSON文件"""
        folder = filedialog.askdirectory(title="选择文件夹")
        if folder:
            # 扫描文件夹中的所有JSON文件
            json_files = list(Path(folder).rglob("*.json"))
            self.selected_files = [str(f) for f in json_files]
            self.update_file_list()

    def clear_file_list(self):
        """清空文件列表"""
        self.selected_files = []
        self.validation_stats = {}
        self.update_file_list()
        self.update_stats_display()

    def update_file_info_display(self):
        """更新已选择文件信息显示"""
        self.file_info_text.config(state=tk.NORMAL)
        self.file_info_text.delete(1.0, tk.END)

        if not self.selected_files:
            self.file_info_text.insert(tk.END, "暂未选择文件")
        else:
            total_count = len(self.selected_files)
            # 获取第一个文件的目录
            if total_count == 1:
                file_path = self.selected_files[0]
                file_name = os.path.basename(file_path)
                file_dir = os.path.dirname(file_path)
                self.file_info_text.insert(tk.END, f"文件: {file_name}\n")
                self.file_info_text.insert(tk.END, f"路径: {file_dir}\n")
            else:
                # 查找公共目录
                common_dir = os.path.dirname(self.selected_files[0])
                all_same_dir = all(os.path.dirname(f) == common_dir for f in self.selected_files)

                self.file_info_text.insert(tk.END, f"已选择 {total_count} 个文件\n")
                if all_same_dir:
                    self.file_info_text.insert(tk.END, f"目录: {common_dir}\n")
                else:
                    self.file_info_text.insert(tk.END, "文件来自多个目录\n")

        self.file_info_text.config(state=tk.DISABLED)

    def update_file_list(self):
        """更新文件列表显示"""
        self.file_listbox.delete(0, tk.END)
        if not self.selected_files:
            self.update_file_info_display()
            return

        for file_path in self.selected_files:
            file_name = os.path.basename(file_path)
            # 如果有统计数据，显示错误数量
            if file_name in self.validation_stats:
                stats = self.validation_stats[file_name]
                error_count = stats.get('total_errors', 0)
                if error_count > 0:
                    display_text = f"❌ {file_name} ({error_count} 错误)"
                else:
                    display_text = f"✓ {file_name}"
            else:
                display_text = f"○ {file_name}"

            self.file_listbox.insert(tk.END, display_text)

        # 更新文件信息显示
        self.update_file_info_display()

    def on_file_select(self, event):
        """文件列表选择事件"""
        selection = self.file_listbox.curselection()
        if not selection:
            return

        index = selection[0]
        if index >= len(self.selected_files):
            return

        file_path = self.selected_files[index]
        file_name = os.path.basename(file_path)

        # 更新文件信息显示 - 显示选中文件的详细信息
        self.file_info_text.config(state=tk.NORMAL)
        self.file_info_text.delete(1.0, tk.END)
        self.file_info_text.insert(tk.END, f"文件: {file_name}\n")
        self.file_info_text.insert(tk.END, f"路径: {os.path.dirname(file_path)}\n")

        # 如果有统计信息，也显示
        if file_name in self.validation_stats:
            stats = self.validation_stats[file_name]
            error_count = stats.get('total_errors', 0)
            self.file_info_text.insert(tk.END, f"错误数: {error_count}\n")

        self.file_info_text.config(state=tk.DISABLED)

        # 更新错误统计显示
        if file_name in self.validation_stats:
            self.update_stats_display(file_name)
        else:
            self.update_stats_display()

    def update_stats_display(self, file_name=None):
        """更新错误统计显示"""
        self.stats_text.config(state=tk.NORMAL)
        self.stats_text.delete(1.0, tk.END)

        if file_name and file_name in self.validation_stats:
            # 显示单个文件的统计
            stats = self.validation_stats[file_name]
            total_errors = stats.get('total_errors', 0)
            error_types = stats.get('error_types', {})

            self.stats_text.insert(tk.END, f"【单文件错误统计】\n")
            self.stats_text.insert(tk.END, f"{'='*40}\n")
            self.stats_text.insert(tk.END, f"文件名: {file_name}\n")
            self.stats_text.insert(tk.END, f"总错误数: {total_errors}\n")
            self.stats_text.insert(tk.END, f"{'='*40}\n\n")

            if error_types:
                self.stats_text.insert(tk.END, "错误类型详情:\n")
                self.stats_text.insert(tk.END, f"{'-'*40}\n")
                # 按错误数量排序
                sorted_errors = sorted(error_types.items(), key=lambda x: x[1], reverse=True)
                for idx, (error_type, count) in enumerate(sorted_errors, 1):
                    percentage = (count / total_errors * 100) if total_errors > 0 else 0
                    self.stats_text.insert(tk.END, f"{idx}. {error_type}\n")
                    self.stats_text.insert(tk.END, f"   数量: {count}  占比: {percentage:.1f}%\n")
                    # 添加简单的可视化条形图
                    bar_length = int(percentage / 5)  # 每5%一个字符
                    bar = "█" * bar_length
                    self.stats_text.insert(tk.END, f"   {bar}\n\n")
            else:
                self.stats_text.insert(tk.END, "✓ 此文件无错误！\n")
        elif self.validation_stats:
            # 按文件显示所有文件的错误统计
            total_files = len(self.validation_stats)
            total_errors = sum(s.get('total_errors', 0) for s in self.validation_stats.values())
            files_with_errors = sum(1 for s in self.validation_stats.values() if s.get('total_errors', 0) > 0)

            self.stats_text.insert(tk.END, f"汇总统计\n")
            self.stats_text.insert(tk.END, f"{'='*40}\n")
            self.stats_text.insert(tk.END, f"总文件数: {total_files}\n")
            self.stats_text.insert(tk.END, f"有错误的文件: {files_with_errors}\n")
            self.stats_text.insert(tk.END, f"总错误数: {total_errors}\n\n")

            # 按文件列出错误类型分布
            self.stats_text.insert(tk.END, f"{'='*40}\n")
            self.stats_text.insert(tk.END, "各文件错误详情:\n\n")

            # 按错误数量排序文件
            sorted_files = sorted(
                self.validation_stats.items(),
                key=lambda x: x[1].get('total_errors', 0),
                reverse=True
            )

            for file_name, stats in sorted_files:
                total_errors = stats.get('total_errors', 0)
                error_types = stats.get('error_types', {})

                if total_errors > 0:
                    self.stats_text.insert(tk.END, f"❌ {file_name} ({total_errors} 错误)\n")
                    for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
                        self.stats_text.insert(tk.END, f"    • {error_type}: {count}\n")
                    self.stats_text.insert(tk.END, "\n")
                else:
                    self.stats_text.insert(tk.END, f"✓ {file_name}\n\n")
        else:
            self.stats_text.insert(tk.END, "暂无统计数据\n")
            self.stats_text.insert(tk.END, "请先进行核查操作")

        self.stats_text.config(state=tk.DISABLED)

    def clear_results(self):
        """清空结果显示"""
        self.result_text.delete(1.0, tk.END)
        self.validation_stats = {}
        self.update_file_list()
        self.update_stats_display()

    def log(self, message: str):
        """向结果文本框插入日志信息（线程安全）"""
        def _insert():
            self.result_text.insert(tk.END, message)
            self.result_text.see(tk.END)

        # 如果在主线程中，直接执行；否则通过after调度到主线程
        if threading.current_thread() is threading.main_thread():
            _insert()
        else:
            self.root.after(0, _insert)

    def update_progress(self, current, total):
        """更新进度条和进度标签（线程安全）"""
        def _update():
            if total > 0:
                percentage = (current / total) * 100
                self.progress_bar['value'] = percentage
                self.progress_label.config(text=f"{current}/{total} ({percentage:.1f}%)")
            else:
                self.progress_bar['value'] = 0
                self.progress_label.config(text="0/0 (0%)")

        # 如果在主线程中，直接执行；否则通过after调度到主线程
        if threading.current_thread() is threading.main_thread():
            _update()
        else:
            self.root.after(0, _update)

    def reset_progress(self):
        """重置进度条"""
        self.progress_bar['value'] = 0
        self.progress_label.config(text="0/0 (0%)")
        self.files_validated = 0
        self.total_files_to_validate = 0

    def start_validation(self):
        """开始验证所有选择的JSON文件"""
        if not self.selected_files:
            messagebox.showwarning("警告", "请先选择JSON文件或文件夹！")
            return

        if self.is_validating:
            messagebox.showwarning("警告", "正在核查中，请稍候...")
            return

        # 清空结果显示区域和统计数据
        self.result_text.delete(1.0, tk.END)
        self.validation_stats = {}

        # 初始化进度
        self.total_files_to_validate = len(self.selected_files)
        self.files_validated = 0
        self.reset_progress()

        # 标记正在验证
        self.is_validating = True

        # 禁用按钮防止重复点击
        self.start_button.config(state=tk.DISABLED, bg="#BDBDBD")
        self.clear_button.config(state=tk.DISABLED)

        # 在后台线程中执行验证，避免界面冻结
        validation_thread = threading.Thread(target=self._run_validation, daemon=True)
        validation_thread.start()

    def _run_validation(self):
        """在后台线程中运行验证"""
        try:
            # 记录开始时间
            start_time = time.time()

            # 根据是否启用多线程选择不同的验证方式
            if self.use_multithreading.get() and self.total_files_to_validate > 1:
                # 使用多线程验证
                thread_num = self.thread_count.get()
                self.log(f"======= 开始核查（多线程模式，{thread_num}个线程）=======\n")
                self.log(f"待核查文件数: {self.total_files_to_validate}\n\n")
                self.validate_with_multithreading()
            else:
                # 单线程验证
                self.log(f"======= 开始核查（单线程模式）=======\n")
                self.log(f"待核查文件数: {self.total_files_to_validate}\n\n")
                self.validate_single_threaded()

            # 计算耗时
            elapsed_time = time.time() - start_time

            # 使用线程安全的方式更新GUI和显示耗时
            self.root.after(0, lambda: self._finish_validation(elapsed_time))
        except Exception as e:
            self.root.after(0, lambda: self.log(f"验证过程发生错误: {str(e)}\n"))
            self.root.after(0, lambda: self._finish_validation(0))

    def _finish_validation(self, elapsed_time=0):
        """完成验证后的GUI更新（在主线程中执行）"""
        # 更新文件列表显示和统计
        self.update_file_list()
        self.update_stats_display()

        # 核查完毕，显示耗时
        if elapsed_time > 0:
            self.log(f"======= 核查完毕（耗时: {elapsed_time:.2f}秒）=======\n")
        else:
            self.log("======= 核查完毕 =======\n")

        # 标记验证完成
        self.is_validating = False

        # 恢复按钮状态
        self.start_button.config(state=tk.NORMAL, bg="#FF9800")
        self.clear_button.config(state=tk.NORMAL)

    def validate_single_threaded(self):
        """单线程验证所有文件"""
        for idx, file_path in enumerate(self.selected_files, 1):
            self.validate_coco_file(file_path)
            self.files_validated = idx
            self.update_progress(self.files_validated, self.total_files_to_validate)

    def validate_with_multithreading(self):
        """使用多线程验证所有文件"""
        thread_num = self.thread_count.get()

        def validate_file_wrapper(file_path):
            """线程包装函数"""
            try:
                # 在子线程中执行验证
                self.validate_coco_file(file_path)
                return True
            except Exception as e:
                self.log(f"验证 {os.path.basename(file_path)} 时出错: {str(e)}\n")
                return False

        # 使用线程池执行
        with ThreadPoolExecutor(max_workers=thread_num) as executor:
            # 提交所有任务
            future_to_file = {executor.submit(validate_file_wrapper, file_path): file_path
                             for file_path in self.selected_files}

            # 处理完成的任务
            for future in as_completed(future_to_file):
                try:
                    future.result()
                except Exception as e:
                    file_path = future_to_file[future]
                    self.log(f"处理 {os.path.basename(file_path)} 时发生异常: {str(e)}\n")
                finally:
                    # 使用线程锁保护进度更新
                    with self.validation_lock:
                        self.files_validated += 1
                        current = self.files_validated
                    # 更新进度
                    self.update_progress(current, self.total_files_to_validate)

    def validate_coco_file(self, file_path: str):
        """验证单个COCO JSON文件（线程安全）"""
        file_name = os.path.basename(file_path)
        errors = []

        # 1. 文件读取 (JSON格式检查)
        if self.validation_checks['json_format'].get():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except json.JSONDecodeError as e:
                self.log(f"[{file_name}]... 发现错误：\n")
                self.log(f"  - 错误类型：JSON格式错误\n")
                self.log(f"    详情：{str(e)}\n\n")
                # 保存错误统计
                with self.validation_lock:
                    self.validation_stats[file_name] = {
                        'total_errors': 1,
                        'error_types': {'JSON格式错误': 1}
                    }
                return
            except Exception as e:
                self.log(f"[{file_name}]... 发现错误：\n")
                self.log(f"  - 错误类型：文件读取错误\n")
                self.log(f"    详情：{str(e)}\n\n")
                # 保存错误统计
                with self.validation_lock:
                    self.validation_stats[file_name] = {
                        'total_errors': 1,
                        'error_types': {'文件读取错误': 1}
                    }
                return
        else:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except:
                return

        # 2. 顶级结构检查
        if self.validation_checks['top_level_keys'].get():
            required_keys = ["images", "annotations", "categories"]
            for key in required_keys:
                if key not in data:
                    errors.append({
                        "type": "缺少顶级键",
                        "detail": f"文件缺少 '{key}' 键。"
                    })
                elif not isinstance(data.get(key), list):
                    errors.append({
                        "type": "顶级键类型错误",
                        "detail": f"'{key}' 的值必须是列表（List）类型。"
                    })

        # 如果缺少必要的顶级键，直接返回
        if errors:
            self.report_errors(file_name, errors)
            return

        images = data.get("images", [])
        annotations = data.get("annotations", [])
        categories = data.get("categories", [])

        # 3. ID索引
        image_ids = set()
        image_id_duplicates = []

        if self.validation_checks['image_id_unique'].get():
            for img in images:
                img_id = img.get("id")
                if img_id in image_ids:
                    image_id_duplicates.append(img_id)
                else:
                    image_ids.add(img_id)

            if image_id_duplicates:
                errors.append({
                    "type": "Image ID重复",
                    "detail": f"以下 image ID 重复: {image_id_duplicates}"
                })
        else:
            # 即使不检查，也需要收集ID用于后续验证
            for img in images:
                img_id = img.get("id")
                if img_id is not None:
                    image_ids.add(img_id)

        category_ids = set()
        category_id_duplicates = []

        if self.validation_checks['category_id_unique'].get():
            for cat in categories:
                cat_id = cat.get("id")
                if cat_id in category_ids:
                    category_id_duplicates.append(cat_id)
                else:
                    category_ids.add(cat_id)

            if category_id_duplicates:
                errors.append({
                    "type": "Category ID重复",
                    "detail": f"以下 category ID 重复: {category_id_duplicates}"
                })
        else:
            # 即使不检查，也需要收集ID用于后续验证
            for cat in categories:
                cat_id = cat.get("id")
                if cat_id is not None:
                    category_ids.add(cat_id)

        # 创建image_id到图像信息的映射
        image_info_map = {}
        for img in images:
            if "id" in img:
                image_info_map[img["id"]] = img

        # 4. images项检查
        if self.validation_checks['image_required_keys'].get():
            for idx, img in enumerate(images):
                required_img_keys = ["id", "file_name", "width", "height"]
                for key in required_img_keys:
                    if key not in img:
                        errors.append({
                            "type": "Image缺少必需键",
                            "detail": f"Images 列表第 {idx} 项缺少 '{key}' 键。"
                        })

        # 检查width和height
        if self.validation_checks['image_dimensions'].get():
            for idx, img in enumerate(images):
                if "width" in img:
                    if not isinstance(img["width"], int) or img["width"] <= 0:
                        errors.append({
                            "type": "Image width无效",
                            "detail": f"Image ID {img.get('id')} 的 width 必须为正整数，当前值: {img['width']}"
                        })

                if "height" in img:
                    if not isinstance(img["height"], int) or img["height"] <= 0:
                        errors.append({
                            "type": "Image height无效",
                            "detail": f"Image ID {img.get('id')} 的 height 必须为正整数，当前值: {img['height']}"
                        })

        # 5. categories项检查
        if self.validation_checks['category_required_keys'].get():
            for idx, cat in enumerate(categories):
                required_cat_keys = ["id", "name", "supercategory"]
                for key in required_cat_keys:
                    if key not in cat:
                        errors.append({
                            "type": "Category缺少必需键",
                            "detail": f"Categories 列表第 {idx} 项缺少 '{key}' 键。"
                        })

        # 6. annotations项检查（核心）
        annotation_ids = set()
        for idx, ann in enumerate(annotations):
            # 检查必需键
            if self.validation_checks['annotation_required_keys'].get():
                required_ann_keys = ["id", "image_id", "category_id", "bbox", "segmentation", "area", "iscrowd"]
                for key in required_ann_keys:
                    if key not in ann:
                        errors.append({
                            "type": "Annotation缺少必需键",
                            "detail": f"Annotation 第 {idx} 项缺少 '{key}' 键。"
                        })
                        continue

            ann_id = ann.get("id")

            # 检查annotation ID唯一性
            if self.validation_checks['annotation_id_unique'].get():
                if ann_id in annotation_ids:
                    errors.append({
                        "type": "Annotation ID重复",
                        "detail": f"Annotation ID {ann_id} 重复出现。"
                    })
                else:
                    annotation_ids.add(ann_id)
            else:
                annotation_ids.add(ann_id)

            # 检查image_id是否存在
            if self.validation_checks['image_id_exists'].get():
                image_id = ann.get("image_id")
                if image_id not in image_ids:
                    errors.append({
                        "type": "image_id未找到",
                        "detail": f"Annotation ID {ann_id} 的 image_id {image_id} 在 'images' 列表中不存在。"
                    })

            # 检查category_id是否存在
            if self.validation_checks['category_id_exists'].get():
                category_id = ann.get("category_id")
                if category_id not in category_ids:
                    errors.append({
                        "type": "category_id未找到",
                        "detail": f"Annotation ID {ann_id} 的 category_id {category_id} 在 'categories' 列表中不存在。"
                    })

            # 检查iscrowd
            if self.validation_checks['iscrowd_valid'].get():
                iscrowd = ann.get("iscrowd")
                if iscrowd not in [0, 1]:
                    errors.append({
                        "type": "iscrowd值无效",
                        "detail": f"Annotation ID {ann_id} 的 iscrowd 值必须为 0 或 1，当前值: {iscrowd}"
                    })

            # 检查bbox格式
            if self.validation_checks['bbox_format'].get():
                bbox = ann.get("bbox")
                if not isinstance(bbox, list) or len(bbox) != 4:
                    errors.append({
                        "type": "BBox格式错误",
                        "detail": f"Annotation ID {ann_id} 的 bbox 必须是包含4个数字的列表 [x, y, width, height]。"
                    })
                else:
                    # BBox边界检查
                    if self.validation_checks['bbox_bounds'].get():
                        try:
                            x, y, w, h = bbox

                            # 基本检查
                            if x < 0:
                                errors.append({
                                    "type": "BBox x坐标无效",
                                    "detail": f"Annotation ID {ann_id} 的 BBox x坐标 {x} 小于0。"
                                })

                            if y < 0:
                                errors.append({
                                    "type": "BBox y坐标无效",
                                    "detail": f"Annotation ID {ann_id} 的 BBox y坐标 {y} 小于0。"
                                })

                            if w <= 0:
                                errors.append({
                                    "type": "BBox width无效",
                                    "detail": f"Annotation ID {ann_id} 的 BBox width {w} 必须大于0。"
                                })

                            if h <= 0:
                                errors.append({
                                    "type": "BBox height无效",
                                    "detail": f"Annotation ID {ann_id} 的 BBox height {h} 必须大于0。"
                                })

                            # 边界检查 - 需要获取对应图像的尺寸
                            image_id = ann.get("image_id")
                            if image_id in image_info_map:
                                img_info = image_info_map[image_id]
                                img_width = img_info.get("width")
                                img_height = img_info.get("height")

                                if img_width is not None and img_height is not None:
                                    if x + w > img_width:
                                        errors.append({
                                            "type": "BBox越界",
                                            "detail": f"Annotation ID {ann_id} 的 BBox [{x}, {y}, {w}, {h}] 超出了图像 {image_id} 的宽度边界 (图像宽度: {img_width})。"
                                        })

                                    if y + h > img_height:
                                        errors.append({
                                            "type": "BBox越界",
                                            "detail": f"Annotation ID {ann_id} 的 BBox [{x}, {y}, {w}, {h}] 超出了图像 {image_id} 的高度边界 (图像高度: {img_height})。"
                                        })

                        except (TypeError, ValueError) as e:
                            errors.append({
                                "type": "BBox数值类型错误",
                                "detail": f"Annotation ID {ann_id} 的 BBox 包含非数字值。"
                            })

            # 检查area
            if self.validation_checks['area_valid'].get():
                area = ann.get("area")
                if not isinstance(area, (int, float)):
                    errors.append({
                        "type": "Area类型错误",
                        "detail": f"Annotation ID {ann_id} 的 area 必须是数字类型。"
                    })
                elif area <= 0:
                    errors.append({
                        "type": "Area值异常",
                        "detail": f"Annotation ID {ann_id} 的 area {area} 应该大于0。"
                    })

            # 检查segmentation格式
            if self.validation_checks['segmentation_format'].get():
                segmentation = ann.get("segmentation")
                if segmentation is not None:
                    # 检查是否为无效的 {"counts": null, "size": null} 格式
                    if isinstance(segmentation, dict):
                        # RLE格式应该有有效的counts和size
                        counts = segmentation.get("counts")
                        size = segmentation.get("size")

                        if counts is None and size is None:
                            errors.append({
                                "type": "Segmentation格式错误",
                                "detail": f"Annotation ID {ann_id} 的 segmentation 为无效的 RLE 格式 {{'counts': null, 'size': null}}。应该是包含坐标点的列表，如 [[x1,y1,x2,y2,...]]。"
                            })
                        elif counts is None or size is None:
                            errors.append({
                                "type": "Segmentation格式错误",
                                "detail": f"Annotation ID {ann_id} 的 segmentation RLE 格式不完整，counts 或 size 缺失。"
                            })
                    elif isinstance(segmentation, list):
                        # polygon格式，应该是list of lists
                        if len(segmentation) == 0:
                            errors.append({
                                "type": "Segmentation格式错误",
                                "detail": f"Annotation ID {ann_id} 的 segmentation 为空列表。"
                            })
                        else:
                            # 检查每个polygon
                            for poly_idx, poly in enumerate(segmentation):
                                if not isinstance(poly, list):
                                    errors.append({
                                        "type": "Segmentation格式错误",
                                        "detail": f"Annotation ID {ann_id} 的 segmentation 第 {poly_idx} 个多边形不是列表类型。"
                                    })
                                elif len(poly) < 6:  # 至少需要3个点（6个坐标值）
                                    errors.append({
                                        "type": "Segmentation格式错误",
                                        "detail": f"Annotation ID {ann_id} 的 segmentation 第 {poly_idx} 个多边形点数不足（需至少3个点，即6个坐标值）。"
                                    })
                                elif len(poly) % 2 != 0:
                                    errors.append({
                                        "type": "Segmentation格式错误",
                                        "detail": f"Annotation ID {ann_id} 的 segmentation 第 {poly_idx} 个多边形坐标数量必须是偶数。"
                                    })
                    else:
                        errors.append({
                            "type": "Segmentation格式错误",
                            "detail": f"Annotation ID {ann_id} 的 segmentation 必须是列表（polygon）或字典（RLE）类型。"
                        })

            # 检查矩形标注segmentation是否为8个值
            if self.validation_checks['segmentation_rectangle'].get():
                segmentation = ann.get("segmentation")
                if segmentation is not None and isinstance(segmentation, list):
                    # 对于矩形标注，segmentation应该是包含一个polygon的列表
                    # 该polygon应该有8个值（4个顶点的x,y坐标）
                    for poly_idx, poly in enumerate(segmentation):
                        if isinstance(poly, list):
                            if len(poly) != 8:
                                errors.append({
                                    "type": "矩形标注坐标数量错误",
                                    "detail": f"Annotation ID {ann_id} 的 segmentation 第 {poly_idx} 个多边形应包含8个值（矩形4个顶点坐标），当前有 {len(poly)} 个值。"
                                })

        # 输出结果和收集统计（线程安全）
        if errors:
            self.report_errors(file_name, errors)
            # 收集统计信息
            error_types = {}
            for error in errors:
                error_type = error['type']
                error_types[error_type] = error_types.get(error_type, 0) + 1

            # 使用线程锁保护共享数据
            with self.validation_lock:
                self.validation_stats[file_name] = {
                    'total_errors': len(errors),
                    'error_types': error_types
                }
        else:
            self.log(f"[{file_name}]... 验证通过。\n\n")
            # 使用线程锁保护共享数据
            with self.validation_lock:
                self.validation_stats[file_name] = {
                    'total_errors': 0,
                    'error_types': {}
                }

    def report_errors(self, file_name: str, errors: List[Dict]):
        """报告错误信息"""
        self.log(f"[{file_name}]... 发现错误：\n")
        for error in errors:
            self.log(f"  - 错误类型：{error['type']}\n")
            self.log(f"    详情：{error['detail']}\n")
        self.log("\n")


def main():
    """主函数"""
    root = tk.Tk()
    app = COCOValidatorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
