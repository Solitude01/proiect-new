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
import random
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
    quality: int = 1


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

        # Trace ID 管理（防止trace累加）
        self._single_dir_path_trace_id = None
        self._single_dir_uniform_count_trace_id = None
        self._fangxinyu_path_trace_id = None
        self._fangxinyu_uniform_count_trace_id = None

        # 模式数据
        self.single_video_path = ttk.StringVar()
        self.single_output_path = ttk.StringVar()
        self.single_video_sub_dir = ttk.StringVar()
        self.single_total = ttk.IntVar(value=100)
        self.output_format = ttk.StringVar(value=self.config.output_format)

        self.single_dir_path = ttk.StringVar()
        self.single_dir_output = ttk.StringVar()
        self.single_dir_split_mode = ttk.StringVar(value="uniform")  # uniform / individual
        self.single_dir_uniform_count = ttk.IntVar(value=100)
        self.single_dir_videos: List[Dict] = []  # 存储视频数据

        # 方欣雨定制模式变量
        self.fangxinyu_split_mode = ttk.StringVar(value="uniform")
        self.fangxinyu_uniform_count = ttk.IntVar(value=100)

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
            try:
                if canvas.winfo_exists():
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except tk.TclError:
                pass
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
            },
            {
                'id': 'fangxinyu_custom',
                'icon': '✨',
                'title': '方欣雨定制专属',
                'desc': '每个视频可单独设置输出目录',
                'bootstyle': 'primary'
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
        elif mode == "fangxinyu_custom":
            self.create_fangxinyu_custom_ui()

    def clear_content(self):
        """清空内容区"""
        # 解绑鼠标滚轮事件，避免对已销毁控件的引用
        self.content_frame.unbind_all("<MouseWheel>")
        # 重置 trace ID，避免对已销毁变量的操作
        self._single_dir_path_trace_id = None
        self._single_dir_uniform_count_trace_id = None
        self._fangxinyu_path_trace_id = None
        self._fangxinyu_uniform_count_trace_id = None
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

        # 子目录名称
        sub_dir_frame = ttk.Frame(output_inner)
        sub_dir_frame.pack(fill=X, pady=(10, 0))

        ttk.Label(sub_dir_frame, text="子目录名称:").pack(side=LEFT)
        ttk.Entry(
            sub_dir_frame,
            textvariable=self.single_video_sub_dir,
            width=30
        ).pack(side=LEFT, padx=10)
        ttk.Button(
            sub_dir_frame,
            text="🎲 随机",
            command=self.random_single_sub_dir,
            bootstyle="outline",
            width=8
        ).pack(side=LEFT, padx=2)
        ttk.Label(
            sub_dir_frame,
            text="子目录将创建于输出目录下",
            bootstyle="secondary",
            font=('Segoe UI', 9)
        ).pack(side=LEFT, padx=(10, 0))

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

        # 视频列表 - 添加切分张数列和子目录名列
        list_frame = ttk.LabelFrame(content_frame, text="待处理视频")
        list_frame.pack(fill=BOTH, expand=True, pady=10)
        list_inner = ttk.Frame(list_frame)
        list_inner.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # 工具栏
        list_toolbar = ttk.Frame(list_inner)
        list_toolbar.pack(fill=X, pady=(0, 5))
        ttk.Button(
            list_toolbar,
            text="🎲 随机子目录名",
            command=self.random_all_single_dir_sub_dirs,
            bootstyle="outline"
        ).pack(side=LEFT, padx=2)

        # 使用Treeview显示视频列表 - 添加切分张数列和子目录名列
        columns = ('filename', 'size', 'frame_count', 'sub_dir')
        self.video_tree = ttk.Treeview(list_inner, columns=columns, show='headings', height=8)
        self.video_tree.heading('filename', text='文件名')
        self.video_tree.heading('size', text='大小')
        self.video_tree.heading('frame_count', text='切分张数')
        self.video_tree.heading('sub_dir', text='子目录名称')
        self.video_tree.column('filename', width=300)
        self.video_tree.column('size', width=80)
        self.video_tree.column('frame_count', width=80)
        self.video_tree.column('sub_dir', width=120)

        scrollbar = ttk.Scrollbar(list_inner, orient=VERTICAL, command=self.video_tree.yview)
        self.video_tree.configure(yscrollcommand=scrollbar.set)

        self.video_tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        # 双击编辑切分张数或子目录名称
        self.video_tree.bind('<Double-Button-1>', self.on_video_tree_double_click)

        # 存储视频数据
        self.single_dir_videos = []

        # 绑定目录变化更新列表 - 先移除旧的再添加新的
        if self._single_dir_path_trace_id:
            try:
                self.single_dir_path.trace_remove('write', self._single_dir_path_trace_id)
            except Exception:
                pass
        self._single_dir_path_trace_id = self.single_dir_path.trace_add('write', lambda *args: self.update_video_list())

        # 绑定统一设置张数变化更新列表 - 先移除旧的再添加新的
        if self._single_dir_uniform_count_trace_id:
            try:
                self.single_dir_uniform_count.trace_remove('write', self._single_dir_uniform_count_trace_id)
            except Exception:
                pass
        self._single_dir_uniform_count_trace_id = self.single_dir_uniform_count.trace_add('write', lambda *args: self.on_uniform_count_change())

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

    def create_fangxinyu_custom_ui(self):
        """创建方欣雨定制专属模式UI - 支持每个视频单独设置输出目录"""
        # 创建主滚动容器
        scroll_container = ttk.Frame(self.content_frame)
        scroll_container.pack(fill=BOTH, expand=True)

        # 创建可滚动区域
        content_frame, canvas = self.create_scrollable_frame(scroll_container)

        # 标题
        ttk.Label(
            content_frame,
            text="✨ 方欣雨定制专属",
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

        ttk.Label(out_entry_frame, text="默认输出目录:").pack(side=LEFT)
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
            text="提示: 可在视频列表中双击\"输出目录\"列为每个视频单独设置输出位置",
            bootstyle="secondary",
            font=('Segoe UI', 9)
        ).pack(anchor=W, pady=(5, 0))

        # 切分模式选择
        split_mode_frame = ttk.LabelFrame(content_frame, text="切分模式")
        split_mode_frame.pack(fill=X, pady=10)
        split_mode_inner = ttk.Frame(split_mode_frame)
        split_mode_inner.pack(fill=X, expand=True, padx=10, pady=10)

        mode_select_frame = ttk.Frame(split_mode_inner)
        mode_select_frame.pack(fill=X)

        ttk.Radiobutton(
            mode_select_frame,
            text="统一设置 (所有视频相同张数)",
            variable=self.fangxinyu_split_mode,
            value="uniform",
            command=self.on_fangxinyu_mode_change
        ).pack(side=LEFT, padx=10)

        ttk.Radiobutton(
            mode_select_frame,
            text="单独设置 (为每个视频指定张数)",
            variable=self.fangxinyu_split_mode,
            value="individual",
            command=self.on_fangxinyu_mode_change
        ).pack(side=LEFT, padx=10)

        # 统一设置时的全局设置
        self.fangxinyu_uniform_frame = ttk.Frame(split_mode_inner)
        self.fangxinyu_uniform_frame.pack(fill=X, pady=(10, 0))

        ttk.Label(self.fangxinyu_uniform_frame, text="切分张数:").pack(side=LEFT, padx=(20, 5))
        ttk.Spinbox(
            self.fangxinyu_uniform_frame,
            from_=1,
            to=1000,
            textvariable=self.fangxinyu_uniform_count,
            width=10
        ).pack(side=LEFT)

        # 快捷按钮
        quick_frame = ttk.Frame(self.fangxinyu_uniform_frame)
        quick_frame.pack(side=LEFT, padx=(20, 0))
        for num in [50, 100, 150, 200]:
            ttk.Button(
                quick_frame,
                text=str(num),
                width=4,
                command=lambda n=num: self.fangxinyu_uniform_count.set(n),
                bootstyle="outline"
            ).pack(side=LEFT, padx=2)

        # 视频列表 - 方欣雨定制专属：增加输出目录列
        list_frame = ttk.LabelFrame(content_frame, text="待处理视频")
        list_frame.pack(fill=BOTH, expand=True, pady=10)
        list_inner = ttk.Frame(list_frame)
        list_inner.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # 工具栏
        list_toolbar = ttk.Frame(list_inner)
        list_toolbar.pack(fill=X, pady=(0, 5))

        ttk.Button(
            list_toolbar,
            text="🎲 随机子目录名",
            command=self.random_fangxinyu_sub_dirs,
            bootstyle="outline"
        ).pack(side=LEFT, padx=2)

        ttk.Button(
            list_toolbar,
            text="📁 统一输出目录",
            command=self.set_unified_output_for_all,
            bootstyle="info-outline"
        ).pack(side=LEFT, padx=2)

        # 使用Treeview显示视频列表 - 5列：文件名、大小、切分张数、子目录、输出目录
        columns = ('filename', 'size', 'frame_count', 'sub_dir', 'output')
        self.fangxinyu_video_tree = ttk.Treeview(list_inner, columns=columns, show='headings', height=8)
        self.fangxinyu_video_tree.heading('filename', text='文件名')
        self.fangxinyu_video_tree.heading('size', text='大小')
        self.fangxinyu_video_tree.heading('frame_count', text='切分张数')
        self.fangxinyu_video_tree.heading('sub_dir', text='子目录')
        self.fangxinyu_video_tree.heading('output', text='输出目录')
        self.fangxinyu_video_tree.column('filename', width=180)
        self.fangxinyu_video_tree.column('size', width=60)
        self.fangxinyu_video_tree.column('frame_count', width=70)
        self.fangxinyu_video_tree.column('sub_dir', width=100)
        self.fangxinyu_video_tree.column('output', width=200)

        scrollbar = ttk.Scrollbar(list_inner, orient=VERTICAL, command=self.fangxinyu_video_tree.yview)
        self.fangxinyu_video_tree.configure(yscrollcommand=scrollbar.set)

        self.fangxinyu_video_tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        # 双击编辑
        self.fangxinyu_video_tree.bind('<Double-Button-1>', self.on_fangxinyu_video_double_click)

        # 存储视频数据
        self.fangxinyu_videos = []

        # 绑定目录变化更新列表 - 先移除旧的再添加新的
        if self._fangxinyu_path_trace_id:
            try:
                self.single_dir_path.trace_remove('write', self._fangxinyu_path_trace_id)
            except Exception:
                pass
        self._fangxinyu_path_trace_id = self.single_dir_path.trace_add('write', lambda *args: self.update_fangxinyu_video_list())

        # 绑定统一设置张数变化更新列表 - 先移除旧的再添加新的
        if self._fangxinyu_uniform_count_trace_id:
            try:
                self.fangxinyu_uniform_count.trace_remove('write', self._fangxinyu_uniform_count_trace_id)
            except Exception:
                pass
        self._fangxinyu_uniform_count_trace_id = self.fangxinyu_uniform_count.trace_add('write', lambda *args: self.on_fangxinyu_uniform_count_change())

        # 执行按钮
        btn_frame = ttk.Frame(content_frame)
        btn_frame.pack(fill=X, pady=20)

        self.fangxinyu_start_btn = ttk.Button(
            btn_frame,
            text="🚀 开始切分",
            command=self.start_fangxinyu_directory,
            bootstyle="success",
            width=20
        )
        self.fangxinyu_start_btn.pack(pady=10)

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
        self.fangxinyu_log_text = self.create_log_viewer(content_frame, height=8)

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

        ttk.Button(
            toolbar,
            text="🎲 随机子目录名",
            command=self.random_multi_sub_dirs,
            bootstyle="info-outline"
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

        # 目录列表 - 新列顺序: path, videos, frame_count, sub_dir, output, status
        columns = ('path', 'videos', 'frame_count', 'sub_dir', 'output', 'status')
        self.multi_tree = ttk.Treeview(list_inner, columns=columns, show='headings', height=10)
        self.multi_tree.heading('path', text='目录路径')
        self.multi_tree.heading('videos', text='视频数')
        self.multi_tree.heading('frame_count', text='切分张数')
        self.multi_tree.heading('sub_dir', text='子目录命名')
        self.multi_tree.heading('output', text='输出路径')
        self.multi_tree.heading('status', text='状态')
        self.multi_tree.column('path', width=200, minwidth=150, stretch=True)
        self.multi_tree.column('videos', width=60, minwidth=60, stretch=False)
        self.multi_tree.column('frame_count', width=80, minwidth=80, stretch=False)
        self.multi_tree.column('sub_dir', width=120, minwidth=100, stretch=False)
        self.multi_tree.column('output', width=150, minwidth=100, stretch=True)
        self.multi_tree.column('status', width=60, minwidth=60, stretch=False)

        scrollbar = ttk.Scrollbar(list_inner, orient=VERTICAL, command=self.multi_tree.yview)
        self.multi_tree.configure(yscrollcommand=scrollbar.set)

        # 水平滚动条
        h_scrollbar = ttk.Scrollbar(list_inner, orient=HORIZONTAL, command=self.multi_tree.xview)
        self.multi_tree.configure(xscrollcommand=h_scrollbar.set)

        self.multi_tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)
        h_scrollbar.pack(side=BOTTOM, fill=X)

        # 双击处理
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
            # 自动设置子目录名称
            self.single_video_sub_dir.set(Path(path).stem)

    def select_output_dir(self):
        """选择输出目录"""
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.single_output_path.set(path)

    def select_input_directory(self):
        """选择输入目录"""
        path = filedialog.askdirectory(title="选择包含视频的目录")
        if path:
            # 先设置输出目录，再设置输入目录（避免trace触发时输出目录还未设置）
            default_output = os.path.join(path, "切分图片")
            self.single_dir_output.set(default_output)
            self.single_dir_path.set(path)

    def select_dir_output(self):
        """选择目录输出路径"""
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.single_dir_output.set(path)
            # 同步更新方欣雨定制专属模式的视频输出目录
            if hasattr(self, 'fangxinyu_videos') and self.fangxinyu_videos:
                for video_data in self.fangxinyu_videos:
                    video_data['output_dir'] = path
                for i, item_id in enumerate(self.fangxinyu_video_tree.get_children()):
                    if i < len(self.fangxinyu_videos):
                        values = self.fangxinyu_video_tree.item(item_id, 'values')
                        display_output = self._truncate_path(path, 25)
                        self.fangxinyu_video_tree.item(item_id, values=(
                            values[0], values[1], values[2], values[3], display_output
                        ))

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
                'frame_count': default_count,
                'sub_dir_name': Path(video).stem
            }
            self.single_dir_videos.append(video_data)

            self.video_tree.insert('', 'end', values=(filename, size_str, default_count, Path(video).stem))

    def update_fangxinyu_video_list(self):
        """更新方欣雨定制专属模式的视频列表 - 包含单独输出目录"""
        directory = self.single_dir_path.get()
        if not directory or not os.path.exists(directory):
            # 清空列表和数据
            for item in self.fangxinyu_video_tree.get_children():
                self.fangxinyu_video_tree.delete(item)
            self.fangxinyu_videos = []
            return

        # 清空列表
        for item in self.fangxinyu_video_tree.get_children():
            self.fangxinyu_video_tree.delete(item)

        # 扫描视频
        videos = self.extractor.scan_videos(directory, recursive=False)
        self.fangxinyu_videos = []

        # 获取默认输出目录
        default_output = self.single_dir_output.get()

        for video in videos:
            filename = os.path.basename(video)
            size = os.path.getsize(video)
            size_str = self.format_size(size)

            # 根据当前模式确定默认值
            if self.fangxinyu_split_mode.get() == "uniform":
                default_count = self.fangxinyu_uniform_count.get()
            else:
                default_count = 100

            # 创建视频数据项 - 包含单独输出目录
            video_data = {
                'path': video,
                'name': filename,
                'size': size,
                'frame_count': default_count,
                'sub_dir_name': Path(video).stem,
                'output_dir': default_output  # 默认使用全局输出目录
            }
            self.fangxinyu_videos.append(video_data)

            # 截断输出目录用于显示
            display_output = self._truncate_path(default_output, 25)
            self.fangxinyu_video_tree.insert('', 'end', values=(filename, size_str, default_count, Path(video).stem, display_output))

    def _set_widget_state_recursive(self, parent, state):
        """递归设置控件状态"""
        for widget in parent.winfo_children():
            if isinstance(widget, (ttk.Spinbox, ttk.Button, ttk.Entry)):
                widget.configure(state=state)
            # 递归处理子容器
            if widget.winfo_children():
                self._set_widget_state_recursive(widget, state)

    def on_single_dir_mode_change(self):
        """单目录模式改变时更新UI"""
        mode = self.single_dir_split_mode.get()

        if mode == "uniform":
            # 统一设置模式：启用全局设置，禁用列表编辑
            self._set_widget_state_recursive(self.uniform_settings_frame, 'normal')
            # 更新列表显示为统一值
            self.update_video_list_display()
        else:
            # 单独设置模式：允许编辑列表，禁用统一设置控件
            self._set_widget_state_recursive(self.uniform_settings_frame, 'disabled')

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
                self.video_tree.item(item_id, values=(values[0], values[1], uniform_count, values[3]))

    def on_uniform_count_change(self):
        """统一设置张数改变时更新视频列表"""
        if self.single_dir_split_mode.get() == "uniform":
            self.update_video_list_display()

    def on_video_tree_double_click(self, event=None):
        """双击视频列表编辑切分张数或子目录名称"""
        selected = self.video_tree.selection()
        if not selected:
            return

        index = self.video_tree.index(selected[0])
        if index < 0 or index >= len(self.single_dir_videos):
            return

        # 获取点击的列
        column = self.video_tree.identify_column(event.x)

        if column == '#3':
            # 编辑切分张数
            if self.single_dir_split_mode.get() == "uniform":
                return  # 统一设置模式下不允许单独编辑

            current_value = self.single_dir_videos[index]['frame_count']
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
                self.single_dir_videos[index]['frame_count'] = new_value
                values = self.video_tree.item(selected[0], 'values')
                self.video_tree.item(selected[0], values=(values[0], values[1], new_value, values[3]))

        elif column == '#4':
            # 编辑子目录名称
            current_value = self.single_dir_videos[index]['sub_dir_name']
            from tkinter.simpledialog import askstring
            new_value = askstring(
                "设置子目录名称",
                f"设置 '{self.single_dir_videos[index]['name']}' 的子目录名称:",
                initialvalue=current_value,
                parent=self.root
            )

            if new_value is not None:
                new_value = new_value.strip()
                if new_value:
                    self.single_dir_videos[index]['sub_dir_name'] = new_value
                    values = self.video_tree.item(selected[0], 'values')
                    self.video_tree.item(selected[0], values=(values[0], values[1], values[2], new_value))

    def on_fangxinyu_video_double_click(self, event=None):
        """方欣雨定制专属模式 - 双击视频列表处理"""
        from tkinter.simpledialog import askinteger, askstring

        selected = self.fangxinyu_video_tree.selection()
        if not selected:
            return

        index = self.fangxinyu_video_tree.index(selected[0])
        if index < 0 or index >= len(self.fangxinyu_videos):
            return

        # 获取点击的列
        column = self.fangxinyu_video_tree.identify_column(event.x)
        video_name = self.fangxinyu_videos[index]['name']

        if column == '#3':
            # 编辑切分张数
            if self.fangxinyu_split_mode.get() == "uniform":
                return  # 统一设置模式下不允许单独编辑

            current_value = self.fangxinyu_videos[index]['frame_count']
            new_value = askinteger(
                "设置切分张数",
                f"设置 '{video_name}' 的切分张数:",
                initialvalue=current_value,
                minvalue=1,
                maxvalue=1000,
                parent=self.root
            )

            if new_value is not None:
                self.fangxinyu_videos[index]['frame_count'] = new_value
                values = self.fangxinyu_video_tree.item(selected[0], 'values')
                self.fangxinyu_video_tree.item(selected[0], values=(values[0], values[1], new_value, values[3], values[4]))

        elif column == '#4':
            # 编辑子目录名称
            current_value = self.fangxinyu_videos[index]['sub_dir_name']
            new_value = askstring(
                "设置子目录名称",
                f"设置 '{video_name}' 的子目录名称:",
                initialvalue=current_value,
                parent=self.root
            )

            if new_value is not None:
                new_value = new_value.strip()
                if new_value:
                    self.fangxinyu_videos[index]['sub_dir_name'] = new_value
                    values = self.fangxinyu_video_tree.item(selected[0], 'values')
                    self.fangxinyu_video_tree.item(selected[0], values=(values[0], values[1], values[2], new_value, values[4]))

        elif column == '#5':
            # 编辑输出目录 - 方欣雨定制专属特性
            current_value = self.fangxinyu_videos[index]['output_dir']
            new_value = filedialog.askdirectory(
                title=f"选择 '{video_name}' 的输出目录",
                initialdir=current_value if current_value else self.single_dir_output.get(),
                parent=self.root
            )

            if new_value:
                self.fangxinyu_videos[index]['output_dir'] = new_value
                values = self.fangxinyu_video_tree.item(selected[0], 'values')
                # 截断路径用于显示
                display_path = self._truncate_path(new_value, 25)
                self.fangxinyu_video_tree.item(selected[0], values=(values[0], values[1], values[2], values[3], display_path))

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
                    'sub_dir_name': Path(video_path).stem,
                    'status': '等待'
                })

            dir_item = {
                'path': path,
                'output': default_output,
                'videos': videos_data,
                'video_count': len(videos_data),
                'status': '等待'
            }
            self.multi_dirs.append(dir_item)
            # 新列顺序: path, videos, frame_count, sub_dir, output, status
            first_sub_dir = videos_data[0]['sub_dir_name'] if videos_data else ''
            self.multi_tree.insert('', 'end', values=(
                path, len(videos_data), default_count, first_sub_dir, default_output, '等待'
            ))
            added_count += 1

        if added_count > 0:
            messagebox.showinfo("提示", f"成功添加 {added_count} 个目录")

    def on_multi_dir_double_click(self, event=None):
        """双击目录列表处理 - 根据点击列执行不同操作"""
        selected = self.multi_tree.selection()
        if not selected:
            return

        index = self.multi_tree.index(selected[0])
        if index < 0 or index >= len(self.multi_dirs):
            return

        # 获取点击的列
        column = self.multi_tree.identify_column(event.x)

        if column == '#1':  # path 列 - 打开视频预览窗口
            self.show_video_preview(index)
        elif column == '#3':  # frame_count 列 - 编辑切分张数
            self.edit_dir_frame_count(index)
        elif column == '#4':  # sub_dir 列 - 编辑子目录名称
            self.edit_dir_sub_dir(index)

    def edit_dir_frame_count(self, dir_index):
        """编辑目录下所有视频的切分张数"""
        from tkinter.simpledialog import askinteger
        dir_item = self.multi_dirs[dir_index]

        # 获取当前值（使用第一个视频的值作为默认）
        current = dir_item['videos'][0]['frame_count'] if dir_item['videos'] else 100

        new_val = askinteger(
            "设置切分张数",
            f"设置 '{os.path.basename(dir_item['path'])}' 下所有视频的切分张数:",
            initialvalue=current,
            minvalue=1,
            maxvalue=1000,
            parent=self.root
        )

        if new_val:
            # 更新该目录下所有视频的 frame_count
            for video in dir_item['videos']:
                video['frame_count'] = new_val

            # 更新 Treeview 显示
            self.update_multi_dir_display(dir_index)

    def edit_dir_sub_dir(self, dir_index):
        """编辑目录下所有视频的子目录名称"""
        from tkinter.simpledialog import askstring
        dir_item = self.multi_dirs[dir_index]

        # 获取当前值
        current = dir_item['videos'][0]['sub_dir_name'] if dir_item['videos'] else ''

        new_val = askstring(
            "设置子目录名称",
            f"设置 '{os.path.basename(dir_item['path'])}' 下所有视频的子目录名称:\n" +
            "使用 {name} 表示原视频文件名",
            initialvalue=current,
            parent=self.root
        )

        if new_val and new_val.strip():
            new_val = new_val.strip()
            # 更新该目录下所有视频的 sub_dir_name
            for video in dir_item['videos']:
                # 替换模板
                sub_dir = new_val.replace('{name}', Path(video['name']).stem)
                video['sub_dir_name'] = sub_dir

            # 更新 Treeview 显示
            self.update_multi_dir_display(dir_index)

    def remove_selected_dir(self):
        """删除选中的目录"""
        selected = self.multi_tree.selection()
        if not selected:
            return

        # 逆序遍历，避免索引错位
        for item in reversed(selected):
            index = self.multi_tree.index(item)
            if 0 <= index < len(self.multi_dirs):
                self.multi_dirs.pop(index)
                self.multi_tree.delete(item)

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

        # 更新所有目录下所有视频的 frame_count
        for dir_item in self.multi_dirs:
            for video in dir_item.get('videos', []):
                video['frame_count'] = global_count

        # 更新Treeview显示
        for i, item_id in enumerate(self.multi_tree.get_children()):
            if i < len(self.multi_dirs):
                self.update_multi_dir_display(i)

        messagebox.showinfo("提示", f"已将切分张数 {global_count} 应用到所有目录")

    def update_mode_ui(self):
        """更新模式UI - 简化为总数模式"""
        # FPS模式已移除，只保留总数模式
        pass

    def set_total(self, num: int):
        """设置总数"""
        self.single_total.set(num)

    def random_single_sub_dir(self):
        """单视频子目录随机名称"""
        self.single_video_sub_dir.set(f"{random.randint(0, 9999):04d}")

    def random_all_single_dir_sub_dirs(self):
        """单目录模式批量随机子目录名称"""
        for video_data in self.single_dir_videos:
            video_data['sub_dir_name'] = f"{random.randint(0, 9999):04d}"

        for i, item_id in enumerate(self.video_tree.get_children()):
            values = self.video_tree.item(item_id, 'values')
            if i < len(self.single_dir_videos):
                self.video_tree.item(item_id, values=(values[0], values[1], values[2], self.single_dir_videos[i]['sub_dir_name']))

    def random_multi_sub_dirs(self):
        """多目录模式批量随机子目录名称"""
        selected = self.multi_tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择目录")
            return

        for item in selected:
            index = self.multi_tree.index(item)
            if index < len(self.multi_dirs):
                dir_item = self.multi_dirs[index]
                for video in dir_item['videos']:
                    video['sub_dir_name'] = f"{random.randint(0, 9999):04d}"
                # 更新显示
                self.update_multi_dir_display(index)

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
        video_output = ""  # 用于异常处理时传递给回调
        try:
            def progress_callback(progress, message):
                self.root.after(0, lambda: self._update_progress(progress, message))
                self.root.after(0, lambda m=message: self.log_message(self.single_log_text, m))

            # 构建子目录
            sub_dir = self.single_video_sub_dir.get() or Path(video_path).stem
            video_output = os.path.join(output_dir, sub_dir)
            os.makedirs(video_output, exist_ok=True)

            self.root.after(0, lambda: self.log_message(self.single_log_text, f"开始处理: {video_path}"))
            self.root.after(0, lambda: self.log_message(self.single_log_text, f"输出目录: {video_output}"))
            self.root.after(0, lambda: self.log_message(self.single_log_text, f"切分张数: {config.total_value}, 格式: {config.output_format}"))

            success, msg = self.extractor.extract_frames(
                video_path, video_output, config,
                progress_callback, self.stop_event
            )

            self.root.after(0, lambda: self.log_message(self.single_log_text, f"处理结果: {msg}"))
            self.root.after(0, lambda: self._on_process_complete(success, msg, video_output))
        except Exception as e:
            error_msg = str(e)
            self.root.after(0, lambda: self.log_message(self.single_log_text, f"错误: {error_msg}"))
            self.root.after(0, lambda: self._on_process_complete(False, error_msg, video_output))

    def _update_progress(self, progress: float, message: str):
        """更新进度"""
        self.progress_var.set(progress)
        self.status_label.configure(text=f"处理中... {progress:.1f}%")
        self.current_file_label.configure(text=message)

    def _on_process_complete(self, success: bool, message: str, video_output: str = ""):
        """处理完成"""
        self.is_processing = False
        if self.start_btn.winfo_exists():
            self.start_btn.configure(state='normal', text='🚀 开始切分')

        if success:
            self.progress_var.set(100)
            if self.status_label.winfo_exists():
                self.status_label.configure(text=f"✅ {message}")
            if messagebox.askyesno("完成", f"{message}\n\n是否打开输出文件夹？"):
                # 使用实际的视频输出目录
                output_path = video_output if video_output else self.single_output_path.get()
                if output_path:
                    if not os.path.exists(output_path):
                        os.makedirs(output_path, exist_ok=True)
                    if os.path.exists(output_path):
                        os.startfile(output_path)
        else:
            if self.status_label.winfo_exists():
                self.status_label.configure(text=f"❌ {message}")
            messagebox.showerror("错误", message)

    def start_single_directory(self):
        """开始单目录处理"""
        # 重置停止事件
        self.stop_event.clear()

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

        # 使用已缓存的视频列表，避免重新扫描导致索引错位
        if not self.single_dir_videos:
            messagebox.showwarning("提示", "所选目录中没有找到视频文件")
            return

        videos = [v['path'] for v in self.single_dir_videos]

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
            video_data = self.single_dir_videos[idx] if idx < len(self.single_dir_videos) else None
            sub_dir = video_data['sub_dir_name'] if video_data else video_name
            video_output = os.path.join(base_output, sub_dir)
            os.makedirs(video_output, exist_ok=True)

            self.root.after(0, lambda v=video_name, i=idx, t=total_videos: self.status_label.configure(
                text=f"处理中... ({i+1}/{t}) {v}"
            ))
            self.root.after(0, lambda v=video_name, s=sub_dir: self.log_message(self.dir_log_text, f"处理: {v} -> {s}"))

            def progress_callback(progress, message, _idx=idx):
                overall = (_idx + progress/100) / total_videos * 100
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
        if self.dir_start_btn.winfo_exists():
            self.dir_start_btn.configure(state='normal', text='🚀 开始切分')
        self.progress_var.set(100)
        if self.status_label.winfo_exists():
            self.status_label.configure(text=f"✅ 完成！共提取 {total_frames} 帧")

        if messagebox.askyesno("完成", f"处理完成！共提取 {total_frames} 帧\n\n是否打开输出文件夹？"):
            default_output = self.single_dir_output.get()
            if default_output and not os.path.exists(default_output):
                os.makedirs(default_output, exist_ok=True)
            if default_output and os.path.exists(default_output):
                os.startfile(default_output)

    def on_fangxinyu_mode_change(self):
        """方欣雨定制专属模式 - 模式改变时更新UI"""
        mode = self.fangxinyu_split_mode.get()

        if mode == "uniform":
            # 统一设置模式：启用全局设置
            self._set_widget_state_recursive(self.fangxinyu_uniform_frame, 'normal')
            # 更新列表显示为统一值
            self.update_fangxinyu_video_list_display()
        else:
            # 单独设置模式
            self._set_widget_state_recursive(self.fangxinyu_uniform_frame, 'disabled')

    def on_fangxinyu_uniform_count_change(self):
        """方欣雨定制专属模式 - 统一设置张数改变时更新视频列表"""
        if self.fangxinyu_split_mode.get() == "uniform":
            self.update_fangxinyu_video_list_display()

    def update_fangxinyu_video_list_display(self):
        """方欣雨定制专属模式 - 根据当前模式更新视频列表显示"""
        if self.fangxinyu_split_mode.get() == "uniform":
            uniform_count = self.fangxinyu_uniform_count.get()
            # 更新所有视频的frame_count
            for video_data in self.fangxinyu_videos:
                video_data['frame_count'] = uniform_count

            # 更新Treeview显示
            for i, item_id in enumerate(self.fangxinyu_video_tree.get_children()):
                values = self.fangxinyu_video_tree.item(item_id, 'values')
                display_output = self._truncate_path(self.fangxinyu_videos[i]['output_dir'], 25)
                self.fangxinyu_video_tree.item(item_id, values=(values[0], values[1], uniform_count, values[3], display_output))

    def random_fangxinyu_sub_dirs(self):
        """方欣雨定制专属模式 - 批量随机子目录名称"""
        for video_data in self.fangxinyu_videos:
            video_data['sub_dir_name'] = f"{random.randint(0, 9999):04d}"

        for i, item_id in enumerate(self.fangxinyu_video_tree.get_children()):
            values = self.fangxinyu_video_tree.item(item_id, 'values')
            if i < len(self.fangxinyu_videos):
                display_output = self._truncate_path(self.fangxinyu_videos[i]['output_dir'], 25)
                self.fangxinyu_video_tree.item(item_id, values=(values[0], values[1], values[2], self.fangxinyu_videos[i]['sub_dir_name'], display_output))

    def set_unified_output_for_all(self):
        """方欣雨定制专属模式 - 统一设置所有视频的输出目录"""
        new_output = filedialog.askdirectory(
            title="选择统一输出目录",
            initialdir=self.single_dir_output.get(),
            parent=self.root
        )

        if new_output:
            self.single_dir_output.set(new_output)
            # 更新所有视频的 output_dir
            for video_data in self.fangxinyu_videos:
                video_data['output_dir'] = new_output

            # 更新Treeview显示
            for i, item_id in enumerate(self.fangxinyu_video_tree.get_children()):
                values = self.fangxinyu_video_tree.item(item_id, 'values')
                display_output = self._truncate_path(new_output, 25)
                self.fangxinyu_video_tree.item(item_id, values=(values[0], values[1], values[2], values[3], display_output))

            messagebox.showinfo("提示", f"已将所有视频的输出目录设置为:\n{new_output}")

    def _truncate_path(self, path, max_len=30):
        """截断路径用于显示"""
        if len(path) <= max_len:
            return path
        return "..." + path[-(max_len-3):]

    def start_fangxinyu_directory(self):
        """方欣雨定制专属模式 - 开始处理"""
        if not self.ffmpeg_available:
            messagebox.showerror("错误", "未检测到FFmpeg")
            return

        directory = self.single_dir_path.get()
        if not directory:
            messagebox.showerror("错误", "请选择输入目录")
            return

        default_output = self.single_dir_output.get()
        if not default_output:
            messagebox.showerror("错误", "请选择默认输出目录")
            return

        # 使用已缓存的视频列表，避免重新扫描导致索引错位
        if not self.fangxinyu_videos:
            messagebox.showwarning("提示", "所选目录中没有找到视频文件")
            return

        videos = [v['path'] for v in self.fangxinyu_videos]

        # 禁用按钮
        self.fangxinyu_start_btn.configure(state='disabled', text='⏳ 处理中...')
        self.is_processing = True

        # 启动处理
        thread = threading.Thread(
            target=self._process_fangxinyu_directory,
            args=(videos, default_output),
            daemon=True
        )
        thread.start()

    def _process_fangxinyu_directory(self, videos: List[str], default_output: str):
        """方欣雨定制专属模式 - 处理目录（支持每个视频单独设置输出目录）"""
        self.root.after(0, lambda: self.log_message(self.fangxinyu_log_text, f"[方欣雨定制专属] 开始处理目录，共 {len(videos)} 个视频"))

        total_videos = len(videos)
        total_frames = 0

        for idx, video in enumerate(videos):
            if self.stop_event.is_set():
                self.root.after(0, lambda: self.log_message(self.fangxinyu_log_text, "用户取消处理"))
                break

            # 获取视频数据
            video_data = self.fangxinyu_videos[idx] if idx < len(self.fangxinyu_videos) else None

            # 获取该视频的输出目录（优先使用单独设置，否则使用默认）
            video_output_dir = video_data.get('output_dir') if video_data else default_output
            sub_dir = video_data.get('sub_dir_name', Path(video).stem) if video_data else Path(video).stem

            # 构建完整输出路径
            video_output = os.path.join(video_output_dir, sub_dir)
            os.makedirs(video_output, exist_ok=True)

            video_name = Path(video).stem
            self.root.after(0, lambda v=video_name, i=idx, t=total_videos: self.status_label.configure(
                text=f"处理中... ({i+1}/{t}) {v}"
            ))
            self.root.after(0, lambda v=video_name, o=video_output_dir: self.log_message(self.fangxinyu_log_text, f"处理: {v} -> {o}/{sub_dir}"))

            def progress_callback(progress, message, _idx=idx):
                overall = (_idx + progress/100) / total_videos * 100
                self.root.after(0, lambda p=overall: self.progress_var.set(p))

            # 使用当前视频的配置
            frame_count = video_data.get('frame_count', 100) if video_data else 100
            video_config = ExtractConfig(
                total_value=frame_count,
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
                self.root.after(0, lambda m=msg: self.log_message(self.fangxinyu_log_text, f"成功: {m}"))
            else:
                self.root.after(0, lambda m=msg: self.log_message(self.fangxinyu_log_text, f"失败: {m}"))

        self.root.after(0, lambda: self.log_message(self.fangxinyu_log_text, f"处理完成，共提取 {total_frames} 帧"))
        self.root.after(0, lambda: self._on_fangxinyu_complete(total_frames))

    def _on_fangxinyu_complete(self, total_frames: int):
        """方欣雨定制专属模式 - 处理完成"""
        self.is_processing = False
        if self.fangxinyu_start_btn.winfo_exists():
            self.fangxinyu_start_btn.configure(state='normal', text='🚀 开始切分')
        self.progress_var.set(100)
        if self.status_label.winfo_exists():
            self.status_label.configure(text=f"✅ 完成！共提取 {total_frames} 帧")

        if messagebox.askyesno("完成", f"处理完成！共提取 {total_frames} 帧\n\n是否打开默认输出文件夹？"):
            default_output = self.single_dir_output.get()
            if default_output and not os.path.exists(default_output):
                os.makedirs(default_output, exist_ok=True)
            if default_output and os.path.exists(default_output):
                os.startfile(default_output)

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

        # 重置处理器前先停止旧的
        if hasattr(self, 'processor') and self.processor:
            self.processor.stop()

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

            for video in videos:
                video_path = video.get('path', '')
                video_name = video.get('name', '')
                if not video_path:
                    continue

                # 直接使用视频的 frame_count，如果不存在则使用全局 single_total
                frame_count = video.get('frame_count') or self.single_total.get()

                # 创建该视频的配置
                config = ExtractConfig(
                    total_value=frame_count,
                    output_format=self.output_format.get()
                )

                sub_dir = video.get('sub_dir_name', '') or Path(video_name).stem
                video_output = os.path.join(dir_item['output'], sub_dir)

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

    def _update_multi_status_safe(self, completed, errors, total):
        """安全更新多目录状态标签"""
        if self.multi_status_label.winfo_exists():
            self.multi_status_label.configure(
                text=f"处理中... 完成: {completed} 失败: {errors} / 总计: {total}"
            )

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
                    self.root.after(0, lambda c=completed, e=errors, t=total_tasks: self._update_multi_status_safe(c, e, t))
            except queue.Empty:
                if not self.is_processing:
                    break

        self.root.after(0, lambda: self.log_message(self.multi_log_text, f"批量处理完成！成功: {completed}, 失败: {errors}"))
        self.root.after(0, lambda: self._on_multi_complete(completed, errors))

    def _on_multi_complete(self, completed: int, errors: int):
        """多目录处理完成"""
        self.is_processing = False

        # 停止处理器
        if hasattr(self, 'processor') and self.processor:
            self.processor.stop()

        if self.multi_start_btn.winfo_exists():
            self.multi_start_btn.configure(state='normal', text='🚀 开始并发切分')
        self.multi_progress_var.set(100)
        if self.multi_status_label.winfo_exists():
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
        """UI更新循环 - 保留定时器以维持UI更新"""
        # 注意：各模式自行处理消息队列，避免消息被窃取
        self.root.after(50, self.process_ui_queue)

    # ========================================================================
    # 视频列表预览窗口
    # ========================================================================
    def show_video_preview(self, dir_index):
        """显示视频列表预览窗口"""
        from tkinter.simpledialog import askinteger, askstring
        dir_item = self.multi_dirs[dir_index]

        # 创建新窗口
        preview_window = tk.Toplevel(self.root)
        preview_window.title(f"视频列表 - {os.path.basename(dir_item['path'])}")
        preview_window.geometry("600x400")
        preview_window.transient(self.root)

        # 视频列表 Treeview
        columns = ('name', 'frame_count', 'sub_dir')
        tree = ttk.Treeview(preview_window, columns=columns, show='headings', height=10)
        tree.heading('name', text='视频名称')
        tree.heading('frame_count', text='切分张数')
        tree.heading('sub_dir', text='子目录名称')
        tree.column('name', width=250)
        tree.column('frame_count', width=80)
        tree.column('sub_dir', width=150)

        # 插入数据
        for i, video in enumerate(dir_item['videos']):
            tree.insert('', 'end', iid=str(i), values=(
                video['name'],
                video['frame_count'],
                video['sub_dir_name']
            ))

        tree.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # 双击编辑
        def on_edit(event):
            if not tree.selection():
                return
            item = tree.selection()[0]
            col = tree.identify_column(event.x)
            video_idx = int(item)

            if col == '#2':  # frame_count
                current = dir_item['videos'][video_idx]['frame_count']
                new_val = askinteger("设置切分张数", "切分张数:", initialvalue=current, minvalue=1, parent=preview_window)
                if new_val:
                    dir_item['videos'][video_idx]['frame_count'] = new_val
                    tree.item(item, values=(
                        dir_item['videos'][video_idx]['name'],
                        new_val,
                        dir_item['videos'][video_idx]['sub_dir_name']
                    ))
                    # 更新主列表显示
                    self.update_multi_dir_display(dir_index)
            elif col == '#3':  # sub_dir
                current = dir_item['videos'][video_idx]['sub_dir_name']
                new_val = askstring("设置子目录", "子目录名称:", initialvalue=current, parent=preview_window)
                if new_val and new_val.strip():
                    dir_item['videos'][video_idx]['sub_dir_name'] = new_val.strip()
                    tree.item(item, values=(
                        dir_item['videos'][video_idx]['name'],
                        dir_item['videos'][video_idx]['frame_count'],
                        new_val.strip()
                    ))
                    # 更新主列表显示
                    self.update_multi_dir_display(dir_index)

        tree.bind('<Double-Button-1>', on_edit)

        # 关闭按钮
        ttk.Button(preview_window, text="关闭", command=preview_window.destroy).pack(pady=10)

    def update_multi_dir_display(self, dir_index):
        """更新目录在multi_tree中的显示"""
        if dir_index < 0 or dir_index >= len(self.multi_dirs):
            return
        dir_item = self.multi_dirs[dir_index]
        item_id = self.multi_tree.get_children()[dir_index]

        # 计算显示的张数（如果所有视频相同则显示该值，否则显示"混合"）
        frame_counts = [v['frame_count'] for v in dir_item['videos']]
        if len(set(frame_counts)) == 1:
            frame_text = str(frame_counts[0])
        else:
            frame_text = f"{min(frame_counts)}-{max(frame_counts)}"

        # 子目录显示（第一个视频的，或"多个"）
        sub_dirs = [v['sub_dir_name'] for v in dir_item['videos']]
        if len(set(sub_dirs)) == 1:
            sub_dir_text = sub_dirs[0]
        else:
            sub_dir_text = "多个"

        self.multi_tree.item(item_id, values=(
            dir_item['path'],
            dir_item['video_count'],
            frame_text,
            sub_dir_text,
            dir_item['output'],
            dir_item['status']
        ))
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
