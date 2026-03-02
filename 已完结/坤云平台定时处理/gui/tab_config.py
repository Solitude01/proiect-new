"""标签页1：配置编辑器"""

import tkinter as tk
from tkinter import ttk, messagebox
from .utils import load_config, save_config, get_config_path
from .widgets import TaskEditDialog


class ConfigTab(ttk.Frame):
    def __init__(self, parent, status_var, **kwargs):
        super().__init__(parent, **kwargs)
        self.status_var = status_var
        self.config = None
        self._create_widgets()
        self.reload()

    def _create_widgets(self):
        # --- 平台信息 ---
        top = ttk.LabelFrame(self, text="平台信息", padding=8)
        top.pack(fill=tk.X, padx=8, pady=(8, 4))

        ttk.Label(top, text="平台名称:").grid(row=0, column=0, sticky=tk.W)
        self.var_platform = tk.StringVar()
        ttk.Entry(top, textvariable=self.var_platform, width=30).grid(row=0, column=1, padx=8, sticky=tk.W)

        # --- 清理任务列表 ---
        mid = ttk.LabelFrame(self, text="清理任务", padding=8)
        mid.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # Treeview
        cols = ("enabled", "path", "mode", "threshold")
        self.tree = ttk.Treeview(mid, columns=cols, show="tree headings", height=8)
        self.tree.heading("#0", text="任务名称")
        self.tree.heading("enabled", text="状态")
        self.tree.heading("path", text="路径")
        self.tree.heading("mode", text="模式")
        self.tree.heading("threshold", text="阈值")

        self.tree.column("#0", width=120, minwidth=80)
        self.tree.column("enabled", width=50, anchor=tk.CENTER)
        self.tree.column("path", width=280)
        self.tree.column("mode", width=70, anchor=tk.CENTER)
        self.tree.column("threshold", width=80, anchor=tk.CENTER)

        vsb = ttk.Scrollbar(mid, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # 按钮区
        btn_frame = ttk.Frame(mid)
        btn_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 0))
        # 实际上放到树下方更好
        # 改为底部按钮
        btn_bar = ttk.Frame(self)
        btn_bar.pack(fill=tk.X, padx=8, pady=2)
        ttk.Button(btn_bar, text="添加任务", command=self._add_task).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar, text="编辑任务", command=self._edit_task).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar, text="删除任务", command=self._delete_task).pack(side=tk.LEFT, padx=2)

        # --- 全局设置 ---
        bot = ttk.LabelFrame(self, text="全局设置", padding=8)
        bot.pack(fill=tk.X, padx=8, pady=4)

        ttk.Label(bot, text="日志目录:").grid(row=0, column=0, sticky=tk.W)
        self.var_logdir = tk.StringVar()
        ttk.Entry(bot, textvariable=self.var_logdir, width=40).grid(row=0, column=1, padx=8, sticky=tk.EW)

        ttk.Label(bot, text="日志保留天数:").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.var_logdays = tk.StringVar()
        ttk.Entry(bot, textvariable=self.var_logdays, width=10).grid(row=1, column=1, padx=8, sticky=tk.W, pady=4)

        self.var_dryrun = tk.BooleanVar()
        ttk.Checkbutton(bot, text="模拟运行 (dryRun)", variable=self.var_dryrun).grid(row=2, column=1, sticky=tk.W)

        bot.columnconfigure(1, weight=1)

        # --- 保存/重新加载 ---
        act_frame = ttk.Frame(self)
        act_frame.pack(fill=tk.X, padx=8, pady=(4, 8))
        ttk.Button(act_frame, text="保存配置", command=self._save).pack(side=tk.RIGHT, padx=2)
        ttk.Button(act_frame, text="重新加载", command=self.reload).pack(side=tk.RIGHT, padx=2)

    def reload(self):
        """从文件重新加载配置"""
        try:
            self.config = load_config()
        except Exception as e:
            messagebox.showerror("错误", f"加载配置失败:\n{e}")
            return

        self.var_platform.set(self.config.get("platform", ""))
        settings = self.config.get("settings", {})
        self.var_logdir.set(settings.get("logDir", ""))
        self.var_logdays.set(str(settings.get("logRetentionDays", 30)))
        self.var_dryrun.set(settings.get("dryRun", False))

        self._refresh_tree()
        self.status_var.set("配置已加载")

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for task in self.config.get("cleanupTasks", []):
            status = "启用" if task.get("enabled") else "禁用"
            mode = task.get("cleanupMode", "")
            if mode == "bySize":
                threshold = f'{task.get("maxSizeGB", "")} GB'
            elif mode == "byDays":
                threshold = f'{task.get("retentionDays", "")} 天'
            else:
                threshold = ""
            self.tree.insert("", tk.END, text=task.get("name", ""),
                             values=(status, task.get("path", ""), mode, threshold))

    def _get_selected_index(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择一个任务")
            return None
        item = sel[0]
        children = self.tree.get_children()
        return list(children).index(item)

    def _add_task(self):
        dlg = TaskEditDialog(self, title="添加任务")
        self.wait_window(dlg)
        if dlg.result:
            self.config.setdefault("cleanupTasks", []).append(dlg.result)
            self._refresh_tree()
            self.status_var.set("已添加任务（未保存）")

    def _edit_task(self):
        idx = self._get_selected_index()
        if idx is None:
            return
        task = self.config["cleanupTasks"][idx]
        dlg = TaskEditDialog(self, task=task, title="编辑任务")
        self.wait_window(dlg)
        if dlg.result:
            self.config["cleanupTasks"][idx] = dlg.result
            self._refresh_tree()
            self.status_var.set("已修改任务（未保存）")

    def _delete_task(self):
        idx = self._get_selected_index()
        if idx is None:
            return
        name = self.config["cleanupTasks"][idx].get("name", "")
        if messagebox.askyesno("确认", f"确定删除任务「{name}」？"):
            del self.config["cleanupTasks"][idx]
            self._refresh_tree()
            self.status_var.set("已删除任务（未保存）")

    def _save(self):
        self.config["platform"] = self.var_platform.get().strip()
        settings = self.config.setdefault("settings", {})
        settings["logDir"] = self.var_logdir.get().strip()
        try:
            settings["logRetentionDays"] = int(self.var_logdays.get())
        except ValueError:
            messagebox.showwarning("提示", "日志保留天数必须为整数")
            return
        settings["dryRun"] = self.var_dryrun.get()

        try:
            save_config(self.config)
            self.status_var.set("配置已保存")
            messagebox.showinfo("成功", "配置已保存到 config.json")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败:\n{e}")
