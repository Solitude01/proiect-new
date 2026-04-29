#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
COCO数据集验证GUI工具
用于验证COCO格式的JSON标注文件是否符合标准
支持跨目录重复检测和一键修复去重
"""

import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox, ttk
import json
import os
import shutil
import hashlib
import math
from pathlib import Path
from typing import List, Set, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import queue
import time
from collections import defaultdict
from datetime import datetime


class COCOValidatorGUI:
    """COCO数据集验证器GUI应用"""

    def __init__(self, root):
        self.root = root
        self.root.title("COCO数据集验证工具")
        self.root.geometry("1400x850")

        # 存储选择的文件路径
        self.selected_files = []

        # 目录模式相关
        self.directory_mode = tk.BooleanVar(value=True)
        self.directory_structure = {}  # {subdir_name: [json_paths]}
        self.cross_dir_results = {}  # 跨目录检查结果
        self._listbox_file_indices = []  # listbox索引 -> (dir_name, file_index) 映射

        # 存储验证结果统计
        self.validation_stats = {}  # {file_path: {"total_errors": int, "error_types": {type: count}}}

        # 多线程相关
        self.use_multithreading = tk.BooleanVar(value=True)
        self.thread_count = tk.IntVar(value=4)
        self.validation_lock = threading.Lock()
        self.is_validating = False

        # 进度跟踪
        self.total_files_to_validate = 0
        self.files_validated = 0

        # 修复相关
        self.pending_fixes = []  # 待修复操作列表
        self.backup_dir = None  # 备份目录

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
            'cross_dir_duplicate_images': tk.BooleanVar(value=True),  # 跨目录图片名重复检查
            'cross_dir_duplicate_annotations': tk.BooleanVar(value=True),  # 跨目录标注内容重复检查
            'cross_json_duplicate_annotations': tk.BooleanVar(value=True),  # 跨JSON文件标注重复检查
            'json_image_mismatch': tk.BooleanVar(value=True),  # JSON标注与图片文件对应检查
        }

        # 创建GUI组件
        self.create_widgets()

        # 默认启用目录模式，显示跨目录检查项
        self.toggle_directory_mode()

    def create_widgets(self):
        """创建GUI界面组件"""
        # 设置整体样式
        style = ttk.Style()
        style.theme_use('clam')

        # 主容器：左中右三栏布局
        main_container = tk.Frame(self.root, bg="#f0f0f0")
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 左侧区域：核查选项
        left_frame = tk.Frame(main_container, relief=tk.RAISED, borderwidth=2, width=240, bg="white")
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

        # 目录模式切换
        dir_mode_frame = tk.Frame(left_frame, pady=8, bg="white")
        dir_mode_frame.pack(fill=tk.X, padx=8)

        tk.Checkbutton(
            dir_mode_frame,
            text="📂 目录模式",
            variable=self.directory_mode,
            font=("Arial", 9, "bold"),
            fg="#1976D2",
            bg="white",
            activebackground="white",
            command=self.toggle_directory_mode,
            cursor="hand2"
        ).pack(anchor="w")

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

        # 跨目录检查项（目录模式下显示）
        self.cross_dir_check_widgets = {}
        cross_dir_labels = {
            'cross_dir_duplicate_images': '🔗 跨目录图片名重复',
            'cross_dir_duplicate_annotations': '🔗 跨目录标注内容重复',
            'cross_json_duplicate_annotations': '🔗 跨JSON文件标注重复',
            'json_image_mismatch': '🔗 JSON标注与图片对应检查',
        }

        for key, label in cross_dir_labels.items():
            cb = tk.Checkbutton(
                checks_frame,
                text=label,
                variable=self.validation_checks[key],
                font=("Arial", 9, "bold"),
                fg="#E91E63",
                anchor="w",
                bg="white",
                activebackground="#fce4ec",
                cursor="hand2"
            )
            cb.pack(fill=tk.X, pady=3, padx=2)
            self.cross_dir_check_widgets[key] = cb
            # 默认隐藏，目录模式下显示
            cb.pack_forget()

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

        # 导出按钮
        self.export_button = tk.Button(
            btn_container,
            text="📥 导出日志",
            command=self.export_log,
            width=15,
            bg="#00BCD4",
            fg="white",
            font=("Arial", 10, "bold"),
            relief=tk.FLAT,
            cursor="hand2",
            padx=10,
            pady=8
        )
        self.export_button.pack(side=tk.LEFT, padx=5)

        # 修复按钮
        self.fix_button = tk.Button(
            btn_container,
            text="🔧 一键修复去重",
            command=self.start_fix,
            width=15,
            bg="#9C27B0",
            fg="white",
            font=("Arial", 10, "bold"),
            relief=tk.FLAT,
            cursor="hand2",
            padx=10,
            pady=8,
            state=tk.DISABLED
        )
        self.fix_button.pack(side=tk.LEFT, padx=5)

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

        tk.Button(
            result_header,
            text="📋 展开日志",
            command=self.show_full_log,
            width=10,
            bg="#607D8B",
            fg="white",
            font=("Arial", 9, "bold"),
            relief=tk.FLAT,
            cursor="hand2"
        ).pack(side=tk.RIGHT, padx=10)

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

    def toggle_directory_mode(self):
        """切换目录模式"""
        is_dir_mode = self.directory_mode.get()
        for widget in self.cross_dir_check_widgets.values():
            if is_dir_mode:
                widget.pack(fill=tk.X, pady=3, padx=2)
            else:
                widget.pack_forget()

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
            self.directory_structure = {}
            self.update_file_list()

    def select_folder(self):
        """选择文件夹并自动扫描所有JSON文件"""
        folder = filedialog.askdirectory(title="选择文件夹")
        if folder:
            if self.directory_mode.get():
                # 目录模式：按子目录分组
                self._scan_directory_structure(folder)
            else:
                # 普通模式：扫描所有JSON文件
                json_files = list(Path(folder).rglob("*.json"))
                self.selected_files = [str(f) for f in json_files]
                self.directory_structure = {}
            self.update_file_list()

    def _scan_directory_structure(self, folder: str):
        """扫描目录结构，递归查找所有JSON文件并按父目录分组"""
        self.directory_structure = {}
        folder_path = Path(folder)

        try:
            # 递归查找所有JSON文件
            json_files = list(folder_path.rglob("*.json"))

            if not json_files:
                messagebox.showinfo("提示", f"在 {folder} 中未找到 JSON 文件")
                self.selected_files = []
                return

            # 按父目录分组（使用相对于根目录的路径）
            for json_file in json_files:
                rel_parent = json_file.parent.relative_to(folder_path)
                dir_key = str(rel_parent) if str(rel_parent) != '.' else 'root'
                if dir_key not in self.directory_structure:
                    self.directory_structure[dir_key] = []
                self.directory_structure[dir_key].append(str(json_file))

        except PermissionError:
            messagebox.showerror("错误", f"无法访问目录: {folder}")
            self.selected_files = []
            return
        except Exception as e:
            messagebox.showerror("错误", f"扫描目录时出错: {str(e)}")
            self.selected_files = []
            return

        # 扁平化所有文件
        self.selected_files = []
        for files in self.directory_structure.values():
            self.selected_files.extend(files)

    def clear_file_list(self):
        """清空文件列表"""
        self.selected_files = []
        self.directory_structure = {}
        self.validation_stats = {}
        self.cross_dir_results = {}
        self.pending_fixes = []
        self._listbox_file_indices = []
        self.update_file_list()
        self.update_stats_display()
        self.fix_button.config(state=tk.DISABLED)

    def update_file_info_display(self):
        """更新已选择文件信息显示"""
        self.file_info_text.config(state=tk.NORMAL)
        self.file_info_text.delete(1.0, tk.END)

        if not self.selected_files:
            self.file_info_text.insert(tk.END, "暂未选择文件")
        else:
            total_count = len(self.selected_files)

            if self.directory_mode.get() and self.directory_structure:
                self.file_info_text.insert(tk.END, f"目录模式：{len(self.directory_structure)} 个子目录\n")
                self.file_info_text.insert(tk.END, f"共 {total_count} 个JSON文件\n")
                for dir_name, files in self.directory_structure.items():
                    self.file_info_text.insert(tk.END, f"  📁 {dir_name}/: {len(files)} 个文件\n")
            elif total_count == 1:
                file_path = self.selected_files[0]
                file_name = os.path.basename(file_path)
                file_dir = os.path.dirname(file_path)
                self.file_info_text.insert(tk.END, f"文件: {file_name}\n")
                self.file_info_text.insert(tk.END, f"路径: {file_dir}\n")
            else:
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

        # 重置索引映射
        self._listbox_file_indices = []

        if self.directory_mode.get() and self.directory_structure:
            # 目录模式：按目录分组显示
            for dir_name, files in self.directory_structure.items():
                self.file_listbox.insert(tk.END, f"📁 {dir_name}/ ({len(files)} 个文件)")
                for file_path in files:
                    # 记录索引映射
                    self._listbox_file_indices.append(file_path)

                    # 使用全路径查找验证统计
                    if file_path in self.validation_stats:
                        stats = self.validation_stats[file_path]
                        error_count = stats.get('total_errors', 0)
                        file_name = os.path.basename(file_path)
                        if error_count > 0:
                            display_text = f"   ❌ {file_name} ({error_count} 错误)"
                        else:
                            display_text = f"   ✓ {file_name}"
                    else:
                        file_name = os.path.basename(file_path)
                        display_text = f"   ○ {file_name}"
                    self.file_listbox.insert(tk.END, display_text)
        else:
            # 普通模式
            for file_path in self.selected_files:
                file_name = os.path.basename(file_path)
                if file_path in self.validation_stats:
                    stats = self.validation_stats[file_path]
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

        # 根据模式获取正确的文件路径
        if self.directory_mode.get() and self._listbox_file_indices:
            # 目录模式：使用索引映射（需要减去目录标题行的数量）
            # 计算到当前index为止有多少个目录标题
            headers_before = 0
            for i in range(index):
                item_text = self.file_listbox.get(i)
                if item_text.startswith("📁 "):
                    headers_before += 1

            file_index = index - headers_before
            if file_index < len(self._listbox_file_indices):
                file_path = self._listbox_file_indices[file_index]
            else:
                return
        else:
            # 普通模式
            if index >= len(self.selected_files):
                return
            file_path = self.selected_files[index]

        file_name = os.path.basename(file_path)

        # 更新文件信息显示
        self.file_info_text.config(state=tk.NORMAL)
        self.file_info_text.delete(1.0, tk.END)
        self.file_info_text.insert(tk.END, f"文件: {file_name}\n")
        self.file_info_text.insert(tk.END, f"路径: {os.path.dirname(file_path)}\n")

        if file_path in self.validation_stats:
            stats = self.validation_stats[file_path]
            error_count = stats.get('total_errors', 0)
            self.file_info_text.insert(tk.END, f"错误数: {error_count}\n")

        self.file_info_text.config(state=tk.DISABLED)

        if file_path in self.validation_stats:
            self.update_stats_display(file_path)
        else:
            self.update_stats_display()

    def update_stats_display(self, file_path=None):
        """更新错误统计显示"""
        self.stats_text.config(state=tk.NORMAL)
        self.stats_text.delete(1.0, tk.END)

        if file_path and file_path in self.validation_stats:
            stats = self.validation_stats[file_path]
            total_errors = stats.get('total_errors', 0)
            error_types = stats.get('error_types', {})
            file_name = os.path.basename(file_path)

            self.stats_text.insert(tk.END, f"【单文件错误统计】\n")
            self.stats_text.insert(tk.END, f"{'='*40}\n")
            self.stats_text.insert(tk.END, f"文件名: {file_name}\n")
            self.stats_text.insert(tk.END, f"路径: {file_path}\n")
            self.stats_text.insert(tk.END, f"总错误数: {total_errors}\n")
            self.stats_text.insert(tk.END, f"{'='*40}\n\n")

            if error_types:
                self.stats_text.insert(tk.END, "错误类型详情:\n")
                self.stats_text.insert(tk.END, f"{'-'*40}\n")
                sorted_errors = sorted(error_types.items(), key=lambda x: x[1], reverse=True)
                for idx, (error_type, count) in enumerate(sorted_errors, 1):
                    percentage = (count / total_errors * 100) if total_errors > 0 else 0
                    self.stats_text.insert(tk.END, f"{idx}. {error_type}\n")
                    self.stats_text.insert(tk.END, f"   数量: {count}  占比: {percentage:.1f}%\n")
                    bar_length = int(percentage / 5)
                    bar = "█" * bar_length
                    self.stats_text.insert(tk.END, f"   {bar}\n\n")
            else:
                self.stats_text.insert(tk.END, "✓ 此文件无错误！\n")
        elif self.validation_stats:
            total_files = len(self.validation_stats)
            total_errors = sum(s.get('total_errors', 0) for s in self.validation_stats.values())
            files_with_errors = sum(1 for s in self.validation_stats.values() if s.get('total_errors', 0) > 0)

            self.stats_text.insert(tk.END, f"汇总统计\n")
            self.stats_text.insert(tk.END, f"{'='*40}\n")
            self.stats_text.insert(tk.END, f"总文件数: {total_files}\n")
            self.stats_text.insert(tk.END, f"有错误的文件: {files_with_errors}\n")
            self.stats_text.insert(tk.END, f"总错误数: {total_errors}\n\n")

            self.stats_text.insert(tk.END, f"{'='*40}\n")
            self.stats_text.insert(tk.END, "各文件错误详情:\n\n")

            sorted_files = sorted(
                self.validation_stats.items(),
                key=lambda x: x[1].get('total_errors', 0),
                reverse=True
            )

            for fpath, stats in sorted_files:
                total_errors = stats.get('total_errors', 0)
                error_types = stats.get('error_types', {})
                fname = os.path.basename(fpath)

                if total_errors > 0:
                    self.stats_text.insert(tk.END, f"❌ {fname} ({total_errors} 错误)\n")
                    for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
                        self.stats_text.insert(tk.END, f"    • {error_type}: {count}\n")
                    self.stats_text.insert(tk.END, "\n")
                else:
                    self.stats_text.insert(tk.END, f"✓ {fname}\n\n")

            # 显示跨目录检查结果
            if self.cross_dir_results:
                self.stats_text.insert(tk.END, f"\n{'='*40}\n")
                self.stats_text.insert(tk.END, "跨目录检查结果:\n\n")

                if 'duplicate_images' in self.cross_dir_results:
                    dup_images = self.cross_dir_results['duplicate_images']
                    if dup_images:
                        self.stats_text.insert(tk.END, f"⚠️ 发现 {len(dup_images)} 个重复图片名:\n")
                        for img_name, dirs in list(dup_images.items())[:10]:
                            self.stats_text.insert(tk.END, f"  🖼️  {img_name}\n")
                            self.stats_text.insert(tk.END, f"     存在于: {', '.join(dirs)}\n")
                        if len(dup_images) > 10:
                            self.stats_text.insert(tk.END, f"  ... 还有 {len(dup_images) - 10} 个\n")
                        self.stats_text.insert(tk.END, "\n")

                if 'duplicate_annotations' in self.cross_dir_results:
                    dup_anns = self.cross_dir_results['duplicate_annotations']
                    if dup_anns:
                        self.stats_text.insert(tk.END, f"⚠️ 发现 {len(dup_anns)} 组重复标注:\n")
                        for i, (key, locations) in enumerate(list(dup_anns.items())[:5]):
                            self.stats_text.insert(tk.END, f"  📝 重复标注 #{i+1}\n")
                            self.stats_text.insert(tk.END, f"     存在于: {', '.join(locations)}\n")
                        if len(dup_anns) > 5:
                            self.stats_text.insert(tk.END, f"  ... 还有 {len(dup_anns) - 5} 组\n")
                        self.stats_text.insert(tk.END, "\n")

                if 'duplicate_json_annotations' in self.cross_dir_results:
                    dup_json_anns = self.cross_dir_results['duplicate_json_annotations']
                    if dup_json_anns:
                        self.stats_text.insert(tk.END, f"⚠️ 发现 {len(dup_json_anns)} 组跨JSON文件重复标注:\n")
                        for i, (key, json_files) in enumerate(list(dup_json_anns.items())[:5]):
                            self.stats_text.insert(tk.END, f"  📝 重复标注 #{i+1}\n")
                            self.stats_text.insert(tk.END, f"     存在于: {', '.join(json_files)}\n")
                        if len(dup_json_anns) > 5:
                            self.stats_text.insert(tk.END, f"  ... 还有 {len(dup_json_anns) - 5} 组\n")
                        self.stats_text.insert(tk.END, "\n")

                if 'json_image_mismatch' in self.cross_dir_results:
                    mismatch = self.cross_dir_results['json_image_mismatch']
                    if mismatch:
                        self.stats_text.insert(tk.END, f"⚠️ 发现 JSON标注与图片文件不对应:\n")
                        for dir_path, data in mismatch.items():
                            self.stats_text.insert(tk.END, f"  📂 {dir_path}\n")
                            if data['json_only']:
                                self.stats_text.insert(tk.END, f"    JSON引用但文件缺失 ({len(data['json_only'])}个):\n")
                                for f in data['json_only'][:5]:
                                    self.stats_text.insert(tk.END, f"      - {f}\n")
                                if len(data['json_only']) > 5:
                                    self.stats_text.insert(tk.END, f"      ... 还有 {len(data['json_only']) - 5} 个\n")
                            if data['file_only']:
                                self.stats_text.insert(tk.END, f"    文件存在但JSON未引用 ({len(data['file_only'])}个):\n")
                                for f in data['file_only'][:5]:
                                    self.stats_text.insert(tk.END, f"      - {f}\n")
                                if len(data['file_only']) > 5:
                                    self.stats_text.insert(tk.END, f"      ... 还有 {len(data['file_only']) - 5} 个\n")
                            self.stats_text.insert(tk.END, f"    匹配: {data['matched']}/{data['json_total']} (JSON) vs {data['file_total']} (文件)\n\n")
        else:
            self.stats_text.insert(tk.END, "暂无统计数据\n")
            self.stats_text.insert(tk.END, "请先进行核查操作")

        self.stats_text.config(state=tk.DISABLED)

    def clear_results(self):
        """清空结果显示"""
        self.result_text.delete(1.0, tk.END)
        self.validation_stats = {}
        self.cross_dir_results = {}
        self.pending_fixes = []
        self.update_file_list()
        self.update_stats_display()
        self.fix_button.config(state=tk.DISABLED)

    def show_full_log(self):
        """展开查看详细日志"""
        log_window = tk.Toplevel(self.root)
        log_window.title("📋 详细日志")
        log_window.geometry("800x600")
        log_window.transient(self.root)

        log_text = scrolledtext.ScrolledText(
            log_window,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg="#f5f5f5"
        )
        log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        log_text.insert(tk.END, self.result_text.get(1.0, tk.END))
        log_text.config(state=tk.DISABLED)

    def export_log(self):
        """导出核查日志和统计信息到文件"""
        # 获取结果文本框内容
        log_content = self.result_text.get(1.0, tk.END)

        # 获取统计文本框内容
        stats_content = self.stats_text.get(1.0, tk.END)

        if not log_content.strip() and not self.validation_stats:
            messagebox.showinfo("提示", "暂无核查结果可导出")
            return

        # 弹出对话框选择保存路径
        file_path = filedialog.asksaveasfilename(
            title="保存核查日志",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"核查报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )

        if not file_path:
            return

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                # 写入标题
                f.write("=" * 80 + "\n")
                f.write("COCO数据集验证报告\n")
                f.write(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 80 + "\n\n")

                # 写入汇总统计
                if self.validation_stats:
                    f.write("【汇总统计】\n")
                    f.write("-" * 40 + "\n")
                    total_files = len(self.validation_stats)
                    total_errors = sum(s.get('total_errors', 0) for s in self.validation_stats.values())
                    files_with_errors = sum(1 for s in self.validation_stats.values() if s.get('total_errors', 0) > 0)
                    f.write(f"总文件数: {total_files}\n")
                    f.write(f"有错误的文件: {files_with_errors}\n")
                    f.write(f"总错误数: {total_errors}\n\n")

                # 写入各文件详情
                if self.validation_stats:
                    f.write("【各文件验证详情】\n")
                    f.write("-" * 40 + "\n")
                    sorted_files = sorted(
                        self.validation_stats.items(),
                        key=lambda x: x[1].get('total_errors', 0),
                        reverse=True
                    )
                    for file_path_item, stats in sorted_files:
                        file_name = os.path.basename(file_path_item)
                        total_errors = stats.get('total_errors', 0)
                        error_types = stats.get('error_types', {})

                        if total_errors > 0:
                            f.write(f"\n❌ {file_name} ({total_errors} 个错误)\n")
                            f.write(f"   路径: {file_path_item}\n")
                            for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
                                f.write(f"   - {error_type}: {count}\n")
                        else:
                            f.write(f"\n✓ {file_name}\n")

                # 写入跨目录检查结果
                if self.cross_dir_results:
                    f.write(f"\n{'='*40}\n")
                    f.write("【跨目录检查结果】\n")
                    f.write("-" * 40 + "\n")

                    if 'duplicate_images' in self.cross_dir_results:
                        dup_images = self.cross_dir_results['duplicate_images']
                        if dup_images:
                            f.write(f"\n重复图片名 ({len(dup_images)} 个):\n")
                            for img_name, dirs in dup_images.items():
                                f.write(f"  🖼️  {img_name}\n")
                                f.write(f"     存在于: {', '.join(dirs)}\n")

                    if 'duplicate_annotations' in self.cross_dir_results:
                        dup_anns = self.cross_dir_results['duplicate_annotations']
                        if dup_anns:
                            f.write(f"\n重复标注 ({len(dup_anns)} 组):\n")
                            for i, (key, locations) in enumerate(dup_anns.items(), 1):
                                f.write(f"  📝 重复标注 #{i}\n")
                                f.write(f"     存在于: {', '.join(locations)}\n")

                    if 'duplicate_json_annotations' in self.cross_dir_results:
                        dup_json_anns = self.cross_dir_results['duplicate_json_annotations']
                        if dup_json_anns:
                            f.write(f"\n跨JSON文件重复标注 ({len(dup_json_anns)} 组):\n")
                            for i, (key, json_files) in enumerate(dup_json_anns.items(), 1):
                                f.write(f"  📝 重复标注 #{i}\n")
                                f.write(f"     存在于: {', '.join(json_files)}\n")

                    if 'json_image_mismatch' in self.cross_dir_results:
                        mismatch = self.cross_dir_results['json_image_mismatch']
                        f.write(f"\nJSON与图片对应检查:\n")
                        for dir_path, data in mismatch.items():
                            f.write(f"  📂 {dir_path}\n")
                            if data['json_only']:
                                f.write(f"    JSON引用但文件缺失 ({len(data['json_only'])}个):\n")
                                for fname in data['json_only']:
                                    f.write(f"      - {fname}\n")
                            if data['file_only']:
                                f.write(f"    文件存在但JSON未引用 ({len(data['file_only'])}个):\n")
                                for fname in data['file_only']:
                                    f.write(f"      - {fname}\n")
                            f.write(f"    匹配: {data['matched']}/{data['json_total']} (JSON) vs {data['file_total']} (文件)\n")

                # 写入详细日志
                f.write(f"\n{'='*80}\n")
                f.write("【详细核查日志】\n")
                f.write("=" * 80 + "\n\n")
                f.write(log_content)

            messagebox.showinfo("✅ 导出成功", f"核查报告已保存到:\n{file_path}")

        except Exception as e:
            messagebox.showerror("❌ 导出失败", f"导出日志时发生错误:\n{str(e)}")

    def log(self, message: str):
        """向结果文本框插入日志信息（线程安全）"""
        def _insert():
            self.result_text.insert(tk.END, message)
            self.result_text.see(tk.END)

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
        self.cross_dir_results = {}
        self.pending_fixes = []

        # 初始化进度
        self.total_files_to_validate = len(self.selected_files)
        self.files_validated = 0
        self.reset_progress()

        # 标记正在验证
        self.is_validating = True

        # 禁用按钮防止重复点击
        self.start_button.config(state=tk.DISABLED, bg="#BDBDBD")
        self.clear_button.config(state=tk.DISABLED)
        self.fix_button.config(state=tk.DISABLED)

        # 在后台线程中执行验证，避免界面冻结
        validation_thread = threading.Thread(target=self._run_validation, daemon=True)
        validation_thread.start()

    def _run_validation(self):
        """在后台线程中运行验证"""
        try:
            start_time = time.time()

            if self.use_multithreading.get() and self.total_files_to_validate > 1:
                thread_num = self.thread_count.get()
                self.log(f"======= 开始核查（多线程模式，{thread_num}个线程）=======\n")
                self.log(f"待核查文件数: {self.total_files_to_validate}\n\n")
                self.validate_with_multithreading()
            else:
                self.log(f"======= 开始核查（单线程模式）=======\n")
                self.log(f"待核查文件数: {self.total_files_to_validate}\n\n")
                self.validate_single_threaded()

            # 跨目录/跨文件检查
            self.log(f"\n======= 跨目录检查 =======\n")
            self._run_cross_dir_checks()

            elapsed_time = time.time() - start_time

            self.root.after(0, lambda: self._finish_validation(elapsed_time))
        except Exception as e:
            self.root.after(0, lambda: self.log(f"验证过程发生错误: {str(e)}\n"))
            self.root.after(0, lambda: self._finish_validation(0))

    def _run_cross_dir_checks(self):
        """执行跨目录检查"""
        # 如果没有目录结构但有选中文件，自动按父目录分组
        if not self.directory_structure and self.selected_files:
            temp_structure = {}
            for json_file in self.selected_files:
                parent = os.path.basename(os.path.dirname(json_file))
                if parent not in temp_structure:
                    temp_structure[parent] = []
                temp_structure[parent].append(json_file)

            if len(temp_structure) < 2:
                self.log("所有文件都在同一目录，跳过跨目录检查。\n")
                return

            # 使用临时结构进行检查
            original_structure = self.directory_structure
            self.directory_structure = temp_structure

            # 执行各项检查
            if self.validation_checks['cross_dir_duplicate_images'].get():
                self.log("🔍 检查跨目录图片名重复...\n")
                duplicate_images = self.check_cross_dir_duplicate_images()
                if duplicate_images:
                    self.cross_dir_results['duplicate_images'] = duplicate_images
                    self.log(f"  ⚠️ 发现 {len(duplicate_images)} 个重复的图片名\n")
                    for img_name, dirs in list(duplicate_images.items())[:5]:
                        self.log(f"    🖼️  {img_name} 存在于: {', '.join(dirs)}\n")
                    if len(duplicate_images) > 5:
                        self.log(f"    ... 还有 {len(duplicate_images) - 5} 个\n")
                else:
                    self.log("  ✓ 未发现重复图片名\n")

            if self.validation_checks['cross_dir_duplicate_annotations'].get():
                self.log("🔍 检查跨目录标注内容重复...\n")
                duplicate_annotations = self.check_cross_dir_duplicate_annotations()
                if duplicate_annotations:
                    self.cross_dir_results['duplicate_annotations'] = duplicate_annotations
                    self.log(f"  ⚠️ 发现 {len(duplicate_annotations)} 组重复标注\n")
                else:
                    self.log("  ✓ 未发现重复标注内容\n")

            if self.validation_checks['cross_json_duplicate_annotations'].get():
                self.log("🔍 检查跨JSON文件标注重复...\n")
                duplicate_json_annotations = self.check_cross_json_duplicate_annotations()
                if duplicate_json_annotations:
                    self.cross_dir_results['duplicate_json_annotations'] = duplicate_json_annotations
                    self.log(f"  ⚠️ 发现 {len(duplicate_json_annotations)} 组跨文件重复标注\n")
                else:
                    self.log("  ✓ 未发现跨文件重复标注\n")

            if self.validation_checks['json_image_mismatch'].get():
                self.log("🔍 检查JSON标注与图片对应关系...\n")
                mismatch_results = self.check_json_image_mismatch()
                if mismatch_results:
                    self.cross_dir_results['json_image_mismatch'] = mismatch_results
                    total_missing = sum(len(v['json_only']) for v in mismatch_results.values())
                    total_extra = sum(len(v['file_only']) for v in mismatch_results.values())
                    self.log(f"  ⚠️ 发现 {total_missing} 个JSON引用的图片缺失，{total_extra} 个图片未被标注\n")
                else:
                    self.log("  ✓ JSON标注与图片文件一一对应\n")

            # 恢复原始结构
            self.directory_structure = original_structure

            if self.cross_dir_results:
                self.root.after(0, lambda: self.fix_button.config(state=tk.NORMAL))

            return

        # 原有的目录模式检查逻辑
        if not self.directory_structure or len(self.directory_structure) < 2:
            self.log("只有一个目录，无需跨目录检查。\n")
            return

        # 跨目录图片名重复检查
        if self.validation_checks['cross_dir_duplicate_images'].get():
            self.log("🔍 检查跨目录图片名重复...\n")
            duplicate_images = self.check_cross_dir_duplicate_images()
            if duplicate_images:
                self.cross_dir_results['duplicate_images'] = duplicate_images
                self.log(f"  ⚠️ 发现 {len(duplicate_images)} 个重复的图片名\n")
                for img_name, dirs in list(duplicate_images.items())[:5]:
                    self.log(f"    🖼️  {img_name} 存在于: {', '.join(dirs)}\n")
                if len(duplicate_images) > 5:
                    self.log(f"    ... 还有 {len(duplicate_images) - 5} 个\n")
            else:
                self.log("  ✓ 未发现重复图片名\n")

        # 跨目录标注内容重复检查
        if self.validation_checks['cross_dir_duplicate_annotations'].get():
            self.log("🔍 检查跨目录标注内容重复...\n")
            duplicate_annotations = self.check_cross_dir_duplicate_annotations()
            if duplicate_annotations:
                self.cross_dir_results['duplicate_annotations'] = duplicate_annotations
                self.log(f"  ⚠️ 发现 {len(duplicate_annotations)} 组重复标注\n")
            else:
                self.log("  ✓ 未发现重复标注内容\n")

        # 跨JSON文件标注重复检查
        if self.validation_checks['cross_json_duplicate_annotations'].get():
            self.log("🔍 检查跨JSON文件标注重复...\n")
            duplicate_json_annotations = self.check_cross_json_duplicate_annotations()
            if duplicate_json_annotations:
                self.cross_dir_results['duplicate_json_annotations'] = duplicate_json_annotations
                self.log(f"  ⚠️ 发现 {len(duplicate_json_annotations)} 组跨文件重复标注\n")
            else:
                self.log("  ✓ 未发现跨文件重复标注\n")

        # JSON标注与图片对应检查
        if self.validation_checks['json_image_mismatch'].get():
            self.log("🔍 检查JSON标注与图片对应关系...\n")
            mismatch_results = self.check_json_image_mismatch()
            if mismatch_results:
                self.cross_dir_results['json_image_mismatch'] = mismatch_results
                total_missing = sum(len(v['json_only']) for v in mismatch_results.values())
                total_extra = sum(len(v['file_only']) for v in mismatch_results.values())
                self.log(f"  ⚠️ 发现 {total_missing} 个JSON引用的图片缺失，{total_extra} 个图片未被标注\n")
            else:
                self.log("  ✓ JSON标注与图片文件一一对应\n")

        # 如果有重复问题，启用修复按钮
        if self.cross_dir_results:
            self.root.after(0, lambda: self.fix_button.config(state=tk.NORMAL))

    def check_cross_dir_duplicate_images(self) -> Dict[str, List[str]]:
        """检查跨目录图片名重复"""
        # 收集所有目录中的图片文件名
        image_files_by_dir = {}  # {dir_name: set of image filenames}

        for dir_name, json_files in self.directory_structure.items():
            image_files = set()
            for json_file in json_files:
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if 'images' in data:
                        for img in data['images']:
                            file_name = img.get('file_name', '')
                            if file_name:
                                image_files.add(file_name)
                except:
                    pass
            image_files_by_dir[dir_name] = image_files

        # 查找重复的图片名
        all_images = {}  # {filename: [dirs]}
        for dir_name, images in image_files_by_dir.items():
            for img_name in images:
                if img_name not in all_images:
                    all_images[img_name] = []
                all_images[img_name].append(dir_name)

        # 过滤出重复的
        duplicates = {k: v for k, v in all_images.items() if len(v) > 1}
        return duplicates

    def check_cross_dir_duplicate_annotations(self) -> Dict[str, List[str]]:
        """检查跨目录标注内容重复"""
        # 收集所有目录中的标注哈希
        annotations_by_dir = {}  # {dir_name: {hash: annotation_data}}

        for dir_name, json_files in self.directory_structure.items():
            ann_hashes = {}
            for json_file in json_files:
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    image_lookup = self._build_image_lookup(data)
                    if 'annotations' in data:
                        for ann in data['annotations']:
                            # 创建标注内容的哈希键
                            ann_key = self._create_annotation_hash(ann, image_lookup)
                            if ann_key:
                                ann_hashes[ann_key] = ann_hashes.get(ann_key, 0) + 1
                except:
                    pass
            annotations_by_dir[dir_name] = ann_hashes

        # 查找跨目录重复的标注
        all_anns = defaultdict(list)  # {hash: [dirs]}
        for dir_name, ann_hashes in annotations_by_dir.items():
            for ann_hash in ann_hashes:
                all_anns[ann_hash].append(dir_name)

        # 过滤出跨目录重复的
        duplicates = {k: v for k, v in all_anns.items() if len(v) > 1}
        return duplicates

    def check_cross_json_duplicate_annotations(self) -> Dict[str, List[str]]:
        """检查跨JSON文件的标注重复（不按目录分组，直接比较所有JSON文件）"""
        # 收集所有JSON文件中的标注哈希
        annotations_by_file = {}  # {json_path: {hash: count}}

        for json_file in self.selected_files:
            ann_hashes = {}
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                image_lookup = self._build_image_lookup(data)
                if 'annotations' in data:
                    for ann in data['annotations']:
                        ann_key = self._create_annotation_hash(ann, image_lookup)
                        if ann_key:
                            ann_hashes[ann_key] = ann_hashes.get(ann_key, 0) + 1
            except:
                pass
            annotations_by_file[json_file] = ann_hashes

        # 查找跨JSON文件重复的标注
        all_anns = defaultdict(list)  # {hash: [json_paths]}
        for json_path, ann_hashes in annotations_by_file.items():
            for ann_hash in ann_hashes:
                all_anns[ann_hash].append(json_path)

        # 过滤出跨文件重复的（出现在多个JSON文件中）
        duplicates = {k: v for k, v in all_anns.items() if len(v) > 1}
        return duplicates

    def check_json_image_mismatch(self) -> Dict[str, dict]:
        """检查JSON标注中的图片引用与实际图片文件是否一一对应（严格按COCO标准结构）"""
        results = {}  # {coco_root: {"json_only": [...], "file_only": [...], "matched": int}}

        # 支持的图片扩展名
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.ppm', '.pgm'}

        # 收集所有 JSON 文件的父目录
        json_dirs = set(os.path.dirname(f) for f in self.selected_files)

        # 按 annotations 目录分组处理
        annotations_dirs = set()
        for json_dir in json_dirs:
            # 检测是否在 annotations 目录中
            if os.path.basename(json_dir) == 'annotations':
                annotations_dirs.add(json_dir)
            else:
                # 如果不在 annotations 目录，检查是否有 annotations 子目录
                annotations_subdir = os.path.join(json_dir, 'annotations')
                if os.path.isdir(annotations_subdir):
                    annotations_dirs.add(annotations_subdir)

        for annotations_dir in annotations_dirs:
            # 标准结构：annotations/ 的同级是 images/
            coco_root = os.path.dirname(annotations_dir)
            images_dir = os.path.join(coco_root, 'images')

            # 收集该 COCO 目录下的所有图片（只在 images/ 目录中搜索）
            actual_images = set()
            if os.path.isdir(images_dir):
                images_path = Path(images_dir)
                for ext in image_extensions:
                    for img_file in images_path.glob(f"*{ext}"):
                        actual_images.add(img_file.name)
                    for img_file in images_path.glob(f"*{ext.upper()}"):
                        actual_images.add(img_file.name)

            # 收集该 annotations 目录下所有 JSON 中的图片引用
            json_images = set()
            annotations_path = Path(annotations_dir)
            for json_file in annotations_path.glob("*.json"):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if 'images' in data:
                        for img in data['images']:
                            file_name = img.get('file_name', '')
                            if file_name:
                                json_images.add(file_name)
                except:
                    pass

            # 计算差异
            json_only = json_images - actual_images
            file_only = actual_images - json_images
            matched_count = len(json_images & actual_images)

            if json_only or file_only:
                results[coco_root] = {
                    'json_only': sorted(list(json_only)),
                    'file_only': sorted(list(file_only)),
                    'matched': matched_count,
                    'json_total': len(json_images),
                    'file_total': len(actual_images),
                }

        return results

    def _build_image_lookup(self, data: dict) -> Dict:
        """构建 image_id 到 file_name 的映射，用于跨文件标注去重"""
        lookup = {}
        for img in data.get('images', []):
            if isinstance(img, dict) and 'id' in img:
                lookup[img['id']] = img.get('file_name', img['id'])
        return lookup

    def _create_annotation_hash(self, annotation: dict, image_lookup: Optional[Dict] = None) -> Optional[str]:
        """创建标注内容的哈希值"""
        try:
            image_id = annotation.get('image_id')
            image_ref = image_lookup.get(image_id, image_id) if image_lookup else image_id
            # 使用关键字段创建哈希
            key_fields = {
                'image_ref': image_ref,
                'category_id': annotation.get('category_id'),
                'bbox': self._normalize_for_hash(annotation.get('bbox', [])),
                'area': annotation.get('area'),
                'segmentation': self._normalize_for_hash(annotation.get('segmentation', '')),
            }
            key_str = json.dumps(key_fields, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            return hashlib.md5(key_str.encode()).hexdigest()
        except:
            return None

    def _normalize_for_hash(self, value):
        """将标注内容规范化，避免字典顺序或元组/列表差异影响哈希"""
        if isinstance(value, dict):
            return {k: self._normalize_for_hash(value[k]) for k in sorted(value)}
        if isinstance(value, (list, tuple)):
            return [self._normalize_for_hash(v) for v in value]
        return value

    def _is_valid_number(self, value) -> bool:
        """判断值是否为有效数字，排除 bool、NaN 和无穷值"""
        return (
            isinstance(value, (int, float)) and
            not isinstance(value, bool) and
            math.isfinite(value)
        )

    def _finish_validation(self, elapsed_time=0):
        """完成验证后的GUI更新（在主线程中执行）"""
        self.update_file_list()
        self.update_stats_display()

        if elapsed_time > 0:
            self.log(f"======= 核查完毕（耗时: {elapsed_time:.2f}秒）=======\n")
        else:
            self.log("======= 核查完毕 =======\n")

        if self.cross_dir_results:
            total_issues = 0
            fixable_issues = 0
            if 'duplicate_images' in self.cross_dir_results:
                total_issues += len(self.cross_dir_results['duplicate_images'])
                fixable_issues += len(self.cross_dir_results['duplicate_images'])
            if 'duplicate_annotations' in self.cross_dir_results:
                total_issues += len(self.cross_dir_results['duplicate_annotations'])
                fixable_issues += len(self.cross_dir_results['duplicate_annotations'])
            if 'duplicate_json_annotations' in self.cross_dir_results:
                total_issues += len(self.cross_dir_results['duplicate_json_annotations'])
                fixable_issues += len(self.cross_dir_results['duplicate_json_annotations'])
            if 'json_image_mismatch' in self.cross_dir_results:
                for v in self.cross_dir_results['json_image_mismatch'].values():
                    total_issues += len(v['json_only']) + len(v['file_only'])
            if total_issues > 0:
                if fixable_issues > 0:
                    self.log(f"\n⚠️ 发现 {total_issues} 个问题（其中 {fixable_issues} 个可自动修复），点击「🔧 一键修复去重」可自动修复\n")
                else:
                    self.log(f"\n⚠️ 发现 {total_issues} 个问题，请根据上方详情手动处理\n")

        self.is_validating = False
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
            try:
                self.validate_coco_file(file_path)
                return True
            except Exception as e:
                self.log(f"验证 {os.path.basename(file_path)} 时出错: {str(e)}\n")
                return False

        with ThreadPoolExecutor(max_workers=thread_num) as executor:
            future_to_file = {executor.submit(validate_file_wrapper, file_path): file_path
                             for file_path in self.selected_files}

            for future in as_completed(future_to_file):
                try:
                    future.result()
                except Exception as e:
                    file_path = future_to_file[future]
                    self.log(f"处理 {os.path.basename(file_path)} 时发生异常: {str(e)}\n")
                finally:
                    with self.validation_lock:
                        self.files_validated += 1
                        current = self.files_validated
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
                with self.validation_lock:
                    self.validation_stats[file_path] = {
                        'total_errors': 1,
                        'error_types': {'JSON格式错误': 1}
                    }
                return
            except Exception as e:
                self.log(f"[{file_name}]... 发现错误：\n")
                self.log(f"  - 错误类型：文件读取错误\n")
                self.log(f"    详情：{str(e)}\n\n")
                with self.validation_lock:
                    self.validation_stats[file_path] = {
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

        if errors:
            self.report_errors(file_name, errors)
            self.record_validation_errors(file_path, errors)
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
            for cat in categories:
                cat_id = cat.get("id")
                if cat_id is not None:
                    category_ids.add(cat_id)

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

            if self.validation_checks['image_id_exists'].get():
                image_id = ann.get("image_id")
                if image_id not in image_ids:
                    errors.append({
                        "type": "image_id未找到",
                        "detail": f"Annotation ID {ann_id} 的 image_id {image_id} 在 'images' 列表中不存在。"
                    })

            if self.validation_checks['category_id_exists'].get():
                category_id = ann.get("category_id")
                if category_id not in category_ids:
                    errors.append({
                        "type": "category_id未找到",
                        "detail": f"Annotation ID {ann_id} 的 category_id {category_id} 在 'categories' 列表中不存在。"
                    })

            if self.validation_checks['iscrowd_valid'].get():
                iscrowd = ann.get("iscrowd")
                if iscrowd not in [0, 1]:
                    errors.append({
                        "type": "iscrowd值无效",
                        "detail": f"Annotation ID {ann_id} 的 iscrowd 值必须为 0 或 1，当前值: {iscrowd}"
                    })

            bbox = ann.get("bbox")
            bbox_has_valid_shape = isinstance(bbox, list) and len(bbox) == 4
            bbox_has_numeric_values = bbox_has_valid_shape and all(self._is_valid_number(v) for v in bbox)

            if self.validation_checks['bbox_format'].get():
                if not bbox_has_valid_shape:
                    errors.append({
                        "type": "BBox格式错误",
                        "detail": f"Annotation ID {ann_id} 的 bbox 必须是包含4个数字的列表 [x, y, width, height]。"
                    })
                elif not bbox_has_numeric_values:
                    errors.append({
                        "type": "BBox数值类型错误",
                        "detail": f"Annotation ID {ann_id} 的 BBox 包含非数字值。"
                    })

            if self.validation_checks['bbox_bounds'].get():
                if not bbox_has_valid_shape:
                    if not self.validation_checks['bbox_format'].get():
                        errors.append({
                            "type": "BBox格式错误",
                            "detail": f"Annotation ID {ann_id} 的 bbox 必须是包含4个数字的列表 [x, y, width, height]，无法进行边界检查。"
                        })
                elif not bbox_has_numeric_values:
                    if not self.validation_checks['bbox_format'].get():
                        errors.append({
                            "type": "BBox数值类型错误",
                            "detail": f"Annotation ID {ann_id} 的 BBox 包含非数字值，无法进行边界检查。"
                        })
                else:
                    x, y, w, h = bbox

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

                    image_id = ann.get("image_id")
                    if image_id in image_info_map:
                        img_info = image_info_map[image_id]
                        img_width = img_info.get("width")
                        img_height = img_info.get("height")

                        if img_width is not None and img_height is not None:
                            dimensions_valid = (
                                self._is_valid_number(img_width) and
                                self._is_valid_number(img_height)
                            )
                            if not dimensions_valid:
                                errors.append({
                                    "type": "Image尺寸类型错误",
                                    "detail": f"Image ID {image_id} 的 width/height 必须是有效数字，无法进行 BBox 边界检查。"
                                })
                            elif x + w > img_width:
                                errors.append({
                                    "type": "BBox越界",
                                    "detail": f"Annotation ID {ann_id} 的 BBox [{x}, {y}, {w}, {h}] 超出了图像 {image_id} 的宽度边界 (图像宽度: {img_width})。"
                                })

                            if dimensions_valid and y + h > img_height:
                                errors.append({
                                    "type": "BBox越界",
                                    "detail": f"Annotation ID {ann_id} 的 BBox [{x}, {y}, {w}, {h}] 超出了图像 {image_id} 的高度边界 (图像高度: {img_height})。"
                                })

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

            if self.validation_checks['segmentation_format'].get():
                segmentation = ann.get("segmentation")
                if segmentation is not None:
                    if isinstance(segmentation, dict):
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
                        if len(segmentation) == 0:
                            errors.append({
                                "type": "Segmentation格式错误",
                                "detail": f"Annotation ID {ann_id} 的 segmentation 为空列表。"
                            })
                        else:
                            for poly_idx, poly in enumerate(segmentation):
                                if not isinstance(poly, list):
                                    errors.append({
                                        "type": "Segmentation格式错误",
                                        "detail": f"Annotation ID {ann_id} 的 segmentation 第 {poly_idx} 个多边形不是列表类型。"
                                    })
                                elif len(poly) < 6:
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

            if self.validation_checks['segmentation_rectangle'].get():
                segmentation = ann.get("segmentation")
                if segmentation is not None and isinstance(segmentation, list):
                    for poly_idx, poly in enumerate(segmentation):
                        if isinstance(poly, list):
                            if len(poly) != 8:
                                errors.append({
                                    "type": "矩形标注坐标数量错误",
                                    "detail": f"Annotation ID {ann_id} 的 segmentation 第 {poly_idx} 个多边形应包含8个值（矩形4个顶点坐标），当前有 {len(poly)} 个值。"
                                })

        if errors:
            self.report_errors(file_name, errors)
            self.record_validation_errors(file_path, errors)
        else:
            self.log(f"[{file_name}]... 验证通过。\n\n")
            with self.validation_lock:
                self.validation_stats[file_path] = {
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

    def record_validation_errors(self, file_path: str, errors: List[Dict]):
        """记录验证错误统计"""
        error_types = {}
        for error in errors:
            error_type = error['type']
            error_types[error_type] = error_types.get(error_type, 0) + 1

        with self.validation_lock:
            self.validation_stats[file_path] = {
                'total_errors': len(errors),
                'error_types': error_types
            }

    def start_fix(self):
        """开始修复去重"""
        if not self.cross_dir_results:
            messagebox.showinfo("提示", "没有发现需要修复的重复问题。")
            return

        # 显示修复预览
        preview = self._generate_fix_preview()
        if not preview:
            messagebox.showinfo("提示", "没有可修复的问题。")
            return

        # 创建预览窗口
        self._show_fix_preview(preview)

    def _sanitize_filename_component(self, value: str) -> str:
        """将目录名转换为可用于文件名前缀的安全文本"""
        sanitized = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in value)
        sanitized = sanitized.strip('_')
        return sanitized or 'dir'

    def _make_prefixed_image_name(self, dir_name: str, image_name: str) -> str:
        """为重复图片生成保留原相对目录的新文件名"""
        normalized = image_name.replace('\\', '/')
        if '/' in normalized:
            rel_dir, base_name = normalized.rsplit('/', 1)
            return f"{rel_dir}/{self._sanitize_filename_component(dir_name)}_{base_name}"
        return f"{self._sanitize_filename_component(dir_name)}_{normalized}"

    def _generate_fix_preview(self) -> dict:
        """生成修复预览"""
        preview = {
            'image_renames': [],
            'annotation_removals': [],
            'json_annotation_removals': [],
        }

        # 图片重命名预览
        if 'duplicate_images' in self.cross_dir_results:
            for img_name, dirs in self.cross_dir_results['duplicate_images'].items():
                for dir_name in dirs[1:]:  # 保留第一个，重命名其余
                    new_name = self._make_prefixed_image_name(dir_name, img_name)
                    preview['image_renames'].append({
                        'original': img_name,
                        'new': new_name,
                        'directory': dir_name,
                    })

        # 标注去重预览
        if 'duplicate_annotations' in self.cross_dir_results:
            for ann_hash, dirs in self.cross_dir_results['duplicate_annotations'].items():
                for dir_name in dirs[1:]:  # 保留第一个，移除其余
                    preview['annotation_removals'].append({
                        'directory': dir_name,
                        'hash': ann_hash,
                        'display_hash': ann_hash[:8] + '...',
                    })

        # 跨JSON文件标注去重预览
        if 'duplicate_json_annotations' in self.cross_dir_results:
            for ann_hash, json_files in self.cross_dir_results['duplicate_json_annotations'].items():
                for json_file in json_files[1:]:  # 保留第一个，移除其余
                    preview['json_annotation_removals'].append({
                        'json_file': json_file,
                        'hash': ann_hash,
                        'display_hash': ann_hash[:8] + '...',
                    })

        return preview

    def _show_fix_preview(self, preview: dict):
        """显示修复预览窗口"""
        preview_window = tk.Toplevel(self.root)
        preview_window.title("🔧 修复预览")
        preview_window.geometry("600x500")
        preview_window.transient(self.root)

        main_frame = tk.Frame(preview_window, bg="white", padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            main_frame,
            text="🔧 修复预览",
            font=("Arial", 14, "bold"),
            bg="white",
            fg="#9C27B0"
        ).pack(pady=(0, 10))

        tk.Label(
            main_frame,
            text="以下操作将在确认后执行：",
            font=("Arial", 10),
            bg="white"
        ).pack(pady=(0, 10))

        # 修复内容显示
        preview_text = scrolledtext.ScrolledText(
            main_frame,
            wrap=tk.WORD,
            width=60,
            height=20,
            font=("Consolas", 9),
            bg="#f5f5f5"
        )
        preview_text.pack(fill=tk.BOTH, expand=True, pady=10)

        # 填充预览内容
        if preview['image_renames']:
            preview_text.insert(tk.END, "🖼️ 图片重命名（解决图片名重复）:\n")
            preview_text.insert(tk.END, "=" * 50 + "\n")
            for item in preview['image_renames']:
                preview_text.insert(tk.END, f"  {item['original']}\n")
                preview_text.insert(tk.END, f"    → {item['new']}\n")
                preview_text.insert(tk.END, f"    目录: {item['directory']}/\n\n")
        else:
            preview_text.insert(tk.END, "无需重命名图片\n\n")

        if preview['annotation_removals']:
            preview_text.insert(tk.END, f"\n📝 移除重复标注（共 {len(preview['annotation_removals'])} 项）:\n")
            preview_text.insert(tk.END, "=" * 50 + "\n")
            for item in preview['annotation_removals']:
                preview_text.insert(tk.END, f"  目录: {item['directory']}/\n")
                preview_text.insert(tk.END, f"  标注哈希: {item['display_hash']}\n\n")
        else:
            preview_text.insert(tk.END, "无需移除标注\n\n")

        if preview['json_annotation_removals']:
            preview_text.insert(tk.END, f"\n📝 移除跨JSON文件重复标注（共 {len(preview['json_annotation_removals'])} 项）:\n")
            preview_text.insert(tk.END, "=" * 50 + "\n")
            for item in preview['json_annotation_removals']:
                preview_text.insert(tk.END, f"  JSON文件: {item['json_file']}\n")
                preview_text.insert(tk.END, f"  标注哈希: {item['display_hash']}\n\n")
        else:
            preview_text.insert(tk.END, "无需移除跨JSON文件重复标注\n\n")

        preview_text.config(state=tk.DISABLED)

        # 按钮区
        btn_frame = tk.Frame(main_frame, bg="white")
        btn_frame.pack(pady=10)

        def do_fix():
            preview_window.destroy()
            self._execute_fix(preview)

        tk.Button(
            btn_frame,
            text="✅ 确认修复",
            command=do_fix,
            width=15,
            bg="#4CAF50",
            fg="white",
            font=("Arial", 10, "bold"),
            relief=tk.FLAT,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=10)

        tk.Button(
            btn_frame,
            text="❌ 取消",
            command=preview_window.destroy,
            width=15,
            bg="#f44336",
            fg="white",
            font=("Arial", 10, "bold"),
            relief=tk.FLAT,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=10)

    def _get_repair_base_dir(self) -> str:
        """获取修复输出时用于计算相对路径的基准目录"""
        if not self.selected_files:
            return os.getcwd()

        parent_dirs = [os.path.dirname(os.path.abspath(f)) for f in self.selected_files]
        common_dir = os.path.commonpath(parent_dirs)
        if os.path.basename(common_dir).lower() == 'annotations':
            return os.path.dirname(common_dir)
        return common_dir

    def _safe_relpath(self, path: str, base_dir: str) -> str:
        """计算安全相对路径；若不在基准目录下，则退回到文件名"""
        abs_path = os.path.abspath(path)
        abs_base = os.path.abspath(base_dir)
        try:
            common = os.path.commonpath([abs_path, abs_base])
            if common == abs_base:
                return os.path.relpath(abs_path, abs_base)
        except ValueError:
            pass
        return os.path.basename(path)

    def _find_image_file(self, json_file: str, image_name: str) -> Optional[str]:
        """根据 JSON 位置和 file_name 寻找真实图片文件"""
        if not image_name:
            return None

        image_path = Path(image_name)
        if image_path.is_absolute() and image_path.exists():
            return str(image_path)

        json_dir = Path(json_file).parent
        candidates = [
            json_dir / image_name,
            json_dir.parent / image_name,
            json_dir / 'images' / image_name,
            json_dir.parent / 'images' / image_name,
        ]

        if json_dir.name.lower() == 'annotations':
            candidates.insert(0, json_dir.parent / 'images' / image_name)

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return str(candidate)
        return None

    def _copy_renamed_image_to_output(self, source_path: str, old_name: str, new_name: str, output_dir: str, base_dir: str) -> Optional[str]:
        """复制真实图片到输出目录，并返回 JSON 中应写入的新 file_name"""
        rel_source = self._safe_relpath(source_path, base_dir)
        rel_source_dir = os.path.dirname(rel_source)
        new_basename = os.path.basename(new_name.replace('\\', '/'))
        output_path = os.path.join(output_dir, rel_source_dir, new_basename)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        if os.path.abspath(source_path) != os.path.abspath(output_path):
            shutil.copy2(source_path, output_path)

        normalized_old = old_name.replace('\\', '/')
        if '/' in normalized_old:
            old_rel_dir = normalized_old.rsplit('/', 1)[0]
            return f"{old_rel_dir}/{new_basename}"
        return new_basename

    def _execute_fix(self, preview: dict):
        """执行修复操作"""
        # 选择输出目录
        output_dir = filedialog.askdirectory(
            title="选择修复后文件的保存目录",
            initialdir=os.path.dirname(self.selected_files[0]) if self.selected_files else None
        )
        if not output_dir:
            return

        try:
            self.log(f"\n======= 开始修复 =======\n")
            base_dir = self._get_repair_base_dir()

            # 创建备份
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = os.path.join(output_dir, f"_backup_{timestamp}")
            os.makedirs(backup_dir, exist_ok=True)

            # 复制原始文件到备份目录
            for json_file in self.selected_files:
                rel_path = self._safe_relpath(json_file, base_dir)
                backup_path = os.path.join(backup_dir, rel_path)
                os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                shutil.copy2(json_file, backup_path)

            self.log(f"✓ 已备份原始文件到: {backup_dir}\n")

            # 加载所有JSON文件
            json_data = {}
            for json_file in self.selected_files:
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        json_data[json_file] = json.load(f)
                except:
                    pass

            # 执行图片重命名
            renamed_count = 0
            copied_image_count = 0
            skipped_image_count = 0
            copied_image_keys = set()
            if preview['image_renames']:
                for item in preview['image_renames']:
                    dir_name = item['directory']
                    old_name = item['original']
                    new_name = item['new']

                    # 找到对应目录的JSON文件
                    if dir_name in self.directory_structure:
                        source_path = None
                        for json_file in self.directory_structure[dir_name]:
                            source_path = self._find_image_file(json_file, old_name)
                            if source_path:
                                break

                        if not source_path:
                            skipped_image_count += 1
                            self.log(f"⚠️ 未找到真实图片文件，跳过重命名引用: {dir_name}/{old_name}\n")
                            continue

                        json_file_name = self._copy_renamed_image_to_output(
                            source_path, old_name, new_name, output_dir, base_dir
                        )
                        image_key = (source_path, json_file_name)
                        if image_key not in copied_image_keys:
                            copied_image_keys.add(image_key)
                            copied_image_count += 1

                        for json_file in self.directory_structure[dir_name]:
                            if json_file in json_data:
                                data = json_data[json_file]
                                # 更新images中的file_name
                                for img in data.get('images', []):
                                    if img.get('file_name') == old_name:
                                        img['file_name'] = json_file_name
                                        renamed_count += 1

                self.log(f"✓ 重命名了 {renamed_count} 个图片引用，复制了 {copied_image_count} 个真实图片文件\n")
                if skipped_image_count:
                    self.log(f"⚠️ 有 {skipped_image_count} 个图片因找不到真实文件而跳过\n")

            # 执行标注去重
            removed_count = 0
            json_removed_count = 0
            if preview['annotation_removals']:
                # 对每个目录的JSON文件，移除重复标注
                for item in preview['annotation_removals']:
                    dir_name = item['directory']
                    if dir_name in self.directory_structure:
                        for json_file in self.directory_structure[dir_name]:
                            if json_file in json_data:
                                data = json_data[json_file]
                                annotations = data.get('annotations', [])
                                image_lookup = self._build_image_lookup(data)
                                # 标记要移除的标注（基于哈希匹配）
                                to_remove = []
                                for i, ann in enumerate(annotations):
                                    ann_hash = self._create_annotation_hash(ann, image_lookup)
                                    if ann_hash and ann_hash == item['hash']:
                                        to_remove.append(i)
                                        break  # 每个文件只移除一个匹配的

                                # 从后往前移除，避免索引问题
                                for i in reversed(to_remove):
                                    annotations.pop(i)
                                    removed_count += 1

                                # 重新编号annotation ID
                                for i, ann in enumerate(annotations, 1):
                                    ann['id'] = i

                self.log(f"✓ 移除了 {removed_count} 个重复标注\n")

            # 执行跨JSON文件标注去重
            json_removed_count = 0
            if preview['json_annotation_removals']:
                # 按JSON文件分组，每个文件可能移除多个标注
                removals_by_file = defaultdict(list)
                for item in preview['json_annotation_removals']:
                    removals_by_file[item['json_file']].append(item['hash'])

                for json_file, hashes in removals_by_file.items():
                    if json_file in json_data:
                        data = json_data[json_file]
                        annotations = data.get('annotations', [])
                        image_lookup = self._build_image_lookup(data)
                        remaining_hashes = set(hashes)
                        to_remove = []
                        for i, ann in enumerate(annotations):
                            ann_hash = self._create_annotation_hash(ann, image_lookup)
                            if ann_hash and ann_hash in remaining_hashes:
                                to_remove.append(i)
                                remaining_hashes.remove(ann_hash)

                        for i in reversed(to_remove):
                            annotations.pop(i)
                            json_removed_count += 1

                        # 重新编号annotation ID
                        for i, ann in enumerate(annotations, 1):
                            ann['id'] = i

                self.log(f"✓ 移除了 {json_removed_count} 个跨JSON文件重复标注\n")

            # 保存修复后的文件
            saved_count = 0
            for json_file, data in json_data.items():
                rel_path = self._safe_relpath(json_file, base_dir)
                output_path = os.path.join(output_dir, rel_path)
                os.makedirs(os.path.dirname(output_path), exist_ok=True)

                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                saved_count += 1

            self.log(f"✓ 已保存 {saved_count} 个修复后的文件到: {output_dir}\n")
            self.log(f"======= 修复完成 =======\n")

            messagebox.showinfo("✅ 修复完成",
                f"修复已完成！\n\n"
                f"• 重命名了 {renamed_count} 个图片引用\n"
                f"• 复制了 {copied_image_count} 个重命名后的图片文件\n"
                f"• 移除了 {removed_count} 个重复标注\n"
                f"• 移除了 {json_removed_count} 个跨JSON文件重复标注\n"
                f"• 保存了 {saved_count} 个文件\n\n"
                f"备份目录: {backup_dir}\n"
                f"输出目录: {output_dir}"
            )

        except Exception as e:
            self.log(f"修复过程中发生错误: {str(e)}\n")
            messagebox.showerror("❌ 修复失败", f"修复过程中发生错误:\n{str(e)}")


def main():
    """主函数"""
    root = tk.Tk()
    app = COCOValidatorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
