"""标签页2：手动执行 + 实时日志"""

import tkinter as tk
from tkinter import ttk
import time
from .utils import get_cleanup_script, get_config_path, ScriptRunner
from .widgets import LogViewer


class ExecuteTab(ttk.Frame):
    def __init__(self, parent, status_var, **kwargs):
        super().__init__(parent, **kwargs)
        self.status_var = status_var
        self.runner = ScriptRunner()
        self.start_time = None
        self.timer_id = None
        self._create_widgets()

    def _create_widgets(self):
        # 控制栏
        ctrl = ttk.Frame(self)
        ctrl.pack(fill=tk.X, padx=8, pady=8)

        self.btn_run = ttk.Button(ctrl, text="执行清理", command=self._start)
        self.btn_run.pack(side=tk.LEFT, padx=2)

        self.btn_stop = ttk.Button(ctrl, text="停止", command=self._stop, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=2)

        self.lbl_duration = ttk.Label(ctrl, text="")
        self.lbl_duration.pack(side=tk.LEFT, padx=10)

        # 日志区
        self.log = LogViewer(self)
        self.log.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

    def _start(self):
        script = get_cleanup_script()
        config = get_config_path()

        self.log.clear()
        self.log.set_status("运行中...")
        self.btn_run.configure(state=tk.DISABLED)
        self.btn_stop.configure(state=tk.NORMAL)
        self.start_time = time.time()
        self.status_var.set("正在执行清理脚本...")

        self.runner = ScriptRunner()
        self.runner.start(script, config)
        self._poll()

    def _stop(self):
        self.runner.stop()
        self.btn_stop.configure(state=tk.DISABLED)
        self.status_var.set("正在停止...")

    def _poll(self):
        lines = self.runner.poll_output()
        finished = False
        for line in lines:
            if line is None:
                finished = True
            else:
                self.log.append(line)

        # 更新运行时长
        if self.start_time:
            elapsed = time.time() - self.start_time
            mins, secs = divmod(int(elapsed), 60)
            self.lbl_duration.configure(text=f"运行时长: {mins:02d}:{secs:02d}")

        if finished:
            self.btn_run.configure(state=tk.NORMAL)
            self.btn_stop.configure(state=tk.DISABLED)
            rc = self.runner.return_code
            if rc == 0 or rc is None:
                self.log.set_status("执行完成")
                self.status_var.set("清理执行完成")
            else:
                self.log.set_status(f"执行结束 (返回码: {rc})")
                self.status_var.set(f"清理脚本返回码: {rc}")
            self.start_time = None
        else:
            self.timer_id = self.after(100, self._poll)
