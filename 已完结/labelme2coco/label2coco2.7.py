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
import queue
try:
    import send2trash
except ImportError:
    send2trash = None

SUPPORTED_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff')


class UserCancelledError(Exception):
    """用户主动取消操作的异常"""


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    import sys
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), relative_path)

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
        image['file_name'] = os.path.basename(data.get('imagePath', ''))
        return image
    
    def categories(self, label):
        category = {}
        category['supercategory'] = 'component'
        category['id'] = len(self.labels_list) + 1
        category['name'] = label
        return category
    
    def annotations_polygon(self, height, width, points, label, image_num, object_num):
        bbox_result = self.get_bbox(height, width, points)
        if bbox_result is None:
            return None

        annotation = {}
        annotation['segmentation'] = [list(np.asarray(points).flatten())]
        annotation['iscrowd'] = 0
        annotation['image_id'] = image_num + 1
        annotation['bbox'] = list(map(float, bbox_result))
        annotation['area'] = annotation['bbox'][2] * annotation['bbox'][3]
        annotation['category_id'] = self.label_to_num[label]
        annotation['id'] = object_num + 1
        return annotation
    
    def annotations_rectangle(self, points, label, image_num, object_num):
        annotation = {}
        # points[0] = [x1, y1] 左上角, points[1] = [x2, y2] 右下角
        x1, y1 = points[0]
        x2, y2 = points[1]

        # 钳制到有效范围并舍入，与 temp_bbox 计算一致
        x1_c = round(max(float(x1), 0), 2)
        y1_c = round(max(float(y1), 0), 2)
        x2_c = round(max(float(x2), 0), 2)
        y2_c = round(max(float(y2), 0), 2)

        rect_points = [
            [x1_c, y1_c],
            [x2_c, y1_c],
            [x2_c, y2_c],
            [x1_c, y2_c]
        ]

        annotation['segmentation'] = [list(np.asarray(rect_points).flatten())]
        annotation['iscrowd'] = 0
        annotation['image_id'] = image_num + 1
        annotation['bbox'] = [
            x1_c, y1_c,
            round(x2_c - x1_c, 2),
            round(y2_c - y1_c, 2)
        ]
        annotation['area'] = round((x2_c - x1_c) * (y2_c - y1_c), 4)
        annotation['category_id'] = self.label_to_num[label]
        annotation['id'] = object_num + 1
        return annotation
    
    def get_bbox(self, height, width, points):
        """从点坐标计算边界框"""
        if not points or len(points) < 1:
            return None
        if height is None or width is None or height <= 0 or width <= 0:
            return None

        # 直接从点坐标计算bbox，避免mask方法的浮点精度问题
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        x_min = min(xs)
        y_min = min(ys)
        x_max = max(xs)
        y_max = max(ys)

        # 确保坐标在合理范围内
        x_limit = max(float(width) - 1e-6, 0)
        y_limit = max(float(height) - 1e-6, 0)
        x_min = max(0, min(x_min, x_limit))
        y_min = max(0, min(y_min, y_limit))
        x_max = max(0, min(x_max, x_limit))
        y_max = max(0, min(y_max, y_limit))

        result = [x_min, y_min, x_max - x_min, y_max - y_min]
        # 四舍五入到2位小数，避免浮点精度问题
        return [round(v, 2) for v in result]

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
        rng = random.Random(random_seed)
        
        # 随机打乱文件列表
        shuffled_files = file_list.copy()
        rng.shuffle(shuffled_files)
        
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
        rng = random.Random(random_seed)
        
        all_train_files = []
        all_test_files = []
        all_verify_files = []
        
        # 为每个文件夹单独切分
        for folder_path, file_list in folder_files_dict.items():
            if not file_list:
                continue
                
            # 随机打乱当前文件夹的文件列表
            shuffled_files = file_list.copy()
            rng.shuffle(shuffled_files)
            
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
        rng = random.Random(random_seed)
        
        folder_info = {}
        
        for folder_path, file_list in folder_files_dict.items():
            if not file_list:
                folder_info[folder_path] = {'train': 0, 'test': 0, 'verify': 0, 'total': 0}
                continue
            
            # 随机打乱当前文件夹的文件列表
            shuffled_files = file_list.copy()
            rng.shuffle(shuffled_files)
            
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
    
    def split_large_folders(self, folder_files_dict, log_callback=None, random_seed=None):
        """
        分割大文件夹，确保每个文件夹不超过最大图片数量

        Args:
            folder_files_dict: 文件夹路径到文件列表的字典
            log_callback: 日志回调函数
            random_seed: 随机种子，确保结果可重现

        Returns:
            dict: 分割后的文件夹字典，可能包含子文件夹
        """
        if not self.auto_split:
            return folder_files_dict
        if self.max_images_per_folder <= 0:
            raise ValueError("每文件夹图片上限必须大于0")
        
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
                if num_splits > 999:
                    raise ValueError(f"分片数量 ({num_splits}) 过多，请增大每文件夹上限值")

                # 随机打乱文件列表以确保均匀分布
                shuffled_files = file_list.copy()
                random.Random(random_seed).shuffle(shuffled_files)
                
                # 分割文件
                for i in range(num_splits):
                    start_idx = i * self.max_images_per_folder
                    end_idx = min((i + 1) * self.max_images_per_folder, len(shuffled_files))
                    sub_files = shuffled_files[start_idx:end_idx]
                    
                    # 创建子文件夹路径标识
                    sub_folder_key = f"{folder_path}_part{i+1:03d}"
                    split_folders_dict[sub_folder_key] = sub_files
                    
                    log(f"  创建子文件夹 {folder_name}_part{i+1:03d}: {len(sub_files)} 张图片")
        
        return split_folders_dict

class MaterialDesignGUI:
    def __init__(self):
        try:
            print("开始初始化GUI...")
            self.root = tk.Tk()
            # 先隐藏窗口，待布局完成后再显示，避免窗口闪烁或尺寸跳变
            self.root.withdraw()
            self.root.title("Labelme to COCO 转换器 - 多文件夹数据集切分版")
            # 设置窗口图标（任务栏 + 窗口左上角）
            try:
                icon_path = resource_path("ICO\\COCO.ico")
                self.root.iconbitmap(icon_path)
            except Exception as e:
                print(f"图标加载失败: {e}")
            self.root.geometry("1200x800")
            self.root.minsize(1000, 650)
            self._main_thread_id = threading.get_ident()
            self._ui_queue = queue.Queue()
            self._worker_lock = threading.Lock()
            self._worker_running = False
            print("窗口创建成功")
            
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

            # Additional colors for styling
            'primary_dark': '#381E72',
            'surface_dark': '#E8E0F0',
            'on_surface_dark': '#1C1B1F',
            
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
        self.quality_check_results = {}  # 数据质量检查结果
        self.problem_files = {}  # 问题文件列表
        self.expanded_types = set()  # 当前展开的错误类型
        self.current_filter = None   # 当前过滤类型，None表示显示全部
        self.stat_widgets = {}       # 保存统计行widget引用 {error_type: (frame, btn, count, icon_var)}
        self.seen_filenames = {}     # 全局文件名去重追踪：basename -> set(已使用的完整文件名)
        self.filename_mapping = {}   # 文件名映射表：(subset_name, original_basename) -> 输出文件名
        print("多文件夹管理变量初始化完成")
        
        # 全局进度与按钮集合
        self.progress_var = tk.DoubleVar(value=0)
        self.convert_buttons = []
        
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
            
            # 所有布局和定位完成后再显示窗口，避免闪烁
            self.root.deiconify()
            self._process_ui_queue()
        except Exception as e:
            print(f"窗口居中失败: {e}")
            import traceback
            traceback.print_exc()

    def _is_ui_thread(self):
        return threading.get_ident() == getattr(self, '_main_thread_id', None)

    def _process_ui_queue(self):
        try:
            while True:
                func, args, kwargs = self._ui_queue.get_nowait()
                try:
                    func(*args, **kwargs)
                except Exception as e:
                    print(f"UI队列任务执行失败: {e}")
        except queue.Empty:
            pass

        if hasattr(self, 'root'):
            self.root.after(100, self._process_ui_queue)

    def _ui_call(self, func, *args, **kwargs):
        if self._is_ui_thread():
            func(*args, **kwargs)
        else:
            self._ui_queue.put((func, args, kwargs))

    def _set_progress(self, value):
        self._ui_call(self.progress_var.set, value)

    def _set_status(self, value):
        self._ui_call(self.status_var.set, value)

    def _show_messagebox(self, kind, title, message):
        def _show():
            getattr(messagebox, kind)(title, message)
        self._ui_call(_show)

    def _begin_worker(self):
        with self._worker_lock:
            if self._worker_running:
                return False
            self._worker_running = True
            return True

    def _finish_worker(self):
        with self._worker_lock:
            self._worker_running = False
        
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
    
    def create_scrollable_area(self, parent, bg=None, height=None):
        """创建带滚动条的区域，适配较长的侧边内容"""
        container = tk.Frame(parent, bg=bg or self.colors['background'], relief='flat')
        
        canvas = tk.Canvas(container, bg=bg or self.colors['background'], highlightthickness=0, bd=0)
        if height is not None:
            container.configure(height=height)
            container.pack_propagate(False)
            canvas.configure(height=height)
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        
        scrollable_frame = tk.Frame(canvas, bg=bg or self.colors['background'], relief='flat')
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        window_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfigure(window_id, width=e.width)
        )
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 仅在鼠标位于区域内时响应滚轮，避免影响其他区域
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"
        
        scrollable_frame.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        scrollable_frame.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        
        return container, scrollable_frame

    def _limit_stats_height(self, widget, max_ratio=0.4):
        """限制统计区域的最大高度为窗口高度的一定比例"""
        window_height = max(self.root.winfo_height(), 600)
        max_height = max(120, int(window_height * max_ratio))
        widget.configure(height=max_height)

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
        
        # 主要转换按钮（头部）
        header_convert_btn = ttk.Button(actions_frame,
                                       text="开始转换",
                                       command=self.start_conversion,
                                       style='MaterialFilledButton.TButton')
        header_convert_btn.pack(side=tk.RIGHT)
        self.header_convert_btn = header_convert_btn
        self.convert_buttons.append(header_convert_btn)
        
        # 进度条
        progress_frame = ttk.Frame(header_content, style='MaterialCard.TFrame')
        progress_frame.pack(fill=tk.X, pady=(12, 0))
        
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
                              text="配置面板",
                              bg=self.colors['surface_container_low'],
                              fg=self.colors['on_surface'],
                              font=('Segoe UI', 14, 'bold'))
        panel_title.pack(anchor=tk.W, padx=16, pady=(16, 8))
        
        # 创建带滚动的内容区域，防止内容过多时被截断
        scroll_container, scrollable_body = self.create_scrollable_area(parent, bg=self.colors['surface_container_low'])
        scroll_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        
        content_frame = tk.Frame(scrollable_body, bg=self.colors['surface_container_low'], relief='flat')
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建内容分组
        self.create_input_section(content_frame)
        self.create_output_section(content_frame)
        self.create_split_section(content_frame)
        self.create_action_section(content_frame)  
    def create_right_panel(self, parent):
        """创建右侧数据面板 - 标签页 + 常驻日志"""
        parent.configure(bg=self.colors['surface_container'])

        # 顶部标题
        panel_title = tk.Label(parent,
                              text="数据展示面板",
                              bg=self.colors['surface_container'],
                              fg=self.colors['on_surface'],
                              font=('Segoe UI', 14, 'bold'))
        panel_title.pack(anchor=tk.W, padx=16, pady=(16, 8))

        # 主内容容器，使用grid分两行：上Notebook、下日志
        content_frame = tk.Frame(parent, bg=self.colors['surface_container'])
        content_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(8, 12))
        content_frame.grid_rowconfigure(0, weight=1)
        content_frame.grid_rowconfigure(1, weight=0, minsize=220)
        content_frame.grid_columnconfigure(0, weight=1)

        # Notebook 区域（占据可扩展空间）
        notebook = ttk.Notebook(content_frame)
        notebook.grid(row=0, column=0, sticky='nsew', pady=(0, 4))

        data_frame = tk.Frame(notebook, bg=self.colors['surface'])
        notebook.add(data_frame, text="文件夹管理")
        self.create_data_management_tab(data_frame)

        label_frame = tk.Frame(notebook, bg=self.colors['surface'])
        notebook.add(label_frame, text="标签映射")
        self.create_label_management_tab(label_frame)

        quality_frame = tk.Frame(notebook, bg=self.colors['surface'])
        notebook.add(quality_frame, text="数据质量检查")
        self.create_quality_check_tab(quality_frame)

        # 日志区域（固定高度，常驻底部）
        log_wrapper = tk.Frame(content_frame, bg=self.colors['surface_container'], height=220)
        log_wrapper.grid(row=1, column=0, sticky='nsew')
        log_wrapper.grid_propagate(False)
        self.create_log_panel(log_wrapper)

    def create_log_panel(self, parent):
        """创建固定显示的日志区域，始终可见"""
        log_container, log_card = self.create_elevated_card(parent, elevation=1)
        log_container.pack(fill=tk.BOTH, expand=True, padx=0, pady=(0, 0))

        header = ttk.Frame(log_card, style='MaterialCard.TFrame')
        header.pack(fill=tk.X, padx=12, pady=(12, 4))

        title_label = ttk.Label(header,
                                text="实时日志",
                                style='MaterialBody.TLabel',
                                font=('Segoe UI', 12, 'bold'))
        title_label.pack(side=tk.LEFT)

        clear_btn = ttk.Button(header,
                               text="清空",
                               command=self.clear_log,
                               style='MaterialTextButton.TButton')
        clear_btn.pack(side=tk.RIGHT)

        text_frame = ttk.Frame(log_card, style='MaterialCard.TFrame')
        text_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        self.log_text = tk.Text(text_frame,
                                wrap=tk.WORD,
                                bg=self.colors['surface'],
                                fg=self.colors['on_surface'],
                                font=('Consolas', 9),
                                borderwidth=0,
                                relief='flat',
                                padx=12,
                                pady=12,
                                height=10,
                                selectbackground=self.colors['primary_container'],
                                selectforeground=self.colors['on_primary_container'])

        log_scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)

        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
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

        self.new_label_name_var = tk.StringVar()

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

        # 当前选中ID（隐藏标签，用于内部追踪）
        self.current_id_label = tk.Label(edit_frame,
                                         text="--",
                                         bg=self.colors['surface_container'],
                                         fg=self.colors['on_surface_variant'],
                                         font=('Segoe UI', 9))
        self.current_id_label.pack(anchor=tk.W, padx=12, pady=(0, 8))
        
        # 绑定选择事件
        self.labels_tree.bind('<<TreeviewSelect>>', self.on_label_select)
    
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
        
        scan_sub_btn = tk.Button(buttons_frame,
                                 text="🔍 扫描子文件夹",
                                 command=self.scan_and_add_subfolders,
                                 bg=self.colors['primary'],
                                 fg=self.colors['on_primary'],
                                 font=('Segoe UI', 9),
                                 relief='flat',
                                 cursor='hand2')
        scan_sub_btn.pack(side=tk.LEFT, padx=(0, 8))
        
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
        self.seed_var = tk.StringVar(value="42")
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
        self.train_ratio_var.trace_add('write', self.update_settings_summary)
        self.test_ratio_var.trace_add('write', self.update_settings_summary)
        self.verify_ratio_var.trace_add('write', self.update_settings_summary)
        self.max_images_per_folder_var.trace_add('write', self.update_settings_summary)
        self.auto_split_var.trace_add('write', self.update_settings_summary)
    
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
                                    text="开始转换与切分",
                                    command=self.start_conversion,
                                    bg=self.colors['primary'],
                                    fg=self.colors['on_primary'],
                                    font=('Segoe UI', 11, 'bold'),
                                    relief='flat',
                                    cursor='hand2',
                                    padx=20, pady=8)
        self.convert_btn.pack(pady=8, padx=16)
        self.convert_buttons.append(self.convert_btn)
        
        # 进度条标签
        tk.Label(action_frame, 
                text="处理进度:", 
                bg=self.colors['surface_container_high'], 
                fg=self.colors['on_surface'],
                font=('Segoe UI', 9)).pack(anchor=tk.W, padx=16)
        
        # 进度条
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
        """兼容旧接口：将日志区域渲染到指定父容器"""
        return self.create_log_panel(parent)

    def create_quality_check_tab(self, parent):
        """创建数据质量检查标签页"""
        # 设置父容器背景
        parent.configure(bg=self.colors['surface'])

        # 主要内容区域
        main_frame = ttk.Frame(parent, style='MaterialCard.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        # 标题和说明
        title_frame = ttk.Frame(main_frame, style='MaterialCard.TFrame')
        title_frame.pack(fill=tk.X, pady=(0, 16))

        title_label = ttk.Label(title_frame,
                               text="🔍 数据质量检查",
                               style='MaterialTitleLarge.TLabel',
                               font=('Segoe UI', 16, 'bold'))
        title_label.pack(anchor=tk.W, pady=(0, 8))

        desc_label = ttk.Label(title_frame,
                              text="自动扫描并分类9类常见错误，提供一键修复功能",
                              style='MaterialBody.TLabel',
                              font=('Segoe UI', 10))
        desc_label.pack(anchor=tk.W)

        # 控制按钮区域
        control_frame = ttk.Frame(main_frame, style='MaterialCard.TFrame')
        control_frame.pack(fill=tk.X, pady=(0, 16))

        # 扫描按钮
        scan_btn = tk.Button(control_frame,
                           text="🔍 开始扫描",
                           command=self.start_quality_check,
                           bg=self.colors['primary'],
                           fg=self.colors['on_primary'],
                           font=('Segoe UI', 10, 'bold'),
                           relief='flat',
                           cursor='hand2',
                           padx=16,
                            pady=8)
        scan_btn.pack(side=tk.LEFT)

        # 一键修复按钮
        fix_btn = tk.Button(control_frame,
                          text="🛠️ 一键修复",
                          command=self.show_fix_options,
                          bg=self.colors['warning'],
                          fg=self.colors['on_warning'],
                          font=('Segoe UI', 10, 'bold'),
                          relief='flat',
                          cursor='hand2',
                          padx=16,
                            pady=8)
        fix_btn.pack(side=tk.LEFT, padx=(16, 0))

        # 刷新按钮
        refresh_btn = tk.Button(control_frame,
                              text="🔄 刷新数据",
                              command=self.refresh_quality_data,
                              bg=self.colors['secondary'],
                              fg=self.colors['on_secondary'],
                              font=('Segoe UI', 10, 'bold'),
                              relief='flat',
                              cursor='hand2',
                              padx=16,
                              pady=8)
        refresh_btn.pack(side=tk.LEFT, padx=(16, 0))

        # 日志按钮
        log_btn = tk.Button(control_frame,
                          text="📋 查看日志",
                          command=self.show_quality_log,
                          bg=self.colors['secondary'],
                          fg=self.colors['on_secondary'],
                          font=('Segoe UI', 10, 'bold'),
                          relief='flat',
                          cursor='hand2',
                          padx=16,
                          pady=8)
        log_btn.pack(side=tk.LEFT, padx=(16, 0))
        self.quality_buttons = [scan_btn, fix_btn, refresh_btn, log_btn]

        # 检查选项区域
        options_frame = ttk.Frame(main_frame, style='MaterialCard.TFrame')
        options_frame.pack(fill=tk.X, pady=(0, 16))

        options_label = ttk.Label(options_frame,
                                  text="🔧 检查选项",
                                  style='MaterialBody.TLabel',
                                  font=('Segoe UI', 12, 'bold'))
        options_label.pack(anchor=tk.W, pady=(0, 8))

        # 创建检查选项框架
        self.check_options_frame = ttk.Frame(options_frame, style='MaterialCard.TFrame')
        self.check_options_frame.pack(fill=tk.X)

        # 初始化检查选项
        self.init_check_options()
        results_frame = ttk.Frame(main_frame, style='MaterialCard.TFrame')
        results_frame.pack(fill=tk.BOTH, expand=True)

        # 错误统计区域
        stats_frame = ttk.Frame(results_frame, style='MaterialCard.TFrame')
        stats_frame.pack(fill=tk.X, pady=(0, 16))

        stats_label = ttk.Label(stats_frame,
                               text="📊 错误统计",
                               style='MaterialBody.TLabel',
                               font=('Segoe UI', 12, 'bold'))
        stats_label.pack(anchor=tk.W, pady=(0, 8))

        # 创建带滚动条的错误统计区域
        stats_scroll_container, stats_scrollable_frame = self.create_scrollable_area(
            stats_frame, bg=self.colors['surface'], height=150)
        stats_scroll_container.pack(fill=tk.X, pady=(0, 8))

        # 创建错误统计网格
        self.error_stats_frame = tk.Frame(stats_scrollable_frame, bg=self.colors['surface'])
        self.error_stats_frame.pack(fill=tk.X)
        # 设置列权重，让内容可以正确扩展
        self.error_stats_frame.grid_columnconfigure(0, weight=1)

        # 详细问题列表区域
        details_frame = ttk.Frame(results_frame, style='MaterialCard.TFrame')
        details_frame.pack(fill=tk.BOTH, expand=True)

        # 标题区域（独立容器，避免与Treeview争夺空间）
        details_title_frame = ttk.Frame(details_frame, style='MaterialCard.TFrame')
        details_title_frame.pack(fill=tk.X)

        details_label = ttk.Label(details_title_frame,
                                 text="📋 问题文件详情",
                                 style='MaterialBody.TLabel',
                                 font=('Segoe UI', 12, 'bold'))
        details_label.pack(anchor=tk.W, pady=(0, 8))

        # 问题文件列表区域（独立容器）
        tree_container = ttk.Frame(details_frame, style='MaterialCard.TFrame')
        tree_container.pack(fill=tk.BOTH, expand=True)

        # 问题文件列表
        self.problem_tree = ttk.Treeview(tree_container,
                                       columns=('folder', 'file', 'error_type', 'description'),
                                       show='headings',
                                       selectmode='extended',
                                       height=15)

        # 设置列标题
        self.problem_tree.heading('folder', text='文件夹')
        self.problem_tree.heading('file', text='文件名')
        self.problem_tree.heading('error_type', text='错误类型')
        self.problem_tree.heading('description', text='描述')

        # 设置列宽
        self.problem_tree.column('folder', width=150)
        self.problem_tree.column('file', width=200)
        self.problem_tree.column('error_type', width=120)
        self.problem_tree.column('description', width=300)

        # 滚动条
        tree_scrollbar = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.problem_tree.yview)
        tree_xscrollbar = ttk.Scrollbar(tree_container, orient=tk.HORIZONTAL, command=self.problem_tree.xview)
        self.problem_tree.configure(yscrollcommand=tree_scrollbar.set, xscrollcommand=tree_xscrollbar.set)

        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)
        self.problem_tree.grid(row=0, column=0, sticky='nsew')
        tree_scrollbar.grid(row=0, column=1, sticky='ns')
        tree_xscrollbar.grid(row=1, column=0, sticky='ew')

        # 初始化空数据显示
        self.show_no_scan_results()
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
                data, read_result = self.read_json_file_safely(label_file)
                if data is None:
                    self.log_message(f"警告: 无法读取JSON文件 {label_file}: {read_result}")
                    continue
                
                for shapes in data.get('shapes', []):
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
                    
                    for shapes in data.get('shapes', []):
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
        except Exception:
            pass
        
        # 显示统计信息
        if hasattr(self, 'labels_stats_frame'):
            try:
                self.labels_stats_frame.pack(fill=tk.X, pady=(0, 10))
            except Exception:
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
            if values and len(values) >= 4 and values[1] != '请先扫描标签映射':  # 不是提示行
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
                
                self.write_json_atomic(file_path, mapping_data)

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
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}"

        if self._is_ui_thread():
            self._append_log_message(formatted, echo=True)
        else:
            print(formatted)
            self._ui_call(self._append_log_message, formatted, False)

    def _append_log_message(self, formatted, echo=True):
        """在主线程追加日志。"""
        if hasattr(self, 'log_text'):
            self.log_text.insert(tk.END, f"{formatted}\n")
            self.log_text.see(tk.END)
        if echo:
            print(formatted)

    def start_quality_check(self):
        """开始数据质量检查"""
        if not self.input_folders:
            messagebox.showwarning("警告", "请先添加文件夹")
            return

        if not self._begin_worker():
            messagebox.showwarning("警告", "已有任务正在运行，请等待完成")
            return

        selected_checks = []
        for check_name, var in self.check_vars.items():
            if var.get():
                selected_checks.append(check_name)

        if not selected_checks:
            self._finish_worker()
            messagebox.showwarning("警告", "请至少选择一个检查项目")
            return

        # 禁用按钮防止重复点击
        self.disable_quality_buttons()

        # 清空之前的检查结果
        self.quality_check_results = {}
        self.problem_files = {}

        # 在新线程中执行检查
        thread = threading.Thread(target=self.run_quality_check, args=(selected_checks,))
        thread.daemon = True
        thread.start()

    def run_quality_check(self, selected_checks):
        """运行数据质量检查（在后台线程中）"""
        try:
            self.log_message(f"=== 开始数据质量检查 ===")
            self.log_message(f"执行检查项目: {', '.join(selected_checks)}")

            all_problems = []
            total_scanned = 0

            for folder_path, json_files in self.input_folders.items():
                folder_name = self.folder_names.get(folder_path, os.path.basename(folder_path))
                self.log_message(f"\n检查文件夹: {folder_name}")

                # 检查该文件夹中的所有文件
                folder_problems = self.check_folder_quality(folder_path, json_files, selected_checks)
                all_problems.extend(folder_problems)
                # 统计扫描的JSON文件数量
                all_files = os.listdir(folder_path)
                json_file_count = len([f for f in all_files if f.lower().endswith('.json')])
                total_scanned += json_file_count

                problem_count = len([p for p in folder_problems if p['error_type'] not in ['图片JSON对应', '标注数量匹配']])
                self.log_message(f"  扫描了 {json_file_count} 个JSON文件，发现 {problem_count} 个问题")

            # 如果选择了图片JSON对应检查，执行额外检查
            if '图片JSON对应' in selected_checks:
                for folder_path, json_files in self.input_folders.items():
                    correspondence_problems = self.check_image_json_correspondence(folder_path, json_files)
                    all_problems.extend(correspondence_problems)

            # 如果选择了文件名重复检查，执行全局检查（支持单个和多个文件夹）
            if '文件名重复' in selected_checks:
                duplicate_problems = self.check_filename_duplicates(self.input_folders)
                all_problems.extend(duplicate_problems)

                # 统计每个文件夹涉及的文件名重复问题数量
                if duplicate_problems:
                    from collections import defaultdict
                    folder_dup_counts = defaultdict(int)
                    for p in duplicate_problems:
                        folder_dup_counts[p['folder']] += 1
                    for folder_path, json_files in self.input_folders.items():
                        folder_name = self.folder_names.get(folder_path, os.path.basename(folder_path))
                        dup_count = folder_dup_counts.get(folder_path, 0)
                        if dup_count > 0:
                            self.log_message(f"  └─ 其中 {folder_name} 涉及 {dup_count} 个文件名重复问题")

            # 分类统计问题
            self.problem_files = self.categorize_problems(all_problems)

            # 更新界面显示
            self._ui_call(self.update_quality_ui)

            # 在控制台打印错误摘要
            if all_problems:
                from collections import Counter
                error_counts = Counter(p['error_type'] for p in all_problems)
                print(f"\n=== 错误统计 ===")
                for error_type, count in sorted(error_counts.items(), key=lambda x: -x[1]):
                    print(f"  {error_type}: {count} 个")

            self.log_message(f"\n=== 检查完成 ===")
            self.log_message(f"总计扫描: {total_scanned} 个JSON文件")
            self.log_message(f"发现问题: {len(all_problems)} 个")

        except Exception as e:
            self.log_message(f"❌ 检查过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._ui_call(self.enable_quality_buttons)
            self._finish_worker()

    def read_json_file_safely(self, json_path):
        """安全读取JSON文件，支持多种编码和错误处理"""
        try:
            # 检查文件是否存在和可读
            if not os.path.exists(json_path):
                return None, "文件不存在"

            # 检查文件大小
            try:
                file_size = os.path.getsize(json_path)
                if file_size == 0:
                    return None, "文件为空文件"
                elif file_size > 10 * 1024 * 1024:  # 超过10MB的文件
                    return None, f"文件过大({file_size}字节)，可能不是有效的JSON文件"
            except Exception as e:
                return None, f"无法获取文件大小: {str(e)}"

            # 尝试多种编码方式读取
            encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'latin1']

            for encoding in encodings:
                try:
                    with open(json_path, 'r', encoding=encoding) as f:
                        content = f.read()

                    # 检查内容
                    if not content.strip():
                        return None, f"文件内容为空({encoding})"

                    # 尝试解析JSON
                    data = json.loads(content)

                    # 验证JSON结构
                    if not isinstance(data, dict):
                        return None, f"JSON数据格式不正确，应为对象，实际为{type(data).__name__}({encoding})"

                    return data, encoding

                except UnicodeDecodeError:
                    continue
                except json.JSONDecodeError as json_err:
                    # JSON格式错误，继续尝试其他编码
                    continue
                except Exception as e:
                    # 其他读取错误
                    continue

            # 如果所有编码都失败，尝试二进制模式获取更多信息
            try:
                with open(json_path, 'rb') as f:
                    binary_content = f.read(100)  # 读取前100字节
                    # 检查文件头
                    if binary_content.startswith(b'\x89PNG'):
                        return None, "文件是PNG图片，不是JSON文件"
                    elif binary_content.startswith(b'\xff\xd8\xff'):
                        return None, "文件是JPEG图片，不是JSON文件"
                    elif binary_content.startswith(b'PK'):
                        return None, "文件是ZIP压缩文件，不是JSON文件"
                    elif binary_content.startswith(b'{'):
                        return None, "文件内容损坏，无法解析JSON"
                    else:
                        return None, f"文件格式未知或损坏，前100字节: {binary_content[:20]}..."
            except Exception:
                return None, "文件读取失败，可能权限不足或文件被占用"

        except Exception as e:
            return None, f"读取文件时发生未知错误: {str(e)}"

    def write_json_atomic(self, json_path, data, indent=2):
        """原子写入JSON，避免中途失败留下半截文件。"""
        tmp_path = f"{json_path}.tmp"
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
            os.replace(tmp_path, json_path)
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise

    def filter_valid_json_files(self, folder_path, file_list):
        """智能过滤出有效的JSON文件"""
        valid_json_files = []
        skipped_files = []

        for file in file_list:
            # 1. 检查文件扩展名
            if not file.lower().endswith('.json'):
                skipped_files.append((file, "扩展名不是.json"))
                continue

            file_path = os.path.join(folder_path, file)

            try:
                # 2. 检查文件是否存在和可读
                if not os.path.exists(file_path):
                    skipped_files.append((file, "文件不存在"))
                    continue

                # 3. 检查文件大小
                file_size = os.path.getsize(file_path)
                if file_size == 0:
                    skipped_files.append((file, "文件为空"))
                    continue
                elif file_size > 10 * 1024 * 1024:  # 超过10MB
                    skipped_files.append((file, f"文件过大({file_size}字节)"))
                    continue

                # 4. 检查文件头，排除明显不是JSON的文件
                with open(file_path, 'rb') as f:
                    first_bytes = f.read(20)

                # 检查常见的非JSON文件头
                if (first_bytes.startswith(b'\x89PNG') or  # PNG图片
                    first_bytes.startswith(b'\xff\xd8\xff') or  # JPEG图片
                    first_bytes.startswith(b'PK') or  # ZIP压缩文件
                    first_bytes.startswith(b'\x00\x01\x02') or  # 二进制数据
                    first_bytes.startswith(b'\x89\x47') or  # GIF图片
                    first_bytes.startswith(b'%PDF') or  # PDF文件
                    first_bytes.startswith(b'\xd0\xcf\x11\xe0')):  # Office文件
                    file_type = "PNG图片" if first_bytes.startswith(b'\x89PNG') else \
                               "JPEG图片" if first_bytes.startswith(b'\xff\xd8\xff') else \
                               "ZIP压缩文件" if first_bytes.startswith(b'PK') else \
                               "二进制文件" if first_bytes.startswith(b'\x00\x01\x02') else \
                               "GIF图片" if first_bytes.startswith(b'\x89\x47') else \
                               "PDF文件" if first_bytes.startswith(b'%PDF') else \
                               "Office文件" if first_bytes.startswith(b'\xd0\xcf\x11\xe0') else \
                               "未知文件类型"
                    skipped_files.append((file, f"是{file_type}"))
                    continue

                # 5. 检查文件内容是否以JSON可能的字符开头
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        first_chars = f.read(10).strip()
                        if first_chars and not (first_chars.startswith('{') or first_chars.startswith('[')):
                            # 不是以JSON格式开头，可能是其他类型的文本文件
                            skipped_files.append((file, "内容不是JSON格式"))
                            continue
                except Exception:
                    # 无法用UTF-8读取，可能是二进制文件
                    skipped_files.append((file, "编码不支持"))
                    continue

                # 通过所有检查，认为是有效的JSON文件
                valid_json_files.append(file)

            except Exception as e:
                skipped_files.append((file, f"检查失败: {str(e)}"))
                continue

        return valid_json_files, skipped_files

    def check_folder_quality(self, folder_path, image_files, selected_checks):
        """检查单个文件夹的数据质量（递归搜索子目录）"""
        # 递归扫描文件夹中的所有文件（收集相对路径，避免子目录同名文件冲突）
        all_files = []
        json_files = []
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                rel = os.path.relpath(os.path.join(root, file), folder_path)
                all_files.append(rel)
                if file.lower().endswith('.json'):
                    json_files.append(rel)

        # 首先过滤出真正的JSON文件
        valid_json_files, skipped_files = self.filter_valid_json_files(folder_path, json_files)

        # 只显示跳过的文件数量，不逐个列出（减少冗余输出）
        if skipped_files:
            self.log_message(f"  自动跳过 {len(skipped_files)} 个非JSON文件")

        problems = []

        # 1.5 检查图片文件是否有对应的JSON标注文件
        if '缺json' in selected_checks:
            # 获取文件夹中的所有图片文件（递归）
            image_files = [f for f in all_files if f.lower().endswith(SUPPORTED_IMAGE_EXTENSIONS)]
            json_file_names_lower = set(f.lower() for f in all_files if f.lower().endswith('.json'))

            # 对每个图片文件检查是否有对应的JSON
            for image_file in image_files:
                base_name = os.path.splitext(image_file)[0]
                json_exists = f"{base_name}.json".lower() in json_file_names_lower

                if not json_exists:
                    problems.append({
                        'folder': folder_path,
                        'file': image_file,
                        'error_type': '缺json',
                        'description': f'图片文件缺少对应的JSON标注文件'
                    })

        for json_file in valid_json_files:
            json_path = os.path.join(folder_path, json_file)

            # 检查JSON文件是否损坏
            if 'json损坏' in selected_checks:
                data, read_result = self.read_json_file_safely(json_path)

                if data is None:
                    # 记录其他类型的错误
                    problems.append({
                        'folder': folder_path,
                        'file': json_file,
                        'error_type': 'json损坏',
                        'description': f'文件读取失败: {read_result}'
                    })
                    continue
            else:
                # 如果不检查json损坏，尝试读取但不报错
                data, read_result = self.read_json_file_safely(json_path)
                if data is None:
                    continue  # 跳过无法读取的文件

            # 2. 检查图片文件是否存在
            if '缺图片' in selected_checks:
                image_path = data.get('imagePath', '')
                if image_path:
                    # 只取文件名检查，避免绝对路径和路径分隔符混合问题
                    image_name = os.path.basename(image_path)
                    full_image_path = os.path.normpath(os.path.join(folder_path, image_name))
                    if not os.path.exists(full_image_path):
                        problems.append({
                            'folder': folder_path,
                            'file': json_file,
                            'error_type': '缺图片',
                            'description': f'图片文件不存在: {image_name}'
                        })

            # 3. 检查是否有标注
            if '空标注' in selected_checks:
                shapes = data.get('shapes', [])
                if not shapes:
                    problems.append({
                        'folder': folder_path,
                        'file': json_file,
                        'error_type': '空标注',
                        'description': 'JSON文件中没有标注信息'
                    })
                    continue

            # 4. 检查每个标注
            if any(check in selected_checks for check in ['标注越界', '无效多边形', '无效矩形', '空标签名', '面积为0', '无效bbox']):
                shapes = data.get('shapes', [])
                for i, shape in enumerate(shapes):
                    shape_problems = self.check_shape_quality(shape, data, i, selected_checks)
                    for problem in shape_problems:
                        problem['folder'] = folder_path
                        problem['file'] = json_file
                        problems.append(problem)

        return problems

    def check_shape_quality(self, shape, data, shape_index, selected_checks):
        """检查单个标注的质量"""
        problems = []

        # 获取图像尺寸
        img_height = data.get('imageHeight', 0)
        img_width = data.get('imageWidth', 0)

        # 获取标签名
        label = shape.get('label', '').strip()
        if '空标签名' in selected_checks and not label:
            problems.append({
                'error_type': '空标签名',
                'description': f'标注 {shape_index + 1}: 标签为空'
            })

        # 获取点坐标
        points = shape.get('points', [])
        shape_type = shape.get('shape_type', 'polygon')

        # 无效多边形检查：只对polygon类型检查点数是否少于3个（rectangle只有2个点，不应报错）
        polygon_points_invalid = False
        if '无效多边形' in selected_checks and shape_type == 'polygon' and len(points) < 3:
            problems.append({
                'error_type': '无效多边形',
                'description': f'标注 {shape_index + 1}: 点数少于3个'
            })
            polygon_points_invalid = True

        # 检查坐标是否越界
        if '标注越界' in selected_checks and img_width > 0 and img_height > 0:
            for j, point in enumerate(points):
                if len(point) != 2:
                    problems.append({
                        'error_type': '坐标格式错误',
                        'description': f'标注 {shape_index + 1} 第{j+1}个点: 坐标格式错误'
                    })
                    continue

                x, y = point
                if x < 0 or x >= img_width or y < 0 or y >= img_height:
                    problems.append({
                        'error_type': '标注越界',
                        'description': f'标注 {shape_index + 1} 第{j+1}个点: 坐标({x:.1f}, {y:.1f})越界(0-{img_width-1}, 0-{img_height-1})'
                    })

        # 检查形状类型
        shape_type = shape.get('shape_type', 'polygon')

        if shape_type == 'rectangle' and '无效矩形' in selected_checks:
            # 检查矩形标注
            if len(points) != 2:
                problems.append({
                    'error_type': '无效矩形',
                    'description': f'标注 {shape_index + 1}: 矩形应该只有2个点'
                })
            else:
                x1, y1 = points[0]
                x2, y2 = points[1]
                width = abs(x2 - x1)
                height = abs(y2 - y1)

                if width < 1e-6 or height < 1e-6:
                    if '面积为0' in selected_checks:
                        problems.append({
                            'error_type': '面积为0',
                            'description': f'标注 {shape_index + 1}: 矩形面积为0'
                        })

        elif shape_type == 'polygon' and '无效多边形' in selected_checks and not polygon_points_invalid:
            # 检查多边形标注
            if len(points) < 3:
                problems.append({
                    'error_type': '无效多边形',
                    'description': f'标注 {shape_index + 1}: 多边形至少需要3个点'
                })
            else:
                # 简单的面积检查（使用鞋带公式）
                if '面积为0' in selected_checks:
                    area = self.calculate_polygon_area(points)
                    if area < 1e-6:
                        problems.append({
                            'error_type': '面积为0',
                            'description': f'标注 {shape_index + 1}: 多边形面积为0'
                        })

        # 检查bbox有效性：验证bbox的宽高是否为正，坐标是否在合理范围内
        if '无效bbox' in selected_checks:
            try:
                points = shape.get('points', [])
                if points and len(points) >= 2:
                    # 直接计算bbox（不依赖SimpleLabelme2COCO类）
                    xs = [p[0] for p in points]
                    ys = [p[1] for p in points]
                    x_min = max(0, round(min(xs), 2))
                    y_min = max(0, round(min(ys), 2))
                    x_max = min(img_width, round(max(xs), 2))
                    y_max = min(img_height, round(max(ys), 2))
                    bbox = [x_min, y_min, round(max(x_max - x_min, 0), 2), round(max(y_max - y_min, 0), 2)]
                    if bbox is not None:
                        x, y, w, h = bbox
                        # get_bbox已经钳制了负值，这里主要检查宽高是否为正
                        if w <= 0 or h <= 0:
                            problems.append({
                                'error_type': '无效bbox',
                                'description': f'标注 {shape_index + 1}: bbox无效 [{x:.2f}, {y:.2f}, {w:.2f}, {h:.2f}]（宽高非正，标注可能退化为线或点）'
                            })
                        # 检查bbox是否超出图片边界
                        elif x + w > img_width or y + h > img_height:
                            problems.append({
                                'error_type': '无效bbox',
                                'description': f'标注 {shape_index + 1}: bbox超出图片边界 [{x:.2f}, {y:.2f}, {w:.2f}, {h:.2f}]，图片尺寸 {img_width}x{img_height}'
                            })
            except (TypeError, ValueError, IndexError):
                problems.append({
                    'error_type': '无效bbox',
                    'description': f'标注 {shape_index + 1}: 无法计算bbox（点坐标格式错误）'
                })

        return problems

    def calculate_polygon_area(self, points):
        """计算多边形面积（鞋带公式）"""
        if len(points) < 3:
            return 0

        area = 0
        n = len(points)
        for i in range(n):
            j = (i + 1) % n
            area += points[i][0] * points[j][1]
            area -= points[j][0] * points[i][1]

        return abs(area) / 2

    def check_image_json_correspondence(self, folder_path, json_files):
        """检查图片和JSON文件的对应关系（支持递归检查）"""
        problems = []

        try:
            # 递归获取文件夹中的所有文件
            image_files = []
            json_file_set = set()

            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, folder_path)
                    if file.lower().endswith(SUPPORTED_IMAGE_EXTENSIONS):
                        image_files.append((file, rel_path, full_path))
                    elif file.lower().endswith('.json'):
                        json_file_set.add((file, rel_path, full_path))

            # 构建文件名到路径的映射（用于快速查找，小写化以兼容大小写不敏感的文件系统）
            json_name_to_path = {}
            for json_file, rel_path, full_path in json_file_set:
                base = os.path.splitext(json_file)[0].lower()
                if base not in json_name_to_path:
                    json_name_to_path[base] = []
                json_name_to_path[base].append((json_file, rel_path, full_path))

            # 检查每个JSON文件对应的图片是否存在
            for json_file, rel_path, full_path in json_file_set:
                try:
                    data, read_result = self.read_json_file_safely(full_path)
                    if data is None:
                        continue

                    image_path = data.get('imagePath', '')
                    if image_path:
                        # 提取图片文件名（支持路径）
                        image_name = os.path.basename(image_path)
                        expected_image_base = os.path.splitext(json_file)[0]
                        referenced_image_base = os.path.splitext(image_name)[0]
                        if referenced_image_base != expected_image_base:
                            problems.append({
                                'folder': folder_path,
                                'file': rel_path,
                                'source_path': full_path,
                                'error_type': '图片JSON对应',
                                'description': f'JSON文件名与imagePath不一致: 期望 {expected_image_base}.*，实际引用 {image_name}'
                            })

                        # 检查是否存在匹配的图片
                        found = any(img[0] == image_name for img in image_files)
                        if not found:
                            problems.append({
                                'folder': folder_path,
                                'file': rel_path,
                                'source_path': full_path,
                                'error_type': 'JSON引用图片缺失',
                                'description': f'JSON文件引用的图片不存在: {image_name}'
                            })
                except Exception:
                    continue

            # 检查每个图片文件是否有对应的JSON文件
            for image_file, rel_path, full_path in image_files:
                base_name = os.path.splitext(image_file)[0].lower()
                json_exists = base_name in json_name_to_path

                if not json_exists:
                    problems.append({
                        'folder': folder_path,
                        'file': rel_path,
                        'source_path': full_path,
                        'error_type': '图片缺少JSON标注',
                        'description': f'图片文件缺少对应的JSON标注文件'
                    })

        except Exception as e:
            self.log_message(f"检查图片JSON对应关系时出错: {e}")

        return problems

    def check_filename_duplicates(self, all_folders):
        """检查所有文件夹中的文件名重复情况（支持文件夹内和跨文件夹全局检查）
        同时检查文件名中是否包含特殊字符（中文、空格、括号等）
        """
        problems = []
        import re

        image_extensions_lower = SUPPORTED_IMAGE_EXTENSIONS

        # 定义特殊字符的正则表达式模式
        special_char_regexes = [
            (re.compile(r'[\u4e00-\u9fff]'), '中文字符'),
            (re.compile(r'[\u3000-\u303f]'), '日文假名'),
            (re.compile(r'[\uac00-\ud7af]'), '韩文字符'),
            (re.compile(r' '), '空格'),
            (re.compile(r'\t'), '制表符'),
            (re.compile(r'-'), '连字符'),
            (re.compile(r'[()]'), '括号'),
            (re.compile(r'[\[\]{}]'), '方括号/花括号'),
            (re.compile(r'[!@#%^&*=,;:?\'\"]'), '特殊符号'),
        ]

        # 第一遍：收集所有文件夹中的所有图片文件，保留真实路径以便后续修复。
        file_instances = {}  # basename_lower -> [instance, ...]
        for folder_path in all_folders.keys():
            if not os.path.exists(folder_path):
                continue
            try:
                folder_filenames = {}  # basename -> [instance, ...]

                for root, dirs, files in os.walk(folder_path):
                    for file in files:
                        if not file.lower().endswith(image_extensions_lower):
                            continue

                        basename = file.lower()
                        full_path = os.path.normpath(os.path.join(root, file))
                        rel_path = os.path.relpath(full_path, folder_path)
                        instance = {
                            'folder': folder_path,
                            'file': rel_path,
                            'name': file,
                            'basename': basename,
                            'source_path': full_path
                        }

                        folder_filenames.setdefault(basename, []).append(instance)
                        file_instances.setdefault(basename, []).append(instance)

                        has_special = False
                        special_types = []
                        for regex, desc in special_char_regexes:
                            if regex.search(file):
                                has_special = True
                                if desc not in special_types:
                                    special_types.append(desc)

                        if has_special:
                            problems.append({
                                'folder': folder_path,
                                'file': rel_path,
                                'source_path': full_path,
                                'error_type': '文件名重复',
                                'description': f'文件名包含特殊字符: {", ".join(special_types)}'
                            })

                # 报告文件夹内重复
                for basename, instances in folder_filenames.items():
                    if len(instances) > 1:
                        for instance in instances[1:]:
                            original_filename = instance['name']
                            problems.append({
                                'folder': instance['folder'],
                                'file': instance['file'],
                                'source_path': instance['source_path'],
                                'error_type': '文件名重复',
                                'description': f'文件名 "{original_filename}" 在当前文件夹内重复 {len(instances)} 次'
                            })
            except Exception:
                continue

        # 第二遍：检查跨文件夹重复
        for basename, instances in file_instances.items():
            unique_folders = set(instance['folder'] for instance in instances)
            if len(unique_folders) > 1:
                first_seen = False
                for instance in instances:
                    if not first_seen:
                        first_seen = True
                        continue
                    original_filename = instance['name']
                    problems.append({
                        'folder': instance['folder'],
                        'file': instance['file'],
                        'source_path': instance['source_path'],
                        'error_type': '文件名重复',
                        'description': f'文件名 "{original_filename}" 在多个文件夹中重复'
                    })

        return problems

    def categorize_problems(self, all_problems):
        """将问题分类统计"""
        categories = {
            '缺图片': [],
            '缺json': [],
            'json损坏': [],
            '空标注': [],
            '标注越界': [],
            '无效多边形': [],
            '无效矩形': [],
            '空标签名': [],
            '面积为0': [],
            '无效bbox': [],
            '文件名重复': [],
            'JSON引用图片缺失': [],
            '图片缺少JSON标注': []
        }

        for problem in all_problems:
            error_type = problem['error_type']
            if error_type in categories:
                categories[error_type].append(problem)
            else:
                # 未知错误类型归类到其他
                if '其他错误' not in categories:
                    categories['其他错误'] = []
                categories['其他错误'].append(problem)

        return categories

    def update_quality_ui(self):
        """更新数据质量检查界面"""
        # 清空之前的统计显示
        for widget in self.error_stats_frame.winfo_children():
            widget.destroy()
        self.stat_widgets.clear()

        # 显示错误统计（可点击）
        row = 0
        for error_type, problems in self.problem_files.items():
            if not problems:  # 跳过没有问题的类型
                continue

            # 创建统计行
            stat_frame = tk.Frame(self.error_stats_frame, bg=self.colors['surface'])
            stat_frame.grid(row=row, column=0, sticky='w', pady=2)

            # 展开/折叠图标
            is_expanded = error_type in self.expanded_types
            icon_var = tk.StringVar(value="▼" if is_expanded else "▶")

            # 错误类型标签（改为按钮，可点击）
            type_btn = tk.Button(
                stat_frame,
                text=f"• {error_type}",
                bg=self.colors['surface'],
                fg=self.colors['primary'] if is_expanded else self.colors['on_surface'],
                font=('Segoe UI', 10, 'bold'),
                bd=0,
                cursor="hand2",
                command=lambda et=error_type: self.toggle_error_type(et)
            )
            type_btn.pack(side=tk.LEFT)

            # 问题数量标签
            count_label = tk.Label(
                stat_frame,
                text=f" ({len(problems)} 个)",
                bg=self.colors['surface'],
                fg=self.colors['error'],
                font=('Segoe UI', 10)
            )
            count_label.pack(side=tk.LEFT, padx=(4, 0))

            # 保存引用
            self.stat_widgets[error_type] = (stat_frame, type_btn, count_label, icon_var)
            row += 1

        # 添加总计行
        total_problems = sum(len(problems) for problems in self.problem_files.values())
        if total_problems > 0:
            total_frame = tk.Frame(self.error_stats_frame, bg=self.colors['error_container'])
            total_frame.grid(row=row, column=0, sticky='w', pady=(8, 2))
            tk.Label(total_frame, text=f"📊 总计: {total_problems} 个问题",
                     bg=self.colors['error_container'],
                     fg=self.colors['on_error_container'],
                     font=('Segoe UI', 10, 'bold')).pack(side=tk.LEFT)

        # 根据当前过滤状态更新问题列表
        self.filter_problem_tree(self.current_filter)

        # 更新状态
        total_problems = sum(len(problems) for problems in self.problem_files.values())
        if total_problems > 0:
            self.log_message(f"✅ 扫描完成，发现 {total_problems} 个问题")
        else:
            self.log_message("✅ 扫描完成，未发现质量问题")

    def toggle_error_type(self, error_type):
        """切换错误类型的展开/折叠状态"""
        if error_type in self.expanded_types:
            self.expanded_types.remove(error_type)
            self.current_filter = None  # 折叠后显示全部
        else:
            self.expanded_types.clear()  # 只允许展开一个
            self.expanded_types.add(error_type)
            self.current_filter = error_type

        # 更新所有统计行的图标和颜色
        for et, (frame, btn, count, icon_var) in self.stat_widgets.items():
            if et in self.expanded_types:
                icon_var.set("▼")
                btn.config(fg=self.colors['primary'])  # 高亮当前选中的类型
            else:
                icon_var.set("▶")
                btn.config(fg=self.colors['on_surface'])

        # 更新问题列表
        self.filter_problem_tree(self.current_filter)

    def filter_problem_tree(self, filter_type=None):
        """根据过滤类型更新问题树显示"""
        # 清空当前列表
        for item in self.problem_tree.get_children():
            self.problem_tree.delete(item)

        if filter_type is None:
            # 显示全部
            for error_type, problems in self.problem_files.items():
                for problem in problems:
                    self._insert_problem_item(problem)
        else:
            # 只显示指定类型
            if filter_type in self.problem_files:
                for problem in self.problem_files[filter_type]:
                    self._insert_problem_item(problem)

    def _insert_problem_item(self, problem):
        """向问题树插入一条记录"""
        folder_name = self.folder_names.get(problem['folder'],
                                            os.path.basename(problem['folder']))
        self.problem_tree.insert('', tk.END, values=(
            folder_name,
            problem['file'],
            problem['error_type'],
            problem['description']
        ))

    def show_no_scan_results(self):
        """显示未扫描状态"""
        # 清空统计显示
        for widget in self.error_stats_frame.winfo_children():
            widget.destroy()

        # 添加提示信息
        no_scan_label = tk.Label(self.error_stats_frame,
                               text="请点击\"🔍 开始扫描\"按钮检查数据质量",
                               bg=self.colors['surface'],
                               fg=self.colors['on_surface_variant'],
                               font=('Segoe UI', 10, 'italic'))
        no_scan_label.pack(pady=20)

    def disable_quality_buttons(self):
        """禁用质量检查按钮"""
        for btn in getattr(self, 'quality_buttons', []):
            try:
                btn.config(state='disabled')
            except Exception:
                pass

    def enable_quality_buttons(self):
        """启用质量检查按钮"""
        for btn in getattr(self, 'quality_buttons', []):
            try:
                btn.config(state='normal')
            except Exception:
                pass

    def show_fix_options(self):
        """显示修复选项"""
        if not self.problem_files:
            messagebox.showinfo("提示", "请先进行数据质量检查")
            return

        # 创建修复选项对话框
        fix_window = tk.Toplevel(self.root)
        fix_window.title("🛠️ 一键修复选项")
        fix_window.geometry("500x400")
        # 设置窗口位置在主窗口中央
        fix_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 500) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 400) // 2
        fix_window.geometry(f"+{x}+{y}")
        fix_window.transient(self.root)
        fix_window.grab_set()

        # 对话框内容
        dialog_frame = ttk.Frame(fix_window, style='MaterialCard.TFrame')
        dialog_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        # 标题
        title_label = ttk.Label(dialog_frame,
                               text="选择要修复的问题类型",
                               style='MaterialTitleMedium.TLabel',
                               font=('Segoe UI', 14, 'bold'))
        title_label.pack(anchor=tk.W, pady=(0, 16))

        # 问题类型选择
        self.fix_checkboxes = {}
        for error_type, problems in self.problem_files.items():
            if not problems:  # 跳过没有问题的类型
                continue

            # 为"文件名重复"问题添加特殊说明（通过重命名修复）
            if error_type == '文件名重复':
                var = tk.BooleanVar(value=False)  # 默认不选中
                checkbox = tk.Checkbutton(dialog_frame,
                                        text=f"{error_type} ({len(problems)} 个) - 可一键重命名修复",
                                        variable=var,
                                        bg=self.colors['surface'],
                                        fg=self.colors['on_surface'],
                                        font=('Segoe UI', 10))
                checkbox.pack(anchor=tk.W, pady=2)
                self.fix_checkboxes[error_type] = var

                # 添加说明标签
                info_text = "  提示：重命名会同时修改图片和JSON文件名，并更新JSON中的imagePath字段"
                info_label = ttk.Label(dialog_frame,
                                      text=info_text,
                                      style='MaterialCaption.TLabel',
                                      font=('Segoe UI', 9, 'italic'))
                info_label.pack(anchor=tk.W, pady=(0, 4))
            else:
                var = tk.BooleanVar(value=True)  # 默认选中所有
                checkbox = tk.Checkbutton(dialog_frame,
                                        text=f"{error_type} ({len(problems)} 个)",
                                        variable=var,
                                        bg=self.colors['surface'],
                                        fg=self.colors['on_surface'],
                                        font=('Segoe UI', 10))
                checkbox.pack(anchor=tk.W, pady=2)
                self.fix_checkboxes[error_type] = var

        # 操作选项
        options_frame = ttk.Frame(dialog_frame, style='MaterialCard.TFrame')
        options_frame.pack(fill=tk.X, pady=(16, 0))

        options_label = ttk.Label(options_frame,
                                 text="修复操作:",
                                 style='MaterialBody.TLabel',
                                 font=('Segoe UI', 10, 'bold'))
        options_label.pack(anchor=tk.W, pady=(0, 8))

        # 删除选项
        self.delete_option = tk.StringVar(value="recycle")  # 默认送回收站

        recycle_radio = tk.Radiobutton(options_frame,
                                     text="删除到回收站",
                                     variable=self.delete_option,
                                     value="recycle",
                                     bg=self.colors['surface'],
                                     fg=self.colors['on_surface'],
                                     font=('Segoe UI', 10))
        recycle_radio.pack(anchor=tk.W)

        delete_radio = tk.Radiobutton(options_frame,
                                    text="永久删除",
                                    variable=self.delete_option,
                                    value="permanent",
                                    bg=self.colors['surface'],
                                    fg=self.colors['on_surface'],
                                    font=('Segoe UI', 10))
        delete_radio.pack(anchor=tk.W)

        # 按钮区域
        button_frame = ttk.Frame(dialog_frame, style='MaterialCard.TFrame')
        button_frame.pack(fill=tk.X, pady=(16, 0))

        # 预览按钮
        preview_btn = tk.Button(button_frame,
                              text="👁️ 预览",
                              command=lambda: self.preview_fix(fix_window),
                              bg=self.colors['secondary'],
                              fg=self.colors['on_secondary'],
                              font=('Segoe UI', 10, 'bold'),
                              relief='flat',
                              cursor='hand2',
                              padx=12,
                              pady=6)
        preview_btn.pack(side=tk.LEFT)

        # 修复按钮
        fix_btn = tk.Button(button_frame,
                          text="🛠️ 执行修复",
                          command=lambda: self.execute_fix(fix_window),
                          bg=self.colors['primary'],
                          fg=self.colors['on_primary'],
                          font=('Segoe UI', 10, 'bold'),
                          relief='flat',
                          cursor='hand2',
                          padx=12,
                          pady=6)
        fix_btn.pack(side=tk.LEFT, padx=(8, 0))

        # 取消按钮
        cancel_btn = tk.Button(button_frame,
                             text="❌ 取消",
                             command=fix_window.destroy,
                             bg=self.colors['error'],
                             fg=self.colors['on_error'],
                             font=('Segoe UI', 10, 'bold'),
                             relief='flat',
                             cursor='hand2',
                             padx=12,
                             pady=6)
        cancel_btn.pack(side=tk.RIGHT)

    def preview_fix(self, parent_window):
        """预览修复操作"""
        selected_types = []
        for error_type, var in self.fix_checkboxes.items():
            if var.get():
                selected_types.append(error_type)

        if not selected_types:
            messagebox.showwarning("警告", "请选择要修复的问题类型")
            return

        # 分离可删除的问题和需要重命名的问题
        rename_types = ['文件名重复']
        deletable_types = [t for t in selected_types if t not in rename_types]
        rename_types = [t for t in selected_types if t in rename_types]

        if not deletable_types and not rename_types:
            messagebox.showinfo("提示", "没有选中任何问题")
            return

        # 创建预览窗口
        preview_window = tk.Toplevel(parent_window)
        preview_window.title("👁️ 修复预览")
        preview_window.geometry("700x500")
        # 设置窗口位置在父窗口中央
        preview_window.update_idletasks()
        parent_x = parent_window.winfo_x()
        parent_y = parent_window.winfo_y()
        parent_w = parent_window.winfo_width()
        parent_h = parent_window.winfo_height()
        x = parent_x + (parent_w - 700) // 2
        y = parent_y + (parent_h - 500) // 2
        preview_window.geometry(f"+{x}+{y}")
        preview_window.transient(parent_window)

        # 预览内容
        preview_frame = ttk.Frame(preview_window, style='MaterialCard.TFrame')
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        # 标题
        title_label = ttk.Label(preview_frame,
                               text="修复预览",
                               style='MaterialTitleMedium.TLabel',
                               font=('Segoe UI', 14, 'bold'))
        title_label.pack(anchor=tk.W, pady=(0, 16))

        # 文件列表
        preview_tree = ttk.Treeview(preview_frame,
                                  columns=('folder', 'file', 'new_name', 'error_type'),
                                  show='headings',
                                  height=15)

        preview_tree.heading('folder', text='文件夹')
        preview_tree.heading('file', text='当前文件名')
        preview_tree.heading('new_name', text='修复后文件名')
        preview_tree.heading('error_type', text='错误类型')

        preview_tree.column('folder', width=120)
        preview_tree.column('file', width=200)
        preview_tree.column('new_name', width=200)
        preview_tree.column('error_type', width=150)

        # 统计
        delete_count = 0
        rename_count = 0

        # 添加要删除的文件
        for error_type in deletable_types:
            if error_type in self.problem_files:
                for file_info in self.problem_files[error_type]:
                    folder_name = self.folder_names.get(file_info['folder'],
                                                      os.path.basename(file_info['folder']))
                    preview_tree.insert('', tk.END, values=(
                        folder_name,
                        file_info['file'],
                        '（删除）',
                        error_type
                    ))
                    delete_count += 1

        # 添加要重命名的文件（文件名重复问题）
        rename_plan = {}  # {original_path: new_name}
        if '文件名重复' in rename_types and '文件名重复' in self.problem_files:
            # 收集所有重复的文件名
            from collections import defaultdict
            filename_groups = defaultdict(list)
            for file_info in self.problem_files['文件名重复']:
                basename = os.path.basename(file_info['file']).lower()
                filename_groups[basename].append(file_info)

            # 为每个重复组生成重命名计划
            for basename, files in filename_groups.items():
                if len(files) > 1:
                    # 第一个文件保持不变，其余重命名
                    for i, file_info in enumerate(files):
                        if i == 0:
                            continue
                        original_name = file_info['file']
                        new_name = self._generate_safe_filename(original_name)

                        folder_name = self.folder_names.get(file_info['folder'],
                                                          os.path.basename(file_info['folder']))
                        preview_tree.insert('', tk.END, values=(
                            folder_name,
                            original_name,
                            new_name,
                            '文件名重复'
                        ))
                        full_path = os.path.normpath(os.path.join(file_info['folder'], file_info['file']))
                        rename_plan[full_path] = new_name
                        rename_count += 1
                else:
                    # 仅含特殊字符的单个文件也需要重命名清理
                    file_info = files[0]
                    if 'description' in file_info and '特殊字符' in file_info['description']:
                        original_name = file_info['file']
                        new_name = self._generate_safe_filename(original_name)

                        folder_name = self.folder_names.get(file_info['folder'],
                                                          os.path.basename(file_info['folder']))
                        preview_tree.insert('', tk.END, values=(
                            folder_name,
                            original_name,
                            new_name,
                            '文件名重复'
                        ))
                        full_path = os.path.normpath(os.path.join(file_info['folder'], file_info['file']))
                        rename_plan[full_path] = new_name
                        rename_count += 1

        preview_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 滚动条
        preview_scrollbar = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=preview_tree.yview)
        preview_tree.configure(yscrollcommand=preview_scrollbar.set)
        preview_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 操作说明
        desc_text = f"选中的问题类型: {', '.join(selected_types)}\n"
        if delete_count > 0:
            desc_text += f"删除文件: {delete_count} 个\n"
        if rename_count > 0:
            desc_text += f"重命名文件: {rename_count} 个（同时重命名图片和JSON文件）\n"

        desc_label = ttk.Label(preview_frame,
                              text=desc_text,
                              style='MaterialBody.TLabel',
                              font=('Segoe UI', 10),
                              wraplength=600)
        desc_label.pack(anchor=tk.W, pady=(16, 0))

        # 关闭按钮
        close_btn = tk.Button(preview_window,
                            text="✅ 确认",
                            command=preview_window.destroy,
                            bg=self.colors['primary'],
                            fg=self.colors['on_primary'],
                            font=('Segoe UI', 10, 'bold'),
                            relief='flat',
                            cursor='hand2',
                            padx=16,
                            pady=8)
        close_btn.pack(pady=16)

        # 保存重命名计划供 execute_fix 使用
        self._rename_plan = rename_plan

    def _generate_rename_plan(self):
        """生成文件名重复问题的重命名计划（包含特殊字符清理）"""
        rename_plan = {}

        if '文件名重复' not in self.problem_files:
            return rename_plan

        for file_info in self.problem_files['文件名重复']:
            desc = file_info.get('description', '')
            if not any(keyword in desc for keyword in ['特殊字符', '在当前文件夹内重复', '在多个文件夹中重复']):
                continue

            full_path = file_info.get('source_path')
            if not full_path:
                full_path = os.path.normpath(os.path.join(file_info['folder'], file_info['file']))
            else:
                full_path = os.path.normpath(full_path)

            if not os.path.exists(full_path):
                # 兼容旧扫描结果：如果file只是basename，则递归寻找真实文件。
                target_name = os.path.basename(file_info['file']).lower()
                for root, _, files in os.walk(file_info['folder']):
                    match = next((f for f in files if f.lower() == target_name), None)
                    if match:
                        full_path = os.path.normpath(os.path.join(root, match))
                        break

            original_name = os.path.basename(full_path)
            new_name = self._generate_safe_filename(original_name)
            rename_plan[full_path] = new_name

        return rename_plan

    def _generate_safe_filename(self, original_name):
        """生成安全的文件名：中文转拼音，清理特殊字符，限制连续字母长度，添加随机后缀"""
        import random
        import re
        try:
            from pypinyin import lazy_pinyin
            has_pypinyin = True
        except ImportError:
            has_pypinyin = False

        name_part, ext_part = os.path.splitext(original_name)

        # 如果安装了pypinyin，将中文转为拼音
        if has_pypinyin:
            # 逐字符处理：中文转拼音，其他字符保留
            converted_name = []
            chinese_buffer = []
            for char in name_part:
                # 判断是否为中文字符
                if '\u4e00' <= char <= '\u9fff':
                    chinese_buffer.append(char)
                else:
                    # 遇到非中文字符，先处理缓冲区中的中文
                    if chinese_buffer:
                        pinyin_list = lazy_pinyin(chinese_buffer)
                        converted_name.extend(pinyin_list)
                        chinese_buffer = []
                    converted_name.append(char)
            # 处理剩余的中文
            if chinese_buffer:
                pinyin_list = lazy_pinyin(chinese_buffer)
                converted_name.extend(pinyin_list)

            # 拼接为字符串
            safe_name = ''.join(converted_name)
        else:
            safe_name = name_part

        # 清理特殊字符：只保留ASCII字母、数字、下划线、点、减号
        safe_name = re.sub(r'[^\w\-\.]', '_', safe_name, flags=re.ASCII)

        # 限制连续字母长度不超过10个
        result = []
        letter_count = 0
        for char in safe_name:
            if char.isalpha():
                letter_count += 1
                if letter_count > 10:
                    result.append('_')
                    letter_count = 0
                else:
                    result.append(char)
            else:
                letter_count = 0
                result.append(char)
        safe_name = ''.join(result)

        # 合并连续下划线
        safe_name = re.sub(r'_+', '_', safe_name)
        # 去掉开头和结尾的下划线
        safe_name = safe_name.strip('_')

        # 如果文件名以点开开头（隐藏文件），保留点
        if original_name.startswith('.'):
            safe_name = '.' + safe_name

        # 如果处理后文件名为空，使用默认名称
        if not safe_name:
            safe_name = 'file'

        # 添加随机后缀确保唯一性
        random_suffix = random.randint(1000, 9999)
        return f"{safe_name}_r{random_suffix}{ext_part}"

    def execute_fix(self, parent_window):
        """执行修复操作"""
        selected_types = []
        for error_type, var in self.fix_checkboxes.items():
            if var.get():
                selected_types.append(error_type)

        if not selected_types:
            messagebox.showwarning("警告", "请选择要修复的问题类型")
            return

        # 分离可删除的问题和需要重命名的问题
        rename_types_list = ['文件名重复']
        deletable_types = [t for t in selected_types if t not in rename_types_list]
        rename_types = [t for t in selected_types if t in rename_types_list]

        # 如果没有预览过，动态生成重命名计划
        if rename_types and not hasattr(self, '_rename_plan'):
            self._rename_plan = self._generate_rename_plan()

        # 确认对话框
        delete_count = sum(len(self.problem_files.get(error_type, [])) for error_type in deletable_types)

        # 统计重命名数量：文件名重复问题的记录数
        rename_count = 0
        if rename_types and '文件名重复' in self.problem_files:
            rename_count = len(self.problem_files['文件名重复'])

        if delete_count == 0 and rename_count == 0:
            messagebox.showinfo("提示", "没有选中的问题文件")
            return

        confirm_text = ""
        if delete_count > 0:
            confirm_text += f"删除文件: {delete_count} 个\n"
        if rename_count > 0:
            confirm_text += f"重命名文件: {rename_count} 个\n"

        confirm = messagebox.askyesno(
            "确认修复",
            f"即将执行以下修复操作:\n{confirm_text}" +
            f"\n此操作不可撤销，是否继续？"
        )

        if not confirm:
            return

        # 执行删除操作
        if deletable_types:
            # 收集需要删除的文件（去重）
            files_to_delete = set()

            for error_type in deletable_types:
                if error_type not in self.problem_files:
                    continue

                for file_info in self.problem_files[error_type]:
                    folder = file_info['folder']
                    filename = file_info['file']

                    file_path = os.path.normpath(os.path.join(folder, filename))
                    files_to_delete.add(file_path)

            # 执行删除
            deleted_count = 0
            error_count = 0
            for file_path in files_to_delete:
                try:
                    self.delete_file_safely(file_path)
                    deleted_count += 1
                except UserCancelledError:
                    self.log_message(f"⏭️ 用户取消删除: {os.path.basename(file_path)}")
                except Exception as e:
                    self.log_message(f"❌ 删除文件失败 {os.path.basename(file_path)}: {e}")
                    error_count += 1

            self.log_message(f"✅ 删除完成: 删除 {deleted_count} 个文件, 失败 {error_count} 个")

        # 执行重命名操作（文件名重复问题）
        if rename_types and hasattr(self, '_rename_plan') and self._rename_plan:
            renamed_count = 0
            rename_error_count = 0

            for original_file, new_name in self._rename_plan.items():
                try:
                    # 获取原始文件的完整路径
                    original_path = os.path.normpath(original_file)
                    if not os.path.exists(original_path):
                        self.log_message(f"❌ 文件不存在: {original_file}")
                        rename_error_count += 1
                        continue

                    # 获取文件夹路径
                    folder = os.path.dirname(original_path)
                    old_basename = os.path.basename(original_path)
                    name_part, ext_part = os.path.splitext(new_name)
                    candidate_name = new_name
                    candidate_path = os.path.join(folder, candidate_name)
                    counter = 1
                    while os.path.exists(candidate_path) and os.path.normcase(candidate_path) != os.path.normcase(original_path):
                        candidate_name = f"{name_part}_{counter}{ext_part}"
                        candidate_path = os.path.join(folder, candidate_name)
                        counter += 1
                    new_name = candidate_name

                    # 重命名图片文件
                    new_path = os.path.join(folder, new_name)
                    os.rename(original_path, new_path)

                    # 同步重命名对应的JSON文件并更新内容
                    # 先尝试直接匹配的JSON文件
                    old_json = os.path.join(folder, os.path.splitext(old_basename)[0] + '.json')
                    new_json = os.path.join(folder, os.path.splitext(new_name)[0] + '.json')

                    if not os.path.exists(old_json):
                        # 如果直接匹配的JSON不存在，尝试查找可能的原始JSON文件
                        # 移除可能的 _rXXXX 后缀来查找原始JSON
                        base_without_suffix = os.path.splitext(old_basename)[0]
                        # 尝试移除末尾的 _r数字 模式
                        import re as _re
                        original_base = _re.sub(r'_r\d+$', '', base_without_suffix)
                        if original_base != base_without_suffix:
                            old_json_alt = os.path.join(folder, original_base + '.json')
                            if os.path.exists(old_json_alt):
                                old_json = old_json_alt
                                self.log_message(f"  找到原始JSON: {os.path.basename(old_json)}")

                    if os.path.exists(old_json):
                        os.rename(old_json, new_json)
                        # 更新JSON文件中的imagePath字段
                        try:
                            with open(new_json, 'r', encoding='utf-8') as f:
                                json_data = json.load(f)
                            if 'imagePath' in json_data:
                                json_data['imagePath'] = new_name
                            if 'imageData' in json_data and json_data['imageData'] is None:
                                pass  # 保持None
                            self.write_json_atomic(new_json, json_data)
                        except Exception as je:
                            self.log_message(f"  ⚠️ 更新JSON内容失败: {je}")

                    renamed_count += 1
                    self.log_message(f"  重命名: {old_basename} -> {new_name}")
                except Exception as e:
                    self.log_message(f"❌ 重命名失败 {os.path.basename(original_file)}: {e}")
                    rename_error_count += 1

            self.log_message(f"✅ 重命名完成: 重命名 {renamed_count} 个文件, 失败 {rename_error_count} 个")

        # 清除重命名计划
        if hasattr(self, '_rename_plan'):
            del self._rename_plan

        # 刷新文件夹数据
        self.refresh_folders_data()

        # 关闭对话框
        parent_window.destroy()

        # 重新扫描质量
        self.start_quality_check()

    def delete_file_safely(self, file_path):
        """安全删除文件（可选择回收站或永久删除）"""
        if self.delete_option.get() == 'recycle':
            # 使用回收站删除
            if send2trash:
                send2trash.send2trash(file_path)
            else:
                # 如果没有send2trash库，回退到永久删除前先确认
                if not messagebox.askyesno("确认永久删除", "当前环境不支持回收站删除，是否改为永久删除？"):
                    raise UserCancelledError("用户取消永久删除")
                os.remove(file_path)
        else:
            # 永久删除
            os.remove(file_path)

    def refresh_quality_data(self):
        """刷新数据质量检查数据"""
        self.log_message("🔄 刷新数据质量检查数据")
        self.start_quality_check()

    def show_quality_log(self):
        """显示详细日志窗口（包含运行日志和问题文件详情两个标签页）"""
        log_window = tk.Toplevel(self.root)
        log_window.title("📋 详细日志")
        log_window.geometry("800x600")
        # 居中显示
        log_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 800) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 600) // 2
        log_window.geometry(f"+{x}+{y}")
        log_window.transient(self.root)

        # 日志内容区域
        log_frame = ttk.Frame(log_window, style='MaterialCard.TFrame')
        log_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        # 标题
        ttk.Label(log_frame, text="📋 详细日志记录",
                  style='MaterialTitleMedium.TLabel',
                  font=('Segoe UI', 14, 'bold')).pack(anchor=tk.W, pady=(0, 16))

        # 使用 Notebook 创建标签页
        notebook = ttk.Notebook(log_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        # ===== 标签页1：运行日志 =====
        log_tab = ttk.Frame(notebook)
        notebook.add(log_tab, text="📋 运行日志")

        # 日志文本区域
        text_frame = ttk.Frame(log_tab)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        log_text = tk.Text(text_frame, wrap=tk.WORD, font=('Consolas', 9))
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=log_text.yview)
        log_text.configure(yscrollcommand=scrollbar.set)

        log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 插入日志内容
        log_content = self.get_log_content()
        log_text.insert(tk.END, log_content)
        log_text.config(state=tk.DISABLED)

        # ===== 标签页2：问题文件详情 =====
        detail_tab = ttk.Frame(notebook)
        notebook.add(detail_tab, text="📋 问题文件详情")

        # 问题文件列表（带折叠功能）
        tree_frame = ttk.Frame(detail_tab)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        detail_tree = ttk.Treeview(tree_frame,
                                   columns=('description',),
                                   show='tree headings',
                                   selectmode='extended')
        detail_tree.heading('#0', text='文件名')
        detail_tree.heading('description', text='描述')
        detail_tree.column('#0', width=300)
        detail_tree.column('description', width=400)

        # 滚动条
        detail_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=detail_tree.yview)
        detail_tree.configure(yscrollcommand=detail_scrollbar.set)

        detail_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        detail_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 填充问题文件数据（按错误类型分组，支持折叠）
        for error_type, problems in self.problem_files.items():
            if not problems:
                continue
            # 创建父节点（错误类型）
            parent_id = detail_tree.insert('', tk.END, text=f"▶ {error_type} ({len(problems)}个)",
                                           values=('',),
                                           tags=('parent',),
                                           open=False)
            # 添加子节点（具体问题）
            for problem in problems:
                detail_tree.insert(parent_id, tk.END,
                                   text=f"  {problem['file']}",
                                   values=(problem['description'],),
                                   tags=('child',))

        # 筛选栏（在Treeview之后创建，避免引用问题）
        filter_frame = ttk.Frame(detail_tab)
        filter_frame.pack(fill=tk.X, padx=4, pady=(4, 0))

        ttk.Label(filter_frame, text="筛选:", font=('Segoe UI', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 8))

        # 为每种错误类型创建复选框
        detail_checkboxes = {}
        for error_type in self.problem_files.keys():
            if not self.problem_files[error_type]:
                continue
            var = tk.BooleanVar(value=True)  # 默认全选
            cb = ttk.Checkbutton(filter_frame, text=f"{error_type}", variable=var,
                                 command=lambda: self._filter_detail_tree(detail_tree, detail_checkboxes))
            cb.pack(side=tk.LEFT, padx=4)
            detail_checkboxes[error_type] = var

        # 全选/全不选按钮
        all_btn = tk.Button(filter_frame, text="全选", font=('Segoe UI', 8),
                            command=lambda cbx=detail_checkboxes: self._set_all_detail_checks(cbx, True),
                            bg=self.colors['secondary'], fg=self.colors['on_secondary'],
                            relief='flat', cursor='hand2', padx=8, pady=2)
        all_btn.pack(side=tk.LEFT, padx=(16, 0))

        none_btn = tk.Button(filter_frame, text="全不选", font=('Segoe UI', 8),
                             command=lambda cbx=detail_checkboxes: self._set_all_detail_checks(cbx, False),
                             bg=self.colors['secondary'], fg=self.colors['on_secondary'],
                             relief='flat', cursor='hand2', padx=8, pady=2)
        none_btn.pack(side=tk.LEFT, padx=(4, 0))

        # 绑定点击事件：点击父节点时切换折叠状态
        def on_tree_click(event):
            item = detail_tree.identify_row(event.y)
            if item and 'parent' in detail_tree.item(item, 'tags'):
                children = detail_tree.get_children(item)
                if children and detail_tree.item(item, 'open'):
                    detail_tree.item(item, open=False)
                    detail_tree.item(item, text=f"▶ {detail_tree.item(item, 'text')[2:]}")
                else:
                    detail_tree.item(item, open=True)
                    detail_tree.item(item, text=f"▼ {detail_tree.item(item, 'text')[2:]}")

        detail_tree.bind('<Button-1>', on_tree_click)

        # 按钮区域
        btn_frame = ttk.Frame(log_frame)
        btn_frame.pack(fill=tk.X, pady=(16, 0))

        # 导出按钮
        export_btn = tk.Button(btn_frame, text="💾 导出日志",
                              command=lambda: self.export_log(log_text),
                              bg=self.colors['primary'],
                              fg=self.colors['on_primary'],
                              font=('Segoe UI', 10, 'bold'),
                              relief='flat', cursor='hand2', padx=16, pady=8)
        export_btn.pack(side=tk.LEFT)

        # 导出问题详情按钮
        export_problems_btn = tk.Button(btn_frame, text="💾 导出问题详情",
                                        command=self.export_problem_files,
                                        bg=self.colors['primary'],
                                        fg=self.colors['on_primary'],
                                        font=('Segoe UI', 10, 'bold'),
                                        relief='flat', cursor='hand2', padx=16, pady=8)
        export_problems_btn.pack(side=tk.LEFT, padx=(8, 0))

        # 关闭按钮
        close_btn = tk.Button(btn_frame, text="❌ 关闭",
                             command=log_window.destroy,
                             bg=self.colors['error'],
                             fg=self.colors['on_error'],
                             font=('Segoe UI', 10, 'bold'),
                             relief='flat', cursor='hand2', padx=16, pady=8)
        close_btn.pack(side=tk.RIGHT)

    def get_log_content(self):
        """获取日志内容"""
        return self.log_text.get(1.0, tk.END)

    def export_log(self, log_text):
        """导出日志到文件"""
        log_content = log_text.get(1.0, tk.END)
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            title="导出日志"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(log_content)
                messagebox.showinfo("成功", f"日志已导出到:\n{file_path}")
            except Exception as e:
                messagebox.showerror("错误", f"导出日志失败:\n{e}")

    def export_problem_files(self):
        """将问题文件详情格式化为可读文本并导出到文件"""
        lines = []
        lines.append("=" * 70)
        lines.append("  数据质量检查 — 问题文件详情")
        lines.append("=" * 70)

        total_count = 0
        for error_type, problems in self.problem_files.items():
            if not problems:
                continue
            count = len(problems)
            total_count += count
            lines.append("")
            lines.append("-" * 60)
            lines.append(f"【{error_type}】共 {count} 个")
            lines.append("-" * 60)
            for i, problem in enumerate(problems, 1):
                folder = problem.get('folder', '')
                file_name = problem.get('file', '')
                description = problem.get('description', '')
                full_path = os.path.join(folder, file_name) if folder else file_name
                lines.append(f"  {i:4d}. {full_path}")
                lines.append(f"        描述: {description}")

        lines.append("")
        lines.append("=" * 70)
        lines.append(f"  总计: {total_count} 个问题")
        lines.append("=" * 70)

        content = "\n".join(lines)

        if total_count == 0:
            messagebox.showinfo("提示", "当前没有问题文件需要导出。")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            title="导出问题详情"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                messagebox.showinfo("成功", f"问题详情已导出到:\n{file_path}")
            except Exception as e:
                messagebox.showerror("错误", f"导出问题详情失败:\n{e}")

    def _filter_detail_tree(self, tree, checkboxes):
        """根据复选框状态筛选Treeview中的父节点"""
        for error_type, var in checkboxes.items():
            for item in tree.get_children(''):
                item_text = tree.item(item, 'text')
                if error_type in item_text:
                    if var.get():
                        # 如果不在根级别，重新插入到根级别
                        if tree.parent(item) != '':
                            tree.detach(item)
                            tree.insert('', 'end', iid=item)
                    else:
                        tree.detach(item)

    def _set_all_detail_checks(self, checkboxes, value):
        """全选/全不选复选框"""
        for var in checkboxes.values():
            var.set(value)

    def init_check_options(self):
        """初始化检查选项"""
        # 定义所有检查项目
        self.check_options = {
            '缺图片': {'description': '检查JSON文件引用的图片文件是否存在', 'default': True},
            '缺json': {'description': '检查图片文件是否有对应的JSON标注文件', 'default': True},
            'json损坏': {'description': '检查JSON文件格式是否正确', 'default': True},
            '空标注': {'description': '检查JSON文件中是否有标注信息', 'default': True},
            '标注越界': {'description': '检查标注点坐标是否超出图片边界', 'default': True},
            '无效多边形': {'description': '检查多边形标注点数是否少于3个', 'default': True},
            '无效矩形': {'description': '检查矩形标注点数是否不等于2个', 'default': True},
            '空标签名': {'description': '检查标注的label字段是否为空', 'default': True},
            '面积为0': {'description': '检查标注区域面积是否为0', 'default': True},
            '图片JSON对应': {'description': '检查图片和JSON文件是否一一对应', 'default': True},
            '标注数量匹配': {'description': '检查图片和标注数量是否匹配', 'default': True},
            '无效bbox': {'description': '检查生成的bbox是否有效（无负值、宽高为正）', 'default': True},
            '文件名重复': {'description': '检查不同文件夹中是否存在重复的图片文件名，以及文件名是否包含特殊字符', 'default': True}
        }

        # 创建检查选项的变量
        self.check_vars = {}

        # 创建3列网格布局
        row = 0
        col = 0
        columns = 3
        for c in range(columns):
            self.check_options_frame.grid_columnconfigure(c, weight=1, uniform='quality_checks')

        for check_name, check_info in self.check_options.items():
            # 创建复选框
            var = tk.BooleanVar(value=check_info['default'])
            self.check_vars[check_name] = var

            checkbox = tk.Checkbutton(self.check_options_frame,
                                    text=f"{check_name}",
                                    variable=var,
                                    bg=self.colors['surface'],
                                    fg=self.colors['on_surface'],
                                    font=('Segoe UI', 10),
                                    anchor='w',
                                    selectcolor=self.colors['primary_container'],
                                    activebackground=self.colors['surface'])

            # 使用等宽网格，避免长选项把布局撑开
            checkbox.grid(row=row, column=col, sticky='ew', padx=(8, 12), pady=2)

            # 更新行列计数
            col += 1
            if col >= columns:
                col = 0
                row += 1

        # 添加说明文字
        info_label = ttk.Label(self.check_options_frame,
                              text="✓ 默认选中所有检查项目，您可以根据需要取消勾选",
                              style='MaterialCaption.TLabel',
                              font=('Segoe UI', 9, 'italic'))
        info_label.grid(row=row+1, column=0, columnspan=columns, sticky='w', pady=(8, 0))
        
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
            for btn in getattr(self, 'convert_buttons', []):
                try:
                    btn.config(state='normal' if can_convert else 'disabled')
                except Exception:
                    pass

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
    
    def set_convert_buttons_state(self, state):
        """统一设置所有转换按钮的状态"""
        for btn in getattr(self, 'convert_buttons', []):
            try:
                btn.config(state=state)
            except Exception:
                pass
    
    # 旧的start_conversion方法已删除，使用新的多文件夹版本
        
    def process_dataset(self, input_dir, output_dir, random_seed,
                        train_ratio=None, test_ratio=None, verify_ratio=None,
                        max_images_per_folder=None, auto_split=None):
        """处理数据集：切分和转换"""
        try:
            self.log_message("=== 开始多文件夹数据集切分和格式转换 ===")
            self.log_message(f"输出目录: {output_dir}")
            self.seen_filenames = {}
            self.filename_mapping = {}
            
            if train_ratio is None or test_ratio is None or verify_ratio is None:
                raise ValueError("缺少切分比例参数")
            
            self.log_message(f"切分比例: 训练集{train_ratio:.1%}, 测试集{test_ratio:.1%}, 验证集{verify_ratio:.1%}")
            if random_seed is not None:
                self.log_message(f"切分策略: 固定切分 (种子: {random_seed})")
            else:
                self.log_message("切分策略: 随机切分")
            
            # 检查是否已添加文件夹
            if not self.input_folders:
                raise ValueError("请先添加至少一个输入文件夹")
            
            if max_images_per_folder is None or auto_split is None:
                raise ValueError("缺少数量限制参数")
            if max_images_per_folder <= 0:
                raise ValueError("每文件夹图片上限必须大于0")
            
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
                
                folder_files_dict = splitter.split_large_folders(folder_files_dict, self.log_message, random_seed)
                
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
                        random.Random(random_seed).shuffle(shuffled_files)
                        
                        # 分割文件
                        split_parts = []
                        for i in range(num_parts):
                            start_idx = i * max_images_per_folder
                            end_idx = min((i + 1) * max_images_per_folder, len(shuffled_files))
                            part_files = shuffled_files[start_idx:end_idx]
                            split_parts.append(part_files)
                            self.log_message(f"    {subset_name}_part{i+1:03d}: {len(part_files)} 张图片")
                        
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
            
            self._set_progress(1.0)
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
                            self.log_message(f"  └─ {subset_name}_part{i+1:03d}: {len(part_files)} 张图片")
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
            if not self.validate_coco_image_files(output_dir):
                raise ValueError("COCO标注中的图片文件名与输出图片不一致，请查看上方日志")
            
            self._set_status("处理完成")
            self._show_messagebox("showinfo", "成功", "多文件夹数据集切分和转换完成！")
            
        except Exception as e:
            self.log_message(f"处理失败: {e}")
            self._set_status("处理失败")
            self._show_messagebox("showerror", "错误", f"处理失败: {e}")
        finally:
            self._ui_call(self.set_convert_buttons_state, 'normal')
            self._finish_worker()
    
    def global_validation(self, output_dir, global_converter):
        """全局验证：确保所有子集的标签ID一致"""
        self.log_message("=== 全局标签ID一致性验证 ===")

        annotation_files = []
        for root, _, files in os.walk(output_dir):
            if os.path.basename(root) != 'annotations':
                continue
            split_name = os.path.basename(os.path.dirname(root))
            for file in files:
                if file.lower().endswith('.json'):
                    annotation_files.append((split_name, os.path.join(root, file)))

        all_categories = {}

        # 收集所有子集的categories信息
        for split_name, json_path in annotation_files:
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
        """获取输入目录中的所有图片文件（递归搜索）"""
        raw_image_files = []
        for root, dirs, files in os.walk(input_dir):
            for file in files:
                if file.lower().endswith(SUPPORTED_IMAGE_EXTENSIONS):
                    raw_image_files.append(os.path.join(root, file))

        # 去重
        image_files = []
        seen_paths = set()
        for p in raw_image_files:
            key = os.path.normcase(os.path.abspath(p))
            if key not in seen_paths:
                seen_paths.add(key)
                image_files.append(p)

        return image_files

    def deduplicate_filename(self, basename, output_dir, subset_name):
        """对文件名进行去重处理

        Args:
            basename: 原始文件名（不含路径）
            output_dir: 输出目录
            subset_name: 子集名称（train/test/verify等）

        Returns:
            str: 去重后的文件名
        """
        import random

        name, ext = os.path.splitext(basename)

        # 使用全局 seen_filenames 进行跨 part 去重追踪
        if not hasattr(self, 'seen_filenames'):
            self.seen_filenames = {}

        # 检查全局是否已有此文件名
        safe_name = basename
        if basename in self.seen_filenames:
            # 文件名已被使用，生成带随机数的新文件名
            for _ in range(100):  # 最多尝试100次
                random_suffix = random.randint(1000, 9999)
                new_name = f"{name}_r{random_suffix}{ext}"
                if new_name not in self.seen_filenames:
                    safe_name = new_name
                    self.log_message(f"  COCO文件名重复: '{basename}' 已出现，标注中改用 '{new_name}'")
                    break
            else:
                # 极端情况：100次随机都冲突，使用时间戳
                import time
                timestamp = int(time.time() * 1000)
                safe_name = f"{name}_r{timestamp}{ext}"
                self.log_message(f"  COCO文件名重复: '{basename}' 已出现，标注中改用 '{safe_name}'")

        # 记录已使用的文件名（全局追踪）
        self.seen_filenames[safe_name] = subset_name
        return safe_name

    def resolve_coco_file_name(self, json_file_name, split_name, output_dir, filename_mapping=None):
        """根据复制阶段的映射解析COCO中的file_name。"""
        if filename_mapping:
            split_key = (split_name, json_file_name)
            if split_key in filename_mapping:
                return filename_mapping[split_key]

        return self.deduplicate_filename(json_file_name, output_dir, split_name)

    def validate_coco_image_files(self, output_dir):
        """检查COCO JSON中的file_name是否能在对应images目录找到。"""
        self.log_message("=== COCO图片文件一致性检查 ===")
        total_missing = 0
        checked_json = 0

        for root, _, files in os.walk(output_dir):
            if os.path.basename(root) != 'annotations':
                continue

            split_dir = os.path.dirname(root)
            images_dir = osp.join(split_dir, 'images')

            for file in files:
                if not file.lower().endswith('.json'):
                    continue

                checked_json += 1
                json_path = osp.join(root, file)
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        coco_data = json.load(f)
                except Exception as e:
                    self.log_message(f"  错误: 无法读取 {json_path}: {e}")
                    total_missing += 1
                    continue

                missing = []
                for image in coco_data.get('images', []):
                    file_name = image.get('file_name', '')
                    if file_name and not os.path.exists(osp.join(images_dir, file_name)):
                        missing.append(file_name)

                if missing:
                    total_missing += len(missing)
                    preview = ', '.join(missing[:5])
                    suffix = ' ...' if len(missing) > 5 else ''
                    self.log_message(f"  错误: {file} 有 {len(missing)} 个图片引用不存在: {preview}{suffix}")
                else:
                    self.log_message(f"  ✓ {file} 图片引用一致")

        if checked_json == 0:
            self.log_message("  警告: 未找到COCO标注JSON，跳过图片一致性检查")
            return True

        if total_missing == 0:
            self.log_message("✓ COCO图片文件一致性检查通过")
            return True

        self.log_message(f"⚠ COCO图片文件一致性检查失败，共 {total_missing} 个图片引用不存在")
        return False

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
                    if folder_key.rsplit("_part", 1)[-1].isdigit():
                        # 分割后的子文件夹
                        original_path, part_num = folder_key.rsplit("_part", 1)
                        
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
        # 规范化输出目录路径，避免混合路径分隔符
        output_dir = os.path.normpath(output_dir)
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
                    part_name = f"{subset_name}_part{i+1:03d}"
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
                            f.write(f"  └─ {subset_name}_part{i+1:03d}: {len(part_files)} 张图片\n")
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

        # 构建全局图片到JSON的映射（用于检查图片是否有标注）
        img_to_json_map = {}
        for folder_path, image_files in folder_files_dict.items():
            for img_file in image_files:
                img_label = os.path.splitext(os.path.basename(img_file))[0]
                # 使用图片文件的实际目录路径，而非 folder_files_dict 的键（可能是分割后的虚拟路径）
                real_folder = os.path.dirname(img_file)
                json_path = osp.join(real_folder, img_label + '.json')
                img_to_json_map[img_file] = json_path

        total_progress_steps = sum(len(parts_list) for parts_list in split_subsets.values())
        current_step = 0

        for subset_name, parts_list in split_subsets.items():
            if len(parts_list) == 1:
                # 未分割的子集
                subset_dir = osp.join(output_dir, subset_name, 'images')
                files = parts_list[0]

                self.log_message(f"复制{subset_name}集文件: {len(files)} 张图片")

                skipped = 0
                for i, img_file in enumerate(files):
                    filename = os.path.basename(img_file)

                    # 检查是否有对应的 JSON 标注文件
                    json_path = img_to_json_map.get(img_file)
                    if not json_path or not os.path.exists(json_path):
                        skipped += 1
                        continue

                    safe_filename = filename
                    dest_path = osp.join(subset_dir, safe_filename)
                    # 如果目标文件已存在，进行重命名
                    if os.path.exists(dest_path):
                        name, ext = os.path.splitext(filename)
                        safe_filename = name + "_r" + str(random.randint(1000, 9999)) + ext
                        while os.path.exists(osp.join(subset_dir, safe_filename)):
                            safe_filename = name + "_r" + str(random.randint(1000, 9999)) + ext
                        dest_path = osp.join(subset_dir, safe_filename)
                        self.log_message(f"  文件名冲突: '{filename}' 已存在，重命名为 '{safe_filename}'")

                    shutil.copy2(img_file, dest_path)

                    # 记录当前输出子集的文件名映射，避免跨子集同名文件互相覆盖。
                    self.filename_mapping[(subset_name, filename)] = safe_filename

                    # 更新进度条
                    progress = (current_step + (i + 1) / len(files)) / total_progress_steps
                    self._set_progress(progress * 0.3 + 0.6)  # 60%-90%的进度区间

                if skipped > 0:
                    self.log_message(f"  跳过 {skipped} 个无标注的图片")
                current_step += 1
                self.log_message(f"✓ {subset_name}集文件复制完成")
            else:
                # 分割后的子集
                for i, part_files in enumerate(parts_list):
                    part_name = f"{subset_name}_part{i+1:03d}"
                    part_images_dir = osp.join(output_dir, part_name, 'images')

                    self.log_message(f"复制{part_name}文件: {len(part_files)} 张图片")

                    skipped = 0
                    for j, img_file in enumerate(part_files):
                        filename = os.path.basename(img_file)

                        # 检查是否有对应的 JSON 标注文件
                        json_path = img_to_json_map.get(img_file)
                        if not json_path or not os.path.exists(json_path):
                            skipped += 1
                            continue

                        safe_filename = filename
                        dest_path = osp.join(part_images_dir, safe_filename)
                        if os.path.exists(dest_path):
                            name, ext = os.path.splitext(filename)
                            safe_filename = name + "_r" + str(random.randint(1000, 9999)) + ext
                            while os.path.exists(osp.join(part_images_dir, safe_filename)):
                                safe_filename = name + "_r" + str(random.randint(1000, 9999)) + ext
                            dest_path = osp.join(part_images_dir, safe_filename)
                            self.log_message(f"  文件名冲突: '{filename}' 已存在，重命名为 '{safe_filename}'")

                        shutil.copy2(img_file, dest_path)

                        # 记录文件名映射
                        self.filename_mapping[(part_name, filename)] = safe_filename

                        # 更新进度条
                        progress = (current_step + (j + 1) / len(part_files)) / total_progress_steps
                        self._set_progress(progress * 0.3 + 0.6)  # 60%-90%的进度区间

                    if skipped > 0:
                        self.log_message(f"  跳过 {skipped} 个无标注的图片")
                    current_step += 1
                    self.log_message(f"✓ {part_name}文件复制完成")
    
    def generate_coco_annotations_for_split_subsets(self, output_dir, split_subsets):
        """为分割后的子集生成COCO格式标注"""
        self.log_message("为分割后的子集生成COCO格式标注...")

        # 初始化全局标注去重集合，确保跨 part 不重复
        self.global_processed_annotations = set()

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

                coco_data = self.process_split_json_files_multi(global_converter, files, subset_name, output_dir, self.filename_mapping)

                annotations_dir = osp.join(output_dir, subset_name, 'annotations')
                json_filename = f'instance_{subset_name}.json'
                json_path = osp.join(annotations_dir, json_filename)

                self.write_json_atomic(json_path, coco_data)

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
                    part_name = f"{subset_name}_part{i+1:03d}"
                    self.log_message(f"生成{part_name}COCO标注...")

                    coco_data = self.process_split_json_files_multi(global_converter, part_files, part_name, output_dir, self.filename_mapping)

                    annotations_dir = osp.join(output_dir, part_name, 'annotations')
                    json_filename = f'instance_{part_name}.json'
                    json_path = osp.join(annotations_dir, json_filename)

                    self.write_json_atomic(json_path, coco_data)

                    self.log_message(f"✓ {part_name}COCO标注生成完成: {json_filename}")
                    self.log_message(f"  - 图片数量: {len(coco_data['images'])}")
                    self.log_message(f"  - 标注数量: {len(coco_data['annotations'])}")
                    self.log_message(f"  - 类别数量: {len(coco_data['categories'])}")

                    # 验证标签ID一致性
                    self.verify_label_consistency(coco_data, global_converter, part_name)

                    current_part += 1
                    
                    # 更新进度条
                    progress = current_part / total_parts
                    self._set_progress(progress * 0.1 + 0.9)  # 90%-100%的进度区间
      
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
            self._set_progress(progress)
        
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
                    if folder_key.rsplit("_part", 1)[-1].isdigit():
                        # 这是分割后的子文件夹
                        original_path, part_num = folder_key.rsplit("_part", 1)
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
            safe_filename = filename
            dest_path = osp.join(split_dir, safe_filename)
            if os.path.exists(dest_path):
                name, ext = os.path.splitext(filename)
                safe_filename = name + "_r" + str(random.randint(1000, 9999)) + ext
                while os.path.exists(osp.join(split_dir, safe_filename)):
                    safe_filename = name + "_r" + str(random.randint(1000, 9999)) + ext
                dest_path = osp.join(split_dir, safe_filename)
                self.log_message(f"  文件名冲突: '{filename}' 已存在，重命名为 '{safe_filename}'")

            shutil.copy2(img_file, dest_path)

            # 记录当前输出子集的文件名映射，避免跨子集同名文件互相覆盖。
            self.filename_mapping[(split_name, filename)] = safe_filename

            # 更新进度条
            progress = progress_start + (i + 1) / len(files) * (progress_end - progress_start)
            self._set_progress(progress)

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
        coco_data = self.process_split_json_files(global_converter, input_dir, files, split_name, output_dir, self.filename_mapping)
        
        # 保存COCO JSON文件
        annotations_dir = osp.join(output_dir, split_name, 'annotations')
        json_filename = f'instance_{split_name}.json'
        json_path = osp.join(annotations_dir, json_filename)
        
        self.write_json_atomic(json_path, coco_data)
        
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
        coco_data = self.process_split_json_files_multi(global_converter, files, split_name, output_dir, self.filename_mapping)
        
        # 保存COCO JSON文件
        annotations_dir = osp.join(output_dir, split_name, 'annotations')
        json_filename = f'instance_{split_name}.json'
        json_path = osp.join(annotations_dir, json_filename)
        
        self.write_json_atomic(json_path, coco_data)
        
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
    
    def process_split_json_files(self, converter, input_dir, files, split_name, output_dir, filename_mapping=None):
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
                data, read_result = self.read_json_file_safely(label_file)
                if data is None:
                    self.log_message(f"警告: 无法读取JSON文件 {label_file}: {read_result}")
                    continue
                
                # 统一获取JSON中引用的文件名
                json_file_name = os.path.basename(data.get('imagePath', ''))

                actual_file_name = os.path.basename(img_file)
                if json_file_name != actual_file_name:
                    self.log_message(
                        f"  警告: {os.path.basename(label_file)} 的imagePath为 {json_file_name}，"
                        f"已按实际图片 {actual_file_name} 写入COCO"
                    )

                # COCO的file_name必须对应实际复制的图片文件名，不能被JSON里错误的imagePath带偏。
                current_file_name = self.resolve_coco_file_name(
                    actual_file_name, split_name, output_dir, filename_mapping
                )
                
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
                for shapes in data.get('shapes', []):
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
                        bbox_result = converter.get_bbox(data['imageHeight'], data['imageWidth'], points)
                        if bbox_result is None:
                            continue
                        temp_bbox = list(map(float, bbox_result))
                    elif p_type == 'rectangle':
                        pts = shapes.get('points', [])
                        if not isinstance(pts, list) or len(pts) != 2:
                            continue
                        (x1, y1), (x2, y2) = pts
                        x1, x2 = sorted([x1, x2])
                        y1, y2 = sorted([y1, y2])
                        temp_points = [[x1, y1], [x2, y2]]  # 只需要对角线两点
                        # 修复bbox的浮点精度问题：钳制负值并四舍五入
                        temp_bbox = [
                            round(max(float(x1), 0), 2),
                            round(max(float(y1), 0), 2),
                            round(max(float(x2 - x1), 0), 2),
                            round(max(float(y2 - y1), 0), 2)
                        ]
                    else:
                        continue
                    
                    # 校验bbox有效性
                    if temp_bbox is None or temp_bbox[0] < 0 or temp_bbox[1] < 0 or temp_bbox[2] <= 0 or temp_bbox[3] <= 0:
                        self.log_message(f"警告: 无效的bbox {temp_bbox}，跳过该标注")
                        continue

                    # 去重（使用文件名而非 image_id，避免跨 part 误删）
                    rounded_bbox = tuple(round(v, 2) for v in temp_bbox)
                    category_id = converter.label_to_num[label]
                    ann_key = (current_file_name, category_id, rounded_bbox)
                    if ann_key in processed_annotations_set:
                        continue
                    processed_annotations_set.add(ann_key)
                    
                    # 生成annotation
                    object_num = object_num + 1
                    if p_type == 'polygon':
                        annotation = converter.annotations_polygon(
                            data['imageHeight'], data['imageWidth'], temp_points, label, image_num_for_converter, object_num
                        )
                        if annotation is None:
                            object_num -= 1
                            continue
                        annotations_list.append(annotation)
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
        for ext in SUPPORTED_IMAGE_EXTENSIONS:
            raw_image_files.extend(glob.glob(osp.join(input_dir, '*' + ext)))
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
                data, read_result = self.read_json_file_safely(label_file)
                if data is None:
                    self.log_message(f"警告: 无法读取JSON文件 {label_file}: {read_result}")
                    continue

                # 统一获取JSON中引用的文件名
                json_file_name = os.path.basename(data.get('imagePath', ''))

                # process_json_files 方法用于简单场景，直接使用原始文件名
                current_file_name = json_file_name

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
                for shapes in data.get('shapes', []):
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
                        bbox_result = converter.get_bbox(data['imageHeight'], data['imageWidth'], points)
                        if bbox_result is None:
                            continue
                        temp_bbox = list(map(float, bbox_result))
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
                    if temp_bbox is None or temp_bbox[0] < 0 or temp_bbox[1] < 0 or temp_bbox[2] <= 0 or temp_bbox[3] <= 0:
                        self.log_message(f"警告: 无效的bbox {temp_bbox}，跳过该标注")
                        continue
                    
                    # 去重：按 file_name, category_id, 取两位小数的bbox
                    rounded_bbox = tuple(round(v, 2) for v in temp_bbox)
                    # 当前 image_id 已统一
                    category_id = converter.label_to_num[label]
                    ann_key = (current_file_name, category_id, rounded_bbox)
                    if ann_key in processed_annotations_set:
                        # 已存在，跳过重复
                        continue
                    processed_annotations_set.add(ann_key)
                    
                    # 生成并添加annotation（只在确定添加时递增object_num）
                    object_num = object_num + 1
                    if p_type == 'polygon':
                        annotation = converter.annotations_polygon(
                            data['imageHeight'], data['imageWidth'], temp_points, label, image_num_for_converter, object_num
                        )
                        if annotation is None:
                            object_num -= 1
                            continue
                        annotations_list.append(annotation)
                    else:  # rectangle
                        annotations_list.append(
                            converter.annotations_rectangle(temp_points, label, image_num_for_converter, object_num)
                        )
                              
            except Exception as e:
                self.log_message(f"处理文件 {label_file} 时出错: {e}")
                continue
            
            processed_count += 1
            self._set_progress(0.3 + (processed_count / total_files) * 0.7)  # 剩余70%进度用于处理
        
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
    
    def scan_and_add_subfolders(self):
        """扫描并添加子文件夹"""
        # 1. 选择根目录
        root_dir = filedialog.askdirectory(title="选择要扫描的根目录")
        if not root_dir:
            return
            
        try:
            self.log_message(f"正在扫描目录: {root_dir} ...")
            self.root.config(cursor="watch")
            self.root.update()
            
            # 2. 递归扫描所有子文件夹
            valid_folders = []
            
            for root, dirs, files in os.walk(root_dir):
                # 检查当前文件夹是否有图片和JSON
                has_images = False
                has_jsons = False
                
                # 快速检查文件扩展名
                for file in files:
                    if file.lower().endswith(SUPPORTED_IMAGE_EXTENSIONS):
                        has_images = True
                    elif file.lower().endswith('.json'):
                        has_jsons = True
                    
                    if has_images and has_jsons:
                        break
                
                if has_images and has_jsons:
                    # 进一步验证：确保至少有一对匹配的图片和JSON（可选，为了性能暂只做简单检查）
                    valid_folders.append(root)
            
            self.root.config(cursor="")
            
            if not valid_folders:
                messagebox.showinfo("扫描结果", "未找到包含图片和JSON文件的子文件夹")
                return
            
            # 3. 显示选择对话框
            self._show_folder_selection_dialog(valid_folders)
            
        except Exception as e:
            self.root.config(cursor="")
            self.log_message(f"扫描文件夹时出错: {e}")
            messagebox.showerror("错误", f"扫描文件夹时出错: {e}")

    def _show_folder_selection_dialog(self, valid_folders):
        """显示文件夹选择对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"扫描结果 - 发现 {len(valid_folders)} 个文件夹")
        dialog.geometry("600x500")
        # 设置窗口位置在主窗口中央
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 600) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 500) // 2
        dialog.geometry(f"+{x}+{y}")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 标题
        tk.Label(dialog, text="请选择要添加的文件夹:", font=('Segoe UI', 11, 'bold')).pack(pady=10)
        
        # 列表区域
        list_frame = tk.Frame(dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 使用Checkbutton列表
        canvas = tk.Canvas(list_frame, yscrollcommand=scrollbar.set, bg='white')
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar.config(command=canvas.yview)
        
        inner_frame = tk.Frame(canvas, bg='white')
        canvas.create_window((0, 0), window=inner_frame, anchor="nw")
        
        folder_vars = []
        
        # 全选/反选控制
        def toggle_all(state):
            for var, _ in folder_vars:
                var.set(state)
        
        # 填充列表
        for folder in valid_folders:
            var = tk.BooleanVar(value=True) # 默认全选
            cb = tk.Checkbutton(inner_frame, text=folder, variable=var, bg='white', anchor='w')
            cb.pack(fill=tk.X, padx=5, pady=2)
            folder_vars.append((var, folder))
        
        inner_frame.update_idletasks()
        canvas.config(scrollregion=canvas.bbox("all"))
        
        # 按钮区域
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Button(btn_frame, text="全选", command=lambda: toggle_all(True)).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="全不选", command=lambda: toggle_all(False)).pack(side=tk.LEFT, padx=5)
        
        def on_confirm():
            selected = [path for var, path in folder_vars if var.get()]
            if not selected:
                messagebox.showwarning("提示", "请至少选择一个文件夹")
                return
            
            dialog.destroy()
            
            # 批量添加
            self.log_message(f"开始添加 {len(selected)} 个文件夹...")
            added_count = 0
            for folder in selected:
                if self._add_single_folder(folder, batch_mode=True):
                    added_count += 1
            
            if added_count > 0:
                self.update_folders_display()
                self.update_folders_stats()
                self._rebuild_state_and_refresh_ui(reason="扫描添加文件夹")
                messagebox.showinfo("完成", f"成功添加 {added_count} 个文件夹")
            else:
                self.log_message("未添加任何新文件夹")
        
        tk.Button(btn_frame, text="确认添加", command=on_confirm, bg=self.colors['primary'], fg='white').pack(side=tk.RIGHT, padx=5)
        tk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
    
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
                data, read_result = self.read_json_file_safely(label_file)
                if data is None:
                    continue
                
                for shapes in data.get('shapes', []):
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
                for ext in SUPPORTED_IMAGE_EXTENSIONS:
                    img_path = os.path.join(folder_path, json_basename + ext)
                    if os.path.exists(img_path):
                        found_image = True
                        break
                
                if not found_image:
                    missing_image_files.append(json_basename + '（图片）')
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
                        for shape in data.get('shapes', []):
                            if 'label' in shape and shape['label'] == label_name:
                                count += 1
                except Exception:
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
                except Exception:
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
                    for shape in data.get('shapes', []):
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
                    self.write_json_atomic(json_file, data)
                    
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
    
    def process_split_json_files_multi(self, converter, files, split_name, output_dir, filename_mapping=None):
        """处理指定子集的JSON文件（多文件夹版本）"""
        data_coco = {}
        images_list = []
        annotations_list = []
        image_num = -1
        object_num = -1

        # 使用全局标注去重集合（跨 part 去重，基于文件名而非 image_id）
        if hasattr(self, 'global_processed_annotations'):
            processed_annotations_set = self.global_processed_annotations
        else:
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
                
                # 统一获取JSON中引用的文件名
                json_file_name = os.path.basename(data.get('imagePath', ''))

                actual_file_name = os.path.basename(img_file)
                if json_file_name != actual_file_name:
                    self.log_message(
                        f"  警告: {os.path.basename(label_file)} 的imagePath为 {json_file_name}，"
                        f"已按实际图片 {actual_file_name} 写入COCO"
                    )

                # COCO的file_name必须对应实际复制的图片文件名，不能被JSON里错误的imagePath带偏。
                current_file_name = self.resolve_coco_file_name(
                    actual_file_name, split_name, output_dir, filename_mapping
                )
                
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
                for shapes in data.get('shapes', []):
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
                        bbox_result = converter.get_bbox(data['imageHeight'], data['imageWidth'], points)
                        if bbox_result is None:
                            continue
                        temp_bbox = list(map(float, bbox_result))
                    elif p_type == 'rectangle':
                        pts = shapes.get('points', [])
                        if not isinstance(pts, list) or len(pts) != 2:
                            continue
                        (x1, y1), (x2, y2) = pts
                        x1, x2 = sorted([x1, x2])
                        y1, y2 = sorted([y1, y2])
                        temp_points = [[x1, y1], [x2, y2]]  # 只需要对角线两点
                        # 修复bbox的浮点精度问题：钳制负值并四舍五入
                        temp_bbox = [
                            round(max(float(x1), 0), 2),
                            round(max(float(y1), 0), 2),
                            round(max(float(x2 - x1), 0), 2),
                            round(max(float(y2 - y1), 0), 2)
                        ]
                    else:
                        continue
                    
                    # 校验bbox有效性
                    if temp_bbox is None or temp_bbox[0] < 0 or temp_bbox[1] < 0 or temp_bbox[2] <= 0 or temp_bbox[3] <= 0:
                        self.log_message(f"警告: 无效的bbox {temp_bbox}，跳过该标注")
                        continue

                    # 去重（使用文件名而非 image_id，避免跨 part 误删）
                    rounded_bbox = tuple(round(v, 2) for v in temp_bbox)
                    category_id = converter.label_to_num[label]
                    ann_key = (current_file_name, category_id, rounded_bbox)
                    if ann_key in processed_annotations_set:
                        continue
                    processed_annotations_set.add(ann_key)
                    
                    # 生成annotation
                    object_num = object_num + 1
                    if p_type == 'polygon':
                        annotation = converter.annotations_polygon(
                            data['imageHeight'], data['imageWidth'], temp_points, label, image_num_for_converter, object_num
                        )
                        if annotation is None:
                            object_num -= 1
                            continue
                        annotations_list.append(annotation)
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

        train_ratio = self.train_ratio_var.get()
        test_ratio = self.test_ratio_var.get()
        verify_ratio = self.verify_ratio_var.get()
        max_images_str = self.max_images_per_folder_var.get().strip()
        max_images_per_folder = int(max_images_str) if max_images_str else 2000
        auto_split = self.auto_split_var.get()

        if not self._begin_worker():
            messagebox.showwarning("警告", "已有任务正在运行，请等待完成")
            return
        
        # 在新线程中执行转换
        self.set_convert_buttons_state('disabled')
        self._set_progress(0)
        self._set_status("处理中...")
        
        thread = threading.Thread(target=self.process_dataset, 
                                args=(None, output_dir, random_seed,
                                      train_ratio, test_ratio, verify_ratio,
                                      max_images_per_folder, auto_split))
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
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Labelme2COCO.App.1')
    except Exception:
        pass
    main()


