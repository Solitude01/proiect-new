#!/usr/bin/env python
# coding: utf-8

import os
import json
import glob
import shutil
import os.path as osp
import numpy as np
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from tqdm import tqdm
import threading
from PIL import Image, ImageTk, ImageDraw
import webbrowser
import random
import datetime

class SimpleLabelme2COCO:
    def __init__(self):
        self.label_to_num = {}
        self.categories_list = []
        self.labels_list = []
        
    def images_labelme(self, data, num):
        image = {}
        image['height'] = data['imageHeight']
        image['width'] = data['imageWidth']
        image['id'] = num + 1
        if '\\' in data['imagePath']:
            image['file_name'] = data['imagePath'].split('\\')[-1]
        else:
            image['file_name'] = data['imagePath'].split('/')[-1]
        return image
    
    def categories(self, label):
        category = {}
        category['supercategory'] = 'component'
        category['id'] = len(self.labels_list) + 1
        category['name'] = label
        return category
    
    def annotations_polygon(self, height, width, points, label, image_num, object_num):
        annotation = {}
        annotation['segmentation'] = [list(np.asarray(points).flatten())]
        annotation['iscrowd'] = 0
        annotation['image_id'] = image_num + 1
        annotation['bbox'] = list(map(float, self.get_bbox(height, width, points)))
        annotation['area'] = annotation['bbox'][2] * annotation['bbox'][3]
        annotation['category_id'] = self.label_to_num[label]
        annotation['id'] = object_num + 1
        return annotation
    
    def annotations_rectangle(self, points, label, image_num, object_num):
        annotation = {}
        # 正确处理矩形的四个顶点，按逆时针顺序：左上->右上->右下->左下
        # points[0] = [x1, y1] 左上角, points[1] = [x2, y2] 右下角
        x1, y1 = points[0]
        x2, y2 = points[1]
        
        # 确保按逆时针顺序排列顶点
        rect_points = [
            [x1, y1],  # 左上
            [x2, y1],  # 右上
            [x2, y2],  # 右下
            [x1, y2]   # 左下
        ]
        
        annotation['segmentation'] = [list(np.asarray(rect_points).flatten())]
        annotation['iscrowd'] = 0
        annotation['image_id'] = image_num + 1
        annotation['bbox'] = list(
            map(float, [
                points[0][0], points[0][1], points[1][0] - points[0][0], points[1][1] - points[0][1]
            ]))
        annotation['area'] = annotation['bbox'][2] * annotation['bbox'][3]
        annotation['category_id'] = self.label_to_num[label]
        annotation['id'] = object_num + 1
        return annotation
    
    def get_bbox(self, height, width, points):
        polygons = points
        mask = np.zeros([height, width], dtype=np.uint8)
        mask = Image.fromarray(mask)
        xy = list(map(tuple, polygons))
        ImageDraw.Draw(mask).polygon(xy=xy, outline=1, fill=1)
        mask = np.array(mask, dtype=bool)
        index = np.argwhere(mask == 1)
        rows = index[:, 0]
        clos = index[:, 1]
        left_top_r = np.min(rows)
        left_top_c = np.min(clos)
        right_bottom_r = np.max(rows)
        right_bottom_c = np.max(clos)
        return [
            left_top_c, left_top_r, right_bottom_c - left_top_c,
            right_bottom_r - left_top_r
        ]

class DatasetSplitter:
    """数据集切分类"""
    
    def __init__(self, train_ratio=0.8, test_ratio=0.1, verify_ratio=0.1):
        """
        初始化数据集切分器
        
        Args:
            train_ratio: 训练集比例
            test_ratio: 测试集比例  
            verify_ratio: 验证集比例
        """
        self.train_ratio = train_ratio
        self.test_ratio = test_ratio
        self.verify_ratio = verify_ratio
        
        # 验证比例总和是否为1
        total = train_ratio + test_ratio + verify_ratio
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"比例总和必须为1，当前为{total}")
    
    def split_dataset(self, file_list, random_seed=None):
        """
        切分数据集
        
        Args:
            file_list: 文件列表
            random_seed: 随机种子，确保结果可重现
            
        Returns:
            dict: 包含train、test、verify三个列表的字典
        """
        if random_seed is not None:
            random.seed(random_seed)
        
        # 随机打乱文件列表
        shuffled_files = file_list.copy()
        random.shuffle(shuffled_files)
        
        total_files = len(shuffled_files)
        train_count = int(total_files * self.train_ratio)
        test_count = int(total_files * self.test_ratio)
        
        # 分配文件
        train_files = shuffled_files[:train_count]
        test_files = shuffled_files[train_count:train_count + test_count]
        verify_files = shuffled_files[train_count + test_count:]
        
        return {
            'train': train_files,
            'test': test_files,
            'verify': verify_files
        }

class MultiFolderDatasetSplitter:
    """多文件夹数据集切分类"""
    
    def __init__(self, train_ratio=0.8, test_ratio=0.1, verify_ratio=0.1, max_images_per_folder=2000, auto_split=True):
        """
        初始化多文件夹数据集切分器
        
        Args:
            train_ratio: 训练集比例
            test_ratio: 测试集比例  
            verify_ratio: 验证集比例
            max_images_per_folder: 每个文件夹最大图片数量
            auto_split: 是否自动分割大文件夹
        """
        self.train_ratio = train_ratio
        self.test_ratio = test_ratio
        self.verify_ratio = verify_ratio
        self.max_images_per_folder = max_images_per_folder
        self.auto_split = auto_split
        
        # 验证比例总和是否为1
        total = train_ratio + test_ratio + verify_ratio
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"比例总和必须为1，当前为{total}")
    
    def split_multiple_folders(self, folder_files_dict, random_seed=None):
        """
        对多个文件夹分别进行切分
        
        Args:
            folder_files_dict: 文件夹路径到文件列表的字典
            random_seed: 随机种子，确保结果可重现
            
        Returns:
            dict: 包含train、test、verify三个列表的字典，每个列表包含所有文件夹的文件
        """
        if random_seed is not None:
            random.seed(random_seed)
        
        all_train_files = []
        all_test_files = []
        all_verify_files = []
        
        # 为每个文件夹单独切分
        for folder_path, file_list in folder_files_dict.items():
            if not file_list:
                continue
                
            # 随机打乱当前文件夹的文件列表
            shuffled_files = file_list.copy()
            random.shuffle(shuffled_files)
            
            total_files = len(shuffled_files)
            train_count = int(total_files * self.train_ratio)
            test_count = int(total_files * self.test_ratio)
            
            # 分配文件
            folder_train_files = shuffled_files[:train_count]
            folder_test_files = shuffled_files[train_count:train_count + test_count]
            folder_verify_files = shuffled_files[train_count + test_count:]
            
            # 添加到总列表
            all_train_files.extend(folder_train_files)
            all_test_files.extend(folder_test_files)
            all_verify_files.extend(folder_verify_files)
        
        return {
            'train': all_train_files,
            'test': all_test_files,
            'verify': all_verify_files
        }
    
    def get_folder_split_info(self, folder_files_dict, random_seed=None):
        """
        获取每个文件夹的切分信息
        
        Args:
            folder_files_dict: 文件夹路径到文件列表的字典
            random_seed: 随机种子
            
        Returns:
            dict: 每个文件夹的切分详细信息
        """
        if random_seed is not None:
            random.seed(random_seed)
        
        folder_info = {}
        
        for folder_path, file_list in folder_files_dict.items():
            if not file_list:
                folder_info[folder_path] = {'train': 0, 'test': 0, 'verify': 0, 'total': 0}
                continue
            
            # 随机打乱当前文件夹的文件列表
            shuffled_files = file_list.copy()
            random.shuffle(shuffled_files)
            
            total_files = len(shuffled_files)
            train_count = int(total_files * self.train_ratio)
            test_count = int(total_files * self.test_ratio)
            
            folder_info[folder_path] = {
                'train': train_count,
                'test': test_count,
                'verify': total_files - train_count - test_count,
                'total': total_files
            }
        
        return folder_info
    
    def split_large_folders(self, folder_files_dict, log_callback=None):
        """
        分割大文件夹，确保每个文件夹不超过最大图片数量
        
        Args:
            folder_files_dict: 文件夹路径到文件列表的字典
            log_callback: 日志回调函数
            
        Returns:
            dict: 分割后的文件夹字典，可能包含子文件夹
        """
        if not self.auto_split:
            return folder_files_dict
        
        def log(message):
            if log_callback:
                log_callback(message)
        
        split_folders_dict = {}
        
        for folder_path, file_list in folder_files_dict.items():
            if len(file_list) <= self.max_images_per_folder:
                # 不需要分割
                split_folders_dict[folder_path] = file_list
            else:
                # 需要分割
                folder_name = os.path.basename(folder_path)
                if not folder_name:
                    folder_name = "folder"
                
                log(f"文件夹 {folder_name} 有 {len(file_list)} 张图片，超过上限 {self.max_images_per_folder}，开始分割...")
                
                # 计算需要分割成多少个子文件夹
                num_splits = (len(file_list) + self.max_images_per_folder - 1) // self.max_images_per_folder
                
                # 随机打乱文件列表以确保均匀分布
                shuffled_files = file_list.copy()
                random.shuffle(shuffled_files)
                
                # 分割文件
                for i in range(num_splits):
                    start_idx = i * self.max_images_per_folder
                    end_idx = min((i + 1) * self.max_images_per_folder, len(shuffled_files))
                    sub_files = shuffled_files[start_idx:end_idx]
                    
                    # 创建子文件夹路径标识
                    sub_folder_key = f"{folder_path}_part{i+1:02d}"
                    split_folders_dict[sub_folder_key] = sub_files
                    
                    log(f"  创建子文件夹 {folder_name}_part{i+1:02d}: {len(sub_files)} 张图片")
        
        return split_folders_dict

class MaterialDesignGUI:
    def __init__(self):
        try:
            print("开始初始化GUI...")
            self.root = tk.Tk()
            self.root.title("Labelme to COCO 转换器 - 多文件夹数据集切分版")
            self.root.geometry("1200x800")
            self.root.minsize(1000, 650)
            print("窗口创建成功")
            
            # 优化初始显示
            self.root.state('normal')  # 确保窗口正常显示
            self.root.update_idletasks()
            print("窗口状态设置完成")
        except Exception as e:
            print(f"窗口初始化失败: {e}")
            import traceback
            traceback.print_exc()
        
        # Google Material Design 3 官方配色方案
        self.colors = {
            # Primary colors
            'primary': '#6750A4',
            'on_primary': '#FFFFFF',
            'primary_container': '#EADDFF',
            'on_primary_container': '#21005D',
            
            # Secondary colors
            'secondary': '#625B71',
            'on_secondary': '#FFFFFF', 
            'secondary_container': '#E8DEF8',
            'on_secondary_container': '#1D192B',
            
            # Tertiary colors
            'tertiary': '#7D5260',
            'on_tertiary': '#FFFFFF',
            'tertiary_container': '#FFD8E4',
            'on_tertiary_container': '#31111D',
            
            # Error colors
            'error': '#BA1A1A',
            'on_error': '#FFFFFF',
            'error_container': '#FFDAD6',
            'on_error_container': '#410002',
            
            # Surface colors
            'surface': '#FFFBFE',
            'on_surface': '#1C1B1F',
            'surface_variant': '#E7E0EC',
            'on_surface_variant': '#49454F',
            'surface_container': '#F3EDF7',
            'surface_container_low': '#F7F2FA',
            'surface_container_high': '#ECE6F0',
            'surface_container_highest': '#E6E0E9',
            
            # Background colors
            'background': '#FFFBFE',
            'on_background': '#1C1B1F',
            
            # Outline colors
            'outline': '#79747E',
            'outline_variant': '#CAC4D0',
            
            # Other colors
            'shadow': '#000000',
            'scrim': '#000000',
            'inverse_surface': '#313033',
            'inverse_on_surface': '#F4EFF4',
            'inverse_primary': '#D0BCFF',
            
            # Success colors (Material Design extended)
            'success': '#146C2E',
            'on_success': '#FFFFFF',
            'success_container': '#A7F3C0',
            'on_success_container': '#002106',
            
            # Warning colors (Material Design extended)
            'warning': '#7A5900',
            'on_warning': '#FFFFFF',
            'warning_container': '#FFE08C',
            'on_warning_container': '#261900'
        }
        
        # 现在可以安全地使用颜色配置窗口
        self.root.configure(bg=self.colors['background'])
        
        # Material Design 阴影效果配置
        self.shadow_colors = {
            'elevation_1': '#00000012',
            'elevation_2': '#0000001f', 
            'elevation_3': '#00000024',
            'elevation_4': '#00000033'
        }
        
        # 多文件夹管理
        self.input_folders = {}  # 文件夹路径 -> 文件列表的映射
        self.folder_names = {}   # 文件夹路径 -> 显示名称的映射
        self.folder_labels = {}  # 文件夹路径 -> 标签集合的映射
        print("多文件夹管理变量初始化完成")
        
        # 设置窗口图标和样式
        try:
            print("开始设置样式...")
            self.setup_styles()
            print("样式设置完成")
        except Exception as e:
            print(f"样式设置失败: {e}")
            import traceback
            traceback.print_exc()
        
        try:
            print("开始创建主界面...")
            self.create_main_interface()
            print("主界面创建完成")
        except Exception as e:
            print(f"主界面创建失败: {e}")
            import traceback
            traceback.print_exc()
        
        try:
            print("开始居中窗口...")
            self.center_window()
            print("窗口居中完成")
        except Exception as e:
            print(f"窗口居中失败: {e}")
            import traceback
            traceback.print_exc()
        
    def setup_styles(self):
        """设置Material Design 3样式"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # 基础框架样式 - 添加明显边框
        style.configure('Material.TFrame', 
                       background=self.colors['background'],
                       relief='solid',
                       borderwidth=1)
        
        # 卡片样式框架 - 使用更明显的边框
        style.configure('MaterialCard.TFrame',
                       background=self.colors['surface_container'],
                       relief='solid',
                       borderwidth=2)
        
        # 高级卡片样式 - 使用更明显的边框
        style.configure('MaterialCardHigh.TFrame',
                       background=self.colors['surface_container_high'],
                       relief='solid',
                       borderwidth=2)
        
        # 标签样式 - 使用明显的颜色对比
        style.configure('Material.TLabel', 
                       background=self.colors['background'],
                       foreground=self.colors['on_background'],
                       font=('Segoe UI', 10))
        
        style.configure('MaterialTitle.TLabel',
                       background=self.colors['primary_container'],
                       foreground=self.colors['on_primary_container'],
                       font=('Segoe UI', 24, 'bold'))
        
        style.configure('MaterialHeadline.TLabel',
                       background=self.colors['primary_container'],
                       foreground=self.colors['on_primary_container'],
                       font=('Segoe UI', 18, 'bold'),
                       relief='solid',
                       borderwidth=1)
        
        style.configure('MaterialSubheading.TLabel',
                       background=self.colors['secondary_container'],
                       foreground=self.colors['on_secondary_container'],
                       font=('Segoe UI', 12))
        
        style.configure('MaterialBody.TLabel',
                       background=self.colors['surface'],
                       foreground=self.colors['on_surface'],
                       font=('Segoe UI', 10, 'bold'))
        
        style.configure('MaterialCaption.TLabel',
                       background=self.colors['surface_variant'],
                       foreground=self.colors['on_surface_variant'],
                       font=('Segoe UI', 9))
        
        # 按钮样式 - 使用明显的颜色对比
        style.configure('MaterialFilledButton.TButton',
                       background=self.colors['primary'],
                       foreground=self.colors['on_primary'],
                       borderwidth=2,
                       focuscolor='none',
                       font=('Segoe UI', 10, 'bold'),
                       padding=(24, 10),
                       relief='solid')
        style.map('MaterialFilledButton.TButton',
                 background=[('active', self.colors['primary_dark']),
                           ('pressed', self.colors['primary_dark'])])
        
        style.configure('MaterialOutlinedButton.TButton',
                       background=self.colors['surface'],
                       foreground=self.colors['primary'],
                       borderwidth=2,
                       focuscolor='none',
                       font=('Segoe UI', 10, 'bold'),
                       padding=(24, 10),
                       relief='solid')
        style.map('MaterialOutlinedButton.TButton',
                 background=[('active', self.colors['primary_container']),
                           ('pressed', self.colors['primary_container'])],
                 bordercolor=[('active', self.colors['primary']),
                            ('pressed', self.colors['primary'])])
        
        style.configure('MaterialTextButton.TButton',
                       background=self.colors['secondary_container'],
                       foreground=self.colors['primary'],
                       borderwidth=1,
                       focuscolor='none',
                       font=('Segoe UI', 10, 'bold'),
                       padding=(12, 10),
                       relief='solid')
        style.map('MaterialTextButton.TButton',
                 background=[('active', self.colors['primary_container']),
                           ('pressed', self.colors['primary_container'])])
        
        # 表单控件样式
        style.configure('Material.TEntry',
                       fieldbackground=self.colors['surface_container'],
                       borderwidth=1,
                       bordercolor=self.colors['outline'],
                       relief='solid',
                       padding=(16, 12),
                       insertcolor=self.colors['primary'])
        style.map('Material.TEntry',
                 bordercolor=[('focus', self.colors['primary']),
                            ('active', self.colors['primary'])],
                 fieldbackground=[('focus', self.colors['surface']),
                                ('active', self.colors['surface'])])
        
        style.configure('Material.TCombobox',
                       fieldbackground=self.colors['surface_container'],
                       borderwidth=1,
                       bordercolor=self.colors['outline'],
                       relief='solid',
                       padding=(16, 12),
                       arrowcolor=self.colors['on_surface_variant'])
        style.map('Material.TCombobox',
                 bordercolor=[('focus', self.colors['primary']),
                            ('active', self.colors['primary'])],
                 fieldbackground=[('focus', self.colors['surface']),
                                ('active', self.colors['surface'])])
        
        style.configure('Material.TSpinbox',
                       fieldbackground=self.colors['surface_container'],
                       borderwidth=1,
                       bordercolor=self.colors['outline'],
                       relief='solid',
                       padding=(16, 12))
        style.map('Material.TSpinbox',
                 bordercolor=[('focus', self.colors['primary']),
                            ('active', self.colors['primary'])],
                 fieldbackground=[('focus', self.colors['surface']),
                                ('active', self.colors['surface'])])
        
        # 进度条样式
        style.configure('Material.Horizontal.TProgressbar',
                       background=self.colors['primary'],
                       troughcolor=self.colors['surface_container'],
                       borderwidth=0,
                       lightcolor=self.colors['primary'],
                       darkcolor=self.colors['primary'])
        
        # 树形视图样式
        style.configure('Material.Treeview',
                       background=self.colors['surface'],
                       foreground=self.colors['on_surface'],
                       fieldbackground=self.colors['surface'],
                       borderwidth=1,
                       bordercolor=self.colors['outline_variant'],
                       relief='solid',
                       rowheight=32)
        style.map('Material.Treeview',
                 background=[('selected', self.colors['primary_container'])],
                 foreground=[('selected', self.colors['on_primary_container'])])
        
        style.configure('Material.Treeview.Heading',
                       background=self.colors['surface_container_high'],
                       foreground=self.colors['on_surface'],
                       font=('Segoe UI', 10, 'bold'),
                       relief='flat',
                       borderwidth=1,
                       bordercolor=self.colors['outline_variant'])
        style.map('Material.Treeview.Heading',
                 background=[('active', self.colors['surface_container_highest'])])
        
        # 标签框样式
        style.configure('Material.TLabelframe',
                       background=self.colors['surface'],
                       foreground=self.colors['on_surface'],
                       font=('Segoe UI', 12, 'bold'),
                       borderwidth=1,
                       bordercolor=self.colors['outline_variant'],
                       relief='solid')
        
        style.configure('Material.TLabelframe.Label',
                       background=self.colors['surface'],
                       foreground=self.colors['primary'],
                       font=('Segoe UI', 12, 'bold'))
    
    def create_elevated_card(self, parent, elevation=1, **kwargs):
        """创建带阴影效果的卡片"""
        # 主容器
        container = ttk.Frame(parent, style='Material.TFrame')
        
        # 模拟阴影效果的底层
        if elevation >= 2:
            shadow_frame = ttk.Frame(container, style='MaterialCardHigh.TFrame')
            shadow_frame.pack(fill=tk.BOTH, expand=True, padx=(0, 2), pady=(0, 2))
            
            # 内容卡片
            content_frame = ttk.Frame(shadow_frame, style='MaterialCard.TFrame', **kwargs)
            content_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        else:
            # 低阴影卡片
            content_frame = ttk.Frame(container, style='MaterialCard.TFrame', **kwargs)
            content_frame.pack(fill=tk.BOTH, expand=True)
        
        return container, content_frame
    
    def add_hover_effect(self, widget, hover_style=None, normal_style=None):
        """为控件添加鼠标悬停效果"""
        def on_enter(event):
            if hover_style:
                widget.configure(style=hover_style)
                
        def on_leave(event):
            if normal_style:
                widget.configure(style=normal_style)
                
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
        
        return widget
    
    def create_modern_button(self, parent, text, command=None, style_type='filled', **kwargs):
        """创建现代化按钮并添加悬停效果"""
        style_map = {
            'filled': 'MaterialFilledButton.TButton',
            'outlined': 'MaterialOutlinedButton.TButton', 
            'text': 'MaterialTextButton.TButton'
        }
        
        button_style = style_map.get(style_type, 'MaterialFilledButton.TButton')
        
        button = ttk.Button(parent, text=text, command=command, style=button_style, **kwargs)
        
        return button
    
    def animate_progress_bar(self, target_value, duration=300):
        """动画化进度条更新"""
        current_value = self.progress_var.get()
        steps = 20
        step_value = (target_value - current_value) / steps
        step_delay = duration // steps
        
        def update_step(step):
            if step <= steps:
                new_value = current_value + (step_value * step)
                self.progress_var.set(new_value)
                self.root.after(step_delay, lambda: update_step(step + 1))
            else:
                self.progress_var.set(target_value)
        
        update_step(1)
    
    def fade_in_widget(self, widget, duration=300):
        """控件淡入效果模拟"""
        # 由于Tkinter限制，这里用包装/显示模拟淡入
        widget.pack_forget()
        self.root.after(50, lambda: widget.pack(fill=tk.X, pady=(0, 16)))
    
    def create_loading_indicator(self, parent):
        """创建加载指示器"""
        loading_frame = ttk.Frame(parent, style='MaterialCard.TFrame')
        
        loading_label = ttk.Label(loading_frame, 
                                text="⏳ 正在处理...", 
                                style='MaterialBody.TLabel')
        loading_label.pack(pady=20)
        
    def create_header(self, parent):
        """创建顶部标题栏"""
        header_card = self.create_elevated_card(parent, elevation=1)[1]
        header_card.pack(fill=tk.X, pady=(0, 16))
        
        header_content = ttk.Frame(header_card, style='MaterialCard.TFrame')
        header_content.pack(fill=tk.X, padx=24, pady=16)
        
        # 标题和副标题
        title_frame = ttk.Frame(header_content, style='MaterialCard.TFrame')
        title_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        title_label = ttk.Label(title_frame, 
                               text="Labelme to COCO 转换器",
                               style='MaterialHeadline.TLabel')
        title_label.pack(anchor=tk.W)
        
        subtitle_label = ttk.Label(title_frame,
                                  text="智能数据集管理与格式转换工具",
                                  style='MaterialCaption.TLabel')
        subtitle_label.pack(anchor=tk.W, pady=(4, 0))
        
        # 快捷操作区域
        actions_frame = ttk.Frame(header_content, style='MaterialCard.TFrame')
        actions_frame.pack(side=tk.RIGHT)
        
        # 主要转换按钮
        self.convert_btn = ttk.Button(actions_frame,
                                    text="🚀 开始转换",
                                    command=self.start_conversion,
                                    style='MaterialFilledButton.TButton')
        self.convert_btn.pack(side=tk.RIGHT)
        
        # 进度条
        progress_frame = ttk.Frame(header_content, style='MaterialCard.TFrame')
        progress_frame.pack(fill=tk.X, pady=(12, 0))
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame,
                                          variable=self.progress_var,
                                          style='Material.Horizontal.TProgressbar')
        self.progress_bar.pack(fill=tk.X, pady=2)
    def create_left_panel(self, parent):
        """创建左侧控制面板"""
        # 设置面板背景色
        parent.configure(bg=self.colors['surface_container_low'])
        
        # 面板标题
        panel_title = tk.Label(parent,
                              text="⚙️ 配置面板",
                              bg=self.colors['surface_container_low'],
                              fg=self.colors['on_surface'],
                              font=('Segoe UI', 14, 'bold'))
        panel_title.pack(anchor=tk.W, padx=16, pady=(16, 8))
        
        # 创建简化的内容区域
        content_frame = tk.Frame(parent, bg=self.colors['surface_container_low'], relief='flat')
        content_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        
        # 创建内容分组
        self.create_input_section(content_frame)
        self.create_output_section(content_frame)
        self.create_split_section(content_frame)
        self.create_action_section(content_frame)  
    def create_right_panel(self, parent):
        """创建右侧数据面板 - 标签页设计"""
        # 设置右侧面板背景色
        parent.configure(bg=self.colors['surface_container'])
        
        # 面板标题
        panel_title = tk.Label(parent,
                              text="📊 数据展示面板",
                              bg=self.colors['surface_container'],
                              fg=self.colors['on_surface'],
                              font=('Segoe UI', 14, 'bold'))
        panel_title.pack(anchor=tk.W, padx=16, pady=(16, 8))
        
        # 创建Notebook控件作为标签页
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        
        # 文件夹数据标签页
        data_frame = tk.Frame(notebook, bg=self.colors['surface'])
        notebook.add(data_frame, text="📁 文件夹管理")
        self.create_data_management_tab(data_frame)
        
        # 标签映射标签页
        label_frame = tk.Frame(notebook, bg=self.colors['surface'])
        notebook.add(label_frame, text="🏷️ 标签映射")
        self.create_label_management_tab(label_frame)
        
        # 实时日志标签页  
        log_frame = tk.Frame(notebook, bg=self.colors['surface'])
        notebook.add(log_frame, text="📋 实时日志")
        self.create_log_tab(log_frame)
    
    def create_data_management_tab(self, parent):
        """创建文件夹数据管理标签页"""
        # 设置父容器背景
        parent.configure(bg=self.colors['surface'])
        
        # 标题栏
        title_frame = tk.Frame(parent, bg=self.colors['surface'])
        title_frame.pack(fill=tk.X, padx=16, pady=16)
        
        title_label = tk.Label(title_frame, 
                              text="📁 文件夹信息总览",
                              bg=self.colors['surface'],
                              fg=self.colors['on_surface'],
                              font=('Segoe UI', 14, 'bold'))
        title_label.pack(side=tk.LEFT)
        
        # 按钮区域
        buttons_frame = tk.Frame(title_frame, bg=self.colors['surface'])
        buttons_frame.pack(side=tk.RIGHT)
        
        # 刷新按钮
        refresh_btn = tk.Button(buttons_frame,
                               text="🔄 刷新数据",
                               command=self.refresh_folders_data,
                               bg=self.colors['secondary'],
                               fg=self.colors['on_secondary'],
                               font=('Segoe UI', 9),
                               relief='flat',
                               cursor='hand2')
        refresh_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        # 扫描按钮
        scan_btn = tk.Button(buttons_frame,
                            text="🔍 扫描检查",
                            command=self.scan_folders_integrity,
                            bg=self.colors['warning'],
                            fg=self.colors['on_warning'],
                            font=('Segoe UI', 9),
                            relief='flat',
                            cursor='hand2')
        scan_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        # 修改标签按钮
        modify_labels_btn = tk.Button(buttons_frame,
                                     text="✏️ 修改标签",
                                     command=self.modify_folder_labels,
                                     bg=self.colors['tertiary'],
                                     fg=self.colors['on_tertiary'],
                                     font=('Segoe UI', 9),
                                     relief='flat',
                                     cursor='hand2')
        modify_labels_btn.pack(side=tk.LEFT)
        
        # 文件夹详情表格
        self.folders_tree = ttk.Treeview(parent,
                                       columns=('Name', 'Path', 'Files', 'Labels', 'Status'),
                                       show='headings',
                                       height=12)
        
        # 设置列标题和宽度
        self.folders_tree.heading('Name', text='文件夹名称')
        self.folders_tree.heading('Path', text='路径')
        self.folders_tree.heading('Files', text='文件数')
        self.folders_tree.heading('Labels', text='标签数')
        self.folders_tree.heading('Status', text='状态')
        
        self.folders_tree.column('Name', width=150, anchor='w')
        self.folders_tree.column('Path', width=300, anchor='w')
        self.folders_tree.column('Files', width=80, anchor='center')
        self.folders_tree.column('Labels', width=80, anchor='center')
        self.folders_tree.column('Status', width=100, anchor='center')
        
        # 滚动条
        tree_scrollbar = tk.Scrollbar(parent, orient=tk.VERTICAL, command=self.folders_tree.yview)
        self.folders_tree.configure(yscrollcommand=tree_scrollbar.set)
        
        self.folders_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=(0, 10))
        
        # 绑定双击事件
        self.folders_tree.bind('<Double-1>', self.show_folder_labels_detail)
    
    def create_label_management_tab(self, parent):
        """创建标签映射管理标签页"""
        # 设置父容器背景
        parent.configure(bg=self.colors['surface'])
        
        # 标题
        title_label = tk.Label(parent,
                              text="🏷️ 标签映射管理",
                              bg=self.colors['surface'],
                              fg=self.colors['on_surface'],
                              font=('Segoe UI', 14, 'bold'))
        title_label.pack(anchor=tk.W, padx=16, pady=16)
        
        # 按钮区域
        button_frame = tk.Frame(parent, bg=self.colors['surface'])
        button_frame.pack(fill=tk.X, padx=16, pady=(0, 8))
        
        self.refresh_labels_btn = tk.Button(button_frame,
                                           text="🔄 刷新映射",
                                           command=self.refresh_label_mapping,
                                           bg=self.colors['secondary'],
                                           fg=self.colors['on_secondary'],
                                           state='disabled',
                                           font=('Segoe UI', 9),
                                           relief='flat',
                                           cursor='hand2')
        self.refresh_labels_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        self.save_mapping_btn = tk.Button(button_frame,
                                         text="💾 保存映射",
                                         command=self.save_label_mapping,
                                         bg=self.colors['tertiary'],
                                         fg=self.colors['on_tertiary'],
                                         font=('Segoe UI', 9),
                                         relief='flat',
                                         cursor='hand2')
        self.save_mapping_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        self.load_mapping_btn = tk.Button(button_frame,
                                         text="📁 加载映射",
                                         command=self.load_label_mapping,
                                         bg=self.colors['primary'],
                                         fg=self.colors['on_primary'],
                                         font=('Segoe UI', 9),
                                         relief='flat',
                                         cursor='hand2')
        self.load_mapping_btn.pack(side=tk.LEFT)
        
        # 标签映射表格
        self.labels_tree = ttk.Treeview(parent,
                                      columns=('ID', 'Label', 'Count', 'Status'),
                                      show='headings',
                                      height=10)
        
        # 设置列标题和宽度
        self.labels_tree.heading('ID', text='标签ID')
        self.labels_tree.heading('Label', text='标签名称')
        self.labels_tree.heading('Count', text='出现次数')
        self.labels_tree.heading('Status', text='状态')
        
        self.labels_tree.column('ID', width=80, anchor='center')
        self.labels_tree.column('Label', width=150, anchor='w')
        self.labels_tree.column('Count', width=100, anchor='center')
        self.labels_tree.column('Status', width=100, anchor='center')
        
        # 滚动条
        labels_scrollbar = tk.Scrollbar(parent, orient=tk.VERTICAL, command=self.labels_tree.yview)
        self.labels_tree.configure(yscrollcommand=labels_scrollbar.set)
        
        self.labels_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        labels_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=(0, 10))
        
        # 编辑区域
        edit_frame = tk.Frame(parent, bg=self.colors['surface_container'], relief='flat')
        edit_frame.pack(fill=tk.X, padx=16, pady=(0, 16))
        
        # 编辑控件
        tk.Label(edit_frame, 
                text="标签编辑:", 
                bg=self.colors['surface_container'], 
                fg=self.colors['on_surface'], 
                font=('Segoe UI', 10, 'bold')).pack(anchor=tk.W, padx=12, pady=(8, 4))
        
        edit_row1 = tk.Frame(edit_frame, bg=self.colors['surface_container'])
        edit_row1.pack(fill=tk.X, padx=12, pady=(0, 4))
        
        tk.Label(edit_row1, 
                text="标签:", 
                bg=self.colors['surface_container'], 
                fg=self.colors['on_surface'],
                font=('Segoe UI', 9)).pack(side=tk.LEFT)
        self.edit_label_var = tk.StringVar()
        self.edit_label_combobox = ttk.Combobox(edit_row1,
                                               textvariable=self.edit_label_var,
                                               width=15, state='readonly')
        self.edit_label_combobox.pack(side=tk.LEFT, padx=(8, 16))
        
        tk.Label(edit_row1, 
                text="新ID:", 
                bg=self.colors['surface_container'], 
                fg=self.colors['on_surface'],
                font=('Segoe UI', 9)).pack(side=tk.LEFT)
        self.edit_id_var = tk.StringVar()
        self.edit_id_entry = tk.Entry(edit_row1,
                                     textvariable=self.edit_id_var,
                                     width=8, 
                                     bg=self.colors['surface'], 
                                     fg=self.colors['on_surface'],
                                     font=('Segoe UI', 9),
                                     relief='flat',
                                     borderwidth=1)
        self.edit_id_entry.pack(side=tk.LEFT, padx=(8, 16))
        
        self.update_label_btn = tk.Button(edit_row1,
                                         text="更新ID",
                                         command=self.update_label_id,
                                         bg=self.colors['primary'],
                                         fg=self.colors['on_primary'],
                                         state='disabled',
                                         font=('Segoe UI', 9),
                                         relief='flat',
                                         cursor='hand2')
        self.update_label_btn.pack(side=tk.LEFT)
        
        # 当前选中信息
        self.current_label_info = tk.Label(edit_frame,
                                           text="请先选择一个标签",
                                           bg=self.colors['surface_container'],
                                           fg=self.colors['on_surface_variant'],
                                           font=('Segoe UI', 9))
        self.current_label_info.pack(anchor=tk.W, padx=12, pady=(0, 8))
        
        # 绑定选择事件
        self.labels_tree.bind('<<TreeviewSelect>>', self.on_label_select)
    
    def create_log_tab(self, parent):
        """创建实时日志标签页"""
        # 设置父容器背景
        parent.configure(bg=self.colors['surface'])
        
        # 标题栏
        title_frame = tk.Frame(parent, bg=self.colors['surface'])
        title_frame.pack(fill=tk.X, padx=16, pady=16)
        
        title_label = tk.Label(title_frame,
                              text="📋 实时处理日志",
                              bg=self.colors['surface'],
                              fg=self.colors['on_surface'],
                              font=('Segoe UI', 14, 'bold'))
        title_label.pack(side=tk.LEFT)
        
        # 清空日志按钮
        clear_btn = tk.Button(title_frame,
                             text="🗑️ 清空日志",
                             command=self.clear_log,
                             bg=self.colors['tertiary'],
                             fg=self.colors['on_tertiary'],
                             font=('Segoe UI', 9),
                             relief='flat',
                             cursor='hand2')
        clear_btn.pack(side=tk.RIGHT)
        
        # 日志文本框
        self.log_text = tk.Text(parent,
                               wrap=tk.WORD,
                               bg=self.colors['surface_container'],
                               fg=self.colors['on_surface'],
                               font=('Consolas', 9),
                               relief='flat',
                               borderwidth=1,
                               selectbackground=self.colors['primary_container'],
                               selectforeground=self.colors['on_primary_container'])
        
        # 滚动条
        log_scrollbar = tk.Scrollbar(parent, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=(0, 16))
    
    def clear_log(self):
        """清空日志"""
        self.log_text.delete(1.0, tk.END)
        self.log_message("日志已清空")
    
    def create_data_tab(self, parent):
        """兼容方法"""
        self.create_data_management_tab(parent)
    
    def create_label_tab(self, parent):
        """兼容方法"""
        self.create_label_management_tab(parent)
    def create_input_section(self, parent):
        """创建输入文件夹配置区域"""
        # 创建输入文件夹区域
        input_frame = tk.Frame(parent, bg=self.colors['surface_container_high'], relief='flat')
        input_frame.pack(fill=tk.X, padx=0, pady=(0, 12))
        
        # 标题
        title_label = tk.Label(input_frame, 
                              text="📁 输入文件夹", 
                              bg=self.colors['surface_container_high'], 
                              fg=self.colors['on_surface'], 
                              font=('Segoe UI', 12, 'bold'))
        title_label.pack(anchor=tk.W, padx=16, pady=(12, 8))
        
        # 文件夹操作按钮
        buttons_frame = tk.Frame(input_frame, bg=self.colors['surface_container_high'])
        buttons_frame.pack(fill=tk.X, padx=16, pady=(0, 8))
        
        add_btn = tk.Button(buttons_frame,
                           text="➕ 添加文件夹",
                           command=self.add_input_folder,
                           bg=self.colors['primary'],
                           fg=self.colors['on_primary'],
                           font=('Segoe UI', 9),
                           relief='flat',
                           cursor='hand2')
        add_btn.pack(side=tk.LEFT, padx=(0, 4))
        
        add_multi_btn = tk.Button(buttons_frame,
                                 text="📁 添加多个文件夹",
                                 command=self.add_multiple_folders,
                                 bg=self.colors['primary'],
                                 fg=self.colors['on_primary'],
                                 font=('Segoe UI', 9),
                                 relief='flat',
                                 cursor='hand2')
        add_multi_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        remove_btn = tk.Button(buttons_frame,
                              text="➖ 移除文件夹",
                              command=self.remove_input_folder,
                              bg=self.colors['secondary'],
                              fg=self.colors['on_secondary'],
                              font=('Segoe UI', 9),
                              relief='flat',
                              cursor='hand2')
        remove_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        clear_btn = tk.Button(buttons_frame,
                             text="🗑 清空全部",
                             command=self.clear_all_folders,
                             bg=self.colors['tertiary'],
                             fg=self.colors['on_tertiary'],
                             font=('Segoe UI', 9),
                             relief='flat',
                             cursor='hand2')
        clear_btn.pack(side=tk.LEFT)
        
        # 统计信息
        self.folders_stats_label = tk.Label(input_frame,
                                            text="已添加 0 个文件夹",
                                            bg=self.colors['surface_container_high'],
                                            fg=self.colors['on_surface_variant'],
                                            font=('Segoe UI', 9))
        self.folders_stats_label.pack(anchor=tk.W, padx=16, pady=(0, 8))
        
        # 文件夹列表
        self.folders_listbox = tk.Listbox(input_frame,
                                        bg=self.colors['surface'],
                                        fg=self.colors['on_surface'],
                                        selectbackground=self.colors['primary_container'],
                                        selectforeground=self.colors['on_primary_container'],
                                        font=('Segoe UI', 9),
                                        height=3,
                                        relief='flat',
                                        borderwidth=1,
                                        highlightcolor=self.colors['primary'])
        self.folders_listbox.pack(fill=tk.X, padx=16, pady=(0, 12))
    
    def create_output_section(self, parent):
        """创建输出目录配置区域"""
        # 创建输出目录区域
        output_frame = tk.Frame(parent, bg=self.colors['surface_container_high'], relief='flat')
        output_frame.pack(fill=tk.X, padx=0, pady=(0, 12))
        
        # 标题
        title_label = tk.Label(output_frame, 
                              text="📁 输出目录", 
                              bg=self.colors['surface_container_high'], 
                              fg=self.colors['on_surface'], 
                              font=('Segoe UI', 12, 'bold'))
        title_label.pack(anchor=tk.W, padx=16, pady=(12, 8))
        
        # 输出目录选择
        dir_frame = tk.Frame(output_frame, bg=self.colors['surface_container_high'])
        dir_frame.pack(fill=tk.X, padx=16, pady=(0, 12))
        
        self.output_var = tk.StringVar()
        self.output_entry = tk.Entry(dir_frame,
                                    textvariable=self.output_var,
                                    bg=self.colors['surface'],
                                    fg=self.colors['on_surface'],
                                    font=('Segoe UI', 9),
                                    relief='flat',
                                    borderwidth=1,
                                    highlightcolor=self.colors['primary'])
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        
        browse_btn = tk.Button(dir_frame,
                              text="📂 浏览",
                              command=self.select_output_dir,
                              bg=self.colors['secondary'],
                              fg=self.colors['on_secondary'],
                              font=('Segoe UI', 9),
                              relief='flat',
                              cursor='hand2')
        browse_btn.pack(side=tk.RIGHT)
    
    def create_split_section(self, parent):
        """创建数据集切分配置区域"""
        # 创建数据集切分区域
        split_frame = tk.Frame(parent, bg=self.colors['surface_container_high'], relief='flat')
        split_frame.pack(fill=tk.X, padx=0, pady=(0, 12))
        
        # 标题
        title_label = tk.Label(split_frame, 
                              text="⚙️ 数据集切分", 
                              bg=self.colors['surface_container_high'], 
                              fg=self.colors['on_surface'], 
                              font=('Segoe UI', 12, 'bold'))
        title_label.pack(anchor=tk.W, padx=16, pady=(12, 8))
        
        # 训练集
        train_frame = tk.Frame(split_frame, bg=self.colors['surface_container_high'])
        train_frame.pack(fill=tk.X, padx=16, pady=(0, 4))
        
        tk.Label(train_frame, 
                text="🏅 训练集", 
                bg=self.colors['surface_container_high'], 
                fg=self.colors['on_surface'],
                font=('Segoe UI', 9)).pack(side=tk.LEFT)
        self.train_ratio_var = tk.DoubleVar(value=0.8)
        tk.Scale(train_frame, from_=0.1, to=0.9, resolution=0.1, orient='horizontal',
                variable=self.train_ratio_var, 
                bg=self.colors['surface_container_high'], 
                fg=self.colors['on_surface'],
                troughcolor=self.colors['primary'],
                length=120).pack(side=tk.RIGHT)
        
        # 测试集
        test_frame = tk.Frame(split_frame, bg=self.colors['surface_container_high'])
        test_frame.pack(fill=tk.X, padx=16, pady=(0, 4))
        
        tk.Label(test_frame, 
                text="🧪 测试集", 
                bg=self.colors['surface_container_high'], 
                fg=self.colors['on_surface'],
                font=('Segoe UI', 9)).pack(side=tk.LEFT)
        self.test_ratio_var = tk.DoubleVar(value=0.1)
        tk.Scale(test_frame, from_=0.05, to=0.3, resolution=0.05, orient='horizontal',
                variable=self.test_ratio_var, 
                bg=self.colors['surface_container_high'], 
                fg=self.colors['on_surface'],
                troughcolor=self.colors['secondary'],
                length=120).pack(side=tk.RIGHT)
        
        # 验证集
        verify_frame = tk.Frame(split_frame, bg=self.colors['surface_container_high'])
        verify_frame.pack(fill=tk.X, padx=16, pady=(0, 8))
        
        tk.Label(verify_frame, 
                text="✅ 验证集", 
                bg=self.colors['surface_container_high'], 
                fg=self.colors['on_surface'],
                font=('Segoe UI', 9)).pack(side=tk.LEFT)
        self.verify_ratio_var = tk.DoubleVar(value=0.1)
        tk.Scale(verify_frame, from_=0.05, to=0.3, resolution=0.05, orient='horizontal',
                variable=self.verify_ratio_var, 
                bg=self.colors['surface_container_high'], 
                fg=self.colors['on_surface'],
                troughcolor=self.colors['tertiary'],
                length=120).pack(side=tk.RIGHT)
        
        # 随机种子
        seed_frame = tk.Frame(split_frame, bg=self.colors['surface_container_high'])
        seed_frame.pack(fill=tk.X, padx=16, pady=(0, 8))
        
        tk.Label(seed_frame, 
                text="🎲 随机种子", 
                bg=self.colors['surface_container_high'], 
                fg=self.colors['on_surface'],
                font=('Segoe UI', 9)).pack(side=tk.LEFT)
        self.seed_var = tk.StringVar()
        seed_entry = tk.Entry(seed_frame, textvariable=self.seed_var,
                             width=12, 
                             bg=self.colors['surface'], 
                             fg=self.colors['on_surface'],
                             font=('Segoe UI', 9),
                             relief='flat',
                             borderwidth=1,
                             highlightcolor=self.colors['primary'])
        seed_entry.pack(side=tk.RIGHT)
        
        # 数量限制选项
        limit_frame = tk.Frame(split_frame, bg=self.colors['surface_container_high'])
        limit_frame.pack(fill=tk.X, padx=16, pady=(0, 8))
        
        tk.Label(limit_frame, 
                text="📊 每文件夹图片上限", 
                bg=self.colors['surface_container_high'], 
                fg=self.colors['on_surface'],
                font=('Segoe UI', 9)).pack(side=tk.LEFT)
        self.max_images_per_folder_var = tk.StringVar(value="2000")
        limit_entry = tk.Entry(limit_frame, textvariable=self.max_images_per_folder_var,
                              width=8, 
                              bg=self.colors['surface'], 
                              fg=self.colors['on_surface'],
                              font=('Segoe UI', 9),
                              relief='flat',
                              borderwidth=1,
                              highlightcolor=self.colors['primary'])
        limit_entry.pack(side=tk.RIGHT)
        
        # 自动分割选项
        auto_split_frame = tk.Frame(split_frame, bg=self.colors['surface_container_high'])
        auto_split_frame.pack(fill=tk.X, padx=16, pady=(0, 12))
        
        self.auto_split_var = tk.BooleanVar(value=True)
        auto_split_check = tk.Checkbutton(auto_split_frame,
                                         text="🔄 自动分割大文件夹 (超出上限时自动分割)",
                                         variable=self.auto_split_var,
                                         bg=self.colors['surface_container_high'],
                                         fg=self.colors['on_surface'],
                                         selectcolor=self.colors['primary'],
                                         font=('Segoe UI', 9),
                                         relief='flat')
        auto_split_check.pack(anchor=tk.W)
        
        # 设置摘要显示
        summary_frame = tk.Frame(split_frame, bg=self.colors['surface_container_high'])
        summary_frame.pack(fill=tk.X, padx=16, pady=(8, 12))
        
        self.settings_summary_label = tk.Label(summary_frame,
                                             text="当前设置: 训练集80%, 测试集10%, 验证集10%, 每文件夹最多2000张图片",
                                             bg=self.colors['surface_container_high'],
                                             fg=self.colors['on_surface_variant'],
                                             font=('Segoe UI', 8),
                                             wraplength=400,
                                             justify=tk.LEFT)
        self.settings_summary_label.pack(anchor=tk.W)
        
        # 绑定变量变化事件以更新摘要
        self.train_ratio_var.trace('w', self.update_settings_summary)
        self.test_ratio_var.trace('w', self.update_settings_summary)
        self.verify_ratio_var.trace('w', self.update_settings_summary)
        self.max_images_per_folder_var.trace('w', self.update_settings_summary)
        self.auto_split_var.trace('w', self.update_settings_summary)
    
    def create_action_section(self, parent):
        """创建操作按钮区域"""
        # 创建操作区域
        action_frame = tk.Frame(parent, bg=self.colors['surface_container_high'], relief='flat')
        action_frame.pack(fill=tk.X, padx=0, pady=(0, 12))
        
        # 标题
        title_label = tk.Label(action_frame, 
                              text="🚀 执行转换", 
                              bg=self.colors['surface_container_high'], 
                              fg=self.colors['on_surface'], 
                              font=('Segoe UI', 12, 'bold'))
        title_label.pack(anchor=tk.W, padx=16, pady=(12, 8))
        
        # 转换按钮
        self.convert_btn = tk.Button(action_frame,
                                    text="🚀 开始转换与切分",
                                    command=self.start_conversion,
                                    bg=self.colors['primary'],
                                    fg=self.colors['on_primary'],
                                    font=('Segoe UI', 11, 'bold'),
                                    relief='flat',
                                    cursor='hand2',
                                    padx=20, pady=8)
        self.convert_btn.pack(pady=8, padx=16)
        
        # 进度条标签
        tk.Label(action_frame, 
                text="处理进度:", 
                bg=self.colors['surface_container_high'], 
                fg=self.colors['on_surface'],
                font=('Segoe UI', 9)).pack(anchor=tk.W, padx=16)
        
        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(action_frame,
                                          variable=self.progress_var,
                                          length=300,
                                          style='Material.Horizontal.TProgressbar')
        self.progress_bar.pack(fill=tk.X, padx=16, pady=(4, 12))
    
    def create_compact_header(self, parent):
        """创建紧凑的顶部标题栏"""
        # 使用Material Design主色调
        header_frame = tk.Frame(parent, bg=self.colors['primary_container'], relief='flat')
        header_frame.pack(fill=tk.X, pady=(0, 8))
        
        # 标题
        title_label = tk.Label(header_frame, 
                              text="Labelme to COCO 转换器 - 多文件夹数据集切分版",
                              bg=self.colors['primary_container'],
                              fg=self.colors['on_primary_container'],
                              font=('Segoe UI', 16, 'bold'))
        title_label.pack(side=tk.LEFT, padx=16, pady=16)
        
        # 右侧状态信息
        self.header_status_var = tk.StringVar(value="✨ 就绪")
        status_label = tk.Label(header_frame,
                               textvariable=self.header_status_var,
                               bg=self.colors['primary_container'],
                               fg=self.colors['on_primary_container'],
                               font=('Segoe UI', 12))
        status_label.pack(side=tk.RIGHT, padx=16, pady=16)
    
    def create_compact_status_bar(self, parent):
        """创建紧凑的底部状态栏"""
        status_card = self.create_elevated_card(parent, elevation=1)[1]
        status_card.pack(fill=tk.X, pady=(8, 0))
        
        status_content = ttk.Frame(status_card, style='MaterialCard.TFrame')
        status_content.pack(fill=tk.X, padx=12, pady=6)
        
        # 状态文本
        self.status_var = tk.StringVar(value="✨ 就绪 - 请添加输入文件夹并配置输出目录")
        status_label = ttk.Label(status_content,
                               textvariable=self.status_var,
                               style='MaterialCaption.TLabel')
        status_label.pack(side=tk.LEFT)
        
        # 右侧时间显示
        import datetime
        time_label = ttk.Label(status_content,
                             text=datetime.datetime.now().strftime("%H:%M"),
                             style='MaterialCaption.TLabel')
        time_label.pack(side=tk.RIGHT)


    def create_collapsible_group(self, parent, title, expanded=True):
        """创建可折叠的组件组"""
        # 主容器
        main_frame = ttk.Frame(parent, style='MaterialCard.TFrame')
        main_frame.pack(fill=tk.X, pady=(0, 16), padx=8)
        
        # 标题栏
        header_frame = ttk.Frame(main_frame, style='MaterialCardHigh.TFrame')
        header_frame.pack(fill=tk.X, pady=(8, 0), padx=8)
        
        # 折叠按钮
        expand_symbol = "▼" if expanded else "▶"
        toggle_btn = ttk.Button(header_frame,
                              text=f"{expand_symbol} {title}",
                              style='MaterialTextButton.TButton',
                              width=25)
        toggle_btn.pack(anchor=tk.W, pady=8)
        
        # 内容区域
        content_frame = ttk.Frame(main_frame, style='MaterialCard.TFrame')
        
        # 折叠功能
        def toggle_content():
            if content_frame.winfo_viewable():
                content_frame.pack_forget()
                toggle_btn.configure(text=f"▶ {title}")
            else:
                content_frame.pack(fill=tk.X, padx=12, pady=(0, 12))
                toggle_btn.configure(text=f"▼ {title}")
        
        toggle_btn.configure(command=toggle_content)
        
        # 初始状态
        if expanded:
            content_frame.pack(fill=tk.X, padx=12, pady=(0, 12))
            
        return content_frame
            
    def create_data_tab(self, parent):
        """创建数据管理标签页"""
        # 文件夹列表和统计
        folders_frame = ttk.Frame(parent, style='MaterialCard.TFrame')
        folders_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        
        # 标题
        title_label = ttk.Label(folders_frame, 
                              text="文件夹信息总览",
                              style='MaterialBody.TLabel',
                              font=('Segoe UI', 12, 'bold'))
        title_label.pack(anchor=tk.W, pady=(0, 12))
        
        # 文件夹详情表格
        self.folders_tree = ttk.Treeview(folders_frame,
                                       columns=('Name', 'Files', 'Labels', 'Status'),
                                       show='headings',
                                       style='Material.Treeview',
                                       height=12)
        
        # 设置列标题
        self.folders_tree.heading('Name', text='文件夹名称')
        self.folders_tree.heading('Files', text='文件数')
        self.folders_tree.heading('Labels', text='标签数')
        self.folders_tree.heading('Status', text='状态')
        
        # 设置列宽
        self.folders_tree.column('Name', width=200, anchor='w')
        self.folders_tree.column('Files', width=80, anchor='center')
        self.folders_tree.column('Labels', width=80, anchor='center')
        self.folders_tree.column('Status', width=100, anchor='center')
        
        # 滚动条
        tree_scrollbar = ttk.Scrollbar(folders_frame, orient=tk.VERTICAL, command=self.folders_tree.yview)
        self.folders_tree.configure(yscrollcommand=tree_scrollbar.set)
        
        self.folders_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 绑定双击事件
        self.folders_tree.bind('<Double-1>', self.show_folder_labels_detail)
    
    def create_label_tab(self, parent):
        """创建标签管理标签页"""
        # 主容器
        main_frame = ttk.Frame(parent, style='MaterialCard.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        
        # 标签操作区域
        controls_frame = ttk.Frame(main_frame, style='MaterialCardHigh.TFrame')
        controls_frame.pack(fill=tk.X, pady=(0, 16), padx=8)
        
        controls_content = ttk.Frame(controls_frame, style='MaterialCardHigh.TFrame')
        controls_content.pack(fill=tk.X, padx=12, pady=12)
        
        # 操作按钮
        self.refresh_labels_btn = ttk.Button(controls_content,
                                           text="🔄 刷新",
                                           command=self.refresh_label_mapping,
                                           style='MaterialOutlinedButton.TButton',
                                           state='disabled')
        self.refresh_labels_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        save_btn = ttk.Button(controls_content,
                            text="💾 保存",
                            command=self.save_label_mapping,
                            style='MaterialOutlinedButton.TButton')
        save_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        load_btn = ttk.Button(controls_content,
                            text="📁 加载",
                            command=self.load_label_mapping,
                            style='MaterialTextButton.TButton')
        load_btn.pack(side=tk.LEFT)
        
        # 标签映射表格
        self.labels_tree = ttk.Treeview(main_frame,
                                      columns=('ID', 'Label', 'Count', 'Status'),
                                      show='headings',
                                      style='Material.Treeview',
                                      height=15)
        
        # 设置列标题
        self.labels_tree.heading('ID', text='标签ID')
        self.labels_tree.heading('Label', text='标签名称')
        self.labels_tree.heading('Count', text='出现次数')
        self.labels_tree.heading('Status', text='状态')
        
        # 设置列宽
        self.labels_tree.column('ID', width=80, anchor='center')
        self.labels_tree.column('Label', width=150, anchor='w')
        self.labels_tree.column('Count', width=100, anchor='center')
        self.labels_tree.column('Status', width=100, anchor='center')
        
        # 滚动条
        labels_scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=self.labels_tree.yview)
        self.labels_tree.configure(yscrollcommand=labels_scrollbar.set)
        
        self.labels_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        labels_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 绑定选择事件
        self.labels_tree.bind('<<TreeviewSelect>>', self.on_label_select)
    
    def create_log_tab(self, parent):
        """创建日志输出标签页"""
        # 日志文本区域
        log_frame = ttk.Frame(parent, style='MaterialCard.TFrame')
        log_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        
        # 日志标题
        log_title = ttk.Label(log_frame,
                            text="实时日志",
                            style='MaterialBody.TLabel',
                            font=('Segoe UI', 12, 'bold'))
        log_title.pack(anchor=tk.W, pady=(0, 8))
        
        # 日志文本框
        self.log_text = tk.Text(log_frame,
                               wrap=tk.WORD,
                               bg=self.colors['surface'],
                               fg=self.colors['on_surface'],
                               font=('Consolas', 9),
                               borderwidth=0,
                               relief='flat',
                               padx=12,
                               pady=12,
                               selectbackground=self.colors['primary_container'],
                               selectforeground=self.colors['on_primary_container'])
        
        # 滚动条
        log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    def create_status_bar(self, parent):
        """创建底部状态栏"""
        status_card = self.create_elevated_card(parent, elevation=1)[1]
        status_card.pack(fill=tk.X, pady=(16, 0))
        
        status_content = ttk.Frame(status_card, style='MaterialCard.TFrame')
        status_content.pack(fill=tk.X, padx=16, pady=8)
        
        # 状态文本
        self.status_var = tk.StringVar(value="✨ 就绪 - 请添加输入文件夹并配置输出目录")
        status_label = ttk.Label(status_content,
                               textvariable=self.status_var,
                               style='MaterialCaption.TLabel')
        status_label.pack(side=tk.LEFT)
        
        # 右侧状态信息
        right_status_frame = ttk.Frame(status_content, style='MaterialCard.TFrame')
        right_status_frame.pack(side=tk.RIGHT)
        
        # 时间显示
        import datetime
        time_label = ttk.Label(right_status_frame,
                             text=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                             style='MaterialCaption.TLabel')
        time_label.pack()
    
    def add_change_history(self, action, details):
        """添加变更历史记录"""
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        history_entry = f"[{timestamp}] {action}: {details}"
        self.change_history.append(history_entry)
        
        # 在日志中显示
        if hasattr(self, 'log_text'):
            self.log_text.insert(tk.END, history_entry + "\n")
            self.log_text.see(tk.END)
    
    def update_folders_detail_display(self):
        """更新文件夹标签详情显示（兼容方法）"""
        # 新的水平布局中不需要该功能，保留以避免错误
        pass
        
    def create_main_interface(self):
        """创建主界面 - 水平布局设计"""
        try:
            print("  创建主容器...")
            # 主容器 - 水平布局，使用Material Design背景色
            main_container = tk.Frame(self.root, bg=self.colors['background'], relief='flat')
            main_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
            print("  主容器创建成功")
            
            # 顶部标题栏
            print("  创建顶部标题栏...")
            self.create_compact_header(main_container)
            print("  顶部标题栏创建成功")
            
            # 主要内容区域 - 水平分栏
            print("  创建内容区域...")
            content_container = tk.Frame(main_container, bg=self.colors['background'], relief='flat')
            content_container.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
            print("  内容区域创建成功")
            
            # 左侧面板 - 配置和控制（固定宽度）
            print("  创建左侧面板...")
            left_panel = tk.Frame(content_container, bg=self.colors['surface_container_low'], relief='flat')
            left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 4))
            left_panel.configure(width=450)  # 固定宽度
            left_panel.pack_propagate(False)  # 固定宽度
            print("  左侧面板创建成功")
            
            # 右侧面板 - 数据展示和日志（自适应）
            print("  创建右侧面板...")
            right_panel = tk.Frame(content_container, bg=self.colors['surface_container'], relief='flat')
            right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(4, 0))
            print("  右侧面板创建成功")
            
            # 创建左右面板内容
            print("  创建左侧面板内容...")
            self.create_left_panel(left_panel)
            print("  左侧面板内容创建成功")
            
            print("  创建右侧面板内容...")
            self.create_right_panel(right_panel)
            print("  右侧面板内容创建成功")
            
            # 底部状态栏
            print("  创建底部状态栏...")
            self.create_compact_status_bar(main_container)
            print("  底部状态栏创建成功")
            
            # 初始化变更历史
            self.change_history = []
            print("  变更历史初始化完成")
            
            # 显示初始状态（仅限于没有文件夹的情况）
            print("  显示初始状态...")
            if not hasattr(self, 'input_folders') or not self.input_folders:
                self.display_initial_state()
            print("  初始状态显示成功")
            
        except Exception as e:
            print(f"  主界面创建过程中出错: {e}")
            import traceback
            traceback.print_exc()
        
    
    def center_window(self):
        """居中显示窗口并优化响应式布局"""
        self.root.update_idletasks()
        
        # 获取屏幕尺寸
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # 计算窗口尺寸（响应式） - 优化为更好的显示效果
        if screen_width >= 1920:  # 4K或更大屏幕
            width, height = 1400, 900
        elif screen_width >= 1440:  # 2K屏幕
            width, height = 1300, 850
        elif screen_width >= 1200:  # 普通大屏
            width, height = 1200, 800
        else:  # 小屏幕
            width = min(1100, int(screen_width * 0.9))
            height = min(750, int(screen_height * 0.85))
        
        # 居中位置
        x = (screen_width - width) // 2
        y = max(50, (screen_height - height) // 2)  # 确保窗口不会太靠上
        
        self.root.geometry(f'{width}x{height}+{x}+{y}')
        
        # 设置最小尺寸 - 调整为更合理的最小尺寸
        self.root.minsize(1000, 650)
    
    def select_input_dir(self):
        """选择输入目录（兼容性方法，现在调用添加文件夹）"""
        self.add_input_folder()
            
    def select_output_dir(self):
        """选择输出目录"""
        directory = filedialog.askdirectory(title="选择输出目录")
        if directory:
            self.output_var.set(directory)
            self.log_message(f"选择输出目录: {directory}")
            self._update_ui_from_state()
    
    def display_initial_state(self):
        """显示初始状态"""
        # 添加欢迎日志消息
        if hasattr(self, 'log_text'):
            self.log_message("✨ 欢迎使用 Labelme to COCO 转换器！")
            self.log_message("🗂️ 请先添加包含 JSON 文件和图片的文件夹")
            self.log_message("📁 支持同时添加多个文件夹进行批量处理")
            self.log_message("⚙️ 系统将自动建立统一的标签映射")
            self.log_message("🚀 配置完成后即可开始转换和数据集切分")
            self.log_message("-" * 50)
        
        # 清空标签映射表格
        if hasattr(self, 'labels_tree'):
            for item in self.labels_tree.get_children():
                self.labels_tree.delete(item)
            
            # 显示初始提示
            self.labels_tree.insert('', 'end', values=('--', '请先添加文件夹并扫描标签映射', '--', '未建立'))
            
            # 绑定选择事件
            self.labels_tree.bind('<<TreeviewSelect>>', self.on_label_select)
        
        # 更新文件夹显示
        self.update_folders_display()
        
        # 更新文件夹统计
        self.update_folders_stats()
        
        # 统一更新UI状态
        self._update_ui_from_state()
    
    def scan_and_show_labels(self):
        """扫描输入目录并显示标签映射"""
        input_dir = self.input_var.get().strip()
        
        if not input_dir:
            messagebox.showerror("错误", "请先选择输入目录")
            return
            
        if not os.path.exists(input_dir):
            messagebox.showerror("错误", "输入目录不存在")
            return
        
        try:
            # 扫描按钮已移除，不再需要禁用/启用
            self.log_message("开始扫描输入目录建立标签映射...")
            
            # 获取所有图片文件
            image_files = self.get_image_files(input_dir)
            if len(image_files) == 0:
                messagebox.showwarning("警告", "没有找到任何图片文件")
                return
            
            # 建立标签映射
            self.global_converter = SimpleLabelme2COCO()
            self.build_global_label_mapping(self.global_converter, input_dir, image_files)
            
            # 显示标签映射
            self.display_label_mapping()
            
            # 启用相关按钮
            self.refresh_labels_btn.config(state='normal')
            self.update_label_btn.config(state='normal')
            self.reset_labels_btn.config(state='normal')
            self.save_mapping_btn.config(state='normal')
            self.load_mapping_btn.config(state='normal')
            self.export_mapping_btn.config(state='normal')
            
            # 添加变更历史
            self.add_change_history("扫描完成", f"发现 {len(self.global_converter.labels_list)} 个标签")
            
            self.log_message(f"标签映射建立完成，共 {len(self.global_converter.labels_list)} 个标签")
            
        except Exception as e:
            self.log_message(f"扫描标签失败: {e}")
            messagebox.showerror("错误", f"扫描标签失败: {e}")
        finally:
            # 扫描按钮已移除，无需恢复状态
            pass
    
    def build_global_label_mapping(self, global_converter, input_dir, all_files):
        """建立全局标签映射"""
        seen_labels = set()
        label_count = {}  # 统计每个标签出现的次数
        
        self.log_message(f"开始扫描 {len(all_files)} 个文件建立标签映射...")
        
        for i, img_file in enumerate(all_files):
            img_label = os.path.splitext(os.path.basename(img_file))[0]
            label_file = osp.join(input_dir, img_label + '.json')
            
            if not os.path.exists(label_file):
                continue
                
            try:
                with open(label_file, encoding='utf-8') as f:
                    data = json.load(f)
                
                for shapes in data['shapes']:
                    label = shapes['label']
                    
                    # 统计标签出现次数
                    if label not in label_count:
                        label_count[label] = 0
                    label_count[label] += 1
                    
                    if label not in seen_labels:
                        seen_labels.add(label)
                        global_converter.categories_list.append(global_converter.categories(label))
                        global_converter.labels_list.append(label)
                        global_converter.label_to_num[label] = len(global_converter.labels_list)
                        self.log_message(f"  发现新标签: '{label}' -> ID {len(global_converter.labels_list)}")
                        
            except Exception as e:
                self.log_message(f"建立标签映射时处理文件 {label_file} 出错: {e}")
                continue
        
        # 保存标签统计信息
        self.label_count = label_count
        
        # 输出标签统计信息
        self.log_message(f"\n标签统计信息:")
        for label, count in sorted(label_count.items()):
            label_id = global_converter.label_to_num[label]
            self.log_message(f"  {label_id:2d}: {label} (出现 {count} 次)")
        
        self.log_message(f"\n全局标签映射建立完成，共 {len(global_converter.labels_list)} 个标签")
    
    def build_unified_label_mapping(self):
        """统一建立所有文件夹的标签映射（避免重复）"""
        seen_labels = set()
        label_count = {}  # 统计每个标签出现的次数
        
        self.log_message("开始统一扫描所有文件夹建立标签映射...")
        
        # 扫描所有文件夹
        for folder_path, image_files in self.input_folders.items():
            folder_name = self.folder_names.get(folder_path, os.path.basename(folder_path))
            self.log_message(f"扫描文件夹: {folder_name} ({len(image_files)} 个文件)")
            
            for img_file in image_files:
                img_label = os.path.splitext(os.path.basename(img_file))[0]
                label_file = osp.join(folder_path, img_label + '.json')
                
                if not os.path.exists(label_file):
                    continue
                    
                try:
                    with open(label_file, encoding='utf-8') as f:
                        data = json.load(f)
                    
                    for shapes in data['shapes']:
                        label = shapes['label']
                        
                        # 统计标签出现次数
                        if label not in label_count:
                            label_count[label] = 0
                        label_count[label] += 1
                        
                        # 只有未见过的标签才添加到全局映射
                        if label not in seen_labels:
                            seen_labels.add(label)
                            self.global_converter.categories_list.append(self.global_converter.categories(label))
                            self.global_converter.labels_list.append(label)
                            self.global_converter.label_to_num[label] = len(self.global_converter.labels_list)
                            self.log_message(f"  发现新标签: '{label}' -> ID {len(self.global_converter.labels_list)}")
                            
                except Exception as e:
                    self.log_message(f"建立标签映射时处理文件 {label_file} 出错: {e}")
                    continue
        
        # 保存标签统计信息
        self.label_count = label_count
        
        # 输出标签统计信息
        self.log_message(f"\n标签统计信息:")
        for label, count in sorted(label_count.items()):
            label_id = self.global_converter.label_to_num[label]
            self.log_message(f"  {label_id:2d}: {label} (出现 {count} 次)")
        
        self.log_message(f"\n统一标签映射建立完成，共 {len(self.global_converter.labels_list)} 个标签")
    
    def display_label_mapping(self):
        """显示标签映射表格"""
        # 检查必要的组件是否存在
        if not hasattr(self, 'labels_tree'):
            self.log_message("警告: 标签映射表格组件未初始化")
            return
            
        self.log_message("开始更新标签映射显示...")
        
        # 清空现有数据并添加新数据
        try:
            for item in self.labels_tree.get_children():
                self.labels_tree.delete(item)
            
            # 添加标签数据
            if hasattr(self, 'global_converter') and hasattr(self, 'label_count'):
                if self.global_converter.labels_list:
                    self.log_message(f"显示 {len(self.global_converter.labels_list)} 个标签:")
                    for i, label in enumerate(self.global_converter.labels_list):
                        label_id = self.global_converter.label_to_num[label]
                        count = self.label_count.get(label, 0)
                        self.labels_tree.insert('', 'end', values=(label_id, label, count, "已建立"))
                        self.log_message(f"  {label_id}: {label} (出现 {count} 次)")
                else:
                    self.log_message("没有发现任何标签")
                    self.labels_tree.insert('', 'end', values=('--', '暂无标签数据', '--', '未扫描'))
            else:
                self.log_message("全局转换器或标签计数未初始化")
                self.labels_tree.insert('', 'end', values=('--', '请先添加文件夹并扫描标签', '--', '未建立'))
            
            # 绑定选择事件
            self.labels_tree.bind('<<TreeviewSelect>>', self.on_label_select)
            
            # 更新标签编辑下拉框选项
            if hasattr(self, 'edit_label_combobox') and hasattr(self, 'global_converter'):
                if hasattr(self.global_converter, 'labels_list'):
                    self.edit_label_combobox['values'] = self.global_converter.labels_list
                    
        except Exception as e:
            self.log_message(f"更新标签映射显示时出错: {e}")
            import traceback
            traceback.print_exc()
        
        self.log_message("标签映射显示更新完成")
    
    def display_label_mapping_with_changes(self, changed_label=None, old_id=None, new_id=None):
        """显示标签映射表格，并标记变更"""
        if not hasattr(self, 'labels_info_label'):
            return
            
        # 隐藏说明文字
        try:
            self.labels_info_label.pack_forget()
        except:
            pass
        
        # 显示统计信息
        if hasattr(self, 'labels_stats_frame'):
            try:
                self.labels_stats_frame.pack(fill=tk.X, pady=(0, 10))
            except:
                pass
        
        # 更新统计信息
        if hasattr(self, 'global_converter') and hasattr(self, 'label_count'):
            total_labels = len(self.global_converter.labels_list)
            total_annotations = sum(self.label_count.values())
            
            if hasattr(self, 'total_labels_label'):
                self.total_labels_label.config(text=f"标签总数: {total_labels} | 标注总数: {total_annotations}")
            
            # 显示标签分布
            label_distribution = []
            for label, count in sorted(self.label_count.items(), key=lambda x: x[1], reverse=True):
                label_distribution.append(f"{label}({count})")
            
            if hasattr(self, 'labels_summary_label'):
                self.labels_summary_label.config(text=f"标签分布: {', '.join(label_distribution[:5])}{'...' if len(label_distribution) > 5 else ''}")
        
        # 清空现有数据
        if hasattr(self, 'labels_tree'):
            for item in self.labels_tree.get_children():
                self.labels_tree.delete(item)
            
            # 添加标签数据
            if hasattr(self, 'global_converter'):
                for i, label in enumerate(self.global_converter.labels_list):
                    label_id = self.global_converter.label_to_num[label]
                    count = self.label_count.get(label, 0)
                    
                    # 标记状态
                    if changed_label and label == changed_label:
                        status = f"已修改 ({old_id}→{new_id})"
                    else:
                        status = "已建立"
                    
                    self.labels_tree.insert('', 'end', values=(label_id, label, count, status))
            
            # 绑定选择事件
            self.labels_tree.bind('<<TreeviewSelect>>', self.on_label_select)
        
        # 更新标签编辑下拉框选项
        if hasattr(self, 'edit_label_combobox') and hasattr(self, 'global_converter'):
            self.edit_label_combobox['values'] = self.global_converter.labels_list
    
    def on_label_select(self, event):
        """标签选择事件"""
        selection = self.labels_tree.selection()
        if selection:
            item = self.labels_tree.item(selection[0])
            values = item['values']
            if values and values[1] != '请先扫描标签映射':  # 不是提示行
                label_name = values[1]
                current_id = values[0]
                count = values[2]
                status = values[3]
                
                self.edit_label_var.set(label_name)  # 标签名称
                # 不自动设置ID，让用户手动输入新ID
                self.edit_id_var.set("")  # 清空ID输入框
                self.new_label_name_var.set("")  # 清空新名称输入框
                
                # 更新当前选中标签信息
                self.current_label_info.config(
                    text=f"当前选中: {label_name} (ID: {current_id}, 出现 {count} 次, 状态: {status})",
                    foreground=self.colors['primary']
                )
                self.current_id_label.config(text=f"{current_id}")
                
                # 启用编辑按钮
                self.update_label_btn.config(state='normal')
                self.rename_label_btn.config(state='normal')
                self.delete_label_btn.config(state='normal')
                
                # 更新下拉框选项
                if hasattr(self, 'global_converter') and self.global_converter.labels_list:
                    self.edit_label_combobox['values'] = self.global_converter.labels_list
        else:
            # 没有选中项时清空信息和禁用按钮
            self.current_label_info.config(
                text="请先选择一个标签",
                foreground=self.colors['text_secondary']
            )
            self.current_id_label.config(text="--")
            self.edit_label_var.set("")
            self.edit_id_var.set("")
            self.new_label_name_var.set("")
            
            # 禁用编辑按钮
            self.update_label_btn.config(state='disabled')
            self.rename_label_btn.config(state='disabled')
            self.delete_label_btn.config(state='disabled')
    
    def update_label_id(self):
        """更新标签ID"""
        label_name = self.edit_label_var.get().strip()
        new_id_str = self.edit_id_var.get().strip()
        
        if not label_name:
            messagebox.showerror("错误", "请输入标签名称")
            return
            
        if not new_id_str:
            messagebox.showerror("错误", "请输入新的标签ID")
            return
        
        try:
            new_id = int(new_id_str)
            if new_id < 1:
                messagebox.showerror("错误", "标签ID必须大于0")
                return
        except ValueError:
            messagebox.showerror("错误", "标签ID必须是整数")
            return
        
        # 检查ID是否已被使用
        if new_id in [self.global_converter.label_to_num[l] for l in self.global_converter.labels_list if l != label_name]:
            messagebox.showerror("错误", f"标签ID {new_id} 已被使用")
            return
        
        # 更新标签映射
        old_id = self.global_converter.label_to_num[label_name]
        self.global_converter.label_to_num[label_name] = new_id
        
        # 更新categories_list中的ID
        for category in self.global_converter.categories_list:
            if category['name'] == label_name:
                category['id'] = new_id
                break
        
        self.log_message(f"标签 '{label_name}' ID已更新: {old_id} -> {new_id}")
        
        # 添加变更历史
        self.add_change_history("标签ID更新", f"'{label_name}': {old_id} → {new_id}")
        
        # 刷新显示并标记为已修改
        self.display_label_mapping_with_changes(label_name, old_id, new_id)
        
        # 清空编辑框
        self.edit_label_var.set("")
        self.edit_id_var.set("")
        
        # 自动选择下一个标签（如果存在）
        self.select_next_label(label_name)
    
    def select_next_label(self, current_label):
        """选择下一个标签"""
        if not hasattr(self, 'global_converter'):
            return
        
        try:
            # 找到当前标签在列表中的位置
            current_index = self.global_converter.labels_list.index(current_label)
            next_index = (current_index + 1) % len(self.global_converter.labels_list)
            next_label = self.global_converter.labels_list[next_index]
            
            # 在表格中找到并选择下一个标签
            for item in self.labels_tree.get_children():
                values = self.labels_tree.item(item)['values']
                if values and values[1] == next_label:
                    self.labels_tree.selection_set(item)
                    self.labels_tree.see(item)  # 确保标签可见
                    break
                    
        except (ValueError, IndexError):
            # 如果出现错误，不进行选择
            pass
    
    def reset_label_mapping(self):
        """重置标签映射为自动分配"""
        if hasattr(self, 'global_converter') and hasattr(self, 'label_count'):
            # 重新扫描所有文件夹建立标签映射
            self.scan_all_folders()
            
            # 添加变更历史
            self.add_change_history("重置映射", "标签映射已重置为自动分配")
            
            self.log_message("标签映射已重置为自动分配")
        else:
            messagebox.showwarning("警告", "请先扫描标签映射")
    
    def rename_label(self):
        """重命名标签"""
        if not hasattr(self, 'global_converter') or not self.global_converter.labels_list:
            messagebox.showwarning("警告", "请先扫描标签映射")
            return
            
        old_label_name = self.edit_label_var.get().strip()
        new_label_name = self.new_label_name_var.get().strip()
        
        if not old_label_name:
            messagebox.showerror("错误", "请先选择要重命名的标签")
            return
            
        if not new_label_name:
            messagebox.showerror("错误", "请输入新的标签名称")
            return
            
        if old_label_name == new_label_name:
            messagebox.showwarning("警告", "新名称与原名称相同")
            return
            
        if new_label_name in self.global_converter.labels_list:
            messagebox.showerror("错误", f"标签名称 '{new_label_name}' 已存在")
            return
        
        # 更新标签名称
        label_id = self.global_converter.label_to_num[old_label_name]
        
        # 更新labels_list
        label_index = self.global_converter.labels_list.index(old_label_name)
        self.global_converter.labels_list[label_index] = new_label_name
        
        # 更新label_to_num映射
        del self.global_converter.label_to_num[old_label_name]
        self.global_converter.label_to_num[new_label_name] = label_id
        
        # 更新categories_list
        for category in self.global_converter.categories_list:
            if category['name'] == old_label_name:
                category['name'] = new_label_name
                break
        
        # 更新label_count
        if hasattr(self, 'label_count') and old_label_name in self.label_count:
            count = self.label_count[old_label_name]
            del self.label_count[old_label_name]
            self.label_count[new_label_name] = count
        
        self.log_message(f"标签重命名: '{old_label_name}' -> '{new_label_name}'")
        
        # 添加变更历史
        self.add_change_history("标签重命名", f"'{old_label_name}' → '{new_label_name}'")
        
        # 刷新显示
        self.display_label_mapping()
        
        # 清空输入框
        self.new_label_name_var.set("")
        
        messagebox.showinfo("成功", f"标签已重命名为 '{new_label_name}'")
    
    def delete_label(self):
        """删除标签"""
        if not hasattr(self, 'global_converter') or not self.global_converter.labels_list:
            messagebox.showwarning("警告", "请先扫描标签映射")
            return
            
        label_name = self.edit_label_var.get().strip()
        
        if not label_name:
            messagebox.showerror("错误", "请先选择要删除的标签")
            return
        
        # 确认删除
        count = self.label_count.get(label_name, 0)
        if not messagebox.askyesno("确认删除", 
                                  f"确定要删除标签 '{label_name}' 吗？\n"
                                  f"该标签共出现 {count} 次。\n"
                                  f"删除后相关标注将不会被转换。"):
            return
        
        # 获取要删除的标签ID
        label_id = self.global_converter.label_to_num[label_name]
        
        # 从各个列表中移除
        self.global_converter.labels_list.remove(label_name)
        del self.global_converter.label_to_num[label_name]
        
        # 从categories_list中移除
        self.global_converter.categories_list = [
            cat for cat in self.global_converter.categories_list 
            if cat['name'] != label_name
        ]
        
        # 重新分配ID（保持连续）
        self.global_converter.label_to_num = {}
        self.global_converter.categories_list = []
        
        for i, label in enumerate(self.global_converter.labels_list):
            new_id = i + 1
            self.global_converter.label_to_num[label] = new_id
            self.global_converter.categories_list.append({
                'supercategory': 'component',
                'id': new_id,
                'name': label
            })
        
        # 从label_count中移除
        if hasattr(self, 'label_count') and label_name in self.label_count:
            del self.label_count[label_name]
        
        self.log_message(f"标签已删除: '{label_name}'")
        
        # 添加变更历史
        self.add_change_history("标签删除", f"删除标签 '{label_name}'")
        
        # 刷新显示
        self.display_label_mapping()
        
        messagebox.showinfo("成功", f"标签 '{label_name}' 已删除")
    
    def add_new_label(self):
        """添加新标签"""
        if not hasattr(self, 'global_converter'):
            # 如果还没有全局转换器，先创建一个
            self.global_converter = SimpleLabelme2COCO()
            self.label_count = {}
            
        new_label_name = self.new_label_name_var.get().strip()
        
        if not new_label_name:
            messagebox.showerror("错误", "请输入新的标签名称")
            return
            
        if new_label_name in self.global_converter.labels_list:
            messagebox.showerror("错误", f"标签名称 '{new_label_name}' 已存在")
            return
        
        # 添加新标签
        new_id = len(self.global_converter.labels_list) + 1
        self.global_converter.labels_list.append(new_label_name)
        self.global_converter.label_to_num[new_label_name] = new_id
        self.global_converter.categories_list.append({
            'supercategory': 'component',
            'id': new_id,
            'name': new_label_name
        })
        
        # 初始化标签计数
        if not hasattr(self, 'label_count'):
            self.label_count = {}
        self.label_count[new_label_name] = 0
        
        self.log_message(f"添加新标签: '{new_label_name}' -> ID {new_id}")
        
        # 添加变更历史
        self.add_change_history("标签添加", f"添加新标签 '{new_label_name}'")
        
        # 刷新显示
        self.display_label_mapping()
        
        # 启用相关按钮
        self.refresh_labels_btn.config(state='normal')
        self.update_label_btn.config(state='normal')
        self.reset_labels_btn.config(state='normal')
        self.save_mapping_btn.config(state='normal')
        self.export_mapping_btn.config(state='normal')
        
        # 清空输入框
        self.new_label_name_var.set("")
        
        messagebox.showinfo("成功", f"新标签 '{new_label_name}' 已添加")
    
    def refresh_label_mapping(self):
        """刷新标签映射"""
        if hasattr(self, 'global_converter'):
            self.display_label_mapping()
            self.log_message("标签映射已刷新")
        else:
            messagebox.showwarning("警告", "请先扫描标签映射")
    
    def save_label_mapping(self):
        """保存标签映射到文件"""
        if not hasattr(self, 'global_converter'):
            messagebox.showwarning("警告", "请先扫描标签映射")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="保存标签映射",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if file_path:
            try:
                mapping_data = {
                    'labels': self.global_converter.labels_list,
                    'label_to_num': self.global_converter.label_to_num,
                    'categories': self.global_converter.categories_list,
                    'label_count': self.label_count,
                    'timestamp': str(datetime.datetime.now())
                }
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(mapping_data, f, indent=2, ensure_ascii=False)
                
                self.log_message(f"标签映射已保存到: {file_path}")
                messagebox.showinfo("成功", f"标签映射已保存到:\n{file_path}")
                
            except Exception as e:
                self.log_message(f"保存标签映射失败: {e}")
                messagebox.showerror("错误", f"保存标签映射失败: {e}")
    
    def load_label_mapping(self):
        """从文件加载标签映射"""
        file_path = filedialog.askopenfilename(
            title="加载标签映射",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    mapping_data = json.load(f)
                
                # 验证数据完整性
                required_keys = ['labels', 'label_to_num', 'categories', 'label_count']
                if not all(key in mapping_data for key in required_keys):
                    raise ValueError("标签映射文件格式不正确")
                
                # 创建新的转换器实例
                self.global_converter = SimpleLabelme2COCO()
                self.global_converter.labels_list = mapping_data['labels']
                self.global_converter.label_to_num = mapping_data['label_to_num']
                self.global_converter.categories_list = mapping_data['categories']
                self.label_count = mapping_data['label_count']
                
                # 显示标签映射
                self.display_label_mapping()
                
                # 启用相关按钮
                self.refresh_labels_btn.config(state='normal')
                self.update_label_btn.config(state='normal')
                self.reset_labels_btn.config(state='normal')
                self.save_mapping_btn.config(state='normal')
                self.export_mapping_btn.config(state='normal')
                
                self._update_ui_from_state()
                
                self.log_message(f"标签映射已从文件加载: {file_path}")
                messagebox.showinfo("成功", f"标签映射已从文件加载:\n{file_path}")
                
            except Exception as e:
                self.log_message(f"加载标签映射失败: {e}")
                messagebox.showerror("错误", f"加载标签映射失败: {e}")
    
    def export_label_mapping_csv(self):
        """导出标签映射为CSV文件"""
        if not hasattr(self, 'global_converter'):
            messagebox.showwarning("警告", "请先扫描标签映射")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="导出标签映射为CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if file_path:
            try:
                import csv
                
                with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow(['标签ID', '标签名称', '出现次数', '类别ID'])
                    
                    for label in self.global_converter.labels_list:
                        label_id = self.global_converter.label_to_num[label]
                        count = self.label_count.get(label, 0)
                        category_id = next((cat['id'] for cat in self.global_converter.categories_list if cat['name'] == label), label_id)
                        writer.writerow([label_id, label, count, category_id])
                
                self.log_message(f"标签映射已导出为CSV: {file_path}")
                messagebox.showinfo("成功", f"标签映射已导出为CSV:\n{file_path}")
                
            except Exception as e:
                self.log_message(f"导出CSV失败: {e}")
                messagebox.showerror("错误", f"导出CSV失败: {e}")
            
    def validate_split_ratios(self):
        """验证切分比例"""
        train_ratio = self.train_ratio_var.get()
        test_ratio = self.test_ratio_var.get()
        verify_ratio = self.verify_ratio_var.get()
        
        total = train_ratio + test_ratio + verify_ratio
        if abs(total - 1.0) > 0.001:
            messagebox.showerror("错误", f"切分比例总和必须为1，当前为{total:.2f}")
            return False
        return True
    
    def validate_quantity_settings(self):
        """验证数量限制设置"""
        try:
            max_images_str = self.max_images_per_folder_var.get().strip()
            if max_images_str:
                max_images = int(max_images_str)
                if max_images <= 0:
                    messagebox.showerror("错误", "每文件夹图片上限必须大于0")
                    return False
                if max_images < 10:
                    if not messagebox.askyesno("警告", 
                                             f"每文件夹图片上限设置为 {max_images}，这可能导致过度分割。\n"
                                             f"建议设置为至少100张。\n\n是否继续？"):
                        return False
            return True
        except ValueError:
            messagebox.showerror("错误", "每文件夹图片上限必须是有效的整数")
            return False
    
    def update_settings_summary(self, *args):
        """更新设置摘要显示"""
        try:
            train_ratio = self.train_ratio_var.get()
            test_ratio = self.test_ratio_var.get()
            verify_ratio = self.verify_ratio_var.get()
            
            max_images_str = self.max_images_per_folder_var.get().strip()
            max_images = max_images_str if max_images_str else "2000"
            
            auto_split = self.auto_split_var.get()
            auto_split_text = "启用" if auto_split else "禁用"
            
            # 检查比例总和
            total_ratio = train_ratio + test_ratio + verify_ratio
            ratio_status = "✓" if abs(total_ratio - 1.0) <= 0.001 else "⚠️"
            
            summary_text = (f"{ratio_status} 当前设置: "
                          f"训练集{train_ratio:.0%}, 测试集{test_ratio:.0%}, 验证集{verify_ratio:.0%}, "
                          f"每文件夹最多{max_images}张图片, 自动分割{auto_split_text}")
            
            if hasattr(self, 'settings_summary_label'):
                self.settings_summary_label.config(text=summary_text)
                
        except Exception as e:
            # 如果出错，显示默认文本
            if hasattr(self, 'settings_summary_label'):
                self.settings_summary_label.config(text="设置更新中...")
            
    def log_message(self, message):
        """添加日志消息"""
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
        
    def _rebuild_state_and_refresh_ui(self, reason=None):
        """基于当前输入文件夹重建标签映射并刷新界面"""
        try:
            if reason:
                self.log_message(f"自动刷新: {reason} 后重建标签映射与界面")
            # 重新扫描每个文件夹的标签
            self.folder_labels = {}
            for folder_path in list(self.input_folders.keys()):
                self.folder_labels[folder_path] = self.scan_folder_labels(folder_path)

            # 根据当前文件夹重建全局标签映射
            if self.input_folders:
                self.log_message("检测到文件夹，开始重建标签映射...")
                self.global_converter = SimpleLabelme2COCO()
                self.build_unified_label_mapping()
                self.display_label_mapping()
                self.log_message("标签映射重建完成")
            else:
                # 没有任何文件夹时，清空映射并显示初始界面
                self.log_message("没有文件夹，显示初始状态")
                self.global_converter = SimpleLabelme2COCO()
                self.label_count = {}
                # 只有在没有文件夹时才显示初始状态
                if hasattr(self, 'labels_tree'):
                    for item in self.labels_tree.get_children():
                        self.labels_tree.delete(item)
                    self.labels_tree.insert('', 'end', values=('--', '请先添加文件夹并扫描标签映射', '--', '未建立'))

            # 刷新文件夹区域与统计
            self.update_folders_display()
            self.update_folders_stats()

            # 统一更新按钮等UI状态
            self._update_ui_from_state()
        except Exception as e:
            self.log_message(f"自动刷新失败: {e}")
            import traceback
            traceback.print_exc()

    def _update_ui_from_state(self):
        """根据当前状态统一更新UI控件可用性"""
        try:
            has_folders = bool(self.input_folders)
            has_mapping = hasattr(self, 'global_converter') and bool(getattr(self.global_converter, 'labels_list', []))
            output_dir = self.output_var.get().strip() if hasattr(self, 'output_var') else ""
            has_output_dir = bool(output_dir and os.path.exists(output_dir))

            # 添加调试信息
            folder_count = len(self.input_folders) if hasattr(self, 'input_folders') else 0
            label_count = len(getattr(self.global_converter, 'labels_list', [])) if hasattr(self, 'global_converter') else 0
            
            self.log_message(f"🔍 转换按钮状态检查:")
            self.log_message(f"  ✅ 文件夹: {has_folders} (已添加 {folder_count} 个文件夹)")
            self.log_message(f"  ✅ 标签映射: {has_mapping} (发现 {label_count} 个标签)")
            if output_dir:
                if os.path.exists(output_dir):
                    self.log_message(f"  ✅ 输出目录: {has_output_dir} (目录: {output_dir})")
                else:
                    self.log_message(f"  ❌ 输出目录: {has_output_dir} (目录不存在: {output_dir})")
            else:
                self.log_message(f"  ❌ 输出目录: {has_output_dir} (未设置输出目录)")
            
            can_convert = has_folders and has_mapping and has_output_dir
            self.log_message(f"  🎯 转换按钮: {'可用' if can_convert else '禁用'}")
            if not can_convert:
                missing = []
                if not has_folders: missing.append("添加文件夹")
                if not has_mapping: missing.append("建立标签映射") 
                if not has_output_dir: missing.append("设置输出目录")
                self.log_message(f"  💡 请先: {', '.join(missing)}")
            self.log_message("-" * 50)

            # 转换按钮
            if hasattr(self, 'convert_btn'):
                self.convert_btn.config(state='normal' if can_convert else 'disabled')

            # 标签映射相关
            for btn_name in ['save_mapping_btn', 'export_mapping_btn', 'refresh_labels_btn', 'reset_labels_btn', 'update_label_btn']:
                if hasattr(self, btn_name):
                    btn = getattr(self, btn_name)
                    # update_label_btn 在未选择行时由 on_label_select 控制，这里先按是否有映射粗粒度设置
                    btn.config(state='normal' if has_mapping else 'disabled')

            # 加载映射始终可用
            if hasattr(self, 'load_mapping_btn'):
                self.load_mapping_btn.config(state='normal')

        except Exception as e:
            self.log_message(f"更新UI状态失败: {e}")
    
    # 旧的start_conversion方法已删除，使用新的多文件夹版本
        
    def process_dataset(self, input_dir, output_dir, random_seed):
        """处理数据集：切分和转换"""
        try:
            self.log_message("=== 开始多文件夹数据集切分和格式转换 ===")
            self.log_message(f"输出目录: {output_dir}")
            
            # 获取切分比例
            train_ratio = self.train_ratio_var.get()
            test_ratio = self.test_ratio_var.get()
            verify_ratio = self.verify_ratio_var.get()
            
            self.log_message(f"切分比例: 训练集{train_ratio:.1%}, 测试集{test_ratio:.1%}, 验证集{verify_ratio:.1%}")
            if random_seed is not None:
                self.log_message(f"切分策略: 固定切分 (种子: {random_seed})")
            else:
                self.log_message("切分策略: 随机切分")
            
            # 检查是否已添加文件夹
            if not self.input_folders:
                raise ValueError("请先添加至少一个输入文件夹")
            
            # 获取数量限制设置
            max_images_per_folder = 2000  # 默认值
            auto_split = True  # 默认启用
            
            try:
                max_images_str = self.max_images_per_folder_var.get().strip()
                if max_images_str:
                    max_images_per_folder = int(max_images_str)
                    if max_images_per_folder <= 0:
                        raise ValueError("数量必须大于0")
                auto_split = self.auto_split_var.get()
            except (ValueError, AttributeError) as e:
                self.log_message(f"数量限制设置错误，使用默认值2000: {e}")
                max_images_per_folder = 2000
                auto_split = True
            
            self.log_message(f"数量限制设置: 每文件夹最多 {max_images_per_folder} 张图片，自动分割: {'启用' if auto_split else '禁用'}")
            
            # 获取文件夹信息
            folder_files_dict = self.get_folder_files_dict()
            total_folders = len(folder_files_dict)
            total_files = sum(len(files) for files in folder_files_dict.values())
            
            self.log_message(f"处理 {total_folders} 个文件夹，共 {total_files} 个图片文件")
            
            # 显示每个文件夹的文件数量
            for folder_path, image_files in folder_files_dict.items():
                folder_name = self.folder_names.get(folder_path, os.path.basename(folder_path))
                self.log_message(f"  {folder_name}: {len(image_files)} 个文件")
            
            # 创建多文件夹数据集切分器
            splitter = MultiFolderDatasetSplitter(train_ratio, test_ratio, verify_ratio, max_images_per_folder, auto_split)
            
            # 检查并分割大文件夹
            if auto_split:
                self.log_message("\n=== 检查文件夹大小并分割 ===")
                
                # 先检查哪些文件夹需要分割
                folders_to_split = []
                for folder_path, files in folder_files_dict.items():
                    if len(files) > max_images_per_folder:
                        folder_name = self.folder_names.get(folder_path, os.path.basename(folder_path))
                        folders_to_split.append((folder_name, len(files)))
                
                if folders_to_split:
                    self.log_message(f"发现 {len(folders_to_split)} 个文件夹需要分割:")
                    for folder_name, file_count in folders_to_split:
                        num_parts = (file_count + max_images_per_folder - 1) // max_images_per_folder
                        self.log_message(f"  {folder_name}: {file_count} 张 → 分割为 {num_parts} 个部分")
                else:
                    self.log_message("所有文件夹都在大小限制内，无需分割")
                
                folder_files_dict = splitter.split_large_folders(folder_files_dict, self.log_message)
                
                # 重新统计分割后的信息
                new_total_folders = len(folder_files_dict)
                new_total_files = sum(len(files) for files in folder_files_dict.values())
                self.log_message(f"分割后: {new_total_folders} 个文件夹，共 {new_total_files} 个图片文件")
            else:
                # 检查是否有文件夹超过限制
                large_folders = []
                for folder_path, files in folder_files_dict.items():
                    if len(files) > max_images_per_folder:
                        folder_name = self.folder_names.get(folder_path, os.path.basename(folder_path))
                        large_folders.append((folder_name, len(files)))
                
                if large_folders:
                    self.log_message("⚠️ 警告: 发现超过大小限制的文件夹，但自动分割已禁用:")
                    for folder_name, file_count in large_folders:
                        self.log_message(f"  {folder_name}: {file_count} 张图片 (超过限制 {max_images_per_folder} 张)")
                    self.log_message("建议启用自动分割功能或手动调整文件夹大小")
                else:
                    self.log_message("已禁用自动分割功能，所有文件夹都在大小限制内")
            
            # 获取切分预览信息
            self.log_message("\n=== 切分预览 ===")
            split_info = splitter.get_folder_split_info(folder_files_dict, random_seed)
            for folder_path, info in split_info.items():
                folder_name = self.folder_names.get(folder_path, os.path.basename(folder_path))
                self.log_message(f"  {folder_name}: 训练集{info['train']}个, 测试集{info['test']}个, 验证集{info['verify']}个")
            
            # 切分数据集
            self.log_message("\n开始切分数据集...")
            split_result = splitter.split_multiple_folders(folder_files_dict, random_seed)
            
            train_files = split_result['train']
            test_files = split_result['test']
            verify_files = split_result['verify']
            
            self.log_message(f"切分完成: 训练集{len(train_files)}个, 测试集{len(test_files)}个, 验证集{len(verify_files)}个")
            
            # 初始化分割结果变量
            split_subsets = None
            
            # 检查并分割输出子集
            if auto_split:
                self.log_message("\n=== 检查输出子集大小并分割 ===")
                
                # 检查每个子集是否超过限制
                subsets = {
                    'train': train_files,
                    'test': test_files, 
                    'verify': verify_files
                }
                
                split_subsets = {}
                for subset_name, files in subsets.items():
                    if len(files) > max_images_per_folder:
                        self.log_message(f"{subset_name}集有 {len(files)} 张图片，超过上限 {max_images_per_folder}，开始分割...")
                        
                        # 计算需要分割成多少个部分
                        num_parts = (len(files) + max_images_per_folder - 1) // max_images_per_folder
                        self.log_message(f"  {subset_name}集将分割为 {num_parts} 个部分")
                        
                        # 随机打乱文件列表
                        shuffled_files = files.copy()
                        random.shuffle(shuffled_files)
                        
                        # 分割文件
                        split_parts = []
                        for i in range(num_parts):
                            start_idx = i * max_images_per_folder
                            end_idx = min((i + 1) * max_images_per_folder, len(shuffled_files))
                            part_files = shuffled_files[start_idx:end_idx]
                            split_parts.append(part_files)
                            self.log_message(f"    {subset_name}_part{i+1:02d}: {len(part_files)} 张图片")
                        
                        split_subsets[subset_name] = split_parts
                    else:
                        self.log_message(f"{subset_name}集有 {len(files)} 张图片，在限制内无需分割")
                        split_subsets[subset_name] = [files]  # 包装成列表以保持一致性
                
                # 创建分割后的输出目录结构
                self.create_split_output_directories(output_dir, split_subsets, max_images_per_folder)
                
                # 复制文件到分割后的目录
                self.copy_files_to_split_output_dirs(output_dir, split_subsets, folder_files_dict)
                
                # 为每个分割后的子集生成COCO格式标注
                self.generate_coco_annotations_for_split_subsets(output_dir, split_subsets)
                
            else:
                # 原有的处理流程（不分割）
                # 检查是否有子集超过限制
                large_subsets = []
                if len(train_files) > max_images_per_folder:
                    large_subsets.append(f"训练集({len(train_files)}张)")
                if len(test_files) > max_images_per_folder:
                    large_subsets.append(f"测试集({len(test_files)}张)")
                if len(verify_files) > max_images_per_folder:
                    large_subsets.append(f"验证集({len(verify_files)}张)")
                
                if large_subsets:
                    self.log_message("⚠️ 警告: 发现超过大小限制的子集，但自动分割已禁用:")
                    for subset_info in large_subsets:
                        self.log_message(f"  {subset_info} (超过限制 {max_images_per_folder} 张)")
                    self.log_message("建议启用自动分割功能")
                
                # 创建输出目录结构
                self.create_output_directories(output_dir, folder_files_dict)
                
                # 复制文件到对应目录（支持多文件夹）
                self.copy_files_to_split_dirs_multi(output_dir, train_files, test_files, verify_files, folder_files_dict)
                
                # 为每个子集生成COCO格式标注（使用已建立的标签映射）
                self.generate_coco_annotations_multi(output_dir, train_files, test_files, verify_files)
            
            self.progress_var.set(1.0)
            self.log_message("✓ 多文件夹数据集切分和转换完成！")
            self.log_message(f"输出目录: {output_dir}")
            
            # 根据是否分割显示不同的总结信息
            if auto_split and any(len(parts) > 1 for parts in split_subsets.values()):
                self.log_message("\n=== 分割后的子集信息 ===")
                for subset_name, parts_list in split_subsets.items():
                    total_images = sum(len(part) for part in parts_list)
                    if len(parts_list) == 1:
                        self.log_message(f"{subset_name}集: {total_images} 张图片 (未分割)")
                    else:
                        self.log_message(f"{subset_name}集: {total_images} 张图片 (分割为 {len(parts_list)} 个部分)")
                        for i, part_files in enumerate(parts_list):
                            self.log_message(f"  └─ {subset_name}_part{i+1:02d}: {len(part_files)} 张图片")
            else:
                self.log_message(f"训练集: {len(train_files)} 张图片")
                self.log_message(f"测试集: {len(test_files)} 张图片")
                self.log_message(f"验证集: {len(verify_files)} 张图片")
            
            # 显示最终标签映射信息
            self.log_message("\n=== 最终标签映射 ===")
            for i, label in enumerate(self.global_converter.labels_list):
                label_id = self.global_converter.label_to_num[label]
                count = self.label_count.get(label, 0)
                self.log_message(f"  {label_id:2d}: {label} (出现 {count} 次)")
            
            # 全局验证标签ID一致性
            self.global_validation(output_dir, self.global_converter)
            
            self.status_var.set("处理完成")
            messagebox.showinfo("成功", "多文件夹数据集切分和转换完成！")
            
        except Exception as e:
            self.log_message(f"处理失败: {e}")
            self.status_var.set("处理失败")
            messagebox.showerror("错误", f"处理失败: {e}")
        finally:
            self.convert_btn.config(state='normal')
    
    def global_validation(self, output_dir, global_converter):
        """全局验证：确保所有子集的标签ID一致"""
        self.log_message("=== 全局标签ID一致性验证 ===")
        
        split_names = ['train', 'test', 'verify']
        all_categories = {}
        
        # 收集所有子集的categories信息
        for split_name in split_names:
            json_path = osp.join(output_dir, split_name, 'annotations', f'instance_{split_name}.json')
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        coco_data = json.load(f)
                    
                    for category in coco_data['categories']:
                        label_name = category['name']
                        category_id = category['id']
                        
                        if label_name not in all_categories:
                            all_categories[label_name] = {}
                        
                        all_categories[label_name][split_name] = category_id
                        
                except Exception as e:
                    self.log_message(f"读取{split_name}集JSON文件失败: {e}")
        
        # 验证每个标签在所有子集中的ID是否一致
        global_errors = 0
        for label_name, split_ids in all_categories.items():
            expected_id = global_converter.label_to_num.get(label_name)
            if expected_id is None:
                self.log_message(f"错误: 标签 '{label_name}' 在全局映射中未找到")
                global_errors += 1
                continue
            
            # 检查所有子集中的ID是否一致
            inconsistent_splits = []
            for split_name, category_id in split_ids.items():
                if category_id != expected_id:
                    inconsistent_splits.append(f"{split_name}:{category_id}")
            
            if inconsistent_splits:
                self.log_message(f"错误: 标签 '{label_name}' ID不一致 - 期望{expected_id}, 实际: {', '.join(inconsistent_splits)}")
                global_errors += 1
            else:
                self.log_message(f"✓ 标签 '{label_name}' 在所有子集中ID一致: {expected_id}")
        
        if global_errors == 0:
            self.log_message("✓ 全局标签ID一致性验证通过！")
        else:
            self.log_message(f"⚠ 全局标签ID一致性验证失败，发现 {global_errors} 个问题")
        
        # 输出全局标签映射表
        self.log_message("\n=== 全局标签映射表 ===")
        for label in global_converter.labels_list:
            label_id = global_converter.label_to_num[label]
            self.log_message(f"{label_id:2d}: {label}")
        
        # 保存标签映射信息到文件
        mapping_file = osp.join(output_dir, "label_mapping.txt")
        try:
            with open(mapping_file, 'w', encoding='utf-8') as f:
                f.write("Labelme to COCO 标签映射表\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"总标签数量: {len(global_converter.labels_list)}\n\n")
                f.write("标签ID映射:\n")
                for label in global_converter.labels_list:
                    label_id = global_converter.label_to_num[label]
                    f.write(f"{label_id:2d}: {label}\n")
                
                f.write("\n" + "=" * 50 + "\n")
                f.write("说明: 此文件记录了转换过程中建立的标签ID映射关系\n")
                f.write("确保所有子集(train/test/verify)中的相同标签具有相同的ID\n")
            
            self.log_message(f"✓ 标签映射信息已保存到: {mapping_file}")
        except Exception as e:
            self.log_message(f"保存标签映射文件失败: {e}")
        
        self.log_message("=== 验证完成 ===")
    
    def get_image_files(self, input_dir):
        """获取输入目录中的所有图片文件"""
        raw_image_files = []
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.JPG', '*.JPEG', '*.PNG']:
            raw_image_files.extend(glob.glob(osp.join(input_dir, ext)))
        
        # 去重
        image_files = []
        seen_paths = set()
        for p in raw_image_files:
            key = os.path.normcase(os.path.abspath(p))
            if key not in seen_paths:
                seen_paths.add(key)
                image_files.append(p)
        
        return image_files
    
    def create_output_directories(self, output_dir, folder_files_dict=None):
        """创建输出目录结构"""
        split_dirs = ['train', 'test', 'verify']
        
        for split_name in split_dirs:
            # 创建主目录
            split_dir = osp.join(output_dir, split_name)
            os.makedirs(split_dir, exist_ok=True)
            
            # 创建子目录
            images_dir = osp.join(split_dir, 'images')
            annotations_dir = osp.join(split_dir, 'annotations')
            
            os.makedirs(images_dir, exist_ok=True)
            os.makedirs(annotations_dir, exist_ok=True)
            
            self.log_message(f"创建目录: {split_dir}")
        
        # 如果启用了文件夹分割，创建分割信息文件
        if folder_files_dict and any("_part" in key for key in folder_files_dict.keys()):
            self.create_split_info_file(output_dir, folder_files_dict)
    
    def create_split_info_file(self, output_dir, folder_files_dict):
        """创建分割信息文件，记录文件夹分割的详细信息"""
        split_info_file = osp.join(output_dir, "folder_split_info.txt")
        
        try:
            with open(split_info_file, 'w', encoding='utf-8') as f:
                f.write("文件夹分割信息\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                # 统计原始文件夹和分割后的文件夹
                original_folders = {}
                split_folders = {}
                
                for folder_key, files in folder_files_dict.items():
                    if "_part" in folder_key:
                        # 分割后的子文件夹
                        original_path = folder_key.split("_part")[0]
                        part_num = folder_key.split("_part")[1]
                        
                        if original_path not in split_folders:
                            split_folders[original_path] = []
                        split_folders[original_path].append((part_num, len(files)))
                    else:
                        # 未分割的原始文件夹
                        original_folders[folder_key] = len(files)
                
                # 写入未分割的文件夹信息
                if original_folders:
                    f.write("未分割的文件夹:\n")
                    f.write("-" * 30 + "\n")
                    for folder_path, file_count in original_folders.items():
                        folder_name = self.folder_names.get(folder_path, os.path.basename(folder_path))
                        f.write(f"{folder_name}: {file_count} 张图片\n")
                    f.write("\n")
                
                # 写入分割的文件夹信息
                if split_folders:
                    f.write("分割的文件夹:\n")
                    f.write("-" * 30 + "\n")
                    for original_path, parts_info in split_folders.items():
                        folder_name = self.folder_names.get(original_path, os.path.basename(original_path))
                        total_files = sum(count for _, count in parts_info)
                        f.write(f"{folder_name} (总计 {total_files} 张图片，分割为 {len(parts_info)} 个部分):\n")
                        
                        for part_num, file_count in sorted(parts_info):
                            f.write(f"  └─ {folder_name}_part{part_num}: {file_count} 张图片\n")
                        f.write("\n")
                
                f.write("说明:\n")
                f.write("- 当文件夹中的图片数量超过设定上限时，会自动分割成多个部分\n")
                f.write("- 分割后的各部分在训练、测试、验证集中保持相同的标签映射\n")
                f.write("- 分割是随机进行的，确保数据的均匀分布\n")
            
            self.log_message(f"✓ 分割信息已保存到: {split_info_file}")
            
        except Exception as e:
                        self.log_message(f"保存分割信息文件失败: {e}")
    
    def create_split_output_directories(self, output_dir, split_subsets, max_images_per_folder):
        """为分割后的子集创建输出目录结构"""
        self.log_message("创建分割后的输出目录结构...")
        
        for subset_name, parts_list in split_subsets.items():
            if len(parts_list) == 1:
                # 未分割的子集，创建标准目录
                subset_dir = osp.join(output_dir, subset_name)
                os.makedirs(subset_dir, exist_ok=True)
                
                images_dir = osp.join(subset_dir, 'images')
                annotations_dir = osp.join(subset_dir, 'annotations')
                
                os.makedirs(images_dir, exist_ok=True)
                os.makedirs(annotations_dir, exist_ok=True)
                
                self.log_message(f"创建目录: {subset_dir}")
            else:
                # 分割后的子集，为每个部分创建目录
                for i, part_files in enumerate(parts_list):
                    part_name = f"{subset_name}_part{i+1:02d}"
                    part_dir = osp.join(output_dir, part_name)
                    os.makedirs(part_dir, exist_ok=True)
                    
                    images_dir = osp.join(part_dir, 'images')
                    annotations_dir = osp.join(part_dir, 'annotations')
                    
                    os.makedirs(images_dir, exist_ok=True)
                    os.makedirs(annotations_dir, exist_ok=True)
                    
                    self.log_message(f"创建分割目录: {part_dir} ({len(part_files)} 张图片)")
        
        # 创建分割信息文件
        self.create_subset_split_info_file(output_dir, split_subsets, max_images_per_folder)
    
    def create_subset_split_info_file(self, output_dir, split_subsets, max_images_per_folder):
        """创建子集分割信息文件"""
        split_info_file = osp.join(output_dir, "subset_split_info.txt")
        
        try:
            with open(split_info_file, 'w', encoding='utf-8') as f:
                f.write("数据集子集分割信息\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"分割上限: 每个子集最多 {max_images_per_folder} 张图片\n\n")
                
                for subset_name, parts_list in split_subsets.items():
                    if len(parts_list) == 1:
                        f.write(f"{subset_name}集: {len(parts_list[0])} 张图片 (未分割)\n")
                    else:
                        total_images = sum(len(part) for part in parts_list)
                        f.write(f"{subset_name}集: 总计 {total_images} 张图片，分割为 {len(parts_list)} 个部分:\n")
                        for i, part_files in enumerate(parts_list):
                            f.write(f"  └─ {subset_name}_part{i+1:02d}: {len(part_files)} 张图片\n")
                    f.write("\n")
                
                f.write("说明:\n")
                f.write("- 当训练集/测试集/验证集的图片数量超过设定上限时，会自动分割成多个部分\n")
                f.write("- 每个部分都有独立的images和annotations目录\n")
                f.write("- 所有部分使用相同的标签映射，确保一致性\n")
                f.write("- 分割是随机进行的，确保数据的均匀分布\n")
            
            self.log_message(f"✓ 子集分割信息已保存到: {split_info_file}")
            
        except Exception as e:
            self.log_message(f"保存子集分割信息文件失败: {e}")
    
    def copy_files_to_split_output_dirs(self, output_dir, split_subsets, folder_files_dict):
        """复制文件到分割后的输出目录"""
        self.log_message("复制文件到分割后的输出目录...")
        
        total_progress_steps = sum(len(parts_list) for parts_list in split_subsets.values())
        current_step = 0
        
        for subset_name, parts_list in split_subsets.items():
            if len(parts_list) == 1:
                # 未分割的子集
                subset_dir = osp.join(output_dir, subset_name, 'images')
                files = parts_list[0]
                
                self.log_message(f"复制{subset_name}集文件: {len(files)} 张图片")
                
                for i, img_file in enumerate(files):
                    filename = os.path.basename(img_file)
                    dest_path = osp.join(subset_dir, filename)
                    shutil.copy2(img_file, dest_path)
                    
                    # 更新进度条
                    progress = (current_step + (i + 1) / len(files)) / total_progress_steps
                    self.progress_var.set(progress * 0.3 + 0.6)  # 60%-90%的进度区间
                
                current_step += 1
                self.log_message(f"✓ {subset_name}集文件复制完成")
            else:
                # 分割后的子集
                for i, part_files in enumerate(parts_list):
                    part_name = f"{subset_name}_part{i+1:02d}"
                    part_images_dir = osp.join(output_dir, part_name, 'images')
                    
                    self.log_message(f"复制{part_name}文件: {len(part_files)} 张图片")
                    
                    for j, img_file in enumerate(part_files):
                        filename = os.path.basename(img_file)
                        dest_path = osp.join(part_images_dir, filename)
                        shutil.copy2(img_file, dest_path)
                        
                        # 更新进度条
                        progress = (current_step + (j + 1) / len(part_files)) / total_progress_steps
                        self.progress_var.set(progress * 0.3 + 0.6)  # 60%-90%的进度区间
                    
                    current_step += 1
                    self.log_message(f"✓ {part_name}文件复制完成")
    
    def generate_coco_annotations_for_split_subsets(self, output_dir, split_subsets):
        """为分割后的子集生成COCO格式标注"""
        self.log_message("为分割后的子集生成COCO格式标注...")
        
        # 使用已建立的全局标签映射
        global_converter = self.global_converter
        self.log_message(f"使用已建立的标签映射，共{len(global_converter.labels_list)}个标签:")
        for label in global_converter.labels_list:
            label_id = global_converter.label_to_num[label]
            self.log_message(f"  {label_id}: {label}")
        
        total_parts = sum(len(parts_list) for parts_list in split_subsets.values())
        current_part = 0
        
        for subset_name, parts_list in split_subsets.items():
            if len(parts_list) == 1:
                # 未分割的子集
                files = parts_list[0]
                self.log_message(f"生成{subset_name}集COCO标注...")
                
                coco_data = self.process_split_json_files_multi(global_converter, files, subset_name)
                
                annotations_dir = osp.join(output_dir, subset_name, 'annotations')
                json_filename = f'instance_{subset_name}.json'
                json_path = osp.join(annotations_dir, json_filename)
                
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(coco_data, f, indent=2, ensure_ascii=False)
                
                self.log_message(f"✓ {subset_name}集COCO标注生成完成: {json_filename}")
                self.log_message(f"  - 图片数量: {len(coco_data['images'])}")
                self.log_message(f"  - 标注数量: {len(coco_data['annotations'])}")
                self.log_message(f"  - 类别数量: {len(coco_data['categories'])}")
                
                # 验证标签ID一致性
                self.verify_label_consistency(coco_data, global_converter, subset_name)
                
                current_part += 1
            else:
                # 分割后的子集
                for i, part_files in enumerate(parts_list):
                    part_name = f"{subset_name}_part{i+1:02d}"
                    self.log_message(f"生成{part_name}COCO标注...")
                    
                    coco_data = self.process_split_json_files_multi(global_converter, part_files, part_name)
                    
                    annotations_dir = osp.join(output_dir, part_name, 'annotations')
                    json_filename = f'instance_{part_name}.json'
                    json_path = osp.join(annotations_dir, json_filename)
                    
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(coco_data, f, indent=2, ensure_ascii=False)
                    
                    self.log_message(f"✓ {part_name}COCO标注生成完成: {json_filename}")
                    self.log_message(f"  - 图片数量: {len(coco_data['images'])}")
                    self.log_message(f"  - 标注数量: {len(coco_data['annotations'])}")
                    self.log_message(f"  - 类别数量: {len(coco_data['categories'])}")
                    
                    # 验证标签ID一致性
                    self.verify_label_consistency(coco_data, global_converter, part_name)
                    
                    current_part += 1
                    
                    # 更新进度条
                    progress = current_part / total_parts
                    self.progress_var.set(progress * 0.1 + 0.9)  # 90%-100%的进度区间
      
    def copy_files_to_split_dirs(self, input_dir, output_dir, train_files, test_files, verify_files):
        """复制文件到对应的切分目录（单文件夹版本，保持兼容性）"""
        self.log_message("复制文件到切分目录...")
        
        # 复制训练集文件
        self.copy_files_to_dir(input_dir, output_dir, 'train', train_files, 0.0, 0.3)
        
        # 复制测试集文件
        self.copy_files_to_dir(input_dir, output_dir, 'test', test_files, 0.3, 0.6)
        
        # 复制验证集文件
        self.copy_files_to_dir(input_dir, output_dir, 'verify', verify_files, 0.6, 0.9)
    
    def copy_files_to_split_dirs_multi(self, output_dir, train_files, test_files, verify_files, folder_files_dict=None):
        """复制文件到对应的切分目录（多文件夹版本）"""
        self.log_message("复制文件到切分目录...")
        
        # 复制训练集文件
        self.copy_files_to_dir_multi(output_dir, 'train', train_files, 0.0, 0.3, folder_files_dict)
        
        # 复制测试集文件
        self.copy_files_to_dir_multi(output_dir, 'test', test_files, 0.3, 0.6, folder_files_dict)
        
        # 复制验证集文件
        self.copy_files_to_dir_multi(output_dir, 'verify', verify_files, 0.6, 0.9, folder_files_dict)
    
    def copy_files_to_dir(self, input_dir, output_dir, split_name, files, progress_start, progress_end):
        """复制文件到指定目录（单文件夹版本，保持兼容性）"""
        split_dir = osp.join(output_dir, split_name, 'images')
        
        for i, img_file in enumerate(files):
            filename = os.path.basename(img_file)
            dest_path = osp.join(split_dir, filename)
            shutil.copy2(img_file, dest_path)
            
            # 更新进度条
            progress = progress_start + (i + 1) / len(files) * (progress_end - progress_start)
            self.progress_var.set(progress)
        
        self.log_message(f"✓ {split_name}集文件复制完成: {len(files)} 个文件")
    
    def copy_files_to_dir_multi(self, output_dir, split_name, files, progress_start, progress_end, folder_files_dict=None):
        """复制文件到指定目录（多文件夹版本，支持分割后的文件夹结构）"""
        split_dir = osp.join(output_dir, split_name, 'images')
        
        # 统计每个文件夹的文件数量
        folder_stats = {}
        
        # 如果提供了folder_files_dict，使用它来确定文件夹归属
        if folder_files_dict:
            # 创建文件到文件夹的映射
            file_to_folder = {}
            for folder_key, folder_files in folder_files_dict.items():
                for file_path in folder_files:
                    file_to_folder[file_path] = folder_key
            
            # 统计每个分割后文件夹的文件数量
            for img_file in files:
                folder_key = file_to_folder.get(img_file)
                if folder_key:
                    # 处理分割后的文件夹名称显示
                    if "_part" in folder_key:
                        # 这是分割后的子文件夹
                        original_path = folder_key.split("_part")[0]
                        part_num = folder_key.split("_part")[1]
                        original_name = self.folder_names.get(original_path, os.path.basename(original_path))
                        display_name = f"{original_name}_part{part_num}"
                    else:
                        # 原始文件夹
                        display_name = self.folder_names.get(folder_key, os.path.basename(folder_key))
                    
                    if display_name not in folder_stats:
                        folder_stats[display_name] = 0
                    folder_stats[display_name] += 1
                else:
                    # 找不到对应文件夹，使用原始路径
                    folder_path = os.path.dirname(img_file)
                    folder_name = self.folder_names.get(folder_path, os.path.basename(folder_path))
                    if folder_name not in folder_stats:
                        folder_stats[folder_name] = 0
                    folder_stats[folder_name] += 1
        else:
            # 原始逻辑，按文件路径统计
            for img_file in files:
                folder_path = os.path.dirname(img_file)
                folder_name = self.folder_names.get(folder_path, os.path.basename(folder_path))
                if folder_name not in folder_stats:
                    folder_stats[folder_name] = 0
                folder_stats[folder_name] += 1
        
        self.log_message(f"开始复制{split_name}集文件...")
        for folder_name, count in folder_stats.items():
            self.log_message(f"  {folder_name}: {count} 个文件")
        
        # 复制文件
        for i, img_file in enumerate(files):
            filename = os.path.basename(img_file)
            dest_path = osp.join(split_dir, filename)
            shutil.copy2(img_file, dest_path)
            
            # 更新进度条
            progress = progress_start + (i + 1) / len(files) * (progress_end - progress_start)
            self.progress_var.set(progress)
        
        self.log_message(f"✓ {split_name}集文件复制完成: {len(files)} 个文件")
    
    def generate_coco_annotations(self, output_dir, train_files, test_files, verify_files, input_dir):
        """为每个子集生成COCO格式标注（单文件夹版本，保持兼容性）"""
        self.log_message("生成COCO格式标注文件...")
        
        # 使用已建立的全局标签映射
        global_converter = self.global_converter
        self.log_message(f"使用已建立的标签映射，共{len(global_converter.labels_list)}个标签:")
        for label in global_converter.labels_list:
            label_id = global_converter.label_to_num[label]
            self.log_message(f"  {label_id}: {label}")
        
        # 生成训练集标注
        self.generate_split_coco_annotations(output_dir, 'train', train_files, input_dir, global_converter, 0.9, 0.95)
        
        # 生成测试集标注
        self.generate_split_coco_annotations(output_dir, 'test', test_files, input_dir, global_converter, 0.95, 0.98)
        
        # 生成验证集标注
        self.generate_split_coco_annotations(output_dir, 'verify', verify_files, input_dir, global_converter, 0.98, 1.0)
    
    def generate_coco_annotations_multi(self, output_dir, train_files, test_files, verify_files):
        """为每个子集生成COCO格式标注（多文件夹版本）"""
        self.log_message("生成COCO格式标注文件...")
        
        # 使用已建立的全局标签映射
        global_converter = self.global_converter
        self.log_message(f"使用已建立的标签映射，共{len(global_converter.labels_list)}个标签:")
        for label in global_converter.labels_list:
            label_id = global_converter.label_to_num[label]
            self.log_message(f"  {label_id}: {label}")
        
        # 生成训练集标注
        self.generate_split_coco_annotations_multi(output_dir, 'train', train_files, global_converter, 0.9, 0.95)
        
        # 生成测试集标注
        self.generate_split_coco_annotations_multi(output_dir, 'test', test_files, global_converter, 0.95, 0.98)
        
        # 生成验证集标注
        self.generate_split_coco_annotations_multi(output_dir, 'verify', verify_files, global_converter, 0.98, 1.0)
    
    def generate_split_coco_annotations(self, output_dir, split_name, files, input_dir, global_converter, progress_start, progress_end):
        """为指定子集生成COCO格式标注（单文件夹版本，保持兼容性）"""
        self.log_message(f"生成{split_name}集COCO标注...")
        
        # 使用全局转换器，确保标签ID一致
        # 注意：这里不再创建新的converter实例
        
        # 处理文件
        coco_data = self.process_split_json_files(global_converter, input_dir, files, split_name)
        
        # 保存COCO JSON文件
        annotations_dir = osp.join(output_dir, split_name, 'annotations')
        json_filename = f'instance_{split_name}.json'
        json_path = osp.join(annotations_dir, json_filename)
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(coco_data, f, indent=2, ensure_ascii=False)
        
        self.log_message(f"✓ {split_name}集COCO标注生成完成: {json_filename}")
        self.log_message(f"  - 图片数量: {len(coco_data['images'])}")
        self.log_message(f"  - 标注数量: {len(coco_data['annotations'])}")
        self.log_message(f"  - 类别数量: {len(coco_data['categories'])}")
        
        # 验证标签ID一致性
        self.verify_label_consistency(coco_data, global_converter, split_name)
    
    def generate_split_coco_annotations_multi(self, output_dir, split_name, files, global_converter, progress_start, progress_end):
        """为指定子集生成COCO格式标注（多文件夹版本）"""
        self.log_message(f"生成{split_name}集COCO标注...")
        
        # 使用全局转换器，确保标签ID一致
        # 注意：这里不再创建新的converter实例
        
        # 处理文件
        coco_data = self.process_split_json_files_multi(global_converter, files, split_name)
        
        # 保存COCO JSON文件
        annotations_dir = osp.join(output_dir, split_name, 'annotations')
        json_filename = f'instance_{split_name}.json'
        json_path = osp.join(annotations_dir, json_filename)
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(coco_data, f, indent=2, ensure_ascii=False)
        
        self.log_message(f"✓ {split_name}集COCO标注生成完成: {json_filename}")
        self.log_message(f"  - 图片数量: {len(coco_data['images'])}")
        self.log_message(f"  - 标注数量: {len(coco_data['annotations'])}")
        self.log_message(f"  - 类别数量: {len(coco_data['categories'])}")
        
        # 验证标签ID一致性
        self.verify_label_consistency(coco_data, global_converter, split_name)
    
    def verify_label_consistency(self, coco_data, global_converter, split_name):
        """验证标签ID一致性"""
        self.log_message(f"验证{split_name}集标签ID一致性...")
        
        # 检查categories中的标签ID
        for category in coco_data['categories']:
            label_name = category['name']
            category_id = category['id']
            expected_id = global_converter.label_to_num.get(label_name)
            
            if expected_id is None:
                self.log_message(f"  警告: 标签 '{label_name}' 在全局映射中未找到")
            elif expected_id != category_id:
                self.log_message(f"  错误: 标签 '{label_name}' ID不匹配 - 期望{expected_id}, 实际{category_id}")
            else:
                self.log_message(f"  ✓ 标签 '{label_name}' ID一致: {category_id}")
        
        # 检查annotations中的category_id
        invalid_annotations = 0
        valid_category_ids = set(global_converter.label_to_num.values())
        for annotation in coco_data['annotations']:
            category_id = annotation['category_id']
            if category_id not in valid_category_ids:
                invalid_annotations += 1
                self.log_message(f"  错误: 标注ID {annotation['id']} 的category_id {category_id} 不在有效范围内 {sorted(valid_category_ids)}")
        
        if invalid_annotations == 0:
            self.log_message(f"  ✓ {split_name}集所有标注的category_id都有效")
        else:
            self.log_message(f"  ⚠ {split_name}集有 {invalid_annotations} 个标注的category_id无效")
    
    def process_split_json_files(self, converter, input_dir, files, split_name):
        """处理指定子集的JSON文件"""
        data_coco = {}
        images_list = []
        annotations_list = []
        image_num = -1
        object_num = -1
        processed_annotations_set = set()
        
        # 文件名到image_id的映射
        file_name_to_image_id = {}
        
        # 使用传入的全局转换器，不再重新创建标签映射
        # 注意：converter.labels_list 和 converter.label_to_num 已经在全局映射中建立
        
        for i, img_file in enumerate(files):
            img_label = os.path.splitext(os.path.basename(img_file))[0]
            label_file = osp.join(input_dir, img_label + '.json')
            
            if not os.path.exists(label_file):
                self.log_message(f"警告: 找不到对应的JSON文件 {label_file}")
                continue
            
            try:
                with open(label_file, encoding='utf-8') as f:
                    data = json.load(f)
                
                # 统一获取文件名
                if '\\' in data['imagePath']:
                    current_file_name = data['imagePath'].split('\\')[-1]
                else:
                    current_file_name = data['imagePath'].split('/')[-1]
                
                # 分配image_id
                if current_file_name in file_name_to_image_id:
                    current_image_id = file_name_to_image_id[current_file_name]
                    image_num_for_converter = current_image_id - 1
                else:
                    image_num = image_num + 1
                    current_image_id = image_num + 1
                    file_name_to_image_id[current_file_name] = current_image_id
                    
                    # 添加图片信息
                    images_list.append({
                        'height': data['imageHeight'],
                        'width': data['imageWidth'],
                        'id': current_image_id,
                        'file_name': current_file_name
                    })
                    image_num_for_converter = image_num
                
                # 处理标注 - 使用全局转换器的标签映射
                for shapes in data['shapes']:
                    label = shapes['label']
                    
                    # 检查标签是否在全局映射中存在
                    if label not in converter.label_to_num:
                        self.log_message(f"警告: 标签 '{label}' 不在全局映射中，跳过该标注")
                        continue
                    
                    p_type = shapes.get('shape_type')
                    temp_bbox = None
                    temp_points = None
                    
                    if p_type == 'polygon':
                        points = shapes.get('points', [])
                        if not isinstance(points, list) or len(points) < 3:
                            continue
                        temp_points = points
                        temp_bbox = list(map(float, converter.get_bbox(data['imageHeight'], data['imageWidth'], points)))
                    elif p_type == 'rectangle':
                        pts = shapes.get('points', [])
                        if not isinstance(pts, list) or len(pts) != 2:
                            continue
                        (x1, y1), (x2, y2) = pts
                        x1, x2 = sorted([x1, x2])
                        y1, y2 = sorted([y1, y2])
                        temp_points = [[x1, y1], [x2, y2]]  # 只需要对角线两点
                        temp_bbox = [float(x1), float(y1), float(x2 - x1), float(y2 - y1)]
                    else:
                        continue
                    
                    # 校验bbox有效性
                    if temp_bbox is None or temp_bbox[2] <= 0 or temp_bbox[3] <= 0:
                        continue
                    
                    # 去重
                    rounded_bbox = tuple(round(v, 2) for v in temp_bbox)
                    category_id = converter.label_to_num[label]
                    ann_key = (current_image_id, category_id, rounded_bbox)
                    if ann_key in processed_annotations_set:
                        continue
                    processed_annotations_set.add(ann_key)
                    
                    # 生成annotation
                    object_num = object_num + 1
                    if p_type == 'polygon':
                        annotations_list.append(
                            converter.annotations_polygon(
                                data['imageHeight'], data['imageWidth'], temp_points, label, image_num_for_converter, object_num
                            )
                        )
                    else:  # rectangle
                        annotations_list.append(
                            converter.annotations_rectangle(temp_points, label, image_num_for_converter, object_num)
                        )
                        
            except Exception as e:
                self.log_message(f"处理文件 {label_file} 时出错: {e}")
                continue
        
        # 使用全局转换器的categories_list，确保标签ID一致
        data_coco['images'] = images_list
        data_coco['categories'] = converter.categories_list
        data_coco['annotations'] = annotations_list
        
        # 添加COCO格式必需的info字段
        data_coco['info'] = {
            "description": "Converted from Labelme format", 
            "version": "1.0",
            "year": 2024,
            "contributor": "Labelme to COCO Converter",
            "date_created": str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        }
        
        return data_coco
    
    def process_json_files(self, converter, input_dir, total_files):
        """处理JSON文件并转换为COCO格式"""
        data_coco = {}
        images_list = []
        annotations_list = []
        image_num = -1
        object_num = -1
        # 新增：已处理标注集合，防止重复（按 image_id, category_id, rounded_bbox 去重）
        processed_annotations_set = set()
        
        # 获取所有图片文件并去重
        raw_image_files = []
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.JPG', '*.JPEG', '*.PNG']:
            raw_image_files.extend(glob.glob(osp.join(input_dir, ext)))
        image_files = []
        seen_paths = set()
        for p in raw_image_files:
            key = os.path.normcase(os.path.abspath(p))
            if key not in seen_paths:
                seen_paths.add(key)
                image_files.append(p)
        
        processed_count = 0
        # 新增：文件名到image_id的映射，防止同名图片重复加入
        file_name_to_image_id = {}
        for img_file in image_files:
            img_label = os.path.splitext(os.path.basename(img_file))[0]
            label_file = osp.join(input_dir, img_label + '.json')
            
            if not os.path.exists(label_file):
                self.log_message(f"警告: 找不到对应的JSON文件 {label_file}")
                continue
                
            self.log_message(f'处理文件: {label_file}')
            # 读取JSON以确定 file_name 和尺寸
            
            try:
                with open(label_file, encoding='utf-8') as f:
                    data = json.load(f)
                
                # 统一获取文件名（兼容不同分隔符）
                if '\\' in data['imagePath']:
                    current_file_name = data['imagePath'].split('\\')[-1]
                else:
                    current_file_name = data['imagePath'].split('/')[-1]
                
                # 分配/复用 image_id，确保同名图片只出现一次
                if current_file_name in file_name_to_image_id:
                    current_image_id = file_name_to_image_id[current_file_name]
                    # 覆盖本次用于annotation的 image_num（converter内部用 image_num+1），保持一致
                    image_num_for_converter = current_image_id - 1
                else:
                    image_num = image_num + 1
                    current_image_id = image_num + 1
                    file_name_to_image_id[current_file_name] = current_image_id
                    # 添加图片信息
                    images_list.append({
                        'height': data['imageHeight'],
                        'width': data['imageWidth'],
                        'id': current_image_id,
                        'file_name': current_file_name
                    })
                    image_num_for_converter = image_num
                
                # 处理标注
                for shapes in data['shapes']:
                    label = shapes['label']
                    
                    if label not in converter.labels_list:
                        converter.categories_list.append(converter.categories(label))
                        converter.labels_list.append(label)
                        converter.label_to_num[label] = len(converter.labels_list)
                    
                    p_type = shapes.get('shape_type')
                    temp_bbox = None
                    temp_points = None
                    
                    if p_type == 'polygon':
                        points = shapes.get('points', [])
                        if not isinstance(points, list) or len(points) < 3:
                            self.log_message("警告: 多边形标注点数量不足，跳过该标注")
                            continue
                        temp_points = points
                        temp_bbox = list(map(float, converter.get_bbox(data['imageHeight'], data['imageWidth'], points)))
                    elif p_type == 'rectangle':
                        pts = shapes.get('points', [])
                        if not isinstance(pts, list) or len(pts) != 2:
                            self.log_message("警告: 矩形标注点数量不正确，跳过该标注")
                            continue
                        (x1, y1), (x2, y2) = pts
                        x1, x2 = sorted([x1, x2])
                        y1, y2 = sorted([y1, y2])
                        # 正确生成矩形的四个顶点，按逆时针顺序排列
                        temp_points = [[x1, y1], [x2, y2]]  # 只需要对角线两点，annotations_rectangle会处理
                        temp_bbox = [float(x1), float(y1), float(x2 - x1), float(y2 - y1)]
                    else:
                        self.log_message(f"警告: 不支持的形状类型 '{p_type}'，跳过该标注")
                        continue
                    
                    # 校验bbox有效性
                    if temp_bbox is None or temp_bbox[2] <= 0 or temp_bbox[3] <= 0:
                        self.log_message(f"警告: 无效的bbox {temp_bbox}，跳过该标注")
                        continue
                    
                    # 去重：按 image_id, category_id, 取两位小数的bbox
                    rounded_bbox = tuple(round(v, 2) for v in temp_bbox)
                    # 当前 image_id 已统一
                    category_id = converter.label_to_num[label]
                    ann_key = (current_image_id, category_id, rounded_bbox)
                    if ann_key in processed_annotations_set:
                        # 已存在，跳过重复
                        continue
                    processed_annotations_set.add(ann_key)
                    
                    # 生成并添加annotation（只在确定添加时递增object_num）
                    object_num = object_num + 1
                    if p_type == 'polygon':
                        annotations_list.append(
                            converter.annotations_polygon(
                                data['imageHeight'], data['imageWidth'], temp_points, label, image_num_for_converter, object_num
                            )
                        )
                    else:  # rectangle
                        annotations_list.append(
                            converter.annotations_rectangle(temp_points, label, image_num_for_converter, object_num)
                        )
                              
            except Exception as e:
                self.log_message(f"处理文件 {label_file} 时出错: {e}")
                continue
            
            processed_count += 1
            self.progress_var.set(0.3 + (processed_count / total_files) * 0.7)  # 剩余70%进度用于处理
        
        data_coco['images'] = images_list
        data_coco['categories'] = converter.categories_list
        data_coco['annotations'] = annotations_list
        
        # 添加COCO格式必需的info字段
        data_coco['info'] = {
            "description": "Converted from Labelme format",
            "version": "1.0",
            "year": 2024,
            "contributor": "Labelme to COCO Converter",
            "date_created": str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        }
        
        return data_coco
    
    # ==================== 多文件夹管理方法 ====================
    
    def add_input_folder(self):
        """添加输入文件夹"""
        directory = filedialog.askdirectory(title="选择包含JSON文件和图片的文件夹")
        if directory:
            self._add_single_folder(directory)
    
    def add_multiple_folders(self):
        """添加多个输入文件夹"""
        import tkinter.filedialog as fd
        
        # 创建一个简单的多选文件夹对话框
        root_temp = tk.Toplevel(self.root)
        root_temp.withdraw()  # 隐藏临时窗口
        
        try:
            # 使用循环方式让用户选择多个文件夹
            selected_folders = []
            
            while True:
                directory = filedialog.askdirectory(
                    parent=root_temp,
                    title=f"选择文件夹 (已选择 {len(selected_folders)} 个，取消结束选择)"
                )
                
                if not directory:  # 用户取消选择
                    break
                    
                if directory in selected_folders:
                    messagebox.showwarning("警告", "该文件夹已经在选择列表中")
                    continue
                    
                if directory in self.input_folders:
                    messagebox.showwarning("警告", "该文件夹已经添加过了")
                    continue
                
                selected_folders.append(directory)
                
                # 询问是否继续添加
                if not messagebox.askyesno("继续选择", 
                                          f"已选择 {len(selected_folders)} 个文件夹\n"
                                          f"最新添加: {os.path.basename(directory)}\n\n"
                                          f"是否继续选择更多文件夹？"):
                    break
            
            root_temp.destroy()
            
            if not selected_folders:
                return
            
            # 添加所有选中的文件夹
            self.log_message(f"开始添加 {len(selected_folders)} 个文件夹...")
            
            added_count = 0
            for directory in selected_folders:
                if self._add_single_folder(directory, batch_mode=True):
                    added_count += 1
            
            # 批量更新完成后统一刷新界面
            if added_count > 0:
                self.update_folders_display()
                self.update_folders_stats()
                self._rebuild_state_and_refresh_ui(reason="批量添加文件夹")
                
                self.log_message(f"批量添加完成: 成功添加 {added_count} 个文件夹")
                messagebox.showinfo("完成", f"成功添加 {added_count} 个文件夹")
            else:
                self.log_message("批量添加取消: 没有添加任何文件夹")
                
        except Exception as e:
            root_temp.destroy()
            self.log_message(f"批量添加文件夹时出错: {e}")
            messagebox.showerror("错误", f"批量添加文件夹时出错: {e}")
    
    def _add_single_folder(self, directory, batch_mode=False):
        """添加单个文件夹的内部方法"""
        try:
            # 检查文件夹是否已经添加
            if directory in self.input_folders:
                if not batch_mode:
                    messagebox.showwarning("警告", "该文件夹已经添加过了")
                return False
            
            # 获取文件夹名称（显示用）
            folder_name = os.path.basename(directory)
            if not folder_name:
                folder_name = directory
            
            # 扫描文件夹中的图片文件
            image_files = self.get_image_files(directory)
            
            if not image_files:
                self.log_message(f"警告: 文件夹 {folder_name} 中没有找到图片文件")
                if not batch_mode:
                    messagebox.showwarning("警告", f"文件夹 {folder_name} 中没有找到图片文件")
                return False
            
            # 添加到文件夹列表
            self.input_folders[directory] = image_files
            self.folder_names[directory] = folder_name
            
            # 扫描该文件夹的标签
            folder_labels = self.scan_folder_labels(directory)
            self.folder_labels[directory] = folder_labels
            
            # 非批量模式时立即更新显示
            if not batch_mode:
                self.update_folders_display()
                self.update_folders_stats()
                self._rebuild_state_and_refresh_ui(reason="添加文件夹")
            
            self.log_message(f"添加文件夹: {folder_name} ({len(image_files)} 个图片文件, {len(folder_labels)} 个标签)")
            return True
            
        except Exception as e:
            self.log_message(f"添加文件夹 {directory} 时出错: {e}")
            if not batch_mode:
                messagebox.showerror("错误", f"添加文件夹时出错: {e}")
            return False
    
    def remove_input_folder(self):
        """移除选中的输入文件夹"""
        selection = self.folders_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要移除的文件夹")
            return
        
        item = self.folders_tree.item(selection[0])
        values = item['values']
        if values and len(values) >= 2 and values[0] != '请添加文件夹':  # 不是初始提示行
            folder_name = values[0]  # 文件夹名称在第一列
            
            # 根据文件夹名称找到对应的路径
            folder_path_to_remove = None
            for folder_path in self.input_folders.keys():
                if self.folder_names.get(folder_path, os.path.basename(folder_path)) == folder_name:
                    folder_path_to_remove = folder_path
                    break
            
            if folder_path_to_remove:
                # 从字典中移除
                del self.input_folders[folder_path_to_remove]
                if folder_path_to_remove in self.folder_names:
                    del self.folder_names[folder_path_to_remove]
                if folder_path_to_remove in self.folder_labels:
                    del self.folder_labels[folder_path_to_remove]
                
                # 更新显示
                self.update_folders_display()
                self.update_folders_stats()
                self._rebuild_state_and_refresh_ui(reason="移除文件夹")
                
                self.log_message(f"移除文件夹: {folder_name} ({folder_path_to_remove})")
            else:
                messagebox.showerror("错误", f"未找到文件夹: {folder_name}")
    
    def clear_all_folders(self):
        """清空所有输入文件夹"""
        if not self.input_folders:
            messagebox.showinfo("提示", "没有添加任何文件夹")
            return
        
        if messagebox.askyesno("确认", f"确定要清空所有 {len(self.input_folders)} 个文件夹吗？"):
            self.input_folders.clear()
            self.folder_names.clear()
            self.folder_labels.clear()
            
            # 更新显示
            self.update_folders_display()
            self.update_folders_stats()
            self._rebuild_state_and_refresh_ui(reason="清空所有文件夹")
            
            self.log_message("已清空所有文件夹")
    
    def update_folders_display(self):
        """更新文件夹列表显示"""
        # 更新简化列表
        if hasattr(self, 'folders_listbox'):
            self.folders_listbox.delete(0, tk.END)
            if not self.input_folders:
                self.folders_listbox.insert(tk.END, "请添加输入文件夹...")
            else:
                for folder_path, files in self.input_folders.items():
                    folder_name = self.folder_names.get(folder_path, os.path.basename(folder_path))
                    label_count = len(self.folder_labels.get(folder_path, set()))
                    self.folders_listbox.insert(tk.END, f"{folder_name} ({len(files)}个文件, {label_count}个标签)")
        
        # 更新详细表格
        if hasattr(self, 'folders_tree'):
            for item in self.folders_tree.get_children():
                self.folders_tree.delete(item)
            
            if not self.input_folders:
                self.folders_tree.insert('', 'end', values=('请添加文件夹', '--', '--', '--', '未添加'))
            else:
                for folder_path, image_files in self.input_folders.items():
                    folder_name = self.folder_names.get(folder_path, os.path.basename(folder_path))
                    file_count = len(image_files)
                    label_count = self.get_folder_label_count(folder_path)
                    # 显示文件夹独立的标签
                    folder_labels = self.folder_labels.get(folder_path, set())
                    if folder_labels:
                        labels_preview = ', '.join(sorted(list(folder_labels))[:3])
                        labels_display = f"{label_count}个 ({labels_preview}{'...' if len(folder_labels) > 3 else ''})"
                    else:
                        labels_display = f"{label_count}个 (无标签)"
                    status = "已添加"
                    
                    self.folders_tree.insert('', 'end', values=(folder_name, folder_path, file_count, labels_display, status))
    
    def update_folders_stats(self):
        """更新文件夹统计信息"""
        total_folders = len(self.input_folders)
        total_files = sum(len(files) for files in self.input_folders.values())
        
        # 计算总标签数量（去重）
        all_labels = set()
        for labels in self.folder_labels.values():
            all_labels.update(labels)
        total_labels = len(all_labels)
        
        self.folders_stats_label.config(
            text=f"已添加 {total_folders} 个文件夹，共 {total_files} 个文件，{total_labels} 个标签"
        )
        
        # 更新文件夹标签详情显示
        self.update_folders_detail_display()
    
    def update_folders_detail_display(self):
        """更新文件夹标签详情显示"""
        if not hasattr(self, 'folders_detail_text'):
            return
            
        # 清空现有内容
        self.folders_detail_text.config(state=tk.NORMAL)
        self.folders_detail_text.delete(1.0, tk.END)
        
        if not self.input_folders:
            self.folders_detail_text.insert(tk.END, "请先添加文件夹，然后查看各文件夹的标签详情。\n\n")
            self.folders_detail_text.insert(tk.END, "操作说明：\n")
            self.folders_detail_text.insert(tk.END, "1. 点击'添加文件夹'按钮添加包含JSON文件的文件夹\n")
            self.folders_detail_text.insert(tk.END, "2. 系统会自动扫描每个文件夹中的标签\n")
            self.folders_detail_text.insert(tk.END, "3. 在此处查看每个文件夹的标签详情")
        else:
            self.folders_detail_text.insert(tk.END, f"文件夹标签详情统计 (共 {len(self.input_folders)} 个文件夹)\n")
            self.folders_detail_text.insert(tk.END, "=" * 60 + "\n\n")
            
            for i, (folder_path, image_files) in enumerate(self.input_folders.items(), 1):
                folder_name = self.folder_names.get(folder_path, os.path.basename(folder_path))
                labels = self.folder_labels.get(folder_path, set())
                
                self.folders_detail_text.insert(tk.END, f"{i}. {folder_name}\n")
                self.folders_detail_text.insert(tk.END, f"   路径: {folder_path}\n")
                self.folders_detail_text.insert(tk.END, f"   文件数量: {len(image_files)} 个\n")
                self.folders_detail_text.insert(tk.END, f"   标签数量: {len(labels)} 个\n")
                
                if labels:
                    self.folders_detail_text.insert(tk.END, "   标签列表: ")
                    sorted_labels = sorted(labels)
                    # 每行显示最多5个标签
                    for j, label in enumerate(sorted_labels):
                        if j > 0 and j % 5 == 0:
                            self.folders_detail_text.insert(tk.END, f"\n             ")
                        self.folders_detail_text.insert(tk.END, f"{label}")
                        if j < len(sorted_labels) - 1:
                            self.folders_detail_text.insert(tk.END, ", ")
                    self.folders_detail_text.insert(tk.END, "\n")
                else:
                    self.folders_detail_text.insert(tk.END, "   标签列表: 暂无标签\n")
                
                self.folders_detail_text.insert(tk.END, "\n")
            
            # 添加全局标签统计
            all_labels = set()
            for labels in self.folder_labels.values():
                all_labels.update(labels)
            
            self.folders_detail_text.insert(tk.END, "全局标签汇总\n")
            self.folders_detail_text.insert(tk.END, "=" * 30 + "\n")
            self.folders_detail_text.insert(tk.END, f"去重后总标签数: {len(all_labels)} 个\n")
            
            if all_labels:
                self.folders_detail_text.insert(tk.END, "全部标签: ")
                sorted_all_labels = sorted(all_labels)
                for j, label in enumerate(sorted_all_labels):
                    if j > 0 and j % 5 == 0:
                        self.folders_detail_text.insert(tk.END, f"\n          ")
                    self.folders_detail_text.insert(tk.END, f"{label}")
                    if j < len(sorted_all_labels) - 1:
                        self.folders_detail_text.insert(tk.END, ", ")
                self.folders_detail_text.insert(tk.END, "\n")
        
        self.folders_detail_text.config(state=tk.DISABLED)
    
    def scan_all_folders(self):
        """扫描所有文件夹建立标签映射"""
        if not self.input_folders:
            messagebox.showwarning("警告", "请先添加至少一个文件夹")
            return
        
        try:
            # 扫描按钮已移除，不再需要禁用/启用
            self.log_message("开始扫描所有文件夹建立标签映射...")
            
            # 建立全局标签映射
            self.global_converter = SimpleLabelme2COCO()
            
            # 统一扫描所有文件夹的标签（避免重复）
            self.build_unified_label_mapping()
            total_files = sum(len(files) for files in self.input_folders.values())
            
            # 显示标签映射
            self.display_label_mapping()
            
            # 启用相关按钮
            self.refresh_labels_btn.config(state='normal')
            self.update_label_btn.config(state='normal')
            self.reset_labels_btn.config(state='normal')
            self.save_mapping_btn.config(state='normal')
            self.load_mapping_btn.config(state='normal')
            self.export_mapping_btn.config(state='normal')
            
            # 添加变更历史
            self.add_change_history("扫描完成", f"扫描 {len(self.input_folders)} 个文件夹，发现 {len(self.global_converter.labels_list)} 个标签")
            
            self.log_message(f"标签映射建立完成，共 {len(self.global_converter.labels_list)} 个标签")
            
        except Exception as e:
            self.log_message(f"扫描标签失败: {e}")
            messagebox.showerror("错误", f"扫描标签失败: {e}")
        finally:
            # 扫描按钮已移除，无需恢复状态
            pass
    
    def get_all_image_files(self):
        """获取所有文件夹中的图片文件"""
        all_files = []
        for folder_path, image_files in self.input_folders.items():
            all_files.extend(image_files)
        return all_files
    
    def get_folder_files_dict(self):
        """获取文件夹到文件列表的映射字典"""
        return self.input_folders.copy()
    
    def get_folder_label_count(self, folder_path):
        """获取指定文件夹的标签数量"""
        if not hasattr(self, 'folder_labels'):
            return 0
        
        folder_labels = self.folder_labels.get(folder_path, set())
        return len(folder_labels)
    
    def scan_folder_labels(self, folder_path):
        """扫描指定文件夹的标签"""
        if not os.path.exists(folder_path):
            return set()
        
        labels = set()
        image_files = self.input_folders.get(folder_path, [])
        
        for img_file in image_files:
            img_label = os.path.splitext(os.path.basename(img_file))[0]
            label_file = osp.join(folder_path, img_label + '.json')
            
            if not os.path.exists(label_file):
                continue
                
            try:
                with open(label_file, encoding='utf-8') as f:
                    data = json.load(f)
                
                for shapes in data['shapes']:
                    label = shapes['label']
                    labels.add(label)
                        
            except Exception as e:
                self.log_message(f"扫描文件夹 {folder_path} 标签时出错: {e}")
                continue
        
        return labels
    
    def refresh_folders_data(self):
        """刷新文件夹数据 - 重新扫描文件夹内容"""
        if not self.input_folders:
            messagebox.showinfo("提示", "没有添加任何文件夹")
            return
        
        self.log_message("开始刷新文件夹数据...")
        
        # 重新扫描每个文件夹的文件和标签
        updated_folders = {}
        for folder_path in list(self.input_folders.keys()):
            if os.path.exists(folder_path):
                # 重新扫描图片文件
                image_files = self.get_image_files(folder_path)
                updated_folders[folder_path] = image_files
                
                # 重新扫描标签
                folder_labels = self.scan_folder_labels(folder_path)
                self.folder_labels[folder_path] = folder_labels
                
                folder_name = self.folder_names.get(folder_path, os.path.basename(folder_path))
                self.log_message(f"  {folder_name}: {len(image_files)} 个文件, {len(folder_labels)} 个标签")
            else:
                # 文件夹不存在，从列表中移除
                folder_name = self.folder_names.get(folder_path, folder_path)
                self.log_message(f"  文件夹不存在，已移除: {folder_name}")
                if folder_path in self.folder_names:
                    del self.folder_names[folder_path]
                if folder_path in self.folder_labels:
                    del self.folder_labels[folder_path]
        
        # 更新文件夹列表
        self.input_folders = updated_folders
        
        # 重新建立标签映射
        self._rebuild_state_and_refresh_ui(reason="刷新文件夹数据")
        
        self.log_message("文件夹数据刷新完成")
        messagebox.showinfo("完成", "文件夹数据已刷新")
    
    def scan_folders_integrity(self):
        """扫描文件夹完整性 - 检查标注文件缺失等问题"""
        if not self.input_folders:
            messagebox.showwarning("警告", "请先添加文件夹")
            return
        
        self.log_message("=== 开始文件夹完整性检查 ===")
        
        total_issues = 0
        
        for folder_path, image_files in self.input_folders.items():
            folder_name = self.folder_names.get(folder_path, os.path.basename(folder_path))
            self.log_message(f"\n检查文件夹: {folder_name}")
            self.log_message(f"路径: {folder_path}")
            
            folder_issues = 0
            missing_json_files = []
            missing_image_files = []
            invalid_json_files = []
            
            # 检查图片对应的JSON文件
            for img_file in image_files:
                img_label = os.path.splitext(os.path.basename(img_file))[0]
                json_file = os.path.join(folder_path, img_label + '.json')
                
                if not os.path.exists(json_file):
                    missing_json_files.append(img_label + '.json')
                    folder_issues += 1
                else:
                    # 检查JSON文件是否有效
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        # 检查必要字段
                        required_fields = ['imagePath', 'imageHeight', 'imageWidth', 'shapes']
                        for field in required_fields:
                            if field not in data:
                                invalid_json_files.append(f"{img_label}.json (缺少字段: {field})")
                                folder_issues += 1
                                break
                    except Exception as e:
                        invalid_json_files.append(f"{img_label}.json (解析错误: {str(e)})")
                        folder_issues += 1
            
            # 检查JSON文件对应的图片
            json_files = glob.glob(os.path.join(folder_path, '*.json'))
            for json_file in json_files:
                json_basename = os.path.splitext(os.path.basename(json_file))[0]
                # 查找对应的图片文件
                found_image = False
                for ext in ['.jpg', '.jpeg', '.png', '.bmp', '.JPG', '.JPEG', '.PNG', '.BMP']:
                    img_path = os.path.join(folder_path, json_basename + ext)
                    if os.path.exists(img_path):
                        found_image = True
                        break
                
                if not found_image:
                    missing_image_files.append(json_basename + '.jpg/.png')
                    folder_issues += 1
            
            # 输出检查结果
            if folder_issues == 0:
                self.log_message("  ✅ 文件夹检查通过，无问题")
            else:
                self.log_message(f"  ❌ 发现 {folder_issues} 个问题:")
                
                if missing_json_files:
                    self.log_message(f"    缺少JSON文件 ({len(missing_json_files)}个):")
                    for missing in missing_json_files[:5]:  # 最多显示5个
                        self.log_message(f"      - {missing}")
                    if len(missing_json_files) > 5:
                        self.log_message(f"      ... 还有 {len(missing_json_files) - 5} 个")
                
                if missing_image_files:
                    self.log_message(f"    缺少图片文件 ({len(missing_image_files)}个):")
                    for missing in missing_image_files[:5]:
                        self.log_message(f"      - {missing}")
                    if len(missing_image_files) > 5:
                        self.log_message(f"      ... 还有 {len(missing_image_files) - 5} 个")
                
                if invalid_json_files:
                    self.log_message(f"    无效JSON文件 ({len(invalid_json_files)}个):")
                    for invalid in invalid_json_files[:5]:
                        self.log_message(f"      - {invalid}")
                    if len(invalid_json_files) > 5:
                        self.log_message(f"      ... 还有 {len(invalid_json_files) - 5} 个")
            
            total_issues += folder_issues
        
        self.log_message(f"\n=== 完整性检查完成 ===")
        if total_issues == 0:
            self.log_message("🎉 所有文件夹检查通过，无问题发现")
            messagebox.showinfo("检查完成", "所有文件夹检查通过，无问题发现")
        else:
            self.log_message(f"⚠️ 总共发现 {total_issues} 个问题，请查看日志详情")
            messagebox.showwarning("检查完成", f"发现 {total_issues} 个问题，请查看日志详情")
    
    def modify_folder_labels(self):
        """修改指定文件夹的标签名称"""
        if not self.input_folders:
            messagebox.showwarning("警告", "请先添加文件夹")
            return
        
        # 创建文件夹选择和标签修改窗口
        self.create_label_modification_window()
    
    def create_label_modification_window(self):
        """创建标签修改窗口"""
        # 创建新窗口
        modify_window = tk.Toplevel(self.root)
        modify_window.title("修改文件夹标签名称")
        modify_window.geometry("1000x750")
        modify_window.configure(bg=self.colors['background'])
        modify_window.transient(self.root)
        modify_window.grab_set()
        
        # 主框架
        main_frame = tk.Frame(modify_window, bg=self.colors['background'])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # 标题
        title_label = tk.Label(main_frame,
                              text="📝 智能标签修改工具",
                              bg=self.colors['background'],
                              fg=self.colors['on_background'],
                              font=('Segoe UI', 18, 'bold'))
        title_label.pack(pady=(0, 20))
        
        # 创建notebook用于分页
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # === 第一个标签页：基础修改 ===
        basic_frame = tk.Frame(notebook, bg=self.colors['background'])
        notebook.add(basic_frame, text="📋 基础修改")
        
        # 文件夹选择区域
        folder_frame = tk.LabelFrame(basic_frame,
                                    text="1. 选择要修改的文件夹",
                                    bg=self.colors['surface_container'],
                                    fg=self.colors['on_surface'],
                                    font=('Segoe UI', 12, 'bold'),
                                    padx=15, pady=10)
        folder_frame.pack(fill=tk.X, pady=(10, 15), padx=10)
        
        # 文件夹列表框架
        folder_list_frame = tk.Frame(folder_frame, bg=self.colors['surface_container'])
        folder_list_frame.pack(fill=tk.X, pady=(5, 10))
        
        # 文件夹列表
        folder_listbox = tk.Listbox(folder_list_frame,
                                   bg=self.colors['surface'],
                                   fg=self.colors['on_surface'],
                                   selectbackground=self.colors['primary_container'],
                                   selectforeground=self.colors['on_primary_container'],
                                   font=('Segoe UI', 10),
                                   height=4)
        folder_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 文件夹列表滚动条
        folder_scrollbar = tk.Scrollbar(folder_list_frame, orient=tk.VERTICAL, command=folder_listbox.yview)
        folder_listbox.configure(yscrollcommand=folder_scrollbar.set)
        folder_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 填充文件夹列表
        folder_paths = []
        for folder_path, files in self.input_folders.items():
            folder_name = self.folder_names.get(folder_path, os.path.basename(folder_path))
            labels = self.folder_labels.get(folder_path, set())
            folder_listbox.insert(tk.END, f"{folder_name} ({len(files)}个文件, {len(labels)}个标签)")
            folder_paths.append(folder_path)
        
        # 文件夹操作按钮
        folder_btn_frame = tk.Frame(folder_frame, bg=self.colors['surface_container'])
        folder_btn_frame.pack(fill=tk.X, pady=(5, 0))
        
        # 显示选中文件夹的标签
        self.selected_folder_info_var = tk.StringVar()
        self.selected_folder_info_var.set("请选择一个文件夹查看标签详情")
        folder_info_label = tk.Label(folder_btn_frame,
                                    textvariable=self.selected_folder_info_var,
                                    bg=self.colors['surface_container'],
                                    fg=self.colors['on_surface_variant'],
                                    font=('Segoe UI', 9),
                                    wraplength=800,
                                    justify=tk.LEFT)
        folder_info_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        def on_folder_select(event):
            """文件夹选择事件"""
            selection = folder_listbox.curselection()
            if selection:
                folder_path = folder_paths[selection[0]]
                folder_name = self.folder_names.get(folder_path, os.path.basename(folder_path))
                labels = self.folder_labels.get(folder_path, set())
                if labels:
                    labels_text = ", ".join(sorted(list(labels))[:8])
                    if len(labels) > 8:
                        labels_text += f"... (共{len(labels)}个标签)"
                    self.selected_folder_info_var.set(f"文件夹 '{folder_name}' 的标签: {labels_text}")
                else:
                    self.selected_folder_info_var.set(f"文件夹 '{folder_name}' 没有标签")
                
                # 刷新标签预览
                refresh_label_preview()
        
        folder_listbox.bind('<<ListboxSelect>>', on_folder_select)
        
        # 标签修改区域
        label_frame = tk.LabelFrame(basic_frame,
                                   text="2. 配置标签修改规则",
                                   bg=self.colors['surface_container'],
                                   fg=self.colors['on_surface'],
                                   font=('Segoe UI', 12, 'bold'),
                                   padx=15, pady=10)
        label_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15), padx=10)
        
        # 修改规则表格框架
        rules_table_frame = tk.Frame(label_frame, bg=self.colors['surface_container'])
        rules_table_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 10))
        
        # 修改规则表格
        columns = ('原标签名', '新标签名', '预计修改数', '状态')
        rules_tree = ttk.Treeview(rules_table_frame, columns=columns, show='headings', height=8)
        
        for col in columns:
            rules_tree.heading(col, text=col)
            if col == '预计修改数':
                rules_tree.column(col, width=100, anchor='center')
            elif col == '状态':
                rules_tree.column(col, width=100, anchor='center')
            else:
                rules_tree.column(col, width=150, anchor='w')
        
        # 表格滚动条
        rules_scrollbar = tk.Scrollbar(rules_table_frame, orient=tk.VERTICAL, command=rules_tree.yview)
        rules_tree.configure(yscrollcommand=rules_scrollbar.set)
        
        rules_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        rules_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 添加规则控件
        rule_control_frame = tk.Frame(label_frame, bg=self.colors['surface_container'])
        rule_control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 第一行：输入框
        input_row = tk.Frame(rule_control_frame, bg=self.colors['surface_container'])
        input_row.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(input_row, text="原标签名:",
                bg=self.colors['surface_container'], fg=self.colors['on_surface'],
                font=('Segoe UI', 10)).pack(side=tk.LEFT)
        
        old_label_var = tk.StringVar()
        old_label_entry = tk.Entry(input_row, textvariable=old_label_var,
                                  bg=self.colors['surface'], fg=self.colors['on_surface'],
                                  font=('Segoe UI', 10), width=20)
        old_label_entry.pack(side=tk.LEFT, padx=(5, 15))
        
        tk.Label(input_row, text="新标签名:",
                bg=self.colors['surface_container'], fg=self.colors['on_surface'],
                font=('Segoe UI', 10)).pack(side=tk.LEFT)
        
        new_label_var = tk.StringVar()
        new_label_entry = tk.Entry(input_row, textvariable=new_label_var,
                                  bg=self.colors['surface'], fg=self.colors['on_surface'],
                                  font=('Segoe UI', 10), width=20)
        new_label_entry.pack(side=tk.LEFT, padx=(5, 15))
        
        # 第二行：按钮
        button_row = tk.Frame(rule_control_frame, bg=self.colors['surface_container'])
        button_row.pack(fill=tk.X)
        
        def count_label_occurrences(folder_path, label_name):
            """统计标签在文件夹中的出现次数"""
            if not os.path.exists(folder_path):
                return 0
            
            count = 0
            json_files = glob.glob(os.path.join(folder_path, '*.json'))
            
            for json_file in json_files:
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    if 'shapes' in data:
                        for shape in data['shapes']:
                            if 'label' in shape and shape['label'] == label_name:
                                count += 1
                except:
                    continue
            
            return count
        
        def refresh_label_preview():
            """刷新标签预览统计"""
            # 更新所有规则的预计修改数
            for item in rules_tree.get_children():
                values = list(rules_tree.item(item)['values'])
                old_label = values[0]
                
                # 获取当前选中的文件夹
                folder_selection = folder_listbox.curselection()
                if folder_selection:
                    folder_path = folder_paths[folder_selection[0]]
                    count = count_label_occurrences(folder_path, old_label)
                    values[2] = str(count)
                    values[3] = "准备中" if count > 0 else "无匹配"
                    rules_tree.item(item, values=values)
        
        def add_rule():
            old_label = old_label_var.get().strip()
            new_label = new_label_var.get().strip()
            
            if not old_label or not new_label:
                messagebox.showwarning("警告", "请输入原标签名和新标签名")
                return
            
            if old_label == new_label:
                messagebox.showwarning("警告", "原标签名和新标签名不能相同")
                return
            
            # 检查是否已存在相同的规则
            for item in rules_tree.get_children():
                values = rules_tree.item(item)['values']
                if values[0] == old_label:
                    messagebox.showwarning("警告", f"已存在标签 '{old_label}' 的修改规则")
                    return
            
            # 统计预计修改数
            folder_selection = folder_listbox.curselection()
            if folder_selection:
                folder_path = folder_paths[folder_selection[0]]
                count = count_label_occurrences(folder_path, old_label)
                status = "准备中" if count > 0 else "无匹配"
            else:
                count = 0
                status = "未选择文件夹"
            
            rules_tree.insert('', 'end', values=(old_label, new_label, str(count), status))
            old_label_var.set("")
            new_label_var.set("")
        
        def remove_rule():
            selection = rules_tree.selection()
            if not selection:
                messagebox.showwarning("警告", "请先选择要删除的规则")
                return
            rules_tree.delete(selection[0])
        
        def load_folder_labels():
            """加载选中文件夹的标签"""
            selection = folder_listbox.curselection()
            if not selection:
                messagebox.showwarning("警告", "请先选择一个文件夹")
                return
            
            folder_path = folder_paths[selection[0]]
            labels = self.folder_labels.get(folder_path, set())
            
            if not labels:
                messagebox.showinfo("提示", "选中的文件夹没有标签")
                return
            
            # 创建标签选择窗口
            label_select_window = tk.Toplevel(modify_window)
            label_select_window.title("选择要修改的标签")
            label_select_window.geometry("500x400")
            label_select_window.configure(bg=self.colors['background'])
            label_select_window.transient(modify_window)
            
            # 标题
            tk.Label(label_select_window, text="双击标签名添加到修改规则:",
                    bg=self.colors['background'], fg=self.colors['on_background'],
                    font=('Segoe UI', 12, 'bold')).pack(pady=10)
            
            # 标签列表框架
            list_frame = tk.Frame(label_select_window, bg=self.colors['background'])
            list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
            
            # 标签列表（带统计信息）
            label_listbox = tk.Listbox(list_frame,
                                      bg=self.colors['surface'],
                                      fg=self.colors['on_surface'],
                                      font=('Segoe UI', 10))
            label_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            # 滚动条
            label_scroll = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=label_listbox.yview)
            label_listbox.configure(yscrollcommand=label_scroll.set)
            label_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            
            # 填充标签列表（带统计）
            for label in sorted(labels):
                count = count_label_occurrences(folder_path, label)
                label_listbox.insert(tk.END, f"{label} ({count}个标注)")
            
            def on_label_double_click(event):
                selection = label_listbox.curselection()
                if selection:
                    selected_text = label_listbox.get(selection[0])
                    selected_label = selected_text.split(' (')[0]  # 提取标签名
                    old_label_var.set(selected_label)
                    label_select_window.destroy()
            
            label_listbox.bind('<Double-Button-1>', on_label_double_click)
        
        def clear_all_rules():
            """清空所有规则"""
            if rules_tree.get_children():
                if messagebox.askyesno("确认", "确定要清空所有修改规则吗？"):
                    for item in rules_tree.get_children():
                        rules_tree.delete(item)
        
        # 按钮布局
        add_rule_btn = tk.Button(button_row, text="➕ 添加规则",
                                command=add_rule,
                                bg=self.colors['primary'], fg=self.colors['on_primary'],
                                font=('Segoe UI', 9), relief='flat', cursor='hand2')
        add_rule_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        remove_rule_btn = tk.Button(button_row, text="➖ 删除规则",
                                   command=remove_rule,
                                   bg=self.colors['secondary'], fg=self.colors['on_secondary'],
                                   font=('Segoe UI', 9), relief='flat', cursor='hand2')
        remove_rule_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        load_labels_btn = tk.Button(button_row, text="📋 加载文件夹标签",
                                   command=load_folder_labels,
                                   bg=self.colors['tertiary'], fg=self.colors['on_tertiary'],
                                   font=('Segoe UI', 9), relief='flat', cursor='hand2')
        load_labels_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        clear_rules_btn = tk.Button(button_row, text="🗑️ 清空规则",
                                   command=clear_all_rules,
                                   bg=self.colors['error'], fg=self.colors['on_error'],
                                   font=('Segoe UI', 9), relief='flat', cursor='hand2')
        clear_rules_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        refresh_btn = tk.Button(button_row, text="🔄 刷新统计",
                               command=refresh_label_preview,
                               bg=self.colors['success'], fg=self.colors['on_success'],
                               font=('Segoe UI', 9), relief='flat', cursor='hand2')
        refresh_btn.pack(side=tk.LEFT)
        
        # === 第二个标签页：高级修改 ===
        advanced_frame = tk.Frame(notebook, bg=self.colors['background'])
        notebook.add(advanced_frame, text="🔧 高级修改")
        
        # 高级修改选项
        advanced_options_frame = tk.LabelFrame(advanced_frame,
                                             text="高级修改选项",
                                             bg=self.colors['surface_container'],
                                             fg=self.colors['on_surface'],
                                             font=('Segoe UI', 12, 'bold'),
                                             padx=15, pady=10)
        advanced_options_frame.pack(fill=tk.X, pady=10, padx=10)
        
        # 正则表达式替换选项
        self.use_regex_var = tk.BooleanVar()
        regex_check = tk.Checkbutton(advanced_options_frame,
                                   text="启用正则表达式替换",
                                   variable=self.use_regex_var,
                                   bg=self.colors['surface_container'],
                                   fg=self.colors['on_surface'],
                                   font=('Segoe UI', 10))
        regex_check.pack(anchor=tk.W, pady=5)
        
        # 大小写敏感选项
        self.case_sensitive_var = tk.BooleanVar(value=True)
        case_check = tk.Checkbutton(advanced_options_frame,
                                  text="大小写敏感",
                                  variable=self.case_sensitive_var,
                                  bg=self.colors['surface_container'],
                                  fg=self.colors['on_surface'],
                                  font=('Segoe UI', 10))
        case_check.pack(anchor=tk.W, pady=5)
        
        # 备份选项
        self.create_backup_var = tk.BooleanVar(value=True)
        backup_check = tk.Checkbutton(advanced_options_frame,
                                    text="创建备份文件（推荐）",
                                    variable=self.create_backup_var,
                                    bg=self.colors['surface_container'],
                                    fg=self.colors['on_surface'],
                                    font=('Segoe UI', 10))
        backup_check.pack(anchor=tk.W, pady=5)
        
        # 批量替换模板
        template_frame = tk.LabelFrame(advanced_frame,
                                     text="快速替换模板",
                                     bg=self.colors['surface_container'],
                                     fg=self.colors['on_surface'],
                                     font=('Segoe UI', 12, 'bold'),
                                     padx=15, pady=10)
        template_frame.pack(fill=tk.X, pady=10, padx=10)
        
        # 模板按钮
        template_btn_frame = tk.Frame(template_frame, bg=self.colors['surface_container'])
        template_btn_frame.pack(fill=tk.X, pady=5)
        
        def apply_template(template_type):
            """应用替换模板"""
            selection = folder_listbox.curselection()
            if not selection:
                messagebox.showwarning("警告", "请先选择一个文件夹")
                return
            
            folder_path = folder_paths[selection[0]]
            labels = self.folder_labels.get(folder_path, set())
            
            if not labels:
                messagebox.showinfo("提示", "选中的文件夹没有标签")
                return
            
            # 清空现有规则
            for item in rules_tree.get_children():
                rules_tree.delete(item)
            
            if template_type == "remove_prefix":
                prefix = simpledialog.askstring("移除前缀", "请输入要移除的前缀:")
                if prefix:
                    for label in labels:
                        if label.startswith(prefix):
                            new_label = label[len(prefix):]
                            if new_label:  # 确保新标签不为空
                                count = count_label_occurrences(folder_path, label)
                                rules_tree.insert('', 'end', values=(label, new_label, str(count), "准备中" if count > 0 else "无匹配"))
            
            elif template_type == "remove_suffix":
                suffix = simpledialog.askstring("移除后缀", "请输入要移除的后缀:")
                if suffix:
                    for label in labels:
                        if label.endswith(suffix):
                            new_label = label[:-len(suffix)]
                            if new_label:  # 确保新标签不为空
                                count = count_label_occurrences(folder_path, label)
                                rules_tree.insert('', 'end', values=(label, new_label, str(count), "准备中" if count > 0 else "无匹配"))
            
            elif template_type == "add_prefix":
                prefix = simpledialog.askstring("添加前缀", "请输入要添加的前缀:")
                if prefix:
                    for label in labels:
                        new_label = prefix + label
                        count = count_label_occurrences(folder_path, label)
                        rules_tree.insert('', 'end', values=(label, new_label, str(count), "准备中" if count > 0 else "无匹配"))
            
            elif template_type == "add_suffix":
                suffix = simpledialog.askstring("添加后缀", "请输入要添加的后缀:")
                if suffix:
                    for label in labels:
                        new_label = label + suffix
                        count = count_label_occurrences(folder_path, label)
                        rules_tree.insert('', 'end', values=(label, new_label, str(count), "准备中" if count > 0 else "无匹配"))
            
            elif template_type == "replace_char":
                old_char = simpledialog.askstring("字符替换", "请输入要替换的字符:")
                if old_char:
                    new_char = simpledialog.askstring("字符替换", "请输入新字符:")
                    if new_char is not None:  # 允许空字符
                        for label in labels:
                            if old_char in label:
                                new_label = label.replace(old_char, new_char)
                                count = count_label_occurrences(folder_path, label)
                                rules_tree.insert('', 'end', values=(label, new_label, str(count), "准备中" if count > 0 else "无匹配"))
            
            elif template_type == "to_lowercase":
                for label in labels:
                    new_label = label.lower()
                    if new_label != label:
                        count = count_label_occurrences(folder_path, label)
                        rules_tree.insert('', 'end', values=(label, new_label, str(count), "准备中" if count > 0 else "无匹配"))
            
            elif template_type == "to_uppercase":
                for label in labels:
                    new_label = label.upper()
                    if new_label != label:
                        count = count_label_occurrences(folder_path, label)
                        rules_tree.insert('', 'end', values=(label, new_label, str(count), "准备中" if count > 0 else "无匹配"))
        
        # 模板按钮
        templates = [
            ("移除前缀", "remove_prefix"),
            ("移除后缀", "remove_suffix"),
            ("添加前缀", "add_prefix"),
            ("添加后缀", "add_suffix"),
            ("字符替换", "replace_char"),
            ("转小写", "to_lowercase"),
            ("转大写", "to_uppercase")
        ]
        
        for i, (text, template_type) in enumerate(templates):
            btn = tk.Button(template_btn_frame, text=text,
                           command=lambda t=template_type: apply_template(t),
                           bg=self.colors['tertiary'], fg=self.colors['on_tertiary'],
                           font=('Segoe UI', 9), relief='flat', cursor='hand2')
            btn.pack(side=tk.LEFT, padx=(0, 5), pady=2)
            if i == 3:  # 换行
                template_btn_frame2 = tk.Frame(template_frame, bg=self.colors['surface_container'])
                template_btn_frame2.pack(fill=tk.X, pady=5)
                template_btn_frame = template_btn_frame2
        
        # === 底部操作按钮 ===
        button_frame = tk.Frame(main_frame, bg=self.colors['background'])
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        def execute_modification():
            """执行标签修改"""
            # 检查是否选择了文件夹
            folder_selection = folder_listbox.curselection()
            if not folder_selection:
                messagebox.showwarning("警告", "请先选择要修改的文件夹")
                return
            
            # 检查是否有修改规则
            if not rules_tree.get_children():
                messagebox.showwarning("警告", "请至少添加一条修改规则")
                return
            
            # 获取选中的文件夹路径
            selected_folder_path = folder_paths[folder_selection[0]]
            folder_name = self.folder_names.get(selected_folder_path, os.path.basename(selected_folder_path))
            
            # 获取修改规则
            modification_rules = {}
            total_expected_changes = 0
            for item in rules_tree.get_children():
                values = rules_tree.item(item)['values']
                old_label, new_label, count_str, status = values
                try:
                    count = int(count_str)
                    total_expected_changes += count
                except:
                    count = 0
                modification_rules[old_label] = new_label
            
            # 确认对话框
            rule_text = '\n'.join([f"  {old} → {new}" for old, new in modification_rules.items()])
            confirm_msg = f"确定要修改文件夹 '{folder_name}' 中的标签吗？\n\n"
            confirm_msg += f"修改规则 ({len(modification_rules)} 条):\n{rule_text}\n\n"
            confirm_msg += f"预计修改 {total_expected_changes} 个标注\n\n"
            confirm_msg += "高级选项:\n"
            confirm_msg += f"  正则表达式: {'启用' if self.use_regex_var.get() else '禁用'}\n"
            confirm_msg += f"  大小写敏感: {'是' if self.case_sensitive_var.get() else '否'}\n"
            confirm_msg += f"  创建备份: {'是' if self.create_backup_var.get() else '否'}\n\n"
            confirm_msg += "此操作不可撤销！"
            
            if not messagebox.askyesno("确认修改", confirm_msg):
                return
            
            # 执行修改
            try:
                # 传递高级选项
                advanced_options = {
                    'use_regex': self.use_regex_var.get(),
                    'case_sensitive': self.case_sensitive_var.get(),
                    'create_backup': self.create_backup_var.get()
                }
                
                modified_files, total_modifications = self.execute_label_modification_advanced(
                    selected_folder_path, modification_rules, advanced_options)
                
                # 显示结果
                result_msg = f"标签修改完成！\n\n"
                result_msg += f"文件夹: {folder_name}\n"
                result_msg += f"修改的文件数: {modified_files}\n"
                result_msg += f"总修改次数: {total_modifications}\n\n"
                result_msg += "修改详情:\n"
                for old_label, new_label in modification_rules.items():
                    result_msg += f"  {old_label} → {new_label}\n"
                
                messagebox.showinfo("修改完成", result_msg)
                
                # 关闭窗口并刷新数据
                modify_window.destroy()
                self._rebuild_state_and_refresh_ui(reason="修改文件夹标签")
                
            except Exception as e:
                messagebox.showerror("修改失败", f"修改标签时发生错误:\n{str(e)}")
        
        def preview_changes():
            """预览修改效果"""
            folder_selection = folder_listbox.curselection()
            if not folder_selection:
                messagebox.showwarning("警告", "请先选择要预览的文件夹")
                return
            
            if not rules_tree.get_children():
                messagebox.showwarning("警告", "请至少添加一条修改规则")
                return
            
            selected_folder_path = folder_paths[folder_selection[0]]
            folder_name = self.folder_names.get(selected_folder_path, os.path.basename(selected_folder_path))
            
            # 创建预览窗口
            preview_window = tk.Toplevel(modify_window)
            preview_window.title(f"修改预览 - {folder_name}")
            preview_window.geometry("800x600")
            preview_window.configure(bg=self.colors['background'])
            preview_window.transient(modify_window)
            
            # 预览内容
            preview_text = tk.Text(preview_window,
                                 wrap=tk.WORD,
                                 bg=self.colors['surface'],
                                 fg=self.colors['on_surface'],
                                 font=('Consolas', 9))
            preview_scrollbar = tk.Scrollbar(preview_window, orient=tk.VERTICAL, command=preview_text.yview)
            preview_text.configure(yscrollcommand=preview_scrollbar.set)
            
            preview_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(20, 0), pady=20)
            preview_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=20, padx=(0, 20))
            
            # 生成预览内容
            preview_text.insert(tk.END, f"文件夹修改预览: {folder_name}\n")
            preview_text.insert(tk.END, "=" * 50 + "\n\n")
            
            modification_rules = {}
            for item in rules_tree.get_children():
                values = rules_tree.item(item)['values']
                old_label, new_label = values[0], values[1]
                modification_rules[old_label] = new_label
            
            # 扫描文件并预览修改
            json_files = glob.glob(os.path.join(selected_folder_path, '*.json'))
            total_changes = 0
            
            for json_file in json_files[:20]:  # 限制预览文件数量
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    file_changes = []
                    if 'shapes' in data:
                        for i, shape in enumerate(data['shapes']):
                            if 'label' in shape and shape['label'] in modification_rules:
                                old_label = shape['label']
                                new_label = modification_rules[old_label]
                                file_changes.append((i, old_label, new_label))
                    
                    if file_changes:
                        preview_text.insert(tk.END, f"文件: {os.path.basename(json_file)}\n")
                        for idx, old_label, new_label in file_changes:
                            preview_text.insert(tk.END, f"  标注 {idx+1}: {old_label} → {new_label}\n")
                            total_changes += 1
                        preview_text.insert(tk.END, "\n")
                
                except Exception as e:
                    preview_text.insert(tk.END, f"错误: 无法读取文件 {os.path.basename(json_file)}: {e}\n\n")
            
            if len(json_files) > 20:
                preview_text.insert(tk.END, f"... 还有 {len(json_files) - 20} 个文件未显示\n\n")
            
            preview_text.insert(tk.END, f"预览总结:\n")
            preview_text.insert(tk.END, f"  总文件数: {len(json_files)}\n")
            preview_text.insert(tk.END, f"  预计修改: {total_changes} 个标注\n")
            
            preview_text.config(state=tk.DISABLED)
        
        # 执行和取消按钮
        preview_btn = tk.Button(button_frame, text="👁️ 预览修改",
                               command=preview_changes,
                               bg=self.colors['warning'], fg=self.colors['on_warning'],
                               font=('Segoe UI', 11, 'bold'), relief='flat',
                               cursor='hand2', padx=20, pady=8)
        preview_btn.pack(side=tk.RIGHT, padx=(10, 0))
        
        execute_btn = tk.Button(button_frame, text="🚀 执行修改",
                               command=execute_modification,
                               bg=self.colors['primary'], fg=self.colors['on_primary'],
                               font=('Segoe UI', 11, 'bold'), relief='flat',
                               cursor='hand2', padx=20, pady=8)
        execute_btn.pack(side=tk.RIGHT, padx=(10, 0))
        
        cancel_btn = tk.Button(button_frame, text="❌ 取消",
                              command=modify_window.destroy,
                              bg=self.colors['secondary'], fg=self.colors['on_secondary'],
                              font=('Segoe UI', 11), relief='flat',
                              cursor='hand2', padx=20, pady=8)
        cancel_btn.pack(side=tk.RIGHT)
        
        # 居中显示窗口
        modify_window.update_idletasks()
        width = modify_window.winfo_width()
        height = modify_window.winfo_height()
        x = (modify_window.winfo_screenwidth() // 2) - (width // 2)
        y = (modify_window.winfo_screenheight() // 2) - (height // 2)
        modify_window.geometry(f'{width}x{height}+{x}+{y}')
    
    def execute_label_modification_advanced(self, folder_path, modification_rules, advanced_options=None):
        """执行高级标签修改操作"""
        if not os.path.exists(folder_path):
            raise Exception(f"文件夹不存在: {folder_path}")
        
        # 默认选项
        if advanced_options is None:
            advanced_options = {
                'use_regex': False,
                'case_sensitive': True,
                'create_backup': True
            }
        
        folder_name = self.folder_names.get(folder_path, os.path.basename(folder_path))
        self.log_message(f"=== 开始高级修改文件夹 '{folder_name}' 的标签 ===")
        
        # 记录修改规则和选项
        self.log_message("修改规则:")
        for old_label, new_label in modification_rules.items():
            self.log_message(f"  {old_label} → {new_label}")
        
        self.log_message("高级选项:")
        self.log_message(f"  正则表达式: {'启用' if advanced_options['use_regex'] else '禁用'}")
        self.log_message(f"  大小写敏感: {'是' if advanced_options['case_sensitive'] else '否'}")
        self.log_message(f"  创建备份: {'是' if advanced_options['create_backup'] else '否'}")
        
        modified_files = 0
        total_modifications = 0
        error_files = []
        
        # 获取文件夹中的所有JSON文件
        json_files = glob.glob(os.path.join(folder_path, '*.json'))
        
        self.log_message(f"找到 {len(json_files)} 个JSON文件")
        
        # 创建备份目录
        backup_dir = None
        if advanced_options['create_backup']:
            backup_dir = os.path.join(folder_path, f"backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}")
            os.makedirs(backup_dir, exist_ok=True)
            self.log_message(f"创建备份目录: {backup_dir}")
        
        # 处理正则表达式
        import re
        compiled_patterns = {}
        if advanced_options['use_regex']:
            try:
                for old_pattern, new_pattern in modification_rules.items():
                    flags = 0 if advanced_options['case_sensitive'] else re.IGNORECASE
                    compiled_patterns[old_pattern] = (re.compile(old_pattern, flags), new_pattern)
                self.log_message("正则表达式编译成功")
            except Exception as e:
                raise Exception(f"正则表达式编译失败: {e}")
        
        for json_file in json_files:
            try:
                # 备份原文件
                if backup_dir:
                    backup_file = os.path.join(backup_dir, os.path.basename(json_file))
                    shutil.copy2(json_file, backup_file)
                
                # 读取JSON文件
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 检查是否有需要修改的标签
                file_modified = False
                file_modifications = 0
                modification_details = []
                
                if 'shapes' in data:
                    for shape in data['shapes']:
                        if 'label' in shape:
                            original_label = shape['label']
                            new_label = None
                            
                            if advanced_options['use_regex']:
                                # 正则表达式模式匹配
                                for old_pattern, (compiled_regex, replacement) in compiled_patterns.items():
                                    if compiled_regex.search(original_label):
                                        new_label = compiled_regex.sub(replacement, original_label)
                                        break
                            else:
                                # 普通字符串匹配
                                for old_label, replacement in modification_rules.items():
                                    if advanced_options['case_sensitive']:
                                        if original_label == old_label:
                                            new_label = replacement
                                            break
                                    else:
                                        if original_label.lower() == old_label.lower():
                                            new_label = replacement
                                            break
                            
                            # 应用修改
                            if new_label and new_label != original_label:
                                shape['label'] = new_label
                                file_modified = True
                                file_modifications += 1
                                modification_details.append(f"{original_label} → {new_label}")
                
                # 如果文件被修改，保存文件
                if file_modified:
                    with open(json_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    
                    modified_files += 1
                    total_modifications += file_modifications
                    
                    # 详细日志
                    self.log_message(f"  {os.path.basename(json_file)}: {file_modifications} 个修改")
                    for detail in modification_details:
                        self.log_message(f"    {detail}")

            except Exception as e:
                error_files.append((os.path.basename(json_file), str(e)))
                self.log_message(f"  错误: 处理文件 {os.path.basename(json_file)} 时出错: {e}")
        
        # 记录修改结果
        self.log_message(f"\n=== 高级修改完成 ===")
        self.log_message(f"修改的文件数: {modified_files}")
        self.log_message(f"总修改次数: {total_modifications}")
        
        if error_files:
            self.log_message(f"处理失败的文件: {len(error_files)} 个")
            for filename, error in error_files:
                self.log_message(f"  {filename}: {error}")
        
        if backup_dir:
            self.log_message(f"备份文件保存在: {backup_dir}")
        
        # 如果有错误文件但也有成功修改的文件，仍然返回成功
        if error_files and modified_files == 0:
            raise Exception(f"所有文件处理失败，详情请查看日志")
        
        return modified_files, total_modifications

    def show_folder_labels_detail(self, event):
        """显示文件夹标签详情"""
        selection = self.folders_tree.selection()
        if not selection:
            return
            
        item = self.folders_tree.item(selection[0])
        values = item['values']
        if not values or len(values) < 2 or values[1] == '--':  # 是初始提示行
            return
            
        folder_path = values[1]  # 路径在第二列
        folder_name = values[0]  # 名称在第一列
        
        if folder_path not in self.folder_labels:
            messagebox.showwarning("警告", f"文件夹 {folder_name} 的标签信息未扫描")
            return
        
        labels = self.folder_labels[folder_path]
        if not labels:
            messagebox.showinfo("信息", f"文件夹 {folder_name} 中没有发现标签")
            return
        
        # 创建标签详情窗口
        detail_window = tk.Toplevel(self.root)
        detail_window.title(f"文件夹标签详情 - {folder_name}")
        detail_window.geometry("500x400")
        detail_window.configure(bg=self.colors['background'])
        
        # 标题
        title_label = ttk.Label(detail_window,
                               text=f"文件夹: {folder_name}",
                               font=('Microsoft YaHei UI', 14, 'bold'),
                               foreground=self.colors['primary'],
                               style='Material.TLabel')
        title_label.pack(pady=10)
        
        # 路径信息
        path_label = ttk.Label(detail_window,
                              text=f"路径: {folder_path}",
                              font=('Microsoft YaHei UI', 9),
                              foreground=self.colors['text_secondary'],
                              style='Material.TLabel',
                              wraplength=450)
        path_label.pack(pady=(0, 10))
        
        # 标签列表
        labels_frame = ttk.LabelFrame(detail_window,
                                    text=f"标签列表 (共 {len(labels)} 个)",
                                    padding=10,
                                    style='Material.TLabelframe')
        labels_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
        
        # 创建标签显示区域
        labels_text = tk.Text(labels_frame,
                             wrap=tk.WORD,
                             bg=self.colors['surface'],
                             fg=self.colors['text_primary'],
                             font=('Microsoft YaHei UI', 10),
                             borderwidth=1,
                             relief='solid',
                             padx=10,
                             pady=10)
        
        labels_scrollbar = ttk.Scrollbar(labels_frame, orient=tk.VERTICAL, command=labels_text.yview)
        labels_text.configure(yscrollcommand=labels_scrollbar.set)
        
        # 添加标签内容
        sorted_labels = sorted(labels)
        for i, label in enumerate(sorted_labels, 1):
            labels_text.insert(tk.END, f"{i:2d}. {label}\n")
        
        labels_text.config(state=tk.DISABLED)  # 设为只读
        
        labels_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        labels_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 关闭按钮
        close_btn = ttk.Button(detail_window,
                              text="关闭",
                              command=detail_window.destroy,
                              style='Material.TButton')
        close_btn.pack(pady=(0, 20))
        
        # 居中显示窗口
        detail_window.transient(self.root)
        detail_window.grab_set()
        
        # 计算居中位置
        detail_window.update_idletasks()
        width = detail_window.winfo_width()
        height = detail_window.winfo_height()
        x = (detail_window.winfo_screenwidth() // 2) - (width // 2)
        y = (detail_window.winfo_screenheight() // 2) - (height // 2)
        detail_window.geometry(f'{width}x{height}+{x}+{y}')
    
    def view_selected_folder_labels(self):
        """查看选中文件夹的标签详情"""
        selection = self.folders_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择一个文件夹")
            return
        
        # 模拟双击事件
        class Event:
            pass
        
        self.show_folder_labels_detail(Event())
    
    # ==================== 修改现有方法以支持多文件夹 ====================
    
    def scan_and_show_labels(self):
        """扫描输入目录并显示标签映射（兼容性方法）"""
        # 现在调用新的多文件夹扫描方法
        self.scan_all_folders()
    
    # ==================== 多文件夹处理方法 ====================
    
    def process_split_json_files_multi(self, converter, files, split_name):
        """处理指定子集的JSON文件（多文件夹版本）"""
        data_coco = {}
        images_list = []
        annotations_list = []
        image_num = -1
        object_num = -1
        processed_annotations_set = set()
        
        # 文件名到image_id的映射
        file_name_to_image_id = {}
        
        # 使用传入的全局转换器，不再重新创建标签映射
        # 注意：converter.labels_list 和 converter.label_to_num 已经在全局映射中建立
        
        # 按文件夹分组处理文件
        folder_files = {}
        for img_file in files:
            folder_path = os.path.dirname(img_file)
            if folder_path not in folder_files:
                folder_files[folder_path] = []
            folder_files[folder_path].append(img_file)
        
        self.log_message(f"处理{split_name}集，按文件夹分组:")
        for folder_path, folder_file_list in folder_files.items():
            folder_name = self.folder_names.get(folder_path, os.path.basename(folder_path))
            self.log_message(f"  {folder_name}: {len(folder_file_list)} 个文件")
        
        for i, img_file in enumerate(files):
            img_label = os.path.splitext(os.path.basename(img_file))[0]
            folder_path = os.path.dirname(img_file)
            label_file = osp.join(folder_path, img_label + '.json')
            
            if not os.path.exists(label_file):
                self.log_message(f"警告: 找不到对应的JSON文件 {label_file}")
                continue
            
            try:
                with open(label_file, encoding='utf-8') as f:
                    data = json.load(f)
                
                # 统一获取文件名
                if '\\' in data['imagePath']:
                    current_file_name = data['imagePath'].split('\\')[-1]
                else:
                    current_file_name = data['imagePath'].split('/')[-1]
                
                # 分配image_id
                if current_file_name in file_name_to_image_id:
                    current_image_id = file_name_to_image_id[current_file_name]
                    image_num_for_converter = current_image_id - 1
                else:
                    image_num = image_num + 1
                    current_image_id = image_num + 1
                    file_name_to_image_id[current_file_name] = current_image_id
                    
                    # 添加图片信息
                    images_list.append({
                        'height': data['imageHeight'],
                        'width': data['imageWidth'],
                        'id': current_image_id,
                        'file_name': current_file_name
                    })
                    image_num_for_converter = image_num
                
                # 处理标注 - 使用全局转换器的标签映射
                for shapes in data['shapes']:
                    label = shapes['label']
                    
                    # 检查标签是否在全局映射中存在
                    if label not in converter.label_to_num:
                        self.log_message(f"警告: 标签 '{label}' 不在全局映射中，跳过该标注")
                        continue
                    
                    p_type = shapes.get('shape_type')
                    temp_bbox = None
                    temp_points = None
                    
                    if p_type == 'polygon':
                        points = shapes.get('points', [])
                        if not isinstance(points, list) or len(points) < 3:
                            continue
                        temp_points = points
                        temp_bbox = list(map(float, converter.get_bbox(data['imageHeight'], data['imageWidth'], points)))
                    elif p_type == 'rectangle':
                        pts = shapes.get('points', [])
                        if not isinstance(pts, list) or len(pts) != 2:
                            continue
                        (x1, y1), (x2, y2) = pts
                        x1, x2 = sorted([x1, x2])
                        y1, y2 = sorted([y1, y2])
                        temp_points = [[x1, y1], [x2, y2]]  # 只需要对角线两点
                        temp_bbox = [float(x1), float(y1), float(x2 - x1), float(y2 - y1)]
                    else:
                        continue
                    
                    # 校验bbox有效性
                    if temp_bbox is None or temp_bbox[2] <= 0 or temp_bbox[3] <= 0:
                        continue
                    
                    # 去重
                    rounded_bbox = tuple(round(v, 2) for v in temp_bbox)
                    category_id = converter.label_to_num[label]
                    ann_key = (current_image_id, category_id, rounded_bbox)
                    if ann_key in processed_annotations_set:
                        continue
                    processed_annotations_set.add(ann_key)
                    
                    # 生成annotation
                    object_num = object_num + 1
                    if p_type == 'polygon':
                        annotations_list.append(
                            converter.annotations_polygon(
                                data['imageHeight'], data['imageWidth'], temp_points, label, image_num_for_converter, object_num
                            )
                        )
                    else:  # rectangle
                        annotations_list.append(
                            converter.annotations_rectangle(temp_points, label, image_num_for_converter, object_num)
                        )
                        
            except Exception as e:
                self.log_message(f"处理文件 {label_file} 时出错: {e}")
                continue
        
        # 使用全局转换器的categories_list，确保标签ID一致
        data_coco['images'] = images_list
        data_coco['categories'] = converter.categories_list
        data_coco['annotations'] = annotations_list
        
        # 添加COCO格式必需的info字段
        data_coco['info'] = {
            "description": "Converted from Labelme format",
            "version": "1.0",
            "year": 2024,
            "contributor": "Labelme to COCO Converter",
            "date_created": str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        }
        
        return data_coco
    
    def start_conversion(self):
        """开始转换（多文件夹版本）"""
        if not self.validate_split_ratios():
            return
        
        if not self.validate_quantity_settings():
            return
            
        output_dir = self.output_var.get().strip()
        
        if not output_dir:
            messagebox.showerror("错误", "请选择输出目录")
            return
            
        if not os.path.exists(output_dir):
            messagebox.showerror("错误", "输出目录不存在")
            return
        
        # 检查是否已添加文件夹
        if not self.input_folders:
            messagebox.showerror("错误", "请先添加至少一个输入文件夹")
            return
        
        # 检查是否已建立标签映射
        if not hasattr(self, 'global_converter') or not self.global_converter.labels_list:
            messagebox.showwarning("警告", "请先扫描所有文件夹建立标签映射")
            return
            
        # 获取随机种子
        seed_str = self.seed_var.get().strip()
        random_seed = None
        
        if seed_str:  # 如果填写了种子，就是固定切分
            try:
                random_seed = int(seed_str)
            except ValueError:
                messagebox.showerror("错误", "随机种子必须是整数")
                return
        # 如果没填写种子，random_seed保持None，就是随机切分
        
        # 在新线程中执行转换
        self.convert_btn.config(state='disabled')
        self.progress_var.set(0)
        self.status_var.set("处理中...")
        
        thread = threading.Thread(target=self.process_dataset, 
                                args=(None, output_dir, random_seed))
        thread.daemon = True
        thread.start()
    
    def run(self):
        """运行GUI应用"""
        self.root.mainloop()

def main():
    """主函数"""
    app = MaterialDesignGUI()
    app.run()

if __name__ == '__main__':
    main()