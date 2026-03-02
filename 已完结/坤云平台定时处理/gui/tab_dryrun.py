"""标签页4：模拟运行"""

import tkinter as tk
from tkinter import ttk
import json
import os
import tempfile
import time
import re
from .utils import load_config, get_cleanup_script, ScriptRunner
from .widgets import LogViewer


class DryRunTab(ttk.Frame):
    def __init__(self, parent, status_var, **kwargs):
        super().__init__(parent, **kwargs)
        self.status_var = status_var
        self.runner = ScriptRunner()
        self.start_time = None
        self.temp_config = None
        self.file_count = 0
        self.freed_space = ""
        self._create_widgets()

    def _create_widgets(self):
        # 控制栏
        ctrl = ttk.Frame(self)
        ctrl.pack(fill=tk.X, padx=8, pady=8)

        self.btn_run = ttk.Button(ctrl, text="开始模拟运行", command=self._start)
        self.btn_run.pack(side=tk.LEFT, padx=2)

        self.btn_stop = ttk.Button(ctrl, text="停止", command=self._stop, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=2)

        self.lbl_duration = ttk.Label(ctrl, text="")
        self.lbl_duration.pack(side=tk.LEFT, padx=10)

        # 提示
        ttk.Label(self, text="模拟运行不会实际删除文件，仅显示将要执行的操作。",
                  foreground="gray").pack(padx=8, anchor=tk.W)

        # 结果汇总
        self.summary_frame = ttk.LabelFrame(self, text="模拟结果汇总", padding=8)
        self.summary_frame.pack(fill=tk.X, padx=8, pady=4)

        self.lbl_summary = ttk.Label(self.summary_frame, text="尚未运行")
        self.lbl_summary.pack(anchor=tk.W)

        # 日志区
        self.log = LogViewer(self)
        self.log.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

    def _start(self):
        # 创建临时配置副本，强制 dryRun=true
        try:
            config = load_config()
        except Exception as e:
            self.log.append(f"[ERROR] 加载配置失败: {e}")
            return

        config["settings"]["dryRun"] = True

        # 写到临时文件
        fd, self.temp_config = tempfile.mkstemp(suffix=".json", prefix="cleanup_dryrun_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        self.log.clear()
        self.log.set_status("模拟运行中...")
        self.btn_run.configure(state=tk.DISABLED)
        self.btn_stop.configure(state=tk.NORMAL)
        self.start_time = time.time()
        self.file_count = 0
        self.freed_space = ""
        self.lbl_summary.configure(text="运行中...")
        self.status_var.set("模拟运行中...")

        self.runner = ScriptRunner()
        self.runner.start(get_cleanup_script(), self.temp_config)
        self._poll()

    def _stop(self):
        self.runner.stop()
        self.btn_stop.configure(state=tk.DISABLED)

    def _poll(self):
        lines = self.runner.poll_output()
        finished = False
        for line in lines:
            if line is None:
                finished = True
            else:
                self.log.append(line)
                # 解析汇总信息
                if "总共删除文件:" in line:
                    m = re.search(r"总共删除文件:\s*(\d+)", line)
                    if m:
                        self.file_count = int(m.group(1))
                if "总共释放空间:" in line:
                    m = re.search(r"总共释放空间:\s*(.+)", line)
                    if m:
                        self.freed_space = m.group(1).strip()

        if self.start_time:
            elapsed = time.time() - self.start_time
            mins, secs = divmod(int(elapsed), 60)
            self.lbl_duration.configure(text=f"运行时长: {mins:02d}:{secs:02d}")

        if finished:
            self.btn_run.configure(state=tk.NORMAL)
            self.btn_stop.configure(state=tk.DISABLED)
            self.log.set_status("模拟运行完成")
            self.status_var.set("模拟运行完成")
            self.start_time = None

            summary = f"将删除文件数: {self.file_count}    将释放空间: {self.freed_space or '0 Bytes'}"
            self.lbl_summary.configure(text=summary)

            # 清理临时文件
            if self.temp_config and os.path.exists(self.temp_config):
                try:
                    os.remove(self.temp_config)
                except Exception:
                    pass
                self.temp_config = None
        else:
            self.after(100, self._poll)
