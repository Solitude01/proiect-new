"""坤云平台定时清理 - GUI 管理工具"""

import tkinter as tk
from tkinter import ttk
import sys
import os

# 支持直接运行 python gui/main.py
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.tab_config import ConfigTab
from gui.tab_execute import ExecuteTab
from gui.tab_dryrun import DryRunTab
from gui.tab_scheduler import SchedulerTab


class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("坤云平台定时清理 - 管理工具")
        self._center_window(900, 650)
        self.minsize(700, 500)

        # 状态栏变量
        self.status_var = tk.StringVar(value="就绪")

        self._create_widgets()

    def _center_window(self, w, h):
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _create_widgets(self):
        # Notebook 标签页容器
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # 四个标签页
        self.tab_config = ConfigTab(self.notebook, self.status_var)
        self.tab_execute = ExecuteTab(self.notebook, self.status_var)
        self.tab_dryrun = DryRunTab(self.notebook, self.status_var)
        self.tab_scheduler = SchedulerTab(self.notebook, self.status_var)

        self.notebook.add(self.tab_config, text="  配置编辑  ")
        self.notebook.add(self.tab_execute, text="  手动执行  ")
        self.notebook.add(self.tab_dryrun, text="  模拟运行  ")
        self.notebook.add(self.tab_scheduler, text="  计划任务  ")

        # 底部状态栏
        status_bar = ttk.Frame(self, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Label(status_bar, textvariable=self.status_var, padding=(8, 2)).pack(side=tk.LEFT)


def main():
    app = MainApp()
    app.mainloop()


if __name__ == "__main__":
    main()
