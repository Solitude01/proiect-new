"""复用组件：LogViewer 日志查看器、TaskEditDialog 任务编辑对话框"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import time


class LogViewer(ttk.Frame):
    """深色背景的日志查看器，支持按日志级别着色。"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._create_widgets()

    def _create_widgets(self):
        # 工具栏
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, 2))

        self.lbl_status = ttk.Label(toolbar, text="就绪")
        self.lbl_status.pack(side=tk.LEFT)

        self.lbl_time = ttk.Label(toolbar, text="")
        self.lbl_time.pack(side=tk.LEFT, padx=(10, 0))

        btn_export = ttk.Button(toolbar, text="导出", width=6, command=self._export)
        btn_export.pack(side=tk.RIGHT, padx=2)

        btn_clear = ttk.Button(toolbar, text="清空", width=6, command=self.clear)
        btn_clear.pack(side=tk.RIGHT, padx=2)

        # 日志文本区
        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True)

        self.text = tk.Text(
            frame, wrap=tk.WORD, state=tk.DISABLED,
            bg="#1e1e1e", fg="#d4d4d4", insertbackground="#d4d4d4",
            font=("Consolas", 10), relief=tk.FLAT, padx=6, pady=4,
        )
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 配置颜色标签
        self.text.tag_configure("ERROR", foreground="#f44747")
        self.text.tag_configure("WARN", foreground="#cca700")
        self.text.tag_configure("SUCCESS", foreground="#6a9955")
        self.text.tag_configure("INFO", foreground="#d4d4d4")
        self.text.tag_configure("DRYRUN", foreground="#569cd6")

    def append(self, line):
        """追加一行日志"""
        tag = "INFO"
        if "[ERROR]" in line:
            tag = "ERROR"
        elif "[WARN]" in line:
            tag = "WARN"
        elif "[SUCCESS]" in line:
            tag = "SUCCESS"
        elif "[模拟]" in line:
            tag = "DRYRUN"

        self.text.configure(state=tk.NORMAL)
        self.text.insert(tk.END, line + "\n", tag)
        self.text.see(tk.END)
        self.text.configure(state=tk.DISABLED)

    def clear(self):
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.configure(state=tk.DISABLED)

    def set_status(self, text):
        self.lbl_status.configure(text=text)

    def set_time(self, text):
        self.lbl_time.configure(text=text)

    def get_content(self):
        return self.text.get("1.0", tk.END)

    def _export(self):
        content = self.get_content().strip()
        if not content:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[("日志文件", "*.log"), ("文本文件", "*.txt"), ("所有文件", "*.*")],
            title="导出日志",
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)


class TaskEditDialog(tk.Toplevel):
    """清理任务编辑对话框"""

    def __init__(self, parent, task=None, title="编辑任务"):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.grab_set()
        self.result = None

        # 初始化数据
        self.task = task or {}

        self._create_widgets()
        self._load_data()
        self._center_window(450, 420)

    def _center_window(self, w, h):
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _create_widgets(self):
        pad = dict(padx=10, pady=4, sticky=tk.W)

        row = 0
        ttk.Label(self, text="任务名称:").grid(row=row, column=0, **pad)
        self.var_name = tk.StringVar()
        ttk.Entry(self, textvariable=self.var_name, width=35).grid(row=row, column=1, columnspan=2, padx=10, pady=4, sticky=tk.EW)

        row += 1
        ttk.Label(self, text="描述:").grid(row=row, column=0, **pad)
        self.var_desc = tk.StringVar()
        ttk.Entry(self, textvariable=self.var_desc, width=35).grid(row=row, column=1, columnspan=2, padx=10, pady=4, sticky=tk.EW)

        row += 1
        self.var_enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(self, text="启用", variable=self.var_enabled).grid(row=row, column=1, padx=10, pady=4, sticky=tk.W)

        row += 1
        ttk.Label(self, text="目录路径:").grid(row=row, column=0, **pad)
        path_frame = ttk.Frame(self)
        path_frame.grid(row=row, column=1, columnspan=2, padx=10, pady=4, sticky=tk.EW)
        self.var_path = tk.StringVar()
        ttk.Entry(path_frame, textvariable=self.var_path, width=28).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(path_frame, text="浏览", width=5, command=self._browse_path).pack(side=tk.RIGHT, padx=(4, 0))

        row += 1
        ttk.Label(self, text="文件类型:").grid(row=row, column=0, **pad)
        ext_frame = ttk.Frame(self)
        ext_frame.grid(row=row, column=1, columnspan=2, padx=10, pady=4, sticky=tk.EW)
        self.var_ext = tk.StringVar()
        ttk.Entry(ext_frame, textvariable=self.var_ext, width=28).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.ext_combo = ttk.Combobox(ext_frame, width=10, state="readonly", values=[
            "图片类型", "视频类型", "日志类型", "自定义",
        ])
        self.ext_combo.pack(side=tk.RIGHT, padx=(4, 0))
        self.ext_combo.bind("<<ComboboxSelected>>", self._on_ext_preset)

        # 预设映射
        self._ext_presets = {
            "图片类型": ".jpg,.jpeg,.png,.bmp,.gif,.webp,.tiff",
            "视频类型": ".mp4,.avi,.mov,.mkv,.flv,.wmv,.webm",
            "日志类型": ".log,.txt",
        }

        row += 1
        ttk.Label(self, text="清理模式:").grid(row=row, column=0, **pad)
        self.var_mode = tk.StringVar(value="bySize")
        mode_frame = ttk.Frame(self)
        mode_frame.grid(row=row, column=1, columnspan=2, padx=10, pady=4, sticky=tk.W)
        ttk.Radiobutton(mode_frame, text="按大小 (bySize)", variable=self.var_mode, value="bySize", command=self._on_mode_change).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(mode_frame, text="按天数 (byDays)", variable=self.var_mode, value="byDays", command=self._on_mode_change).pack(side=tk.LEFT)

        row += 1
        self.lbl_threshold = ttk.Label(self, text="阈值 (GB):")
        self.lbl_threshold.grid(row=row, column=0, **pad)
        self.var_threshold = tk.StringVar()
        self.ent_threshold = ttk.Entry(self, textvariable=self.var_threshold, width=15)
        self.ent_threshold.grid(row=row, column=1, padx=10, pady=4, sticky=tk.W)

        # 按钮
        row += 1
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=row, column=0, columnspan=3, pady=15)
        ttk.Button(btn_frame, text="确定", width=10, command=self._on_ok).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="取消", width=10, command=self.destroy).pack(side=tk.LEFT, padx=10)

        self.columnconfigure(1, weight=1)

    def _on_ext_preset(self, event=None):
        """选择预设文件类型时填充到输入框"""
        sel = self.ext_combo.get()
        if sel in self._ext_presets:
            self.var_ext.set(self._ext_presets[sel])

    def _on_mode_change(self):
        mode = self.var_mode.get()
        if mode == "bySize":
            self.lbl_threshold.configure(text="阈值 (GB):")
        else:
            self.lbl_threshold.configure(text="保留天数:")

    def _browse_path(self):
        path = filedialog.askdirectory(title="选择目录")
        if path:
            self.var_path.set(path.replace("/", "\\"))

    def _load_data(self):
        if not self.task:
            return
        self.var_name.set(self.task.get("name", ""))
        self.var_desc.set(self.task.get("description", ""))
        self.var_enabled.set(self.task.get("enabled", True))
        self.var_path.set(self.task.get("path", ""))
        exts = self.task.get("fileExtensions", [])
        self.var_ext.set(",".join(exts))
        # 匹配预设类型
        ext_str = ",".join(exts)
        matched = False
        for label, preset in self._ext_presets.items():
            preset_set = {e.strip() for e in preset.split(",")}
            if set(exts) <= preset_set:
                self.ext_combo.set(label)
                matched = True
                break
        if not matched:
            self.ext_combo.set("自定义")
        mode = self.task.get("cleanupMode", "bySize")
        self.var_mode.set(mode)
        if mode == "bySize":
            self.var_threshold.set(str(self.task.get("maxSizeGB", "")))
        else:
            self.var_threshold.set(str(self.task.get("retentionDays", "")))
        self._on_mode_change()

    def _on_ok(self):
        name = self.var_name.get().strip()
        if not name:
            tk.messagebox.showwarning("提示", "请输入任务名称", parent=self)
            return
        path = self.var_path.get().strip()
        if not path:
            tk.messagebox.showwarning("提示", "请输入目录路径", parent=self)
            return

        ext_str = self.var_ext.get().strip()
        exts = [e.strip() for e in ext_str.split(",") if e.strip()]

        mode = self.var_mode.get()
        threshold_str = self.var_threshold.get().strip()
        try:
            threshold = float(threshold_str) if threshold_str else 0
        except ValueError:
            tk.messagebox.showwarning("提示", "阈值必须为数字", parent=self)
            return

        self.result = {
            "name": name,
            "description": self.var_desc.get().strip(),
            "enabled": self.var_enabled.get(),
            "path": path,
            "fileExtensions": exts,
            "cleanupMode": mode,
            "retentionDays": int(threshold) if mode == "byDays" else None,
            "maxSizeGB": threshold if mode == "bySize" else None,
        }
        self.destroy()
