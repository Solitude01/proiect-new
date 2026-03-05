"""标签页3：计划任务管理"""

import os
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import json
import ctypes
from .utils import (
    get_install_script, get_cleanup_script, get_config_path,
    run_ps_command, run_as_admin_command, ScriptRunner,
)


TASK_NAME = "坤云平台定时清理"


def _run_elevated_script(ps_code, visible=True):
    """将 PowerShell 代码写入临时 .ps1 文件，通过 UAC 提权执行。

    避免中文路径通过命令行参数传递时被损坏编码。
    临时文件在 Temp 目录（ASCII 路径），中文只在文件内容中（UTF-8-BOM）。
    """
    fd, wrapper = tempfile.mkstemp(suffix=".ps1", prefix="ky_task_")
    with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
        f.write(ps_code)

    show_flag = 1 if visible else 0  # SW_SHOWNORMAL / SW_HIDE
    params = f'-ExecutionPolicy Bypass -NoProfile -File "{wrapper}"'
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "powershell.exe", params, None, show_flag
        )
        ok = ret > 32
    except Exception:
        ok = False

    # 延迟清理临时文件
    def cleanup():
        import time
        time.sleep(60)
        try:
            os.remove(wrapper)
        except Exception:
            pass
    threading.Thread(target=cleanup, daemon=True).start()

    return ok


class SchedulerTab(ttk.Frame):
    def __init__(self, parent, status_var, **kwargs):
        super().__init__(parent, **kwargs)
        self.status_var = status_var
        self.runner = None
        self._create_widgets()
        self.after(500, self.refresh)

    def _create_widgets(self):
        # 任务状态信息
        info_frame = ttk.LabelFrame(self, text="计划任务状态", padding=10)
        info_frame.pack(fill=tk.X, padx=8, pady=8)

        labels = [
            ("任务名称:", "name"),
            ("状态:", "state"),
            ("上次运行:", "last_run"),
            ("上次结果:", "last_result"),
            ("下次运行:", "next_run"),
        ]
        self.info_vars = {}
        for i, (label, key) in enumerate(labels):
            ttk.Label(info_frame, text=label).grid(row=i, column=0, sticky=tk.W, padx=(0, 8), pady=2)
            var = tk.StringVar(value="--")
            ttk.Label(info_frame, textvariable=var, width=50).grid(row=i, column=1, sticky=tk.W, pady=2)
            self.info_vars[key] = var

        # 操作按钮
        btn_frame = ttk.LabelFrame(self, text="操作", padding=10)
        btn_frame.pack(fill=tk.X, padx=8, pady=4)

        row1 = ttk.Frame(btn_frame)
        row1.pack(fill=tk.X, pady=4)

        ttk.Button(row1, text="刷新状态", command=self.refresh).pack(side=tk.LEFT, padx=4)
        ttk.Button(row1, text="立即执行一次", command=self._trigger).pack(side=tk.LEFT, padx=4)
        ttk.Button(row1, text="停止运行中的任务 (需管理员)", command=self._stop_task).pack(side=tk.LEFT, padx=4)

        row2 = ttk.Frame(btn_frame)
        row2.pack(fill=tk.X, pady=4)

        ttk.Label(row2, text="触发间隔:").pack(side=tk.LEFT, padx=4)
        self.var_interval = tk.StringVar(value="2")
        spin = ttk.Spinbox(row2, from_=1, to=24, width=4, textvariable=self.var_interval)
        spin.pack(side=tk.LEFT)
        ttk.Label(row2, text="小时").pack(side=tk.LEFT, padx=(2, 12))

        ttk.Button(row2, text="安装计划任务 (需管理员)", command=self._install).pack(side=tk.LEFT, padx=4)
        ttk.Button(row2, text="卸载计划任务 (需管理员)", command=self._uninstall).pack(side=tk.LEFT, padx=4)

        # 日志区
        log_frame = ttk.LabelFrame(self, text="操作日志", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))

        self.log_text = tk.Text(log_frame, height=8, wrap=tk.WORD, state=tk.DISABLED,
                                bg="#1e1e1e", fg="#d4d4d4", font=("Consolas", 10))
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _log(self, msg):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def refresh(self):
        """查询计划任务状态（不需要管理员权限）"""
        self.status_var.set("正在查询计划任务状态...")

        cmd = f'''
        $task = Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue
        if ($task) {{
            $info = $task | Get-ScheduledTaskInfo
            @{{
                Name = $task.TaskName
                State = $task.State.ToString()
                LastRun = if ($info.LastRunTime) {{ $info.LastRunTime.ToString('yyyy-MM-dd HH:mm:ss') }} else {{ 'N/A' }}
                LastResult = $info.LastTaskResult
                NextRun = if ($info.NextRunTime) {{ $info.NextRunTime.ToString('yyyy-MM-dd HH:mm:ss') }} else {{ 'N/A' }}
            }} | ConvertTo-Json
        }} else {{
            @{{ Name = '{TASK_NAME}'; State = 'NotFound' }} | ConvertTo-Json
        }}
        '''
        output, rc = run_ps_command(cmd)

        try:
            data = json.loads(output)
            self.info_vars["name"].set(data.get("Name", TASK_NAME))
            state = data.get("State", "Unknown")
            self.info_vars["state"].set(state)
            self.info_vars["last_run"].set(data.get("LastRun", "--"))

            last_result = data.get("LastResult", "--")
            if last_result == 0:
                result_text = "0 (成功)"
            elif last_result == 267009:
                result_text = "267009 (任务正在运行)"
            elif last_result == 267011:
                result_text = "267011 (尚未运行)"
            else:
                result_text = str(last_result)
            self.info_vars["last_result"].set(result_text)

            self.info_vars["next_run"].set(data.get("NextRun", "--"))
            self.status_var.set(f"计划任务状态: {state}")
        except Exception:
            self.info_vars["state"].set("查询失败")
            self.status_var.set("查询计划任务状态失败")
            if output:
                self._log(f"查询输出: {output}")

    def _trigger(self):
        """直接运行清理脚本，实时显示输出（不经过计划任务）"""
        script = get_cleanup_script()
        config = get_config_path()

        if not os.path.isfile(script):
            self._log(f"[ERROR] 脚本不存在: {script}")
            return

        if self.runner and self.runner.running:
            self._log("[WARN] 上一次执行尚未完成")
            return

        self._log("--- 直接运行清理脚本 ---")
        self._log(f"脚本: {script}")
        self._log(f"配置: {config}")
        self.status_var.set("正在执行清理脚本...")

        self.runner = ScriptRunner()
        self.runner.start(script, config)
        self._poll_trigger()

    def _poll_trigger(self):
        """轮询脚本输出，实时显示到日志区"""
        lines = self.runner.poll_output()
        for line in lines:
            if line is None:
                rc = self.runner.return_code
                self._log(f"--- 执行完成 (返回码: {rc}) ---")
                self.status_var.set(f"触发执行完成 (返回码: {rc})")
                self.after(2000, self.refresh)
                return
            self._log(line)
        self.after(100, self._poll_trigger)

    def _stop_task(self):
        """通过 UAC 提权停止运行中的任务"""
        self._log(f"正在停止任务: {TASK_NAME} (需要管理员权限)")
        ps_code = f"Stop-ScheduledTask -TaskName '{TASK_NAME}'\n"
        ok = _run_elevated_script(ps_code, visible=False)
        if ok:
            self._log("已发送停止请求")
        else:
            self._log("停止失败: UAC 被拒绝或权限不足")
        self.after(2000, self.refresh)

    def _install(self):
        """通过 UAC 提权安装计划任务"""
        try:
            interval = int(self.var_interval.get())
            if interval < 1 or interval > 24:
                raise ValueError
        except ValueError:
            messagebox.showwarning("提示", "触发间隔必须为 1-24 的整数")
            return

        # 预检查文件是否存在
        install_script = get_install_script()
        cleanup_script = get_cleanup_script()
        config_file = get_config_path()

        missing = []
        if not os.path.isfile(install_script):
            missing.append(f"install.ps1: {install_script}")
        if not os.path.isfile(cleanup_script):
            missing.append(f"cleanup.ps1: {cleanup_script}")
        if not os.path.isfile(config_file):
            missing.append(f"config.json: {config_file}")
        if missing:
            messagebox.showerror("文件缺失",
                "以下文件不存在，请确保它们与 exe 放在同一目录:\n\n" + "\n".join(missing))
            return

        if not messagebox.askyesno("确认",
                f"将以管理员身份安装计划任务\n执行间隔: 每 {interval} 小时\n是否继续？"):
            return

        self._log(f"正在提权安装计划任务 (间隔 {interval} 小时)...")

        # 生成临时 .ps1 包装脚本，显式传入所有路径
        # 中文路径只出现在文件内容中（UTF-8-BOM 编码），不经过命令行
        ps_code = (
            f'try {{\n'
            f'    & "{install_script}" '
            f'-ScriptPath "{cleanup_script}" '
            f'-ConfigPath "{config_file}" '
            f'-IntervalHours {interval}\n'
            f'}} catch {{\n'
            f'    Write-Host "安装出错: $_" -ForegroundColor Red\n'
            f'}}\n'
            f'Write-Host ""\n'
            f'Read-Host "按回车键关闭此窗口"\n'
        )
        ok = _run_elevated_script(ps_code, visible=True)
        if ok:
            self._log("UAC 提权请求已发送，请在弹出的窗口中完成安装")
            self.status_var.set("安装窗口已打开")
        else:
            self._log("提权失败，可能用户拒绝了 UAC 提示")
        self.after(10000, self.refresh)

    def _uninstall(self):
        """通过 UAC 提权卸载计划任务"""
        if not messagebox.askyesno("确认", "确定要卸载计划任务？"):
            return

        install_script = get_install_script()
        if not os.path.isfile(install_script):
            messagebox.showerror("文件缺失", f"install.ps1 不存在:\n{install_script}")
            return

        self._log("正在提权卸载计划任务...")
        ps_code = (
            f'try {{\n'
            f'    & "{install_script}" -Uninstall\n'
            f'}} catch {{\n'
            f'    Write-Host "卸载出错: $_" -ForegroundColor Red\n'
            f'}}\n'
            f'Write-Host ""\n'
            f'Read-Host "按回车键关闭此窗口"\n'
        )
        ok = _run_elevated_script(ps_code, visible=True)
        if ok:
            self._log("UAC 提权请求已发送")
            self.status_var.set("卸载窗口已打开")
        else:
            self._log("提权失败，可能用户拒绝了 UAC 提示")
        self.after(5000, self.refresh)
