"""工具函数：配置读写、subprocess封装、路径解析、权限检查"""

import json
import os
import sys
import subprocess
import ctypes
import threading
import queue


def get_project_root():
    """获取项目根目录，支持 PyInstaller frozen 模式"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后，exe 所在目录即项目根目录
        return os.path.dirname(sys.executable)
    else:
        # 开发模式，gui/ 的上级目录
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_config_path():
    return os.path.join(get_project_root(), "config.json")


def get_cleanup_script():
    return os.path.join(get_project_root(), "cleanup.ps1")


def get_install_script():
    return os.path.join(get_project_root(), "install.ps1")


def load_config(path=None):
    """读取 config.json，返回 dict"""
    if path is None:
        path = get_config_path()
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def save_config(config, path=None):
    """保存 config.json"""
    if path is None:
        path = get_config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def is_admin():
    """检查当前进程是否拥有管理员权限"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def run_as_admin(script_path, arguments=""):
    """通过 UAC 提权运行 PowerShell 脚本"""
    params = f'-ExecutionPolicy Bypass -NoProfile -File "{script_path}" {arguments}'
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "powershell.exe", params, None, 1  # SW_SHOWNORMAL
        )
        return ret > 32  # ShellExecute 返回值 > 32 表示成功
    except Exception:
        return False


def _decode_line(raw_line):
    """智能解码一行字节：优先 UTF-8，失败则回退 GBK"""
    try:
        return raw_line.decode("utf-8")
    except (UnicodeDecodeError, AttributeError):
        pass
    try:
        return raw_line.decode("gbk")
    except (UnicodeDecodeError, AttributeError):
        pass
    return raw_line.decode("utf-8", errors="replace")


def run_ps_script(script_path, config_path=None, on_output=None, stop_event=None):
    """在子线程中运行 PowerShell 脚本，实时捕获输出。

    Args:
        script_path: ps1 脚本路径
        config_path: 配置文件路径（可选）
        on_output: 回调函数 (line: str) -> None，每行输出都调用
        stop_event: threading.Event，设置后终止进程
    Returns:
        returncode
    """
    # 先检查脚本文件是否存在
    if not os.path.isfile(script_path):
        if on_output:
            on_output(f"[ERROR] 脚本文件不存在: {script_path}")
        return -1

    config_arg = ""
    if config_path:
        config_arg = f' -ConfigPath "{config_path}"'

    args = [
        "powershell.exe",
        "-ExecutionPolicy", "Bypass",
        "-NoProfile",
        "-Command",
        f'& "{script_path}"{config_arg}',
    ]

    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            # 不指定 encoding，读取原始字节后手动解码
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception as e:
        if on_output:
            on_output(f"[ERROR] 启动脚本失败: {e}")
        return -1

    try:
        for raw_line in proc.stdout:
            if stop_event and stop_event.is_set():
                proc.terminate()
                if on_output:
                    on_output("[WARN] 用户终止了执行")
                break
            line = _decode_line(raw_line).rstrip("\n\r")
            if line and on_output:
                on_output(line)
        proc.wait()
    except Exception as e:
        if on_output:
            on_output(f"[ERROR] 执行异常: {e}")
        try:
            proc.kill()
        except Exception:
            pass
        return -1

    return proc.returncode


def run_ps_command(cmd):
    """运行 PowerShell 命令并返回输出（字节自动解码，合并 stderr）"""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        output = _decode_line(result.stdout).strip()
        return output, result.returncode
    except Exception as e:
        return str(e), -1


def run_as_admin_command(ps_command):
    """通过 UAC 提权运行 PowerShell 命令，返回是否成功发起提权"""
    params = f'-ExecutionPolicy Bypass -NoProfile -Command "& {{{ps_command}}}"'
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "powershell.exe", params, None, 0  # SW_HIDE
        )
        return ret > 32
    except Exception:
        return False


class ScriptRunner:
    """封装脚本执行的线程管理，配合 Queue 实现主线程安全的日志更新。"""

    def __init__(self):
        self.output_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.thread = None
        self.running = False
        self.return_code = None

    def start(self, script_path, config_path=None):
        if self.running:
            return False
        self.stop_event.clear()
        self.running = True
        self.return_code = None

        def worker():
            rc = run_ps_script(
                script_path, config_path,
                on_output=lambda line: self.output_queue.put(line),
                stop_event=self.stop_event,
            )
            self.return_code = rc
            self.running = False
            self.output_queue.put(None)  # sentinel

        self.thread = threading.Thread(target=worker, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.stop_event.set()

    def poll_output(self):
        """非阻塞地从队列中取出所有待处理行，返回 list[str|None]"""
        lines = []
        while True:
            try:
                item = self.output_queue.get_nowait()
                lines.append(item)
            except queue.Empty:
                break
        return lines
