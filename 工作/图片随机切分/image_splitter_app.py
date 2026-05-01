import os
import random
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from image_distributor import SUPPORTED_EXTENSIONS, ImageDistributor


def random_folder_name() -> str:
    """生成随机文件夹名，用于默认命名"""
    colors = [
        "red", "blue", "green", "yellow", "purple", "orange",
        "cyan", "magenta", "lime", "teal", "pink", "gold",
        "silver", "navy", "coral", "mint", "peach", "indigo",
    ]
    animals = [
        "cat", "dog", "fox", "bear", "wolf", "deer",
        "hawk", "lion", "dove", "frog", "seal", "swan",
        "owl", "hare", "lynx", "puma", "crow", "newt",
    ]
    return f"{random.choice(colors)}_{random.choice(animals)}"


class FolderRow(ttk.Frame):
    """单行文件夹配置组件"""

    def __init__(self, parent, name="", ratio=0.0, on_change=None, on_delete=None):
        super().__init__(parent)
        self.on_change = on_change
        self.on_delete = on_delete

        self.name_var = tk.StringVar(value=name)
        self.ratio_var = tk.StringVar(value=str(ratio) if ratio else "")

        self.name_entry = ttk.Entry(self, textvariable=self.name_var, width=20)
        self.name_entry.pack(side=tk.LEFT, padx=(0, 4))

        ttk.Label(self, text="比例(%)").pack(side=tk.LEFT, padx=(4, 2))
        self.ratio_entry = ttk.Entry(self, textvariable=self.ratio_var, width=8)
        self.ratio_entry.pack(side=tk.LEFT, padx=(2, 4))

        self.delete_btn = ttk.Button(self, text="删除", command=self._on_delete)
        self.delete_btn.pack(side=tk.LEFT, padx=(4, 0))

        self.name_var.trace_add("write", lambda *_: self._notify_change())
        self.ratio_var.trace_add("write", lambda *_: self._notify_change())

    def _on_delete(self):
        if self.on_delete:
            self.on_delete(self)

    def _notify_change(self):
        if self.on_change:
            self.on_change()

    def get_name(self) -> str:
        return self.name_var.get().strip()

    def get_ratio(self) -> float | None:
        text = self.ratio_var.get().strip()
        if not text:
            return None
        try:
            val = float(text)
            return val
        except ValueError:
            return None

    def set_name(self, name: str):
        self.name_var.set(name)

    def set_ratio(self, ratio: float):
        self.ratio_var.set(str(ratio))


class ImageSplitterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("图片随机切分工具")
        self.geometry("720x620")
        self.minsize(600, 500)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.distributor = ImageDistributor(seed=42)

        # 数据
        self.input_dir = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.seed_var = tk.StringVar(value="42")
        self.operation_mode = tk.StringVar(value="copy")
        self.image_count = 0
        self.folder_rows: list[FolderRow] = []

        self._build_ui()
        self._add_default_rows()

    def _build_ui(self):
        main_frame = ttk.Frame(self, padding=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- 输入目录 ---
        input_frame = ttk.LabelFrame(main_frame, text="输入设置", padding=8)
        input_frame.pack(fill=tk.X, pady=(0, 8))

        row1 = ttk.Frame(input_frame)
        row1.pack(fill=tk.X)
        ttk.Label(row1, text="输入目录:").pack(side=tk.LEFT)
        self.input_entry = ttk.Entry(row1, textvariable=self.input_dir)
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.input_entry.bind("<FocusOut>", lambda e: self._on_input_changed())
        ttk.Button(row1, text="选择...", command=self._on_select_input).pack(side=tk.LEFT)

        self.count_label = ttk.Label(input_frame, text="图片文件数: 0 张")
        self.count_label.pack(anchor=tk.W, pady=(4, 0))

        # --- 输出目录 ---
        output_frame = ttk.LabelFrame(main_frame, text="输出设置", padding=8)
        output_frame.pack(fill=tk.X, pady=(0, 8))

        row2 = ttk.Frame(output_frame)
        row2.pack(fill=tk.X)
        ttk.Label(row2, text="输出根目录:").pack(side=tk.LEFT)
        self.output_entry = ttk.Entry(row2, textvariable=self.output_dir)
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(row2, text="选择...", command=self._on_select_output).pack(side=tk.LEFT)

        # --- 子文件夹配置 ---
        folder_frame = ttk.LabelFrame(main_frame, text="输出子文件夹配置", padding=8)
        folder_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        header = ttk.Frame(folder_frame)
        header.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(header, text="文件夹名", width=22).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Label(header, text="比例(%)", width=8).pack(side=tk.LEFT, padx=(6, 4))
        ttk.Label(header, text="操作").pack(side=tk.LEFT, padx=(4, 0))

        self.folders_container = ttk.Frame(folder_frame)
        self.folders_container.pack(fill=tk.BOTH, expand=True, pady=(0, 4))

        add_frame = ttk.Frame(folder_frame)
        add_frame.pack(fill=tk.X)
        ttk.Button(add_frame, text="+ 添加文件夹", command=self._add_folder_row).pack(side=tk.LEFT)

        self.ratio_sum_label = ttk.Label(folder_frame, text="合计: 0%")
        self.ratio_sum_label.pack(anchor=tk.E)

        # --- 种子和模式 ---
        settings_frame = ttk.Frame(main_frame)
        settings_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(settings_frame, text="随机种子:").pack(side=tk.LEFT)
        seed_entry = ttk.Entry(settings_frame, textvariable=self.seed_var, width=10)
        seed_entry.pack(side=tk.LEFT, padx=4)

        ttk.Separator(settings_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=12)

        ttk.Label(settings_frame, text="操作模式:").pack(side=tk.LEFT)
        ttk.Radiobutton(
            settings_frame, text="复制", variable=self.operation_mode, value="copy"
        ).pack(side=tk.LEFT, padx=2)
        ttk.Radiobutton(
            settings_frame, text="移动", variable=self.operation_mode, value="move"
        ).pack(side=tk.LEFT, padx=2)

        # --- 进度和状态 ---
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=(0, 8))

        self.progress = ttk.Progressbar(bottom_frame, mode="determinate")
        self.progress.pack(fill=tk.X, pady=(0, 4))

        self.status_label = ttk.Label(bottom_frame, text="就绪")
        self.status_label.pack(anchor=tk.W)

        # --- 开始按钮 ---
        self.start_btn = ttk.Button(main_frame, text="开始切分", command=self._on_start)
        self.start_btn.pack(pady=(4, 0))
        self.start_btn.config(state=tk.DISABLED)

    def _add_default_rows(self):
        self._add_folder_row("train", 60.0)
        self._add_folder_row("val", 40.0)

    def _add_folder_row(self, name="", ratio=None):
        if not name:
            name = random_folder_name()
        if ratio is None:
            ratio_str = 0.0
        else:
            ratio_str = ratio

        row = FolderRow(
            self.folders_container,
            name=name,
            ratio=ratio_str,
            on_change=self._update_validation,
            on_delete=self._remove_folder_row,
        )
        row.pack(fill=tk.X, pady=1)
        self.folder_rows.append(row)
        self._update_validation()

    def _remove_folder_row(self, row: FolderRow):
        if len(self.folder_rows) <= 1:
            messagebox.showwarning("提示", "至少保留一个文件夹")
            return
        row.destroy()
        self.folder_rows.remove(row)
        self._update_validation()

    def _on_select_input(self):
        path = filedialog.askdirectory(title="选择输入目录")
        if path:
            self.input_dir.set(path)
            self._on_input_changed()

    def _on_input_changed(self):
        path = self.input_dir.get().strip()
        if path and os.path.isdir(path):
            try:
                images = self.distributor.scan_images(path)
                self.image_count = len(images)
                self.count_label.config(text=f"图片文件数: {self.image_count} 张 (支持格式: {', '.join(SUPPORTED_EXTENSIONS)})")
            except Exception as e:
                self.image_count = 0
                self.count_label.config(text=f"图片文件数: 错误 - {e}")
        else:
            self.image_count = 0
            self.count_label.config(text="图片文件数: 0 张")
        self._update_validation()

    def _on_select_output(self):
        path = filedialog.askdirectory(title="选择输出根目录")
        if path:
            self.output_dir.set(path)

    def _get_ratios(self) -> list[float]:
        ratios = []
        for row in self.folder_rows:
            r = row.get_ratio()
            if r is not None:
                ratios.append(r)
        return ratios

    def _update_validation(self, *_):
        valid = True
        issues = []

        # 检验输入目录
        in_dir = self.input_dir.get().strip()
        if not in_dir or not os.path.isdir(in_dir):
            valid = False
            issues.append("请选择有效的输入目录")
        elif self.image_count == 0:
            valid = False
            issues.append("输入目录中没有支持的图片文件")

        # 检验输出目录
        out_dir = self.output_dir.get().strip()
        if not out_dir:
            valid = False
            issues.append("请选择输出根目录")

        # 检验比例
        ratios = self._get_ratios()
        ratio_sum = sum(ratios) if ratios else 0
        self.ratio_sum_label.config(text=f"合计: {ratio_sum:.1f}%")

        if not ratios:
            valid = False
            issues.append("请为每个文件夹设置比例")
        elif not all(isinstance(r, (int, float)) for r in ratios):
            valid = False
            issues.append("比例必须为数字")
        elif any(r < 0 for r in ratios):
            valid = False
            issues.append("比例不能为负数")
        else:
            if abs(ratio_sum - 100.0) > 0.01:
                valid = False
                issues.append(f"比例合计必须为 100%，当前为 {ratio_sum:.1f}%")

            # 检查文件夹名
            names = [r.get_name() for r in self.folder_rows]
            if any(not n for n in names):
                valid = False
                issues.append("文件夹名不能为空")
            if len(names) != len(set(names)):
                valid = False
                issues.append("文件夹名不能重复")

        if issues:
            self.status_label.config(text="; ".join(issues), foreground="red")
        else:
            self.status_label.config(text="就绪", foreground="")

        self.start_btn.config(state=tk.NORMAL if valid else tk.DISABLED)

    def _on_start(self):
        in_dir = self.input_dir.get().strip()
        out_dir = self.output_dir.get().strip()
        ratios = self._get_ratios()
        names = [r.get_name() for r in self.folder_rows]
        mode = self.operation_mode.get()

        if mode == "move":
            ok = messagebox.askyesno(
                "确认移动操作",
                "移动模式会将原文件移动到输出目录，原始位置的文件将被删除。\n\n确定要继续吗？",
                icon="warning",
            )
            if not ok:
                return

        try:
            seed = int(self.seed_var.get().strip())
        except ValueError:
            messagebox.showerror("错误", "随机种子必须为整数")
            return

        self.distributor.seed = seed

        output_dirs = [os.path.join(out_dir, name) for name in names]
        ratio_fractions = [r / 100.0 for r in ratios]

        images = self.distributor.scan_images(in_dir)
        if not images:
            messagebox.showwarning("警告", "输入目录中没有图片文件")
            return

        try:
            plan = self.distributor.generate_plan(images, ratio_fractions, output_dirs)
        except Exception as e:
            messagebox.showerror("错误", f"生成分配计划失败: {e}")
            return

        # 在后台线程中执行，避免 GUI 冻结
        self.start_btn.config(state=tk.DISABLED)
        self.progress.config(maximum=sum(len(f) for f in plan), value=0)
        self.status_label.config(text="正在处理...", foreground="")

        import threading

        def run():
            stats = self.distributor.execute_plan(
                plan, output_dirs, mode=mode,
                progress_callback=lambda cur, tot: self.after(
                    0, self._on_progress, cur, tot
                ),
            )
            self.after(0, self._on_complete, stats)

        threading.Thread(target=run, daemon=True).start()

    def _on_progress(self, current, total):
        self.progress.config(value=current)
        self.status_label.config(
            text=f"处理中... {current}/{total}", foreground=""
        )

    def _on_complete(self, stats):
        self.progress.config(value=stats["total"])
        total = stats["total"]
        errors = stats["errors"]
        if errors:
            msg = f"处理完成。成功: {total} 个文件，失败: {len(errors)} 个文件。\n\n错误详情:\n"
            for err in errors[:5]:
                msg += f"  - {os.path.basename(err['file'])}: {err['error']}\n"
            if len(errors) > 5:
                msg += f"  ...及其他 {len(errors) - 5} 个错误"
            messagebox.showwarning("完成（有错误）", msg)
            self.status_label.config(
                text=f"完成，{total} 成功，{len(errors)} 失败", foreground="orange"
            )
        else:
            messagebox.showinfo("完成", f"切分完成！共处理 {total} 个文件。")
            self.status_label.config(text=f"完成，共 {total} 个文件", foreground="green")
        self._update_validation()
