#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI主窗口 - tkinter图形界面
提供用户友好的数据集下载界面
"""

import sys
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass
import threading
import json

# 添加项目目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.auth import AuthManager
from core.downloader import DatasetDownloader, DownloadResult
from core.converter import COCOConverter, ConversionResult
from core.hikvision_format_converter import HikvisionFormatConverter, HikvisionExportResult


@dataclass
class PageInfo:
    """页面信息数据类"""
    dataset_id: str
    version_id: str
    labeled_count: int
    url: str
    title: str
    cookies: dict


class MainWindow:
    """主窗口类"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("海康威视AI平台数据集导出工具")
        self.root.geometry("850x720")
        self.root.minsize(650, 620)

        # 状态变量
        self.page_info: Optional[PageInfo] = None
        self.auth_manager: Optional[AuthManager] = None
        self.is_downloading = False
        self.download_thread: Optional[threading.Thread] = None
        self.last_download_dir: Optional[Path] = None

        # 创建UI
        self._create_widgets()
        self._create_layout()

        # 初始化日志
        self.log("程序启动")
        self.log("请输入Token、数据集ID和版本ID后点击连接")

        # 尝试加载上次配置
        self._load_config_on_startup()

    def _create_widgets(self):
        """创建UI组件"""
        # 标题
        self.title_label = ttk.Label(
            self.root,
            text="海康威视AI平台数据集导出工具",
            font=("Microsoft YaHei", 16, "bold")
        )

        # 认证区域
        self.auth_frame = ttk.LabelFrame(self.root, text="认证信息", padding=10)

        self.token_var = tk.StringVar()
        self.dataset_id_input_var = tk.StringVar()
        self.version_id_input_var = tk.StringVar()

        self.connect_btn = ttk.Button(
            self.auth_frame,
            text="连接",
            command=self._on_connect
        )

        self.status_label = ttk.Label(
            self.auth_frame,
            text="未连接",
            foreground="red"
        )

        # 页面信息区域
        self.info_frame = ttk.LabelFrame(self.root, text="当前页面信息", padding=10)

        self.dataset_id_var = tk.StringVar(value="-")
        self.version_id_var = tk.StringVar(value="-")
        self.labeled_count_var = tk.StringVar(value="-")
        self.page_title_var = tk.StringVar(value="-")

        ttk.Label(self.info_frame, text="数据集ID:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Label(self.info_frame, textvariable=self.dataset_id_var).grid(row=0, column=1, sticky=tk.W, pady=2)

        ttk.Label(self.info_frame, text="版本ID:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Label(self.info_frame, textvariable=self.version_id_var).grid(row=1, column=1, sticky=tk.W, pady=2)

        ttk.Label(self.info_frame, text="已标注图片:").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Label(self.info_frame, textvariable=self.labeled_count_var).grid(row=2, column=1, sticky=tk.W, pady=2)

        ttk.Label(self.info_frame, text="页面标题:").grid(row=3, column=0, sticky=tk.W, pady=2)
        ttk.Label(self.info_frame, textvariable=self.page_title_var, wraplength=600).grid(row=3, column=1, sticky=tk.W, pady=2)

        # 下载设置区域
        self.download_frame = ttk.LabelFrame(self.root, text="下载设置", padding=10)

        self.output_dir_var = tk.StringVar()
        default_dir = str(Path.home() / "Downloads")
        self.output_dir_var.set(default_dir)

        ttk.Label(self.download_frame, text="下载目录:").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(self.download_frame, textvariable=self.output_dir_var).grid(row=0, column=1, sticky=tk.EW, pady=5, padx=5)
        ttk.Button(self.download_frame, text="浏览...", command=self._on_browse).grid(row=0, column=2, sticky=tk.W, pady=5)

        ttk.Label(self.download_frame, text="并发数:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.concurrent_var = tk.IntVar(value=5)
        self.concurrent_spin = ttk.Spinbox(
            self.download_frame,
            from_=1,
            to=10,
            textvariable=self.concurrent_var,
            width=10
        )
        self.concurrent_spin.grid(row=1, column=1, sticky=tk.W, pady=5)

        # 操作按钮区域
        self.button_frame = ttk.Frame(self.root)

        self.download_btn = ttk.Button(
            self.button_frame,
            text="开始下载",
            command=self._on_start_download,
            width=16
        )

        self.cancel_btn = ttk.Button(
            self.button_frame,
            text="取消",
            command=self._on_cancel,
            width=16,
            state=tk.DISABLED
        )

        self.btn_separator = ttk.Separator(self.button_frame, orient=tk.VERTICAL)

        self.export_coco_btn = ttk.Button(
            self.button_frame,
            text="导出COCO格式",
            command=self._on_export_coco,
            width=16
        )

        self.export_hikvision_btn = ttk.Button(
            self.button_frame,
            text="导出海康本地格式",
            command=self._on_export_hikvision,
            width=16
        )

        self.export_hikvision_official_btn = ttk.Button(
            self.button_frame,
            text="导出海康官方格式",
            command=self._on_export_hikvision_official,
            width=16
        )

        # 导出设置
        self.export_settings_frame = ttk.LabelFrame(self.root, text="导出设置", padding=8)

        self.use_default_export_var = tk.BooleanVar(value=False)
        self.default_export_check = ttk.Checkbutton(
            self.export_settings_frame,
            text="使用默认导出目录",
            variable=self.use_default_export_var,
        )

        self.export_output_dir_var = tk.StringVar(value="")
        self.export_output_entry = ttk.Entry(self.export_settings_frame, textvariable=self.export_output_dir_var)
        self.export_browse_btn = ttk.Button(
            self.export_settings_frame,
            text="浏览...",
            command=self._on_browse_export_dir,
            width=8
        )

        # 进度区域
        self.progress_frame = ttk.LabelFrame(self.root, text="下载进度", padding=10)

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            variable=self.progress_var,
            maximum=100,
            mode='determinate'
        )

        self.progress_label = ttk.Label(self.progress_frame, text="就绪", wraplength=700)
        self.current_file_var = tk.StringVar(value="")
        self.current_file_label = ttk.Label(self.progress_frame, textvariable=self.current_file_var, wraplength=700)

        # 日志区域
        self.log_frame = ttk.LabelFrame(self.root, text="日志", padding=10)

        self.log_text = scrolledtext.ScrolledText(
            self.log_frame,
            wrap=tk.WORD,
            height=6,
            state=tk.DISABLED
        )

    def _create_layout(self):
        """布局UI组件"""
        # 标题
        self.title_label.pack(pady=15)

        # 认证区域
        self.auth_frame.pack(fill=tk.X, padx=15, pady=5)

        ttk.Label(self.auth_frame, text="Token:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=3)
        ttk.Entry(self.auth_frame, textvariable=self.token_var).grid(row=0, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=3)

        ttk.Label(self.auth_frame, text="数据集ID:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=3)
        ttk.Entry(self.auth_frame, textvariable=self.dataset_id_input_var).grid(row=1, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=3)

        ttk.Label(self.auth_frame, text="版本ID:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=3)
        ttk.Entry(self.auth_frame, textvariable=self.version_id_input_var).grid(row=2, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=3)

        self.connect_btn.grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        self.status_label.grid(row=3, column=2, sticky=tk.W, padx=10, pady=5)

        # 页面信息区域
        self.info_frame.pack(fill=tk.X, padx=15, pady=5)

        # 下载设置区域
        self.download_frame.pack(fill=tk.X, padx=15, pady=5)

        # 操作按钮
        self.button_frame.pack(fill=tk.X, pady=10)
        self.download_btn.pack(side=tk.LEFT, padx=5)
        self.cancel_btn.pack(side=tk.LEFT, padx=5)
        self.btn_separator.pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=4)
        self.export_coco_btn.pack(side=tk.LEFT, padx=5)
        self.export_hikvision_btn.pack(side=tk.LEFT, padx=5)
        self.export_hikvision_official_btn.pack(side=tk.LEFT, padx=5)

        # 导出设置
        self.export_settings_frame.pack(fill=tk.X, padx=15, pady=5)
        self.default_export_check.pack(side=tk.LEFT, padx=(5, 15))
        self.export_output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.export_browse_btn.pack(side=tk.LEFT, padx=5)

        # 进度区域
        self.progress_frame.pack(fill=tk.X, padx=15, pady=5)
        self.progress_bar.pack(fill=tk.X, pady=5)
        self.progress_label.pack(anchor=tk.W, pady=2)
        self.current_file_label.pack(anchor=tk.W, pady=2)

        # 日志区域
        self.log_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def log(self, message: str):
        """添加日志（含时间戳，上限 2000 行）"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"

        self.log_text.configure(state=tk.NORMAL)

        # 限制日志行数，超出时删除旧行
        line_count = int(float(self.log_text.index('end-1c')))
        if line_count > 2000:
            self.log_text.delete('1.0', f'{line_count - 2000}.0')

        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _load_config(self) -> dict:
        """加载配置文件"""
        config_path = project_root / "config.json"
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.log(f"加载配置失败: {e}")
        return {}

    def _save_config(self, token: str, dataset_id: str, version_id: str):
        """保存配置文件"""
        config_path = project_root / "config.json"
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "token": token,
                    "dataset_id": dataset_id,
                    "version_id": version_id
                }, f, indent=2, ensure_ascii=False)
            self.log("配置已保存")
        except Exception as e:
            self.log(f"保存配置失败: {e}")

    def _load_config_on_startup(self):
        """启动时加载配置，预填充输入框"""
        cfg = self._load_config()
        if cfg.get("token"):
            self.token_var.set(cfg["token"])
        if cfg.get("dataset_id"):
            self.dataset_id_input_var.set(cfg["dataset_id"])
        if cfg.get("version_id"):
            self.version_id_input_var.set(cfg["version_id"])
        if cfg.get("token") or cfg.get("dataset_id") or cfg.get("version_id"):
            self.log("已加载上次配置")

    def _on_connect(self):
        """连接按钮事件 - 使用手动输入的信息建立连接"""
        token = self.token_var.get().strip()
        dataset_id = self.dataset_id_input_var.get().strip()
        version_id = self.version_id_input_var.get().strip()

        if not token:
            messagebox.showwarning("提示", "Token不能为空")
            return
        if not dataset_id:
            messagebox.showwarning("提示", "数据集ID不能为空")
            return
        if not version_id:
            messagebox.showwarning("提示", "版本ID不能为空")
            return

        self.log(f"正在连接... Dataset: {dataset_id}, Version: {version_id}")
        self.status_label.config(text="连接中...", foreground="orange")
        self.root.update()

        self._setup_connection(
            token=token,
            cookies={"token": token},
            dataset_id=dataset_id,
            version_id=version_id,
            title=f"数据集 {dataset_id}",
            labeled_count=0
        )

    def _setup_connection(
        self,
        token: str,
        cookies: dict,
        dataset_id: str,
        version_id: str,
        title: str,
        labeled_count: int
    ):
        """设置连接状态并更新UI"""
        self.page_info = PageInfo(
            dataset_id=dataset_id,
            version_id=version_id,
            labeled_count=labeled_count,
            url="",
            title=title,
            cookies=cookies
        )

        # 更新UI
        self.dataset_id_var.set(dataset_id)
        self.version_id_var.set(version_id)
        self.labeled_count_var.set("（下载时获取）" if labeled_count == 0 else str(labeled_count))
        self.page_title_var.set(title)

        # 设置认证
        self.auth_manager = AuthManager()
        self.auth_manager.authenticate_manual(
            token=token,
            account_name=cookies.get("accountName", ""),
            sub_account_name=cookies.get("subAccountName", ""),
            project_id=cookies.get("projectId", "")
        )

        self.status_label.config(text="已连接", foreground="green")
        self.log(f"连接成功! Dataset: {dataset_id}, Version: {version_id}")

        # 保存配置
        self._save_config(token, dataset_id, version_id)

    def _on_browse(self):
        """浏览按钮事件"""
        dir_path = filedialog.askdirectory(
            initialdir=self.output_dir_var.get(),
            title="选择下载目录"
        )
        if dir_path:
            self.output_dir_var.set(dir_path)
            self.log(f"下载目录: {dir_path}")

    def _on_browse_export_dir(self):
        """浏览导出目录按钮事件"""
        initial = self.export_output_dir_var.get() or str(Path.home() / "Downloads")
        dir_path = filedialog.askdirectory(
            initialdir=initial,
            title="选择导出目标目录"
        )
        if dir_path:
            self.export_output_dir_var.set(dir_path)
            self.log(f"导出目录: {dir_path}")

    def _get_export_output_dir(self) -> Optional[Path]:
        """获取导出目标目录：勾选默认则 None（自动生成），否则取输入框路径"""
        if self.use_default_export_var.get():
            return None
        path_str = self.export_output_dir_var.get().strip()
        return Path(path_str) if path_str else None

    def _generate_output_dir(self) -> Path:
        """生成带时间戳的输出目录"""
        base_dir = Path(self.output_dir_var.get())
        dataset_id = self.page_info.dataset_id if self.page_info else "unknown"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = base_dir / f"dataset_{dataset_id}_{timestamp}"

        # 避免覆盖
        counter = 1
        original_output_dir = output_dir
        while output_dir.exists():
            output_dir = base_dir / f"dataset_{dataset_id}_{timestamp}_{counter}"
            counter += 1

        return output_dir

    def _on_start_download(self):
        """开始下载按钮事件"""
        if not self.page_info or not self.auth_manager:
            messagebox.showwarning("提示", "请先连接浏览器获取页面信息")
            return

        if self.is_downloading:
            return

        # 确认下载
        count_str = f"{self.page_info.labeled_count} 张" if self.page_info.labeled_count > 0 else "所有已标注"
        if not messagebox.askyesno(
            "确认下载",
            f"即将下载 {count_str} 图片和标注数据\n\n是否继续?"
        ):
            return

        # 生成输出目录
        output_dir = self._generate_output_dir()
        self.log(f"输出目录: {output_dir}")

        # 更新UI状态
        self.is_downloading = True
        self.download_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.connect_btn.config(state=tk.DISABLED)
        self.progress_var.set(0)
        self.progress_label.config(text="准备下载...")

        # 在后台线程执行下载
        self.download_thread = threading.Thread(
            target=self._download_worker,
            args=(output_dir,),
            daemon=True
        )
        self.download_thread.start()

    def _download_worker(self, output_dir: Path):
        """下载工作线程"""
        try:
            def progress_callback(current: int, total: int, filename: str):
                """进度回调"""
                pct = (current / total * 100) if total > 0 else 0
                self.root.after(0, lambda: self._update_progress(pct, current, total, filename))

            downloader = DatasetDownloader(
                auth_manager=self.auth_manager,
                dataset_id=self.page_info.dataset_id,
                version_id=self.page_info.version_id,
                output_dir=output_dir,
                max_concurrent=self.concurrent_var.get(),
                progress_callback=progress_callback
            )

            result = downloader.run(labeled_only=True)

            # 在主线程更新UI
            self.root.after(0, lambda r=result, d=output_dir: self._download_complete(r, d))

        except Exception as e:
            msg = str(e)
            self.root.after(0, lambda m=msg: self._download_error(m))

    def _update_progress(self, pct: float, current: int, total: int, filename: str):
        """更新进度"""
        self.progress_var.set(pct)
        self.progress_label.config(text=f"进度: {pct:.1f}% ({current}/{total})")
        self.current_file_var.set(f"当前: {filename[:50]}..." if len(filename) > 50 else f"当前: {filename}")
        self.log(f"下载 {filename}")

    def _download_complete(self, result: DownloadResult, output_dir: Path):
        """下载完成"""
        self.is_downloading = False
        self.last_download_dir = output_dir
        self.download_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        self.connect_btn.config(state=tk.NORMAL)
        self.progress_label.config(text="下载完成")
        self.current_file_var.set("")

        self.log("=" * 40)
        self.log(f"下载完成!")
        self.log(f"成功: {result.success}/{result.total}")
        self.log(f"失败: {result.failed}")
        self.log(f"保存位置: {output_dir}")

        if result.failed > 0:
            messagebox.showwarning(
                "下载完成",
                f"下载完成，但有 {result.failed} 个文件失败\n\n"
                f"成功: {result.success}\n"
                f"失败: {result.failed}\n\n"
                f"保存位置:\n{output_dir}"
            )
        else:
            messagebox.showinfo(
                "下载完成",
                f"所有文件下载成功!\n\n"
                f"总计: {result.success} 个文件\n\n"
                f"保存位置:\n{output_dir}"
            )

    def _download_error(self, error_msg: str):
        """下载错误"""
        self.is_downloading = False
        self.download_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        self.connect_btn.config(state=tk.NORMAL)
        self.progress_label.config(text="下载失败")

        self.log(f"下载错误: {error_msg}")
        messagebox.showerror("下载失败", error_msg)

    def _on_export_coco(self):
        """导出COCO格式按钮事件"""
        initial_dir = str(self.last_download_dir) if self.last_download_dir else str(Path.home() / "Downloads")
        folder = filedialog.askdirectory(
            initialdir=initial_dir,
            title="选择已下载的数据集目录"
        )
        if not folder:
            return

        self.export_coco_btn.config(state=tk.DISABLED)
        self.log(f"开始转换COCO格式: {folder}")

        export_dir = self._get_export_output_dir()
        t = threading.Thread(
            target=self._export_coco_worker,
            args=(Path(folder), export_dir),
            daemon=True
        )
        t.start()

    def _export_coco_worker(self, folder: Path, export_dir: Optional[Path] = None):
        """后台线程执行转换"""
        try:
            converter = COCOConverter(folder)
            result = converter.convert()
            # COCO 格式始终输出到 dataset/COCO/ 下；如指定了导出目录则额外复制
            if export_dir and result.coco_dir:
                import shutil
                dst = export_dir / result.coco_dir.name
                if not dst.exists():
                    shutil.copytree(result.coco_dir, dst)
                    self.root.after(0, lambda: self.log(f"COCO已复制到: {dst}"))
            self.root.after(0, lambda r=result: self._export_coco_complete(r))
        except FileNotFoundError as e:
            msg = f"目录不完整: {e}"
            self.root.after(0, lambda m=msg: self._export_coco_error(m))
        except ValueError as e:
            msg = f"无有效数据: {e}"
            self.root.after(0, lambda m=msg: self._export_coco_error(m))
        except Exception as e:
            import traceback
            traceback.print_exc()
            msg = f"转换失败: {e}"
            self.root.after(0, lambda m=msg: self._export_coco_error(m))

    def _export_coco_complete(self, result: ConversionResult):
        """转换完成，显示结果并恢复按钮"""
        self.log("=" * 40)
        self.log("COCO格式转换完成!")
        self.log(f"图片数: {result.images_count}")
        self.log(f"标注数: {result.annotations_count}")
        self.log(f"类别数: {result.categories_count}")
        if result.skipped_count > 0:
            self.log(f"跳过: {result.skipped_count} 条（无效bbox/空label）")
        self.log(f"输出: {result.output_path}")

        messagebox.showinfo(
            "COCO转换完成",
            f"转换成功!\n\n"
            f"图片数: {result.images_count}\n"
            f"标注数: {result.annotations_count}\n"
            f"类别数: {result.categories_count}\n"
            + (f"跳过: {result.skipped_count} 条\n" if result.skipped_count else "")
            + f"\nCOCO目录:\n{result.coco_dir}"
        )
        self.export_coco_btn.config(state=tk.NORMAL)

    def _export_coco_error(self, msg: str):
        """转换出错，显示错误并恢复按钮"""
        self.log(f"COCO转换失败: {msg}")
        messagebox.showerror("COCO转换失败", msg)
        self.export_coco_btn.config(state=tk.NORMAL)

    def _on_export_hikvision(self):
        """导出海康本地格式按钮事件"""
        initial_dir = str(self.last_download_dir) if self.last_download_dir else str(Path.home() / "Downloads")
        folder = filedialog.askdirectory(
            initialdir=initial_dir,
            title="选择已下载的数据集目录"
        )
        if not folder:
            return

        self.export_hikvision_btn.config(state=tk.DISABLED)
        self.log(f"开始转换海康本地格式: {folder}")

        export_dir = self._get_export_output_dir()
        t = threading.Thread(
            target=self._export_hikvision_worker,
            args=(Path(folder), export_dir),
            daemon=True
        )
        t.start()

    def _export_hikvision_worker(self, folder: Path, export_dir: Optional[Path] = None):
        """后台线程执行转换"""
        try:
            converter = HikvisionFormatConverter(folder, export_dir)
            result = converter.convert()
            self.root.after(0, lambda r=result: self._export_hikvision_complete(r))
        except FileNotFoundError as e:
            msg = f"目录不完整: {e}"
            self.root.after(0, lambda m=msg: self._export_hikvision_error(m))
        except ValueError as e:
            msg = f"无有效数据: {e}"
            self.root.after(0, lambda m=msg: self._export_hikvision_error(m))
        except Exception as e:
            import traceback
            traceback.print_exc()
            msg = f"转换失败: {e}"
            self.root.after(0, lambda m=msg: self._export_hikvision_error(m))

    def _export_hikvision_complete(self, result: HikvisionExportResult):
        """转换完成，显示结果并恢复按钮"""
        format_label = "混合标注" if result.format_type == "mixed" else "单检测"
        self.log("=" * 40)
        self.log("海康本地格式转换完成!")
        self.log(f"格式: {format_label}")
        self.log(f"图片数: {result.images_count}")
        self.log(f"标注数: {result.annotations_count}")
        if result.skipped_count > 0:
            self.log(f"跳过: {result.skipped_count} 条")
        self.log(f"输出: {result.output_dir}")
        if result.summary_path:
            self.log(f"汇总: {result.summary_path}")

        msg = (f"导出成功!\n\n"
               f"格式: {format_label}\n"
               f"图片数: {result.images_count}\n"
               f"标注数: {result.annotations_count}\n"
               + (f"跳过: {result.skipped_count} 条\n" if result.skipped_count else "")
               + f"\n输出目录:\n{result.output_dir}\n"
               + f"标注目录:\n{result.result_dir}")
        if result.summary_path:
            msg += f"\n\n汇总JSON:\n{result.summary_path}"

        messagebox.showinfo("海康本地格式转换完成", msg)
        self.export_hikvision_btn.config(state=tk.NORMAL)

    def _export_hikvision_error(self, msg: str):
        """转换出错，显示错误并恢复按钮"""
        self.log(f"海康本地格式转换失败: {msg}")
        messagebox.showerror("海康本地格式转换失败", msg)
        self.export_hikvision_btn.config(state=tk.NORMAL)

    def _on_export_hikvision_official(self):
        """导出海康官方完整格式按钮事件"""
        initial_dir = str(self.last_download_dir) if self.last_download_dir else str(Path.home() / "Downloads")
        folder = filedialog.askdirectory(
            initialdir=initial_dir,
            title="选择已下载的数据集目录"
        )
        if not folder:
            return

        self.export_hikvision_official_btn.config(state=tk.DISABLED)
        self.log(f"开始转换海康官方完整格式: {folder}")

        export_dir = self._get_export_output_dir()
        t = threading.Thread(
            target=self._export_hikvision_official_worker,
            args=(Path(folder), export_dir),
            daemon=True
        )
        t.start()

    def _export_hikvision_official_worker(self, folder: Path, export_dir: Optional[Path] = None):
        """后台线程执行官方格式转换"""
        try:
            converter = HikvisionFormatConverter(folder, export_dir, mode="official")
            result = converter.convert()
            self.root.after(0, lambda r=result: self._export_hikvision_official_complete(r))
        except FileNotFoundError as e:
            msg = f"目录不完整: {e}"
            self.root.after(0, lambda m=msg: self._export_hikvision_official_error(m))
        except ValueError as e:
            msg = f"无有效数据: {e}"
            self.root.after(0, lambda m=msg: self._export_hikvision_official_error(m))
        except Exception as e:
            import traceback
            traceback.print_exc()
            msg = f"转换失败: {e}"
            self.root.after(0, lambda m=msg: self._export_hikvision_official_error(m))

    def _export_hikvision_official_complete(self, result: HikvisionExportResult):
        """官方格式转换完成"""
        format_label = "混合标注" if result.format_type == "mixed" else "单检测"
        self.log("=" * 40)
        self.log("海康官方完整格式导出完成!")
        self.log(f"格式: {format_label}")
        self.log(f"有标注图片: {result.images_count}")
        self.log(f"标注数: {result.annotations_count}")
        if result.no_target_count > 0:
            self.log(f"无标注图片: {result.no_target_count} → 不包含目标/")
        if result.skipped_count > 0:
            self.log(f"跳过: {result.skipped_count} 条")
        self.log(f"输出: {result.output_dir}")
        if result.summary_path:
            self.log(f"汇总: {result.summary_path}")

        msg = (f"导出成功!\n\n"
               f"格式: {format_label}\n"
               f"有标注图片: {result.images_count}\n"
               f"标注数: {result.annotations_count}\n"
               + (f"无标注图片: {result.no_target_count}\n" if result.no_target_count else "")
               + (f"跳过: {result.skipped_count} 条\n" if result.skipped_count else "")
               + f"\n输出目录:\n{result.output_dir}\n"
               + f"汇总JSON:\n{result.result_dir}")
        if result.summary_path:
            msg += f"\n\n汇总文件:\n{result.summary_path}"

        messagebox.showinfo("海康官方格式导出完成", msg)
        self.export_hikvision_official_btn.config(state=tk.NORMAL)

    def _export_hikvision_official_error(self, msg: str):
        """官方格式转换出错"""
        self.log(f"海康官方格式导出失败: {msg}")
        messagebox.showerror("海康官方格式导出失败", msg)
        self.export_hikvision_official_btn.config(state=tk.NORMAL)


    def _on_cancel(self):
        """取消按钮事件"""
        if self.is_downloading and self.download_thread:
            # 注意：实际上无法真正中断线程，只能标记状态
            self.is_downloading = False
            self.log("用户取消下载")
            self.progress_label.config(text="已取消")
            self.download_btn.config(state=tk.NORMAL)
            self.cancel_btn.config(state=tk.DISABLED)
            self.connect_btn.config(state=tk.NORMAL)

    def run(self):
        """运行主循环"""
        self.root.mainloop()


def main():
    """主函数"""
    # 设置DPI感知（Windows）
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = MainWindow()
    app.run()


if __name__ == "__main__":
    main()
