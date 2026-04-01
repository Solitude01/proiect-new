#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频帧提取工具 v3.2 - 紧凑布局设计
优化空间利用，提高信息密度
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import subprocess
import sys
import threading
from datetime import datetime
import random


class CompactVideoFrameExtractor:
    def __init__(self, root):
        self.root = root
        self.root.title("视频帧提取工具")
        self.root.geometry("720x600")
        self.root.minsize(800, 550)
        self.root.configure(bg="#f0f0f0")

        # 紧凑配色方案
        self.colors = {
            'bg_main': '#f0f0f0',
            'bg_header': '#1a1a2e',
            'bg_card': '#ffffff',
            'bg_button': '#e5e7eb',
            'primary': '#4361ee',
            'primary_hover': '#3651d4',
            'success': '#10b981',
            'warning': '#f59e0b',
            'error': '#ef4444',
            'text_primary': '#1a1a2e',
            'text_secondary': '#6b7280',
            'border': '#d1d5db',
        }

        # 紧凑字体
        self.fonts = {
            'title': ("Microsoft YaHei UI", 14, "bold"),
            'subtitle': ("Microsoft YaHei UI", 8),
            'section': ("Microsoft YaHei UI", 9, "bold"),
            'body': ("Microsoft YaHei UI", 9),
            'small': ("Microsoft YaHei UI", 8),
            'mono': ("Consolas", 8),
        }

        # 状态变量
        self.video_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.extract_mode = tk.StringVar(value="total")
        self.fps_value = tk.StringVar(value="1")
        self.total_images = tk.StringVar(value="100")
        self.output_format = tk.StringVar(value="jpg")
        self.status_text = tk.StringVar(value="准备就绪")
        self.current_file = tk.StringVar(value="")
        self.progress_value = tk.DoubleVar(value=0)

        self.is_processing = False
        self.should_stop = False
        self.ffmpeg_available = self.check_ffmpeg()

        self.setup_styles()
        self.create_ui()

    def setup_styles(self):
        """配置ttk样式"""
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(
            'Compact.Horizontal.TProgressbar',
            thickness=6,
            background=self.colors['primary'],
            troughcolor=self.colors['border'],
            borderwidth=0,
        )

    def check_ffmpeg(self):
        """检查FFmpeg是否安装"""
        ffmpeg_path = self.get_ffmpeg_path()
        try:
            self.run_subprocess(
                [ffmpeg_path, "-version"],
                capture_output=True,
                encoding='utf-8',
                errors='ignore',
                timeout=5
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def run_subprocess(self, cmd, **kwargs):
        """运行子进程，Windows 下隐藏命令行窗口"""
        if os.name == 'nt':  # Windows
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        return subprocess.run(cmd, **kwargs)

    def get_ffmpeg_path(self):
        """获取 ffmpeg 路径，优先使用打包目录中的版本"""
        # PyInstaller 打包后的 exe 所在目录
        if hasattr(sys, '_MEIPASS'):
            exe_dir = os.path.dirname(sys.executable)
        else:
            exe_dir = os.path.dirname(os.path.abspath(__file__))

        # 优先查找 exe 同级目录的 ffmpeg.exe
        local_ffmpeg = os.path.join(exe_dir, 'ffmpeg.exe')
        if os.path.exists(local_ffmpeg):
            return local_ffmpeg

        # 检查 _internal 目录（PyInstaller onedir 模式）
        internal_ffmpeg = os.path.join(exe_dir, '_internal', 'ffmpeg.exe')
        if os.path.exists(internal_ffmpeg):
            return internal_ffmpeg

        # 回退到系统 PATH
        return 'ffmpeg'

    def get_ffprobe_path(self):
        """获取 ffprobe 路径，优先使用打包目录中的版本"""
        ffmpeg_path = self.get_ffmpeg_path()
        if ffmpeg_path.endswith('.exe'):
            return ffmpeg_path.replace('ffmpeg.exe', 'ffprobe.exe')
        return 'ffprobe'

    def create_ui(self):
        """创建紧凑UI"""
        # 创建可滚动容器
        self.create_scrollable_frame()

        # 创建紧凑标题栏（60px高度）
        self.create_compact_header()

        # 内容区域
        content = tk.Frame(self.scrollable_frame, bg=self.colors['bg_main'])
        content.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        # 创建紧凑卡片
        self.create_video_section(content)
        self.create_mode_section(content)
        self.create_output_section(content)
        self.create_progress_section(content)
        self.create_buttons_section(content)

    def create_scrollable_frame(self):
        """创建可滚动框架"""
        container = tk.Frame(self.root, bg=self.colors['bg_main'])
        container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(container, bg=self.colors['bg_main'], highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.scrollable_frame = tk.Frame(self.canvas, bg=self.colors['bg_main'])
        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.scrollable_frame, anchor="nw"
        )

        self.scrollable_frame.bind("<Configure>", self.on_frame_configure)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)

    def on_frame_configure(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def on_mousewheel(self, event):
        if event.delta > 0:
            self.canvas.yview_scroll(-1, "units")
        else:
            self.canvas.yview_scroll(1, "units")

    def create_compact_header(self):
        """创建紧凑标题栏（60px）"""
        header = tk.Frame(self.root, bg=self.colors['bg_header'], height=60)
        header.pack(fill=tk.X, side=tk.TOP)
        header.pack_propagate(False)

        # 渐变条
        tk.Frame(header, bg=self.colors['primary'], height=2).pack(fill=tk.X)

        # 标题行
        title_row = tk.Frame(header, bg=self.colors['bg_header'])
        title_row.pack(fill=tk.X, padx=15, pady=(8, 2))

        tk.Label(
            title_row,
            text="SCC-🎬 视频帧提取工具",
            font=self.fonts['title'],
            bg=self.colors['bg_header'],
            fg='white',
        ).pack(side=tk.LEFT)

        # 副标题
        tk.Label(
            header,
            text="使用 FFmpeg 将视频切分为图片 | 支持 FPS/总数模式",
            font=self.fonts['subtitle'],
            bg=self.colors['bg_header'],
            fg='#94a3b8',
        ).pack(anchor=tk.W, padx=15)

        # FFmpeg警告
        if not self.ffmpeg_available:
            tk.Label(
                header,
                text="⚠️ 未检测到 FFmpeg",
                font=self.fonts['small'],
                bg=self.colors['bg_header'],
                fg=self.colors['error'],
            ).pack(anchor=tk.W, padx=15)

    def create_section(self, parent, title):
        """创建紧凑区块"""
        section = tk.Frame(parent, bg=self.colors['bg_card'])
        section.pack(fill=tk.X, pady=(0, 8))

        # 标题行（带分隔线）
        header = tk.Frame(section, bg=self.colors['bg_card'])
        header.pack(fill=tk.X, padx=10, pady=(8, 0))

        tk.Label(
            header,
            text=title,
            font=self.fonts['section'],
            bg=self.colors['bg_card'],
            fg=self.colors['text_primary'],
        ).pack(side=tk.LEFT)

        tk.Frame(header, bg=self.colors['border'], height=1).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0), pady=(0, 0)
        )

        return section

    def create_video_section(self, parent):
        """视频选择区块"""
        section = self.create_section(parent, "📁 视频文件")

        # 输入行
        row = tk.Frame(section, bg=self.colors['bg_card'])
        row.pack(fill=tk.X, padx=10, pady=(6, 4))

        self.video_entry = tk.Entry(
            row,
            textvariable=self.video_path,
            state='readonly',
            font=self.fonts['mono'],
            bg='#f9fafb',
            relief='solid',
            bd=1,
        )
        self.video_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6), ipady=3)

        tk.Button(
            row,
            text="选择",
            command=self.select_video,
            font=self.fonts['body'],
            bg=self.colors['primary'],
            fg='white',
            activebackground=self.colors['primary_hover'],
            relief='flat',
            padx=12,
            pady=3,
            cursor='hand2',
        ).pack(side=tk.RIGHT)

        # 视频信息
        self.video_info_label = tk.Label(
            section,
            text="未选择视频",
            font=self.fonts['small'],
            bg=self.colors['bg_card'],
            fg=self.colors['text_secondary'],
        )
        self.video_info_label.pack(anchor=tk.W, padx=10, pady=(0, 6))

    def create_mode_section(self, parent):
        """切分模式区块 - 水平布局"""
        section = self.create_section(parent, "⚙️ 切分模式")

        # 模式选择行
        mode_row = tk.Frame(section, bg=self.colors['bg_card'])
        mode_row.pack(fill=tk.X, padx=10, pady=(6, 4))

        # FPS模式
        fps_frame = tk.Frame(mode_row, bg=self.colors['bg_card'])
        fps_frame.pack(side=tk.LEFT)

        tk.Radiobutton(
            fps_frame,
            text="FPS",
            variable=self.extract_mode,
            value="fps",
            command=self.update_mode_ui,
            bg=self.colors['bg_card'],
            font=self.fonts['body'],
        ).pack(side=tk.LEFT)

        self.fps_spin = tk.Spinbox(
            fps_frame,
            from_=0.1,
            to=60,
            increment=0.1,
            textvariable=self.fps_value,
            width=6,
            font=self.fonts['body'],
            relief='solid',
            bd=1,
        )
        self.fps_spin.pack(side=tk.LEFT, padx=(4, 0))

        # 分隔
        tk.Frame(mode_row, bg=self.colors['border'], width=1).pack(
            side=tk.LEFT, fill=tk.Y, padx=12, pady=2
        )

        # 总数模式
        total_frame = tk.Frame(mode_row, bg=self.colors['bg_card'])
        total_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Radiobutton(
            total_frame,
            text="总数",
            variable=self.extract_mode,
            value="total",
            command=self.update_mode_ui,
            bg=self.colors['bg_card'],
            font=self.fonts['body'],
        ).pack(side=tk.LEFT)

        self.total_spin = tk.Spinbox(
            total_frame,
            from_=1,
            to=1000,
            increment=1,
            textvariable=self.total_images,
            width=6,
            font=self.fonts['body'],
            relief='solid',
            bd=1,
        )
        self.total_spin.pack(side=tk.LEFT, padx=(4, 8))

        # 快捷按钮
        tk.Label(
            total_frame,
            text="快捷:",
            font=self.fonts['small'],
            bg=self.colors['bg_card'],
            fg=self.colors['text_secondary'],
        ).pack(side=tk.LEFT, padx=(0, 4))

        for num in [50, 100, 150, 200]:
            tk.Button(
                total_frame,
                text=str(num),
                command=lambda n=num: self.set_total(n),
                font=self.fonts['small'],
                bg='#f3f4f6',
                fg=self.colors['primary'],
                activebackground=self.colors['primary'],
                activeforeground='white',
                relief='flat',
                padx=6,
                pady=1,
                cursor='hand2',
            ).pack(side=tk.LEFT, padx=(0, 3))

    def create_output_section(self, parent):
        """输出设置区块"""
        section = self.create_section(parent, "💾 输出设置")

        # 目录选择行
        row1 = tk.Frame(section, bg=self.colors['bg_card'])
        row1.pack(fill=tk.X, padx=10, pady=(6, 4))

        tk.Entry(
            row1,
            textvariable=self.output_path,
            state='readonly',
            font=self.fonts['mono'],
            bg='#f9fafb',
            relief='solid',
            bd=1,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6), ipady=3)

        tk.Button(
            row1,
            text="选择目录",
            command=self.select_output,
            font=self.fonts['body'],
            bg=self.colors['bg_button'],
            fg=self.colors['text_primary'],
            activebackground='#d1d5db',
            relief='solid',
            bd=1,
            padx=10,
            pady=3,
            cursor='hand2',
        ).pack(side=tk.RIGHT)

        # 格式和示例行
        row2 = tk.Frame(section, bg=self.colors['bg_card'])
        row2.pack(fill=tk.X, padx=10, pady=(0, 6))

        tk.Label(
            row2,
            text="格式:",
            font=self.fonts['body'],
            bg=self.colors['bg_card'],
        ).pack(side=tk.LEFT)

        ttk.Combobox(
            row2,
            textvariable=self.output_format,
            values=["jpg", "png", "bmp", "tiff"],
            width=8,
            state="readonly",
            font=self.fonts['body'],
        ).pack(side=tk.LEFT, padx=(4, 12))

        tk.Label(
            row2,
            text="示例: 03271245_789_0001_1920_1080.jpg",
            font=self.fonts['mono'],
            bg=self.colors['bg_card'],
            fg=self.colors['text_secondary'],
        ).pack(side=tk.LEFT)

    def create_progress_section(self, parent):
        """进度区块"""
        section = self.create_section(parent, "📊 处理进度")

        content = tk.Frame(section, bg=self.colors['bg_card'])
        content.pack(fill=tk.X, padx=10, pady=(6, 8))

        # 状态和百分比同行
        top_row = tk.Frame(content, bg=self.colors['bg_card'])
        top_row.pack(fill=tk.X)

        tk.Label(
            top_row,
            textvariable=self.status_text,
            font=self.fonts['body'],
            bg=self.colors['bg_card'],
            fg=self.colors['text_secondary'],
        ).pack(side=tk.LEFT)

        self.percent_label = tk.Label(
            top_row,
            text="0%",
            font=self.fonts['body'],
            bg=self.colors['bg_card'],
            fg=self.colors['text_secondary'],
        )
        self.percent_label.pack(side=tk.RIGHT)

        # 进度条
        self.progress = ttk.Progressbar(
            content,
            mode='determinate',
            variable=self.progress_value,
            maximum=100,
            style='Compact.Horizontal.TProgressbar',
        )
        self.progress.pack(fill=tk.X, pady=(4, 4), ipady=3)

        # 当前文件
        tk.Label(
            content,
            textvariable=self.current_file,
            font=self.fonts['mono'],
            bg=self.colors['bg_card'],
            fg=self.colors['text_secondary'],
        ).pack(anchor=tk.W)

    def create_buttons_section(self, parent):
        """按钮区块"""
        section = tk.Frame(parent, bg=self.colors['bg_main'])
        section.pack(fill=tk.X, pady=(4, 0))

        # 主按钮
        self.start_btn = tk.Button(
            section,
            text="🚀 开始提取",
            command=self.start_extraction,
            font=("Microsoft YaHei UI", 10, "bold"),
            bg=self.colors['success'],
            fg='white',
            activebackground='#059669',
            relief='flat',
            padx=30,
            pady=10,
            cursor='hand2',
        )
        self.start_btn.pack(fill=tk.X, pady=(0, 8))

        # 辅助按钮
        aux = tk.Frame(section, bg=self.colors['bg_main'])
        aux.pack(fill=tk.X)

        self.open_btn = tk.Button(
            aux,
            text="📂 打开文件夹",
            command=self.open_output_folder,
            font=self.fonts['body'],
            bg=self.colors['bg_button'],
            fg=self.colors['text_primary'],
            activebackground='#d1d5db',
            relief='solid',
            bd=1,
            padx=15,
            pady=7,
            cursor='hand2',
            state='disabled',
        )
        self.open_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        self.copy_btn = tk.Button(
            aux,
            text="📋 复制路径",
            command=self.copy_output_path,
            font=self.fonts['body'],
            bg=self.colors['bg_button'],
            fg=self.colors['text_primary'],
            activebackground='#d1d5db',
            relief='solid',
            bd=1,
            padx=15,
            pady=7,
            cursor='hand2',
        )
        self.copy_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(6, 0))

    def update_mode_ui(self):
        """更新模式UI"""
        mode = self.extract_mode.get()
        if mode == "fps":
            self.fps_spin.config(state='normal')
            self.total_spin.config(state='disabled')
        else:
            self.fps_spin.config(state='disabled')
            self.total_spin.config(state='normal')

    def set_total(self, num):
        """设置总张数"""
        self.total_images.set(str(num))
        self.extract_mode.set("total")
        self.update_mode_ui()

    def get_video_info(self, video_path):
        """获取视频信息"""
        ffprobe_path = self.get_ffprobe_path()
        try:
            cmd = [
                ffprobe_path, "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0",
                video_path
            ]
            result = self.run_subprocess(cmd, capture_output=True, encoding='utf-8', errors='ignore', timeout=10)
            if 'x' in result.stdout:
                w, h = result.stdout.strip().split('x')
                return {'width': int(w), 'height': int(h)}
        except:
            pass
        return {'width': 1920, 'height': 1080}

    def select_video(self):
        """选择视频文件，自动设置输出目录为视频所在文件夹"""
        path = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[("视频文件", "*.mp4 *.avi *.mov *.mkv *.flv *.wmv *.webm"), ("所有文件", "*.*")]
        )
        if path:
            self.video_path.set(path)
            # 自动设置输出目录为视频所在目录
            video_dir = os.path.dirname(path)
            self.output_path.set(video_dir)
            info = self.get_video_info(path)
            self.video_info_label.config(
                text=f"📹 {info['width']}x{info['height']} | 输出目录: {video_dir}",
                fg=self.colors['text_primary']
            )

    def select_output(self):
        """选择输出目录"""
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_path.set(path)

    def copy_output_path(self):
        """复制输出路径"""
        path = self.output_path.get()
        if path:
            self.root.clipboard_clear()
            self.root.clipboard_append(path)
            self.root.update()
            messagebox.showinfo("提示", "输出路径已复制到剪贴板")
        else:
            messagebox.showwarning("提示", "请先选择输出目录")

    def open_output_folder(self):
        """打开输出文件夹"""
        path = self.output_path.get()
        if path and os.path.exists(path):
            if os.name == 'nt':
                os.startfile(path)
            elif os.name == 'posix':
                os.system(f'open "{path}"')
        else:
            messagebox.showwarning("提示", "输出目录不存在")

    def validate_inputs(self):
        """验证输入"""
        if not self.ffmpeg_available:
            messagebox.showerror("错误", "未检测到 FFmpeg，请先安装")
            return False
        if not self.video_path.get():
            messagebox.showerror("错误", "请选择视频文件")
            return False
        if not self.output_path.get():
            messagebox.showerror("错误", "请选择输出目录")
            return False
        if not os.path.exists(self.output_path.get()):
            try:
                os.makedirs(self.output_path.get(), exist_ok=True)
            except Exception as e:
                messagebox.showerror("错误", f"无法创建输出目录: {e}")
                return False
        return True

    def update_progress(self, percentage, message=""):
        """更新进度"""
        self.progress_value.set(percentage)
        self.percent_label.config(text=f"{percentage:.1f}%")
        if message:
            self.current_file.set(message)
        self.status_text.set(f"处理中... {percentage:.1f}%")

    def extract_frames(self, video_path, output_dir, fmt, total=None, fps=None):
        """提取帧并实时重命名"""
        ffmpeg_path = self.get_ffmpeg_path()
        ffprobe_path = self.get_ffprobe_path()
        info = self.get_video_info(video_path)
        width, height = info['width'], info['height']

        # 获取视频时长
        cmd = [ffprobe_path, "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", video_path]
        result = self.run_subprocess(cmd, capture_output=True, encoding='utf-8', errors='ignore', timeout=10)
        duration = float(result.stdout.strip()) if result.stdout.strip() else 0

        timestamp = datetime.now().strftime("%m%d%H%M")
        random_num = random.randint(100, 999)

        if total:
            timestamps = [duration * i / total for i in range(total)]
            total_extract = total
        else:
            interval = 1.0 / fps
            timestamps = [i * interval for i in range(int(duration / interval))]
            total_extract = len(timestamps)

        for idx, ts in enumerate(timestamps):
            if self.should_stop:
                break

            temp_path = os.path.join(output_dir, f"_temp_{idx:06d}.{fmt}")
            cmd = [ffmpeg_path, "-y", "-ss", str(ts), "-i", video_path, "-vframes", "1", "-threads", "1", temp_path]

            if fmt.lower() in ['jpg', 'jpeg']:
                cmd.extend(["-q:v", "2"])
            elif fmt.lower() == 'png':
                cmd.extend(["-compression_level", "3"])

            result = self.run_subprocess(cmd, capture_output=True, encoding='utf-8', errors='ignore', timeout=60)

            if result.returncode == 0 and os.path.exists(temp_path):
                final_name = f"{timestamp}_{random_num}_{idx+1:04d}_{width}_{height}.{fmt}"
                final_path = os.path.join(output_dir, final_name)
                os.rename(temp_path, final_path)

                progress = ((idx + 1) / total_extract) * 100
                self.root.after(0, lambda p=progress, f=final_name: self.update_progress(p, f"已保存: {f}"))

        return total_extract

    def start_extraction(self):
        """开始提取"""
        if not self.validate_inputs():
            return

        self.is_processing = True
        self.should_stop = False
        self.start_btn.config(state='disabled', text="⏳ 处理中...", bg=self.colors['warning'])
        self.open_btn.config(state='disabled')
        self.progress_value.set(0)

        thread = threading.Thread(target=self.extraction_worker, daemon=True)
        thread.start()

    def extraction_worker(self):
        """后台提取"""
        try:
            video_path = self.video_path.get()
            output_dir = self.output_path.get()
            fmt = self.output_format.get()
            mode = self.extract_mode.get()

            if mode == "total":
                total = int(self.total_images.get())
                file_count = self.extract_frames(video_path, output_dir, fmt, total=total)
            else:
                fps = float(self.fps_value.get())
                file_count = self.extract_frames(video_path, output_dir, fmt, fps=fps)

            if not self.should_stop:
                self.root.after(0, lambda: self.on_success(file_count))
        except Exception as e:
            self.root.after(0, lambda: self.on_error(str(e)))

    def on_success(self, file_count):
        """成功处理"""
        self.progress_value.set(100)
        self.percent_label.config(text="100%")
        self.status_text.set(f"✅ 完成! 共 {file_count} 张")
        self.current_file.set("处理完成")
        self.start_btn.config(state='normal', text="🚀 开始提取", bg=self.colors['success'])
        self.open_btn.config(state='normal')
        self.is_processing = False

        if messagebox.askyesno("✅ 完成", f"提取完成！共 {file_count} 张\n\n是否打开输出文件夹?"):
            self.open_output_folder()

    def on_error(self, error_msg):
        """错误处理"""
        self.status_text.set("❌ 错误")
        self.current_file.set(error_msg[:50])
        self.start_btn.config(state='normal', text="🚀 开始提取", bg=self.colors['success'])
        self.is_processing = False
        messagebox.showerror("❌ 错误", f"提取失败:\n\n{error_msg[:500]}")

    def on_closing(self):
        """关闭窗口"""
        if self.is_processing:
            if messagebox.askokcancel("确认", "正在处理中，确定要退出吗?"):
                self.should_stop = True
                self.root.destroy()
        else:
            self.root.destroy()


def main():
    root = tk.Tk()
    app = CompactVideoFrameExtractor(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
