"""视频帧切分工具 v4.0 - 重构版
支持三种模式：单视频/单目录/多目录并发
"""

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import tkinter as tk
from tkinter import messagebox, filedialog
import os
import sys
import json
import subprocess
import threading
import queue
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Callable, List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum, auto


# ============================================================================
# 配置管理
# ============================================================================
class Config:
    """配置管理类"""
    CONFIG_FILE = "config.json"

    def __init__(self):
        self.last_mode = "single_video"
        self.last_video_path = ""
        self.last_directory = ""
        self.last_multi_dirs = []
        self.output_format = "jpg"
        self.thread_count = 3
        self.window_size = "900x700"
        self.load()

    def load(self):
        """加载配置"""
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, value in data.items():
                        if hasattr(self, key):
                            setattr(self, key, value)
            except Exception:
                pass

    def save(self):
        """保存配置"""
        try:
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.__dict__, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


# ============================================================================
# 数据模型
# ============================================================================
class ExtractMode(Enum):
    """切分模式"""
    TOTAL = "total"


@dataclass
class VideoInfo:
    """视频信息"""
    width: int = 1920
    height: int = 1080
    duration: float = 0.0
    fps: float = 30.0


@dataclass
class ExtractConfig:
    """切分配置"""
    total_value: int = 100
    output_format: str = "jpg"
    quality: int = 2


@dataclass
class TaskItem:
    """任务项"""
    id: str
    video_path: str
    output_dir: str
    config: ExtractConfig
    status: str = "pending"  # pending, running, completed, error
    progress: float = 0.0
    message: str = ""


# ============================================================================
# FFmpeg处理器
# ============================================================================
class FFmpegFrameExtractor:
    """FFmpeg帧提取处理器"""

    VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm'}

    def __init__(self):
        self.ffmpeg_path = self._get_ffmpeg_path()
        self.ffprobe_path = self._get_ffprobe_path()

    def _get_ffmpeg_path(self) -> str:
        """获取ffmpeg路径"""
        if hasattr(sys, '_MEIPASS'):
            exe_dir = os.path.dirname(sys.executable)
        else:
            exe_dir = os.path.dirname(os.path.abspath(__file__))

        local_ffmpeg = os.path.join(exe_dir, 'ffmpeg.exe')
        if os.path.exists(local_ffmpeg):
            return local_ffmpeg

        internal_ffmpeg = os.path.join(exe_dir, '_internal', 'ffmpeg.exe')
        if os.path.exists(internal_ffmpeg):
            return internal_ffmpeg

        return 'ffmpeg'

    def _get_ffprobe_path(self) -> str:
        """获取ffprobe路径"""
        ffmpeg_path = self._get_ffmpeg_path()
        if ffmpeg_path.endswith('.exe'):
            return ffmpeg_path.replace('ffmpeg.exe', 'ffprobe.exe')
        return 'ffprobe'

    def check_ffmpeg(self) -> bool:
        """检查ffmpeg是否可用"""
        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-version"],
                capture_output=True,
                encoding='utf-8',
                errors='ignore',
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            return result.returncode == 0
        except:
            return False

    def get_video_info(self, video_path: str) -> VideoInfo:
        """获取视频信息"""
        info = VideoInfo()
        try:
            # 获取分辨率
            cmd = [
                self.ffprobe_path, "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate",
                "-of", "csv=s=x:p=0",
                video_path
            ]
            result = subprocess.run(
                cmd, capture_output=True, encoding='utf-8',
                errors='ignore', timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if 'x' in result.stdout:
                parts = result.stdout.strip().split('x')
                if len(parts) >= 2:
                    info.width = int(parts[0])
                    info.height = int(parts[1])
                    # 解析帧率
                    if len(parts) > 2 and '/' in parts[2]:
                        num, den = parts[2].split('/')
                        info.fps = float(num) / float(den) if float(den) != 0 else 30.0

            # 获取时长
            cmd = [
                self.ffprobe_path, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ]
            result = subprocess.run(
                cmd, capture_output=True, encoding='utf-8',
                errors='ignore', timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if result.stdout.strip():
                info.duration = float(result.stdout.strip())
        except:
            pass
        return info

    def scan_videos(self, directory: str, recursive: bool = False) -> List[str]:
        """扫描目录中的视频文件"""
        videos = []
        try:
            if recursive:
                for root, dirs, files in os.walk(directory):
                    for file in files:
                        if Path(file).suffix.lower() in self.VIDEO_EXTENSIONS:
                            videos.append(os.path.join(root, file))
            else:
                for file in os.listdir(directory):
                    if Path(file).suffix.lower() in self.VIDEO_EXTENSIONS:
                        videos.append(os.path.join(directory, file))
        except:
            pass
        return sorted(videos)

    def extract_frames(
        self,
        video_path: str,
        output_dir: str,
        config: ExtractConfig,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        stop_event: Optional[threading.Event] = None
    ) -> tuple[bool, str]:
        """提取帧"""
        try:
            info = self.get_video_info(video_path)

            # 创建输出目录
            os.makedirs(output_dir, exist_ok=True)

            # 生成时间戳和随机数
            timestamp = datetime.now().strftime("%m%d%H%M")
            import random
            random_num = random.randint(100, 999)

            # 计算提取时间点
            timestamps = [info.duration * i / config.total_value for i in range(config.total_value)]

            total_count = len(timestamps)

            for idx, ts in enumerate(timestamps):
                # 检查取消
                if stop_event and stop_event.is_set():
                    return False, "用户取消"

                # 构建输出文件名
                filename = f"{timestamp}_{random_num}_{idx+1:04d}_{info.width}_{info.height}.{config.output_format}"
                output_path = os.path.join(output_dir, filename)

                # 构建ffmpeg命令
                cmd = [
                    self.ffmpeg_path, "-y",
                    "-ss", str(ts),
                    "-i", video_path,
                    "-vframes", "1",
                    "-threads", "1"
                ]

                # 添加格式参数
                if config.output_format.lower() in ['jpg', 'jpeg']:
                    cmd.extend(["-q:v", str(config.quality)])
                elif config.output_format.lower() == 'png':
                    cmd.extend(["-compression_level", "3"])

                cmd.append(output_path)

                # 执行提取
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    encoding='utf-8',
                    errors='ignore',
                    timeout=60,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )

                # 更新进度
                progress = ((idx + 1) / total_count) * 100
                message = f"已保存: {filename}"
                if progress_callback:
                    progress_callback(progress, message)

            return True, f"成功提取 {total_count} 帧"

        except Exception as e:
            return False, str(e)

    def extract_frames_to_shared_dir(
        self,
        video_path: str,
        output_dir: str,
        video_prefix: str,
        config: ExtractConfig,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        stop_event: Optional[threading.Event] = None
    ) -> tuple[bool, str]:
        """提取帧到共享目录，使用video_prefix作为文件名前缀区分不同视频"""
        try:
            info = self.get_video_info(video_path)

            # 创建输出目录
            os.makedirs(output_dir, exist_ok=True)

            # 生成时间戳和随机数
            timestamp = datetime.now().strftime("%m%d%H%M")
            import random
            random_num = random.randint(100, 999)

            # 计算提取时间点
            timestamps = [info.duration * i / config.total_value for i in range(config.total_value)]

            total_count = len(timestamps)

            for idx, ts in enumerate(timestamps):
                # 检查取消
                if stop_event and stop_event.is_set():
                    return False, "用户取消"

                # 构建输出文件名，添加视频名前缀以区分不同视频
                filename = f"{video_prefix}_{timestamp}_{random_num}_{idx+1:04d}_{info.width}_{info.height}.{config.output_format}"
                output_path = os.path.join(output_dir, filename)

                # 构建ffmpeg命令
                cmd = [
                    self.ffmpeg_path, "-y",
                    "-ss", str(ts),
                    "-i", video_path,
                    "-vframes", "1",
                    "-threads", "1"
                ]

                # 添加格式参数
                if config.output_format.lower() in ['jpg', 'jpeg']:
                    cmd.extend(["-q:v", str(config.quality)])
                elif config.output_format.lower() == 'png':
                    cmd.extend(["-compression_level", "3"])

                cmd.append(output_path)

                # 执行提取
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    encoding='utf-8',
                    errors='ignore',
                    timeout=60,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )

                # 更新进度
                progress = ((idx + 1) / total_count) * 100
                message = f"已保存: {filename}"
                if progress_callback:
                    progress_callback(progress, message)

            return True, f"成功提取 {total_count} 帧"

        except Exception as e:
            return False, str(e)


# ============================================================================
# 批量处理器
# ============================================================================
class BatchProcessor:
    """批量处理器"""

    def __init__(self, max_workers: int = 3):
        self.max_workers = max_workers
        self.executor = None
        self.tasks: Dict[str, TaskItem] = {}
        self.ui_queue = queue.Queue()
        self.stop_event = threading.Event()

    def start(self):
        """启动处理器"""
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.stop_event.clear()

    def stop(self):
        """停止处理器"""
        self.stop_event.set()
        if self.executor:
            self.executor.shutdown(wait=False)
            self.executor = None

    def submit_task(self, task: TaskItem, extractor: FFmpegFrameExtractor):
        """提交任务"""
        self.tasks[task.id] = task
        task.status = "running"

        def progress_callback(progress, message):
            self.ui_queue.put({
                'type': 'progress',
                'task_id': task.id,
                'progress': progress,
                'message': message
            })

        def task_wrapper():
            try:
                success, msg = extractor.extract_frames(
                    task.video_path,
                    task.output_dir,
                    task.config,
                    progress_callback,
                    self.stop_event
                )
                task.status = "completed" if success else "error"
                task.message = msg
                self.ui_queue.put({
                    'type': 'complete',
                    'task_id': task.id,
                    'success': success,
                    'message': msg
                })
            except Exception as e:
                task.status = "error"
                task.message = str(e)
                self.ui_queue.put({
                    'type': 'error',
                    'task_id': task.id,
                    'message': str(e)
                })

        return self.executor.submit(task_wrapper)


# ============================================================================
# 主应用
# ============================================================================
class VideoFrameExtractorApp:
    """视频帧切分工具主应用"""

    # 颜色配置
    COLORS = {
        'bg_primary': '#f8f9fa',
        'bg_secondary': '#ffffff',
        'accent_blue': '#007bff',
        'accent_gold': '#d4a017',
        'success': '#28a745',
        'warning': '#ffc107',
        'error': '#dc3545',
        'text_primary': '#212529',
        'text_secondary': '#6c757d',
        'border': '#dee2e6',
    }

    def __init__(self, root: ttk.Window):
        self.root = root
        self.root.title("视频帧切分工具 v4.0")
        self.root.geometry("1100x800")
        self.root.minsize(1000, 700)

        # 配置
        self.config = Config()
        self.extractor = FFmpegFrameExtractor()
        self.processor = BatchProcessor(self.config.thread_count)

        # 状态变量 - 强制启动时显示模式选择
        self.current_mode = ttk.StringVar(value="select")
        self.is_processing = False
        self.stop_event = threading.Event()

        # 模式数据
        self.single_video_path = ttk.StringVar()
        self.single_output_path = ttk.StringVar()
        self.single_total = ttk.IntVar(value=100)
        self.output_format = ttk.StringVar(value=self.config.output_format)

        self.single_dir_path = ttk.StringVar()
        self.single_dir_output = ttk.StringVar()
        self.single_dir_split_mode = ttk.StringVar(value="uniform")  # uniform / individual
        self.single_dir_uniform_count = ttk.IntVar(value=100)
        self.single_dir_videos: List[Dict] = []  # 存储视频数据

        self.multi_dirs: List[Dict] = []  # [{path, output, videos, status, split_mode, uniform_count}]

        # 检查FFmpeg
        self.ffmpeg_available = self.extractor.check_ffmpeg()

        # 创建UI
        self.setup_styles()
        self.create_ui()

        # 启动UI更新循环
        self.process_ui_queue()

    def setup_styles(self):
        """设置样式"""
        style = ttk.Style()

        # 配置颜色 - 使用ttkbootstrap默认浅色主题
        # 不再强制设置背景色，让ttkbootstrap主题管理颜色
        pass

    def create_ui(self):
        """创建UI - 始终先显示模式选择"""
        # 主容器
        self.main_container = ttk.Frame(self.root)
        self.main_container.pack(fill=BOTH, expand=True)

        # 标题栏
        self.create_header()

        # 内容区
        self.content_frame = ttk.Frame(self.main_container)
        self.content_frame.pack(fill=BOTH, expand=True, padx=20, pady=10)

        # 始终先显示模式选择
        self.show_mode_selection()

    def create_scrollable_frame(self, parent):
        """创建可滚动的Frame容器

        Returns:
            tuple: (content_frame, canvas) - 内容Frame和Canvas引用
        """
        # 创建Canvas
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)

        # 创建内容Frame
        content_frame = ttk.Frame(canvas)

        # 配置滚动
        content_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=content_frame, anchor="nw", width=canvas.winfo_width())
        canvas.configure(yscrollcommand=scrollbar.set)

        # 布局
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 鼠标滚轮支持
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", on_mousewheel)

        # 窗口大小变化时调整内容宽度
        def on_canvas_configure(event):
            canvas.itemconfig(canvas.find_all()[0], width=event.width)
        canvas.bind("<Configure>", on_canvas_configure)

        return content_frame, canvas

    def create_header(self):
        """创建标题栏"""
        header = ttk.Frame(self.main_container, bootstyle="dark")
        header.pack(fill=X)

        # 渐变条
        gradient = ttk.Frame(header, height=3, bootstyle="info")
        gradient.pack(fill=X)

        # 标题行
        title_frame = ttk.Frame(header, bootstyle="dark")
        title_frame.pack(fill=X, padx=15, pady=10)

        ttk.Label(
            title_frame,
            text="🎬 视频帧切分工具",
            font=('Segoe UI', 16, 'bold'),
            bootstyle="inverse-dark"
        ).pack(side=LEFT)

        # 模式切换按钮
        ttk.Button(
            title_frame,
            text="切换模式",
            command=self.show_mode_selection,
            bootstyle="info-outline"
        ).pack(side=RIGHT)

        # FFmpeg状态
        if not self.ffmpeg_available:
            ttk.Label(
                title_frame,
                text="⚠️ 未检测到FFmpeg",
                bootstyle="danger-inverse"
            ).pack(side=RIGHT, padx=10)

    def show_mode_selection(self):
        """显示模式选择界面"""
        self.clear_content()
        self.current_mode.set("select")

        # 标题
        ttk.Label(
            self.content_frame,
            text="选择操作模式",
            font=('Segoe UI', 20, 'bold')
        ).pack(pady=30)

        ttk.Label(
            self.content_frame,
            text="请选择您要执行的操作类型",
            bootstyle="secondary"
        ).pack(pady=(0, 30))

        # 卡片容器
        cards_frame = ttk.Frame(self.content_frame)
        cards_frame.pack(expand=True)

        # 三种模式卡片
        modes = [
            {
                'id': 'single_video',
                'icon': '🎞️',
                'title': '单视频切分',
                'desc': '选择单个视频文件进行帧提取',
                'bootstyle': 'info'
            },
            {
                'id': 'single_directory',
                'icon': '📁',
                'title': '单目录切分',
                'desc': '批量处理目录中的所有视频',
                'bootstyle': 'success'
            },
            {
                'id': 'multi_directory',
                'icon': '📂',
                'title': '多目录并发切分',
                'desc': '并发处理多个目录，提高效率',
                'bootstyle': 'warning'
            }
        ]

        for mode in modes:
            card = self.create_mode_card(cards_frame, mode)
            card.pack(side=LEFT, expand=True, padx=10, fill=BOTH)

    def create_mode_card(self, parent, mode: dict) -> ttk.Frame:
        """创建模式卡片"""
        card = ttk.Frame(parent, bootstyle="dark")

        # 添加边框效果
        border = ttk.Frame(card, bootstyle=mode['bootstyle'])
        border.pack(fill=BOTH, expand=True, padx=2, pady=2)

        inner = ttk.Frame(border, bootstyle="dark")
        inner.pack(fill=BOTH, expand=True, padx=10, pady=15)

        # 图标
        ttk.Label(
            inner,
            text=mode['icon'],
            font=('Segoe UI Emoji', 48)
        ).pack(pady=10)

        # 标题
        ttk.Label(
            inner,
            text=mode['title'],
            font=('Segoe UI', 14, 'bold'),
            bootstyle="inverse-dark"
        ).pack(pady=5)

        # 描述
        ttk.Label(
            inner,
            text=mode['desc'],
            wraplength=200,
            justify=CENTER,
            bootstyle="secondary-inverse"
        ).pack(pady=5)

        # 选择按钮
        ttk.Button(
            inner,
            text="选择此模式",
            command=lambda m=mode['id']: self.select_mode(m),
            bootstyle=f"{mode['bootstyle']}-outline"
        ).pack(pady=15)

        return card

    def select_mode(self, mode: str):
        """选择模式"""
        self.current_mode.set(mode)
        self.config.last_mode = mode
        self.config.save()
        self.show_operation_area()

    def show_operation_area(self):
        """显示操作区"""
        self.clear_content()

        mode = self.current_mode.get()

        if mode == "single_video":
            self.create_single_video_ui()
        elif mode == "single_directory":
            self.create_single_directory_ui()
        elif mode == "multi_directory":
            self.create_multi_directory_ui()

    def clear_content(self):
        """清空内容区"""
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    def create_single_video_ui(self):
        """创建单视频模式UI"""
        # 标题
        ttk.Label(
            self.content_frame,
            text="🎞️ 单视频切分",
            font=('Segoe UI', 16, 'bold')
        ).pack(anchor=W, pady=(0, 20))

        # 视频文件选择
        file_frame = ttk.LabelFrame(self.content_frame, text="视频文件")
        file_frame.pack(fill=X, pady=10)
        file_inner = ttk.Frame(file_frame)
        file_inner.pack(fill=X, expand=True, padx=10, pady=10)

        entry_frame = ttk.Frame(file_inner)
        entry_frame.pack(fill=X)

        ttk.Entry(
            entry_frame,
            textvariable=self.single_video_path,
            state='readonly'
        ).pack(side=LEFT, fill=X, expand=True, padx=(0, 10))

        ttk.Button(
            entry_frame,
            text="选择视频",
            command=self.select_video_file,
            bootstyle="info"
        ).pack(side=RIGHT)

        # 复制和打开按钮
        file_btn_frame = ttk.Frame(file_inner)
        file_btn_frame.pack(fill=X, pady=(5, 0))

        ttk.Button(
            file_btn_frame,
            text="📋 复制路径",
            command=lambda: self.copy_to_clipboard(self.single_video_path.get()),
            bootstyle="outline",
            width=12
        ).pack(side=LEFT, padx=2)

        ttk.Button(
            file_btn_frame,
            text="📂 打开目录",
            command=lambda: self.open_directory(os.path.dirname(self.single_video_path.get())),
            bootstyle="outline",
            width=12
        ).pack(side=LEFT, padx=2)

        # 输出目录
        output_frame = ttk.LabelFrame(self.content_frame, text="输出设置")
        output_frame.pack(fill=X, pady=10)
        output_inner = ttk.Frame(output_frame)
        output_inner.pack(fill=X, expand=True, padx=10, pady=10)

        # 输出路径
        out_entry_frame = ttk.Frame(output_inner)
        out_entry_frame.pack(fill=X, pady=5)

        ttk.Label(out_entry_frame, text="输出目录:").pack(side=LEFT)
        ttk.Entry(
            out_entry_frame,
            textvariable=self.single_output_path,
            state='readonly'
        ).pack(side=LEFT, fill=X, expand=True, padx=10)

        ttk.Button(
            out_entry_frame,
            text="更改",
            command=self.select_output_dir
        ).pack(side=RIGHT)

        # 复制和打开按钮
        out_btn_frame = ttk.Frame(output_inner)
        out_btn_frame.pack(fill=X, pady=(5, 0))

        ttk.Button(
            out_btn_frame,
            text="📋 复制路径",
            command=lambda: self.copy_to_clipboard(self.single_output_path.get()),
            bootstyle="outline",
            width=12
        ).pack(side=LEFT, padx=2)

        ttk.Button(
            out_btn_frame,
            text="📂 打开目录",
            command=lambda: self.open_directory(self.single_output_path.get()),
            bootstyle="outline",
            width=12
        ).pack(side=LEFT, padx=2)

        # 切分参数
        params_frame = ttk.LabelFrame(self.content_frame, text="切分参数")
        params_frame.pack(fill=X, pady=10)
        params_inner = ttk.Frame(params_frame)
        params_inner.pack(fill=X, expand=True, padx=10, pady=10)

        # 切分数量设置
        total_frame = ttk.Frame(params_frame)
        total_frame.pack(fill=X, pady=5)

        ttk.Label(total_frame, text="切分张数:").pack(side=LEFT)

        self.total_spin = ttk.Spinbox(
            total_frame,
            from_=1,
            to=1000,
            textvariable=self.single_total,
            width=8
        )
        self.total_spin.pack(side=LEFT, padx=10)

        # 快捷按钮
        ttk.Label(total_frame, text="快捷:").pack(side=LEFT, padx=(20, 5))
        for num in [50, 100, 150, 200]:
            ttk.Button(
                total_frame,
                text=str(num),
                width=4,
                command=lambda n=num: self.set_total(n)
            ).pack(side=LEFT, padx=2)

        # 格式选择
        format_frame = ttk.Frame(params_frame)
        format_frame.pack(fill=X, pady=10)

        ttk.Label(format_frame, text="输出格式:").pack(side=LEFT)
        ttk.Combobox(
            format_frame,
            textvariable=self.output_format,
            values=["jpg", "png", "bmp"],
            width=10,
            state="readonly"
        ).pack(side=LEFT, padx=10)

        # 执行按钮
        btn_frame = ttk.Frame(self.content_frame)
        btn_frame.pack(fill=X, pady=20)

        self.start_btn = ttk.Button(
            btn_frame,
            text="🚀 开始切分",
            command=self.start_single_video,
            bootstyle="success",
            width=20
        )
        self.start_btn.pack(pady=10)

        # 进度区域
        self.progress_frame = ttk.LabelFrame(self.content_frame, text="处理进度")
        self.progress_frame.pack(fill=X, pady=10)
        progress_inner = ttk.Frame(self.progress_frame)
        progress_inner.pack(fill=X, expand=True, padx=10, pady=10)

        self.progress_var = ttk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            variable=self.progress_var,
            maximum=100,
            bootstyle="success",
            length=400
        )
        self.progress_bar.pack(fill=X, pady=5)

        self.status_label = ttk.Label(self.progress_frame, text="准备就绪")
        self.status_label.pack(anchor=W)

        self.current_file_label = ttk.Label(self.progress_frame, text="", bootstyle="secondary")
        self.current_file_label.pack(anchor=W)

        # 日志区域
        self.single_log_text = self.create_log_viewer(self.content_frame, height=8)

        # 初始化UI状态
        self.update_mode_ui()

    def create_single_directory_ui(self):
        """创建单目录模式UI"""
        # 创建主滚动容器
        scroll_container = ttk.Frame(self.content_frame)
        scroll_container.pack(fill=BOTH, expand=True)

        # 创建可滚动区域
        content_frame, canvas = self.create_scrollable_frame(scroll_container)

        # 标题
        ttk.Label(
            content_frame,
            text="📁 单目录切分",
            font=('Segoe UI', 16, 'bold')
        ).pack(anchor=W, pady=(0, 20))

        # 目录选择
        dir_frame = ttk.LabelFrame(content_frame, text="输入目录")
        dir_frame.pack(fill=X, pady=10)
        dir_inner = ttk.Frame(dir_frame)
        dir_inner.pack(fill=X, expand=True, padx=10, pady=10)

        entry_frame = ttk.Frame(dir_inner)
        entry_frame.pack(fill=X)

        ttk.Entry(
            entry_frame,
            textvariable=self.single_dir_path,
            state='readonly'
        ).pack(side=LEFT, fill=X, expand=True, padx=(0, 10))

        ttk.Button(
            entry_frame,
            text="选择目录",
            command=self.select_input_directory,
            bootstyle="info"
        ).pack(side=RIGHT)

        # 复制和打开按钮
        dir_btn_frame = ttk.Frame(dir_inner)
        dir_btn_frame.pack(fill=X, pady=(5, 0))

        ttk.Button(
            dir_btn_frame,
            text="📋 复制路径",
            command=lambda: self.copy_to_clipboard(self.single_dir_path.get()),
            bootstyle="outline",
            width=12
        ).pack(side=LEFT, padx=2)

        ttk.Button(
            dir_btn_frame,
            text="📂 打开目录",
            command=lambda: self.open_directory(self.single_dir_path.get()),
            bootstyle="outline",
            width=12
        ).pack(side=LEFT, padx=2)

        # 输出目录
        out_frame = ttk.LabelFrame(content_frame, text="输出设置")
        out_frame.pack(fill=X, pady=10)
        out_inner = ttk.Frame(out_frame)
        out_inner.pack(fill=X, expand=True, padx=10, pady=10)

        out_entry_frame = ttk.Frame(out_inner)
        out_entry_frame.pack(fill=X, pady=5)

        ttk.Label(out_entry_frame, text="输出目录:").pack(side=LEFT)
        ttk.Entry(
            out_entry_frame,
            textvariable=self.single_dir_output,
            state='readonly'
        ).pack(side=LEFT, fill=X, expand=True, padx=10)

        ttk.Button(
            out_entry_frame,
            text="更改",
            command=self.select_dir_output
        ).pack(side=RIGHT)

        # 复制和打开按钮
        out_btn_frame = ttk.Frame(out_inner)
        out_btn_frame.pack(fill=X, pady=(5, 0))

        ttk.Button(
            out_btn_frame,
            text="📋 复制路径",
            command=lambda: self.copy_to_clipboard(self.single_dir_output.get()),
            bootstyle="outline",
            width=12
        ).pack(side=LEFT, padx=2)

        ttk.Button(
            out_btn_frame,
            text="📂 打开目录",
            command=lambda: self.open_directory(self.single_dir_output.get()),
            bootstyle="outline",
            width=12
        ).pack(side=LEFT, padx=2)

        ttk.Label(
            out_frame,
            text="提示: 默认在输入目录下创建「切分图片」文件夹",
            bootstyle="secondary",
            font=('Segoe UI', 9)
        ).pack(anchor=W, pady=(5, 0))

        # 切分模式选择 - 修改为统一/单独设置
        split_mode_frame = ttk.LabelFrame(content_frame, text="切分模式")
        split_mode_frame.pack(fill=X, pady=10)
        split_mode_inner = ttk.Frame(split_mode_frame)
        split_mode_inner.pack(fill=X, expand=True, padx=10, pady=10)

        self.single_dir_split_mode = ttk.StringVar(value="uniform")

        mode_select_frame = ttk.Frame(split_mode_inner)
        mode_select_frame.pack(fill=X)

        ttk.Radiobutton(
            mode_select_frame,
            text="统一设置 (所有视频相同张数)",
            variable=self.single_dir_split_mode,
            value="uniform",
            command=self.on_single_dir_mode_change
        ).pack(side=LEFT, padx=10)

        ttk.Radiobutton(
            mode_select_frame,
            text="单独设置 (为每个视频指定张数)",
            variable=self.single_dir_split_mode,
            value="individual",
            command=self.on_single_dir_mode_change
        ).pack(side=LEFT, padx=10)

        # 统一设置时的全局设置
        self.uniform_settings_frame = ttk.Frame(split_mode_inner)
        self.uniform_settings_frame.pack(fill=X, pady=(10, 0))

        ttk.Label(self.uniform_settings_frame, text="切分张数:").pack(side=LEFT, padx=(20, 5))
        self.single_dir_uniform_count = ttk.IntVar(value=100)
        ttk.Spinbox(
            self.uniform_settings_frame,
            from_=1,
            to=1000,
            textvariable=self.single_dir_uniform_count,
            width=10
        ).pack(side=LEFT)

        # 快捷按钮
        quick_frame = ttk.Frame(self.uniform_settings_frame)
        quick_frame.pack(side=LEFT, padx=(20, 0))
        for num in [50, 100, 150, 200]:
            ttk.Button(
                quick_frame,
                text=str(num),
                width=4,
                command=lambda n=num: self.single_dir_uniform_count.set(n),
                bootstyle="outline"
            ).pack(side=LEFT, padx=2)

        # 视频列表 - 添加切分张数列
        list_frame = ttk.LabelFrame(content_frame, text="待处理视频")
        list_frame.pack(fill=BOTH, expand=True, pady=10)
        list_inner = ttk.Frame(list_frame)
        list_inner.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # 使用Treeview显示视频列表 - 添加切分张数列
        columns = ('filename', 'size', 'frame_count')
        self.video_tree = ttk.Treeview(list_inner, columns=columns, show='headings', height=8)
        self.video_tree.heading('filename', text='文件名')
        self.video_tree.heading('size', text='大小')
        self.video_tree.heading('frame_count', text='切分张数')
        self.video_tree.column('filename', width=350)
        self.video_tree.column('size', width=100)
        self.video_tree.column('frame_count', width=100)

        scrollbar = ttk.Scrollbar(list_inner, orient=VERTICAL, command=self.video_tree.yview)
        self.video_tree.configure(yscrollcommand=scrollbar.set)

        self.video_tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        # 双击编辑切分张数
        self.video_tree.bind('<Double-Button-1>', self.on_video_tree_double_click)

        # 存储视频数据
        self.single_dir_videos = []

        # 绑定目录变化更新列表
        self.single_dir_path.trace_add('write', lambda *args: self.update_video_list())

        # 绑定统一设置张数变化更新列表
        self.single_dir_uniform_count.trace_add('write', lambda *args: self.on_uniform_count_change())

        # 执行按钮
        btn_frame = ttk.Frame(content_frame)
        btn_frame.pack(fill=X, pady=20)

        self.dir_start_btn = ttk.Button(
            btn_frame,
            text="🚀 开始切分",
            command=self.start_single_directory,
            bootstyle="success",
            width=20
        )
        self.dir_start_btn.pack(pady=10)

        # 进度区域
        self.progress_frame = ttk.LabelFrame(content_frame, text="处理进度")
        self.progress_frame.pack(fill=X, pady=10)
        progress_inner = ttk.Frame(self.progress_frame)
        progress_inner.pack(fill=X, expand=True, padx=10, pady=10)

        self.progress_var = ttk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            progress_inner,
            variable=self.progress_var,
            maximum=100,
            bootstyle="success"
        )
        self.progress_bar.pack(fill=X, pady=5)

        self.status_label = ttk.Label(progress_inner, text="准备就绪")
        self.status_label.pack(anchor=W)

        self.current_file_label = ttk.Label(progress_inner, text="", bootstyle="secondary")
        self.current_file_label.pack(anchor=W)

        # 日志区域
        self.dir_log_text = self.create_log_viewer(content_frame, height=8)

    def create_multi_directory_ui(self):
        """创建多目录并发模式UI"""
        # 创建主滚动容器
        scroll_container = ttk.Frame(self.content_frame)
        scroll_container.pack(fill=BOTH, expand=True)

        # 创建可滚动区域
        content_frame, canvas = self.create_scrollable_frame(scroll_container)

        ttk.Label(
            content_frame,
            text="📂 多目录并发切分",
            font=('Segoe UI', 16, 'bold')
        ).pack(anchor=W, pady=(0, 20))

        # 目录列表管理
        list_frame = ttk.LabelFrame(content_frame, text="目录列表")
        list_frame.pack(fill=BOTH, expand=True, pady=10)
        list_inner = ttk.Frame(list_frame)
        list_inner.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # 按钮工具栏
        toolbar = ttk.Frame(list_inner)
        toolbar.pack(fill=X, pady=(0, 10))

        ttk.Button(
            toolbar,
            text="➕ 添加目录",
            command=self.add_multi_directory,
            bootstyle="info"
        ).pack(side=LEFT, padx=2)

        ttk.Button(
            toolbar,
            text="🗑️ 删除选中",
            command=self.remove_selected_dir,
            bootstyle="danger-outline"
        ).pack(side=LEFT, padx=2)

        ttk.Button(
            toolbar,
            text="🧹 清空全部",
            command=self.clear_all_dirs,
            bootstyle="warning-outline"
        ).pack(side=LEFT, padx=2)

        # 选中项操作按钮
        ttk.Button(
            toolbar,
            text="📋 复制选中路径",
            command=self.copy_selected_multi_path,
            bootstyle="info-outline",
            width=14
        ).pack(side=RIGHT, padx=2)

        ttk.Button(
            toolbar,
            text="📂 打开选中路径",
            command=self.open_selected_multi_path,
            bootstyle="success-outline",
            width=14
        ).pack(side=RIGHT, padx=2)

        # 目录列表
        columns = ('path', 'output', 'videos', 'status', 'settings')
        self.multi_tree = ttk.Treeview(list_inner, columns=columns, show='headings', height=10)
        self.multi_tree.heading('path', text='目录路径')
        self.multi_tree.heading('output', text='输出路径')
        self.multi_tree.heading('videos', text='视频数')
        self.multi_tree.heading('status', text='状态')
        self.multi_tree.heading('settings', text='切分设置')
        self.multi_tree.column('path', width=300, minwidth=150, stretch=True)
        self.multi_tree.column('output', width=200, minwidth=100, stretch=True)
        self.multi_tree.column('videos', width=60, minwidth=60, stretch=False)
        self.multi_tree.column('status', width=80, minwidth=80, stretch=False)
        self.multi_tree.column('settings', width=100, minwidth=80, stretch=False)

        scrollbar = ttk.Scrollbar(list_inner, orient=VERTICAL, command=self.multi_tree.yview)
        self.multi_tree.configure(yscrollcommand=scrollbar.set)

        # 水平滚动条
        h_scrollbar = ttk.Scrollbar(list_inner, orient=HORIZONTAL, command=self.multi_tree.xview)
        self.multi_tree.configure(xscrollcommand=h_scrollbar.set)

        self.multi_tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)
        h_scrollbar.pack(side=BOTTOM, fill=X)

        # 双击打开设置对话框
        self.multi_tree.bind('<Double-Button-1>', self.on_multi_dir_double_click)

        # 切分参数 - 只保留总数模式
        params_frame = ttk.LabelFrame(content_frame, text="切分参数")
        params_frame.pack(fill=X, pady=10)
        params_inner = ttk.Frame(params_frame)
        params_inner.pack(fill=X, expand=True, padx=10, pady=10)

        # 切分张数设置
        total_frame = ttk.Frame(params_inner)
        total_frame.pack(fill=X)

        ttk.Label(total_frame, text="切分张数:").pack(side=LEFT, padx=10)

        ttk.Spinbox(
            total_frame,
            from_=1,
            to=1000,
            textvariable=self.single_total,
            width=8
        ).pack(side=LEFT)

        # 快捷按钮
        ttk.Label(total_frame, text="快捷:").pack(side=LEFT, padx=(20, 5))
        for num in [50, 100, 150, 200]:
            ttk.Button(
                total_frame,
                text=str(num),
                width=4,
                command=lambda n=num: self.single_total.set(n),
                bootstyle="outline"
            ).pack(side=LEFT, padx=2)

        # 应用到所有目录按钮
        ttk.Button(
            total_frame,
            text="应用到所有目录",
            command=self.apply_global_settings_to_all,
            bootstyle="info-outline"
        ).pack(side=LEFT, padx=(20, 0))

        # 格式
        format_frame = ttk.Frame(params_inner)
        format_frame.pack(fill=X, pady=(10, 0))

        ttk.Label(format_frame, text="输出格式:").pack(side=LEFT)
        ttk.Combobox(
            format_frame,
            textvariable=self.output_format,
            values=["jpg", "png", "bmp"],
            width=10,
            state="readonly"
        ).pack(side=LEFT, padx=10)

        # 并发设置
        thread_frame = ttk.LabelFrame(content_frame, text="并发设置")
        thread_frame.pack(fill=X, pady=10)
        thread_inner = ttk.Frame(thread_frame)
        thread_inner.pack(fill=X, expand=True, padx=10, pady=10)

        ttk.Label(thread_inner, text="并发线程数:").pack(side=LEFT)
        self.thread_spin = ttk.Spinbox(
            thread_inner,
            from_=1,
            to=10,
            width=5
        )
        self.thread_spin.set(self.config.thread_count)
        self.thread_spin.pack(side=LEFT, padx=10)

        ttk.Label(
            thread_inner,
            text="建议: 根据CPU核心数设置，通常3-5为宜",
            bootstyle="secondary"
        ).pack(side=LEFT)

        # 执行按钮
        btn_frame = ttk.Frame(content_frame)
        btn_frame.pack(fill=X, pady=20)

        self.multi_start_btn = ttk.Button(
            btn_frame,
            text="🚀 开始并发切分",
            command=self.start_multi_directory,
            bootstyle="success",
            width=25
        )
        self.multi_start_btn.pack(pady=10)

        # 总体进度
        self.multi_progress_frame = ttk.LabelFrame(content_frame, text="总体进度")
        self.multi_progress_frame.pack(fill=X, pady=10)
        multi_progress_inner = ttk.Frame(self.multi_progress_frame)
        multi_progress_inner.pack(fill=X, expand=True, padx=10, pady=10)

        self.multi_progress_var = ttk.DoubleVar(value=0)
        self.multi_progress_bar = ttk.Progressbar(
            multi_progress_inner,
            variable=self.multi_progress_var,
            maximum=100,
            bootstyle="info"
        )
        self.multi_progress_bar.pack(fill=X, pady=5)

        self.multi_status_label = ttk.Label(multi_progress_inner, text="准备就绪")
        self.multi_status_label.pack(anchor=W)

        # 日志区域
        self.multi_log_text = self.create_log_viewer(content_frame, height=8)

    def create_common_params(self, parent):
        """创建通用参数区域"""
        params_frame = ttk.LabelFrame(parent, text="切分参数")
        params_frame.pack(fill=X, pady=10)
        params_inner = ttk.Frame(params_frame)
        params_inner.pack(fill=X, expand=True, padx=10, pady=10)

        # 切分张数设置
        mode_frame = ttk.Frame(params_inner)
        mode_frame.pack(fill=X)

        ttk.Label(mode_frame, text="切分张数:").pack(side=LEFT, padx=10)

        ttk.Spinbox(
            mode_frame,
            from_=1,
            to=1000,
            textvariable=self.single_total,
            width=8
        ).pack(side=LEFT)

        # 快捷按钮
        ttk.Label(mode_frame, text="快捷:").pack(side=LEFT, padx=(20, 5))
        for num in [50, 100, 150, 200]:
            ttk.Button(
                mode_frame,
                text=str(num),
                width=4,
                command=lambda n=num: self.single_total.set(n),
                bootstyle="outline"
            ).pack(side=LEFT, padx=2)

        # 格式
        format_frame = ttk.Frame(params_frame)
        format_frame.pack(fill=X, pady=(10, 0))

        ttk.Label(format_frame, text="输出格式:").pack(side=LEFT)
        ttk.Combobox(
            format_frame,
            textvariable=self.output_format,
            values=["jpg", "png", "bmp"],
            width=10,
            state="readonly"
        ).pack(side=LEFT, padx=10)

        # 执行按钮
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=X, pady=20)

        self.dir_start_btn = ttk.Button(
            btn_frame,
            text="🚀 开始切分",
            command=self.start_single_directory,
            bootstyle="success",
            width=20
        )
        self.dir_start_btn.pack(pady=10)

    # ========================================================================
    # 事件处理方法
    # ========================================================================
    def select_video_file(self):
        """选择视频文件"""
        path = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[("视频文件", "*.mp4 *.avi *.mov *.mkv *.flv *.wmv *.webm"), ("所有文件", "*.*")]
        )
        if path:
            self.single_video_path.set(path)
            # 自动设置输出目录
            video_dir = os.path.dirname(path)
            default_output = os.path.join(video_dir, "切分图片")
            self.single_output_path.set(default_output)

    def select_output_dir(self):
        """选择输出目录"""
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.single_output_path.set(path)

    def select_input_directory(self):
        """选择输入目录"""
        path = filedialog.askdirectory(title="选择包含视频的目录")
        if path:
            self.single_dir_path.set(path)
            # 自动设置输出目录
            default_output = os.path.join(path, "切分图片")
            self.single_dir_output.set(default_output)

    def select_dir_output(self):
        """选择目录输出路径"""
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.single_dir_output.set(path)

    def update_video_list(self):
        """更新视频列表"""
        directory = self.single_dir_path.get()
        if not directory or not os.path.exists(directory):
            # 清空列表和数据
            for item in self.video_tree.get_children():
                self.video_tree.delete(item)
            self.single_dir_videos = []
            return

        # 清空列表
        for item in self.video_tree.get_children():
            self.video_tree.delete(item)

        # 扫描视频
        videos = self.extractor.scan_videos(directory, recursive=False)
        self.single_dir_videos = []

        for video in videos:
            filename = os.path.basename(video)
            size = os.path.getsize(video)
            size_str = self.format_size(size)

            # 根据当前模式确定默认值
            if self.single_dir_split_mode.get() == "uniform":
                default_count = self.single_dir_uniform_count.get()
            else:
                default_count = 100

            # 创建视频数据项
            video_data = {
                'path': video,
                'name': filename,
                'size': size,
                'frame_count': default_count
            }
            self.single_dir_videos.append(video_data)

            self.video_tree.insert('', 'end', values=(filename, size_str, default_count))

    def on_single_dir_mode_change(self):
        """单目录模式改变时更新UI"""
        mode = self.single_dir_split_mode.get()

        if mode == "uniform":
            # 统一设置模式：启用全局设置，禁用列表编辑
            for widget in self.uniform_settings_frame.winfo_children():
                if isinstance(widget, ttk.Spinbox) or isinstance(widget, ttk.Button):
                    widget.configure(state='normal')
            # 更新列表显示为统一值
            self.update_video_list_display()
        else:
            # 单独设置模式：允许编辑列表
            for widget in self.uniform_settings_frame.winfo_children():
                if isinstance(widget, ttk.Spinbox) or isinstance(widget, ttk.Button):
                    widget.configure(state='disabled')

    def update_video_list_display(self):
        """根据当前模式更新视频列表显示"""
        if self.single_dir_split_mode.get() == "uniform":
            uniform_count = self.single_dir_uniform_count.get()
            # 更新所有视频的frame_count
            for video_data in self.single_dir_videos:
                video_data['frame_count'] = uniform_count

            # 更新Treeview显示
            for i, item_id in enumerate(self.video_tree.get_children()):
                values = self.video_tree.item(item_id, 'values')
                self.video_tree.item(item_id, values=(values[0], values[1], uniform_count))

    def on_uniform_count_change(self):
        """统一设置张数改变时更新视频列表"""
        if self.single_dir_split_mode.get() == "uniform":
            self.update_video_list_display()

    def on_video_tree_double_click(self, event=None):
        """双击视频列表编辑切分张数"""
        if self.single_dir_split_mode.get() == "uniform":
            return  # 统一设置模式下不允许单独编辑

        selected = self.video_tree.selection()
        if not selected:
            return

        index = self.video_tree.index(selected[0])
        if index < 0 or index >= len(self.single_dir_videos):
            return

        # 获取当前值
        current_value = self.single_dir_videos[index]['frame_count']

        # 弹出输入对话框
        from tkinter.simpledialog import askinteger
        new_value = askinteger(
            "设置切分张数",
            f"设置 '{self.single_dir_videos[index]['name']}' 的切分张数:",
            initialvalue=current_value,
            minvalue=1,
            maxvalue=1000,
            parent=self.root
        )

        if new_value is not None:
            # 更新数据
            self.single_dir_videos[index]['frame_count'] = new_value
            # 更新显示
            values = self.video_tree.item(selected[0], 'values')
            self.video_tree.item(selected[0], values=(values[0], values[1], new_value))

    def format_size(self, size: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def add_multi_directory(self):
        """添加多目录 - 循环选择单个目录"""
        selected_paths = []

        while True:
            path = filedialog.askdirectory(
                title=f"选择目录（已选 {len(selected_paths)} 个，取消结束选择）",
                parent=self.root
            )

            if not path:  # 用户取消，结束选择
                break

            # 检查是否已选择过
            if path in selected_paths:
                messagebox.showwarning("提示", "该目录已选择", parent=self.root)
                continue

            # 检查是否已在主列表中存在
            if any(item['path'] == path for item in self.multi_dirs):
                messagebox.showwarning("提示", f"该目录已存在:\n{path}", parent=self.root)
                continue

            selected_paths.append(path)

            # 询问是否继续添加
            if not messagebox.askyesno(
                "继续添加",
                f"已选择 {len(selected_paths)} 个目录\n\n是否继续添加？",
                parent=self.root
            ):
                break

        if not selected_paths:
            return

        # 使用当前全局设置作为默认值
        default_count = self.single_total.get()

        added_count = 0
        # 批量添加目录
        for path in selected_paths:
            default_output = os.path.join(path, "切分图片")

            # 扫描该目录下的所有视频
            videos = self.extractor.scan_videos(path, recursive=False)

            # 创建视频列表数据结构
            videos_data = []
            for video_path in videos:
                videos_data.append({
                    'path': video_path,
                    'name': os.path.basename(video_path),
                    'frame_count': default_count,
                    'status': '等待'
                })

            dir_item = {
                'path': path,
                'output': default_output,
                'videos': videos_data,
                'video_count': len(videos_data),
                'status': '等待',
                'split_mode': 'uniform',
                'uniform_count': default_count
            }
            self.multi_dirs.append(dir_item)
            self.multi_tree.insert('', 'end', values=(
                path, default_output, len(videos_data), '等待', f'统一: {default_count}'
            ))
            added_count += 1

        if added_count > 0:
            messagebox.showinfo("提示", f"成功添加 {added_count} 个目录")

    def on_multi_dir_double_click(self, event=None):
        """双击目录列表打开设置对话框"""
        selected = self.multi_tree.selection()
        if not selected:
            return

        index = self.multi_tree.index(selected[0])
        if index < 0 or index >= len(self.multi_dirs):
            return

        dir_item = self.multi_dirs[index]

        # 打开设置对话框
        dialog = self.DirectorySettingsDialog(self.root, dir_item, self.extractor)
        self.root.wait_window(dialog)

        if dialog.result:
            # 更新目录项数据
            dir_item['split_mode'] = dialog.result['split_mode']
            dir_item['uniform_count'] = dialog.result['uniform_count']
            dir_item['videos'] = dialog.result['videos']

            # 更新显示
            self.update_multi_dir_settings_display(index)

    def update_multi_dir_settings_display(self, index):
        """更新目录的切分设置显示"""
        if index < 0 or index >= len(self.multi_dirs):
            return

        dir_item = self.multi_dirs[index]
        mode = dir_item.get('split_mode', 'uniform')

        if mode == 'uniform':
            count = dir_item.get('uniform_count', 100)
            settings_text = f"统一: {count}"
        else:
            # 单独设置
            video_count = len(dir_item.get('videos', []))
            settings_text = f"单独: {video_count}个"

        # 更新Treeview中的值
        item_id = self.multi_tree.get_children()[index]
        current_values = self.multi_tree.item(item_id, 'values')
        self.multi_tree.item(item_id, values=(
            current_values[0],  # path
            current_values[1],  # output
            current_values[2],  # videos
            current_values[3],  # status
            settings_text       # settings
        ))

    def remove_selected_dir(self):
        """删除选中的目录"""
        selected = self.multi_tree.selection()
        if not selected:
            return

        index = self.multi_tree.index(selected[0])
        self.multi_dirs.pop(index)
        self.multi_tree.delete(selected[0])

    def clear_all_dirs(self):
        """清空所有目录"""
        if messagebox.askyesno("确认", "确定要清空所有目录吗？"):
            self.multi_dirs.clear()
            for item in self.multi_tree.get_children():
                self.multi_tree.delete(item)

    def apply_global_settings_to_all(self):
        """将当前全局设置应用到所有目录"""
        if not self.multi_dirs:
            messagebox.showinfo("提示", "没有可应用的目录")
            return

        global_count = self.single_total.get()

        # 更新所有目录的uniform_count
        for dir_item in self.multi_dirs:
            dir_item['uniform_count'] = global_count
            # 同时更新所有视频的frame_count
            for video in dir_item.get('videos', []):
                video['frame_count'] = global_count

        # 更新Treeview显示
        for i, item_id in enumerate(self.multi_tree.get_children()):
            if i < len(self.multi_dirs):
                dir_item = self.multi_dirs[i]
                values = self.multi_tree.item(item_id, 'values')
                # 更新切分设置列
                mode = dir_item.get('split_mode', 'uniform')
                if mode == 'uniform':
                    settings_text = f"统一: {global_count}"
                else:
                    settings_text = f"单独: {len(dir_item.get('videos', []))}个"
                self.multi_tree.item(item_id, values=(
                    values[0],  # path
                    values[1],  # output
                    values[2],  # videos
                    values[3],  # status
                    settings_text
                ))

        messagebox.showinfo("提示", f"已将切分张数 {global_count} 应用到所有目录")

    def update_mode_ui(self):
        """更新模式UI - 简化为总数模式"""
        # FPS模式已移除，只保留总数模式
        pass

    def set_total(self, num: int):
        """设置总数"""
        self.single_total.set(num)

    # ========================================================================
    # 处理逻辑
    # ========================================================================
    def start_single_video(self):
        """开始单视频处理"""
        if not self.ffmpeg_available:
            messagebox.showerror("错误", "未检测到FFmpeg，请先安装")
            return

        video_path = self.single_video_path.get()
        if not video_path:
            messagebox.showerror("错误", "请选择视频文件")
            return

        output_dir = self.single_output_path.get()
        if not output_dir:
            messagebox.showerror("错误", "请选择输出目录")
            return

        # 创建配置
        config = ExtractConfig(
            total_value=self.single_total.get(),
            output_format=self.output_format.get()
        )

        # 禁用按钮
        self.start_btn.configure(state='disabled', text='⏳ 处理中...')
        self.is_processing = True
        self.stop_event.clear()

        # 启动处理线程
        thread = threading.Thread(
            target=self._process_single_video,
            args=(video_path, output_dir, config),
            daemon=True
        )
        thread.start()

    def _process_single_video(self, video_path: str, output_dir: str, config: ExtractConfig):
        """处理单个视频（后台线程）"""
        def progress_callback(progress, message):
            self.root.after(0, lambda: self._update_progress(progress, message))
            self.root.after(0, lambda m=message: self.log_message(self.single_log_text, m))

        self.root.after(0, lambda: self.log_message(self.single_log_text, f"开始处理: {video_path}"))
        self.root.after(0, lambda: self.log_message(self.single_log_text, f"输出目录: {output_dir}"))
        self.root.after(0, lambda: self.log_message(self.single_log_text, f"切分张数: {config.total_value}, 格式: {config.output_format}"))

        success, msg = self.extractor.extract_frames(
            video_path, output_dir, config,
            progress_callback, self.stop_event
        )

        self.root.after(0, lambda: self.log_message(self.single_log_text, f"处理结果: {msg}"))
        self.root.after(0, lambda: self._on_process_complete(success, msg))

    def _update_progress(self, progress: float, message: str):
        """更新进度"""
        self.progress_var.set(progress)
        self.status_label.configure(text=f"处理中... {progress:.1f}%")
        self.current_file_label.configure(text=message)

    def _on_process_complete(self, success: bool, message: str):
        """处理完成"""
        self.is_processing = False
        self.start_btn.configure(state='normal', text='🚀 开始切分')

        if success:
            self.progress_var.set(100)
            self.status_label.configure(text=f"✅ {message}")
            if messagebox.askyesno("完成", f"{message}\n\n是否打开输出文件夹？"):
                os.startfile(self.single_output_path.get())
        else:
            self.status_label.configure(text=f"❌ {message}")
            messagebox.showerror("错误", message)

    def start_single_directory(self):
        """开始单目录处理"""
        if not self.ffmpeg_available:
            messagebox.showerror("错误", "未检测到FFmpeg")
            return

        directory = self.single_dir_path.get()
        if not directory:
            messagebox.showerror("错误", "请选择输入目录")
            return

        output_dir = self.single_dir_output.get()
        if not output_dir:
            messagebox.showerror("错误", "请选择输出目录")
            return

        videos = self.extractor.scan_videos(directory)
        if not videos:
            messagebox.showwarning("提示", "所选目录中没有找到视频文件")
            return

        # 禁用按钮
        self.dir_start_btn.configure(state='disabled', text='⏳ 处理中...')
        self.is_processing = True

        # 启动处理
        thread = threading.Thread(
            target=self._process_directory,
            args=(videos, output_dir),
            daemon=True
        )
        thread.start()

    def _process_directory(self, videos: List[str], base_output: str):
        """处理目录（后台线程）"""
        split_mode = self.single_dir_split_mode.get()

        # 准备视频配置
        video_configs = []
        for i, video in enumerate(videos):
            if i < len(self.single_dir_videos):
                frame_count = self.single_dir_videos[i]['frame_count']
            else:
                frame_count = 100

            config = ExtractConfig(
                total_value=frame_count,
                output_format=self.output_format.get()
            )
            video_configs.append(config)

        self._process_directory_separate(videos, base_output, video_configs)

    def _process_directory_separate(self, videos: List[str], base_output: str, video_configs: List[ExtractConfig] = None):
        """单独切分模式：每个视频输出到各自子目录"""
        # 如果没有传入配置，使用默认配置
        if video_configs is None:
            video_configs = []
            for video in videos:
                config = ExtractConfig(
                    total_value=self.single_total.get(),
                    output_format=self.output_format.get()
                )
                video_configs.append(config)

        self.root.after(0, lambda: self.log_message(self.dir_log_text, f"[单独切分模式] 开始处理目录，共 {len(videos)} 个视频"))
        self.root.after(0, lambda: self.log_message(self.dir_log_text, f"输出目录: {base_output}"))

        total_videos = len(videos)
        total_frames = 0

        for idx, video in enumerate(videos):
            if self.stop_event.is_set():
                self.root.after(0, lambda: self.log_message(self.dir_log_text, "用户取消处理"))
                break

            # 每个视频创建子目录
            video_name = Path(video).stem
            video_output = os.path.join(base_output, video_name)
            os.makedirs(video_output, exist_ok=True)

            self.root.after(0, lambda v=video_name: self.status_label.configure(
                text=f"处理中... ({idx+1}/{total_videos}) {v}"
            ))
            self.root.after(0, lambda v=video_name: self.log_message(self.dir_log_text, f"处理: {v}"))

            def progress_callback(progress, message):
                overall = (idx + progress/100) / total_videos * 100
                self.root.after(0, lambda p=overall: self.progress_var.set(p))

            # 使用当前视频的配置
            video_config = video_configs[idx] if idx < len(video_configs) else video_configs[0] if video_configs else ExtractConfig(
                total_value=100,
                output_format=self.output_format.get()
            )

            success, msg = self.extractor.extract_frames(
                video, video_output, video_config,
                progress_callback, self.stop_event
            )

            if success:
                # 解析提取的帧数
                import re
                match = re.search(r'(\d+)', msg)
                if match:
                    total_frames += int(match.group(1))
                self.root.after(0, lambda m=msg: self.log_message(self.dir_log_text, f"成功: {m}"))
            else:
                self.root.after(0, lambda m=msg: self.log_message(self.dir_log_text, f"失败: {m}"))

        self.root.after(0, lambda: self.log_message(self.dir_log_text, f"处理完成，共提取 {total_frames} 帧"))
        self.root.after(0, lambda: self._on_dir_complete(total_frames))

    def _on_dir_complete(self, total_frames: int):
        """目录处理完成"""
        self.is_processing = False
        self.dir_start_btn.configure(state='normal', text='🚀 开始切分')
        self.progress_var.set(100)
        self.status_label.configure(text=f"✅ 完成！共提取 {total_frames} 帧")

        if messagebox.askyesno("完成", f"处理完成！共提取 {total_frames} 帧\n\n是否打开输出文件夹？"):
            os.startfile(self.single_dir_output.get())

    def start_multi_directory(self):
        """开始多目录并发处理"""
        if not self.ffmpeg_available:
            messagebox.showerror("错误", "未检测到FFmpeg")
            return

        if not self.multi_dirs:
            messagebox.showwarning("提示", "请先添加目录")
            return

        # 更新线程数
        try:
            self.config.thread_count = int(self.thread_spin.get())
            self.processor.max_workers = self.config.thread_count
            self.config.save()
        except:
            pass

        # 重置处理器
        self.processor = BatchProcessor(self.config.thread_count)
        self.processor.start()

        # 禁用按钮
        self.multi_start_btn.configure(state='disabled', text='⏳ 处理中...')
        self.is_processing = True

        # 为每个目录、每个视频创建任务
        total_tasks = 0
        for dir_idx, dir_item in enumerate(self.multi_dirs):
            videos = dir_item.get('videos', [])
            split_mode = dir_item.get('split_mode', 'uniform')
            uniform_count = dir_item.get('uniform_count', 100)

            for video in videos:
                video_path = video.get('path', '')
                video_name = video.get('name', '')
                if not video_path:
                    continue

                # 根据模式确定切分张数
                if split_mode == 'uniform':
                    frame_count = uniform_count
                else:
                    frame_count = video.get('frame_count', 100)

                # 创建该视频的配置
                config = ExtractConfig(
                    total_value=frame_count,
                    output_format=self.output_format.get()
                )

                video_output = os.path.join(dir_item['output'], Path(video_name).stem)

                task = TaskItem(
                    id=f"{dir_idx}_{video_name}",
                    video_path=video_path,
                    output_dir=video_output,
                    config=config,
                    status="pending"
                )

                self.processor.submit_task(task, self.extractor)
                total_tasks += 1

        # 启动监控线程
        monitor_thread = threading.Thread(
            target=self._monitor_multi_progress,
            args=(total_tasks,),
            daemon=True
        )
        monitor_thread.start()

    def _monitor_multi_progress(self, total_tasks: int):
        """监控多目录进度"""
        completed = 0
        errors = 0

        self.root.after(0, lambda: self.log_message(self.multi_log_text, f"开始并发处理，共 {total_tasks} 个任务"))

        while completed + errors < total_tasks:
            try:
                msg = self.processor.ui_queue.get(timeout=0.1)

                if msg['type'] in ('complete', 'error'):
                    if msg['type'] == 'complete':
                        completed += 1
                        self.root.after(0, lambda m=msg: self.log_message(self.multi_log_text, f"完成: {m.get('message', '')}"))
                    else:
                        errors += 1
                        self.root.after(0, lambda m=msg: self.log_message(self.multi_log_text, f"错误: {m.get('message', '')}"))

                    progress = (completed + errors) / total_tasks * 100
                    self.root.after(0, lambda p=progress: self.multi_progress_var.set(p))
                    self.root.after(0, lambda c=completed, e=errors: self.multi_status_label.configure(
                        text=f"处理中... 完成: {c} 失败: {e} / 总计: {total_tasks}"
                    ))
            except queue.Empty:
                if not self.is_processing:
                    break

        self.root.after(0, lambda: self.log_message(self.multi_log_text, f"批量处理完成！成功: {completed}, 失败: {errors}"))
        self.root.after(0, lambda: self._on_multi_complete(completed, errors))

    def _on_multi_complete(self, completed: int, errors: int):
        """多目录处理完成"""
        self.is_processing = False
        self.multi_start_btn.configure(state='normal', text='🚀 开始并发切分')
        self.multi_progress_var.set(100)
        self.multi_status_label.configure(
            text=f"✅ 完成！成功: {completed} 失败: {errors}"
        )

        messagebox.showinfo("完成", f"批量处理完成！\n成功: {completed}\n失败: {errors}")

    def create_log_viewer(self, parent, height=8):
        """创建日志查看器"""
        log_frame = ttk.LabelFrame(parent, text="处理日志")
        log_frame.pack(fill=X, pady=10)
        log_inner = ttk.Frame(log_frame)
        log_inner.pack(fill=X, expand=True, padx=10, pady=10)

        # 创建Text控件 - 使用固定高度和适当字体
        log_text = tk.Text(log_inner, height=height, wrap=tk.WORD, font=('Consolas', 9))
        log_text.pack(side=LEFT, fill=BOTH, expand=True)

        # 滚动条
        scrollbar = ttk.Scrollbar(log_inner, orient=VERTICAL, command=log_text.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        log_text.configure(yscrollcommand=scrollbar.set)

        # 按钮区域
        btn_frame = ttk.Frame(log_frame)
        btn_frame.pack(fill=X, padx=10, pady=(0, 10))

        ttk.Button(
            btn_frame,
            text="📋 复制日志",
            command=lambda: self.copy_log(log_text),
            bootstyle="info-outline",
            width=12
        ).pack(side=LEFT, padx=2)

        ttk.Button(
            btn_frame,
            text="🗑️ 清空日志",
            command=lambda: log_text.delete(1.0, tk.END),
            bootstyle="warning-outline",
            width=12
        ).pack(side=LEFT, padx=2)

        # 添加初始化消息验证显示
        log_text.insert(tk.END, "[系统] 日志区域就绪\n")
        log_text.see(tk.END)

        return log_text

    def log_message(self, log_widget, message):
        """添加日志消息"""
        import time
        timestamp = time.strftime("%H:%M:%S")
        log_widget.insert(tk.END, f"[{timestamp}] {message}\n")
        log_widget.see(tk.END)

    def copy_log(self, log_widget):
        """复制日志内容"""
        content = log_widget.get(1.0, tk.END).strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.root.update()
            messagebox.showinfo("提示", "日志已复制到剪贴板")

    def copy_to_clipboard(self, text):
        """复制文本到剪贴板"""
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()
            messagebox.showinfo("提示", "已复制到剪贴板")

    def open_directory(self, path):
        """打开目录"""
        if path and os.path.exists(path):
            os.startfile(path)
        else:
            messagebox.showwarning("提示", "路径不存在")

    def open_multi_output_dirs(self):
        """打开多目录的输出目录"""
        if not self.multi_dirs:
            messagebox.showwarning("提示", "没有可打开的目录")
            return

        # 获取第一个目录的输出路径并打开
        output_path = self.multi_dirs[0]['output']
        if os.path.exists(output_path):
            os.startfile(output_path)
        else:
            messagebox.showwarning("提示", "输出目录不存在")

    def copy_selected_multi_path(self):
        """复制选中的目录路径"""
        selected = self.multi_tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择目录")
            return

        # 获取选中项的路径
        paths = []
        for item in selected:
            values = self.multi_tree.item(item, 'values')
            if values:
                paths.append(values[0])  # path列

        self.copy_to_clipboard('\n'.join(paths))

    def open_selected_multi_path(self):
        """打开选中的目录路径"""
        selected = self.multi_tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择目录")
            return

        # 打开第一个选中的
        values = self.multi_tree.item(selected[0], 'values')
        if values:
            self.open_directory(values[0])

    def process_ui_queue(self):
        if hasattr(self, 'processor') and self.processor:
            try:
                while True:
                    msg = self.processor.ui_queue.get_nowait()
                    # 处理UI更新
                    pass
            except queue.Empty:
                pass

        self.root.after(50, self.process_ui_queue)

    # ========================================================================
    # 自定义对话框类
    # ========================================================================
    class MultiDirectoryDialog(tk.Toplevel):
        """多目录选择对话框"""

        def __init__(self, parent, extractor):
            super().__init__(parent)
            self.parent = parent
            self.extractor = extractor
            self.selected_dirs = []

            self.title("选择多个目录")
            self.geometry("600x500")
            self.transient(parent)
            self.grab_set()

            self.create_ui()
            self.center_window()

        def center_window(self):
            """窗口居中"""
            self.update_idletasks()
            width = self.winfo_width()
            height = self.winfo_height()
            x = (self.winfo_screenwidth() // 2) - (width // 2)
            y = (self.winfo_screenheight() // 2) - (height // 2)
            self.geometry(f'{width}x{height}+{x}+{y}')

        def create_ui(self):
            """创建UI"""
            # 提示标签
            ttk.Label(
                self,
                text="点击\"添加目录\"选择目录，已选目录会显示在下方列表中",
                wraplength=550
            ).pack(pady=10)

            # 按钮区域
            btn_frame = ttk.Frame(self)
            btn_frame.pack(fill=X, padx=20, pady=5)

            ttk.Button(
                btn_frame,
                text="➕ 添加目录",
                command=self.add_directory,
                bootstyle="info"
            ).pack(side=LEFT, padx=5)

            ttk.Button(
                btn_frame,
                text="🗑️ 删除选中",
                command=self.remove_selected,
                bootstyle="danger-outline"
            ).pack(side=LEFT, padx=5)

            ttk.Button(
                btn_frame,
                text="🧹 清空全部",
                command=self.clear_all,
                bootstyle="warning-outline"
            ).pack(side=LEFT, padx=5)

            # 已选目录列表
            list_frame = ttk.LabelFrame(self, text="已选目录")
            list_frame.pack(fill=BOTH, expand=True, padx=20, pady=10)

            # Treeview显示目录
            columns = ('path', 'videos')
            self.tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=12)
            self.tree.heading('path', text='目录路径')
            self.tree.heading('videos', text='视频数')
            self.tree.column('path', width=450, stretch=True)
            self.tree.column('videos', width=80, stretch=False)

            scrollbar = ttk.Scrollbar(list_frame, orient=VERTICAL, command=self.tree.yview)
            self.tree.configure(yscrollcommand=scrollbar.set)

            self.tree.pack(side=LEFT, fill=BOTH, expand=True)
            scrollbar.pack(side=RIGHT, fill=Y)

            # 底部按钮
            bottom_frame = ttk.Frame(self)
            bottom_frame.pack(fill=X, padx=20, pady=15)

            self.status_label = ttk.Label(bottom_frame, text="已选 0 个目录")
            self.status_label.pack(side=LEFT)

            ttk.Button(
                bottom_frame,
                text="取消",
                command=self.cancel,
                bootstyle="outline",
                width=10
            ).pack(side=RIGHT, padx=5)

            ttk.Button(
                bottom_frame,
                text="确定",
                command=self.confirm,
                bootstyle="success",
                width=10
            ).pack(side=RIGHT, padx=5)

        def add_directory(self):
            """添加目录"""
            path = filedialog.askdirectory(title="选择目录", parent=self)
            if not path:
                return

            # 检查是否已存在
            if any(d['path'] == path for d in self.selected_dirs):
                messagebox.showwarning("提示", "该目录已存在", parent=self)
                return

            # 扫描视频（非递归）
            videos = self.extractor.scan_videos(path, recursive=False)

            dir_info = {
                'path': path,
                'videos': len(videos),
                'video_list': videos
            }
            self.selected_dirs.append(dir_info)

            self.tree.insert('', 'end', values=(path, len(videos)))
            self.update_status()

        def remove_selected(self):
            """删除选中的目录"""
            selected = self.tree.selection()
            if not selected:
                return

            index = self.tree.index(selected[0])
            self.selected_dirs.pop(index)
            self.tree.delete(selected[0])
            self.update_status()

        def clear_all(self):
            """清空全部"""
            if not self.selected_dirs:
                return

            if messagebox.askyesno("确认", "确定要清空所有已选目录吗？", parent=self):
                self.selected_dirs.clear()
                for item in self.tree.get_children():
                    self.tree.delete(item)
                self.update_status()

        def update_status(self):
            """更新状态标签"""
            total = len(self.selected_dirs)
            total_videos = sum(d['videos'] for d in self.selected_dirs)
            self.status_label.configure(text=f"已选 {total} 个目录，共 {total_videos} 个视频")

        def confirm(self):
            """确认选择"""
            self.destroy()

        def cancel(self):
            """取消选择"""
            self.selected_dirs = []
            self.destroy()

    class DirectorySettingsDialog(ttk.Toplevel):
        """目录切分设置对话框"""

        def __init__(self, parent, dir_item, extractor):
            """
            初始化设置对话框

            Args:
                parent: 父窗口
                dir_item: 目录项数据字典
                extractor: 视频提取器实例
            """
            super().__init__(parent)
            self.dir_item = dir_item
            self.extractor = extractor
            self.result = None
            self._mousewheel_bind_id = None  # 用于存储鼠标滚轮绑定ID

            self.title("目录切分设置")
            self.geometry("550x600")
            self.minsize(550, 500)
            self.transient(parent)
            self.grab_set()

            # 居中显示
            self.update_idletasks()
            x = (self.winfo_screenwidth() - self.winfo_width()) // 2
            y = (self.winfo_screenheight() - self.winfo_height()) // 2
            self.geometry(f"+{x}+{y}")

            self.create_ui()

            # 绑定关闭事件
            self.protocol("WM_DELETE_WINDOW", self.cancel)

        def create_ui(self):
            """创建UI - 使用固定底部按钮布局"""
            # 主容器 - 使用grid布局
            self.grid_columnconfigure(0, weight=1)
            self.grid_rowconfigure(0, weight=1)

            # 主内容容器
            main_container = ttk.Frame(self)
            main_container.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
            main_container.columnconfigure(0, weight=1)
            main_container.rowconfigure(0, weight=0)  # 标题
            main_container.rowconfigure(1, weight=0)  # 分隔线
            main_container.rowconfigure(2, weight=0)  # 模式选择
            main_container.rowconfigure(3, weight=1)  # 视频列表（可扩展）

            # 标题区域
            header = ttk.Frame(main_container)
            header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))

            ttk.Label(
                header,
                text=f"目录: {os.path.basename(self.dir_item['path'])}",
                font=("Microsoft YaHei UI", 12, "bold")
            ).pack(anchor=W)

            ttk.Label(
                header,
                text=self.dir_item['path'],
                font=("Microsoft YaHei UI", 9),
                foreground="gray"
            ).pack(anchor=W, pady=(5, 0))

            # 分隔线
            ttk.Separator(main_container, orient=HORIZONTAL).grid(row=1, column=0, sticky="ew", padx=20, pady=10)

            # 模式选择区域
            mode_frame = ttk.LabelFrame(main_container, text="切分模式")
            mode_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=10)

            self.split_mode = tk.StringVar(value=self.dir_item.get('split_mode', 'uniform'))

            # 统一设置选项
            uniform_frame = ttk.Frame(mode_frame)
            uniform_frame.pack(fill=X, padx=15, pady=(10, 5))

            ttk.Radiobutton(
                uniform_frame,
                text="统一设置 (所有视频相同张数)",
                variable=self.split_mode,
                value="uniform",
                command=self.on_mode_change
            ).pack(side=LEFT)

            # 统一设置输入框
            self.uniform_frame = ttk.Frame(mode_frame)
            self.uniform_frame.pack(fill=X, padx=15, pady=5)

            ttk.Label(self.uniform_frame, text="切分张数:").pack(side=LEFT, padx=(20, 5))
            self.uniform_count = tk.IntVar(value=self.dir_item.get('uniform_count', 100))
            ttk.Spinbox(
                self.uniform_frame,
                from_=1,
                to=1000,
                textvariable=self.uniform_count,
                width=10
            ).pack(side=LEFT)

            # 快捷按钮
            quick_frame = ttk.Frame(self.uniform_frame)
            quick_frame.pack(side=LEFT, padx=(20, 0))
            for num in [50, 100, 150, 200]:
                ttk.Button(
                    quick_frame,
                    text=str(num),
                    width=4,
                    command=lambda n=num: self.uniform_count.set(n),
                    bootstyle="outline"
                ).pack(side=LEFT, padx=2)

            ttk.Separator(mode_frame, orient=HORIZONTAL).pack(fill=X, padx=15, pady=10)

            # 单独设置选项
            individual_frame = ttk.Frame(mode_frame)
            individual_frame.pack(fill=X, padx=15, pady=5)

            ttk.Radiobutton(
                individual_frame,
                text="单独设置 (为每个视频指定张数)",
                variable=self.split_mode,
                value="individual",
                command=self.on_mode_change
            ).pack(side=LEFT)

            # 视频列表区域 - 使用滚动Canvas
            self.video_list_frame = ttk.LabelFrame(main_container, text="视频列表")
            self.video_list_frame.grid(row=3, column=0, sticky="nsew", padx=20, pady=10)
            self.video_list_frame.columnconfigure(0, weight=1)
            self.video_list_frame.rowconfigure(1, weight=1)  # 可滚动区域

            # 表头
            header_frame = ttk.Frame(self.video_list_frame)
            header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))

            ttk.Label(header_frame, text="视频名称", width=40).pack(side=LEFT, padx=5)
            ttk.Label(header_frame, text="切分张数", width=12).pack(side=LEFT, padx=5)

            # 滚动区域
            canvas_frame = ttk.Frame(self.video_list_frame)
            canvas_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
            canvas_frame.columnconfigure(0, weight=1)
            canvas_frame.rowconfigure(0, weight=1)

            self.canvas = tk.Canvas(canvas_frame, highlightthickness=0)
            scrollbar = ttk.Scrollbar(canvas_frame, orient=VERTICAL, command=self.canvas.yview)

            self.video_container = ttk.Frame(self.canvas)
            self.video_container.bind(
                "<Configure>",
                lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            )

            self.canvas.create_window((0, 0), window=self.video_container, anchor="nw", width=480)
            self.canvas.configure(yscrollcommand=scrollbar.set)

            self.canvas.grid(row=0, column=0, sticky="nsew")
            scrollbar.grid(row=0, column=1, sticky="ns")

            # 鼠标滚轮支持
            self.canvas.bind("<MouseWheel>", self._on_mousewheel)

            # 创建视频条目
            self.video_vars = []
            self.create_video_entries()

            # 底部按钮区域 - 固定在窗口底部
            btn_frame = ttk.Frame(self)
            btn_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=15)

            ttk.Button(
                btn_frame,
                text="取消",
                command=self.cancel,
                bootstyle="outline",
                width=10
            ).pack(side=RIGHT, padx=5)

            ttk.Button(
                btn_frame,
                text="确定",
                command=self.confirm,
                bootstyle="success",
                width=10
            ).pack(side=RIGHT, padx=5)

            # 初始化状态
            self.on_mode_change()

        def _on_mousewheel(self, event):
            """鼠标滚轮事件"""
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def create_video_entries(self):
            """创建视频条目输入框"""
            videos = self.dir_item.get('videos', [])

            for i, video in enumerate(videos):
                frame = ttk.Frame(self.video_container)
                frame.pack(fill=X, pady=2)

                # 视频名称
                name_label = ttk.Label(
                    frame,
                    text=video.get('name', ''),
                    width=40,
                    anchor=W
                )
                name_label.pack(side=LEFT, padx=5)
                name_label.bind("<Enter>", lambda e, p=video.get('path', ''): self._show_tooltip(e, p))
                name_label.bind("<Leave>", lambda e: self._hide_tooltip())

                # 切分张数输入
                var = tk.IntVar(value=video.get('frame_count', 100))
                self.video_vars.append({
                    'path': video.get('path', ''),
                    'name': video.get('name', ''),
                    'var': var
                })

                spinbox = ttk.Spinbox(
                    frame,
                    from_=1,
                    to=1000,
                    textvariable=var,
                    width=12
                )
                spinbox.pack(side=LEFT, padx=5)

        def _show_tooltip(self, event, text):
            """显示工具提示"""
            self.tooltip = tk.Toplevel(self)
            self.tooltip.wm_overrideredirect(True)
            self.tooltip.wm_geometry(f"+{event.x_root + 10}+{event.y_root + 10}")
            ttk.Label(
                self.tooltip,
                text=text,
                background="#ffffe0",
                relief=SOLID,
                borderwidth=1
            ).pack()

        def _hide_tooltip(self):
            """隐藏工具提示"""
            if hasattr(self, 'tooltip'):
                self.tooltip.destroy()

        def on_mode_change(self):
            """模式改变时更新UI状态"""
            mode = self.split_mode.get()

            if mode == "uniform":
                # 统一设置模式
                for widget in self.video_container.winfo_children():
                    for child in widget.winfo_children():
                        if isinstance(child, ttk.Spinbox):
                            child.configure(state='disabled')
            else:
                # 单独设置模式
                for widget in self.video_container.winfo_children():
                    for child in widget.winfo_children():
                        if isinstance(child, ttk.Spinbox):
                            child.configure(state='normal')

        def confirm(self):
            """确认设置"""
            mode = self.split_mode.get()

            # 更新视频数据
            if mode == "uniform":
                # 统一设置：所有视频使用相同的张数
                uniform_count = self.uniform_count.get()
                for video_var in self.video_vars:
                    video_var['var'].set(uniform_count)

            # 构建结果
            videos_result = []
            for video_var in self.video_vars:
                videos_result.append({
                    'path': video_var['path'],
                    'name': video_var['name'],
                    'frame_count': video_var['var'].get(),
                    'status': '等待'
                })

            self.result = {
                'split_mode': mode,
                'uniform_count': self.uniform_count.get() if mode == "uniform" else None,
                'videos': videos_result
            }

            self.destroy()

        def cancel(self):
            """取消设置"""
            self.result = None
            self.destroy()
def main():
    """主函数"""
    # 创建窗口 - 使用浅色主题
    root = ttk.Window(themename="flatly")

    # 创建应用
    app = VideoFrameExtractorApp(root)

    # 运行
    root.mainloop()


if __name__ == "__main__":
    main()
