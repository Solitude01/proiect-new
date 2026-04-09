# -*- coding: utf-8 -*-
"""
同步时钟源 GUI 工具
功能：检查并配置 Windows 系统的 NTP 时钟源，强制锁定为指定本地时钟源
支持：Windows 10, Windows 11, Windows Server
"""

import sys
import os
import subprocess
import socket
import threading
import ctypes
import re
from datetime import datetime

import ttkbootstrap as ttk
from ttkbootstrap.constants import *


# ============== 常量 ==============
NTP_SERVER = "10.30.5.100"  # 默认时钟源
NTP_PORT = 123
NTP_SERVERS = {
    "无锡": "10.20.5.1",
    "深圳广州": "10.10.96.45",
    "南通": "10.30.5.100",
    "AI训练平台": "10.30.6.179",
}


# ============== 工具函数 ==============
def is_admin():
    """检测是否以管理员权限运行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def run_command(cmd, shell=True):
    """执行命令并返回 (returncode, stdout, stderr)"""
    try:
        result = subprocess.run(
            cmd, shell=shell, capture_output=True, text=True,
            encoding='gbk', errors='replace', timeout=30
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "命令执行超时"
    except Exception as e:
        return -1, "", str(e)


def check_udp_connectivity(host, port=123, timeout=5):
    """测试 UDP 端口连通性"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        # 尝试连接（UDP 无连接，但可以通过发送空包探测）
        sock.sendto(b"", (host, port))
        # 尝试接收响应（不一定能收到）
        sock.recvfrom(1024)
        sock.close()
        return True, "端口可达"
    except socket.timeout:
        # UDP 超时不代表不可达，可能是防火墙丢弃
        return True, "端口可能可达（UDP无响应，可能正常）"
    except socket.error as e:
        return False, f"连接失败: {e}"
    except Exception as e:
        return False, f"检查失败: {e}"


def format_output(text):
    """格式化命令输出"""
    return text.strip() if text else "(无输出)"


# ============== 主应用类 ==============
class ClockSyncApp:
    def __init__(self, root):
        self.root = root
        self.root.title("同步时钟源配置工具")
        self.root.geometry("800x700")

        # 检查管理员权限（在 build_ui 之后设置状态）
        self.is_admin = is_admin()

        self.build_ui()
        self.log("=== 同步时钟源配置工具已启动 ===")
        self.log(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log("")

        # 设置管理员状态
        if self.is_admin:
            self.admin_label.config(text="✓ 当前以管理员权限运行", bootstyle="success")
        else:
            self.show_admin_warning()

    def show_admin_warning(self):
        """显示管理员权限警告"""
        warning_win = ttk.Toplevel(self.root)
        warning_win.title("权限警告")
        warning_win.geometry("400x200")
        warning_win.resizable(False, False)

        frame = ttk.Frame(warning_win, padding=20)
        frame.pack(fill=BOTH, expand=True)

        ttk.Label(
            frame,
            text="⚠ 未以管理员权限运行！",
            font=("Arial", 14, "bold"),
            bootstyle="warning"
        ).pack(pady=(0, 10))

        ttk.Label(
            frame,
            text="本工具需要管理员权限才能配置 Windows 时间服务。\n\n"
                 "请关闭本程序，右键点击程序选择「以管理员身份运行」\n"
                 "或联系系统管理员。",
            wraplength=350,
            justify=CENTER
        ).pack(pady=10)

        ttk.Button(
            frame, text="我知道了", bootstyle="warning",
            command=warning_win.destroy
        ).pack()

        # 模态
        warning_win.transient(self.root)
        warning_win.grab_set()

    def build_ui(self):
        """构建 UI"""
        # 主容器
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=BOTH, expand=True)

        # ---- 顶部状态栏 ----
        status_frame = ttk.LabelFrame(main_frame, text="系统状态")
        status_inner = ttk.Frame(status_frame, padding=10)
        status_inner.pack(fill=X)
        status_frame.pack(fill=X, pady=(0, 10))

        # 管理员状态
        admin_row = ttk.Frame(status_inner)
        admin_row.pack(fill=X, pady=2)
        ttk.Label(admin_row, text="权限状态: ", width=12, anchor=W).pack(side=LEFT)
        self.admin_label = ttk.Label(admin_row, text="✗ 非管理员", bootstyle="danger")
        self.admin_label.pack(side=LEFT)

        # 当前同步源
        source_row = ttk.Frame(status_inner)
        source_row.pack(fill=X, pady=2)
        ttk.Label(source_row, text="当前同步源: ", width=12, anchor=W).pack(side=LEFT)
        self.source_label = ttk.Label(source_row, text="点击「检测状态」查看", bootstyle="info")
        self.source_label.pack(side=LEFT)

        # 服务状态
        service_row = ttk.Frame(status_inner)
        service_row.pack(fill=X, pady=2)
        ttk.Label(service_row, text="w32time服务: ", width=12, anchor=W).pack(side=LEFT)
        self.service_label = ttk.Label(service_row, text="未知", bootstyle="secondary")
        self.service_label.pack(side=LEFT)

        # 南通时钟源连通性
        conn_row = ttk.Frame(status_inner)
        conn_row.pack(fill=X, pady=2)
        ttk.Label(conn_row, text="南通时钟源: ", width=12, anchor=W).pack(side=LEFT)
        self.conn_label = ttk.Label(conn_row, text="未检查", bootstyle="secondary")
        self.conn_label.pack(side=LEFT)

        # 时间偏移
        offset_row = ttk.Frame(status_inner)
        offset_row.pack(fill=X, pady=2)
        ttk.Label(offset_row, text="时间偏移: ", width=12, anchor=W).pack(side=LEFT)
        self.offset_label = ttk.Label(offset_row, text="未测量", bootstyle="secondary")
        self.offset_label.pack(side=LEFT)

        # ---- 操作按钮区 ----
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=X, pady=10)

        ttk.Button(
            btn_frame, text="🔍 检测状态",
            command=self.check_status,
            bootstyle="info",
            width=14
        ).pack(side=LEFT, padx=5)

        ttk.Button(
            btn_frame, text="🌐 检查连通性",
            command=self.check_connectivity,
            bootstyle="info",
            width=14
        ).pack(side=LEFT, padx=5)

        ttk.Button(
            btn_frame, text="⏱ 测量偏移",
            command=self.measure_offset,
            bootstyle="info",
            width=14
        ).pack(side=LEFT, padx=5)

        ttk.Button(
            btn_frame, text="⚙ 配置时钟源",
            command=self.configure_ntp,
            bootstyle="primary",
            width=18
        ).pack(side=LEFT, padx=5)
        self.config_btn_label = ttk.Label(btn_frame, text="(AI训练平台)", bootstyle="info")
        self.config_btn_label.pack(side=LEFT, padx=2)

        ttk.Button(
            btn_frame, text="🔄 强制同步",
            command=self.force_sync,
            bootstyle="warning",
            width=14
        ).pack(side=LEFT, padx=5)

        # ---- 时钟源选择 ----
        select_frame = ttk.LabelFrame(main_frame, text="时钟源选择")
        select_inner = ttk.Frame(select_frame, padding=10)
        select_inner.pack(fill=X)
        select_frame.pack(fill=X, pady=(0, 10))

        select_row = ttk.Frame(select_inner)
        select_row.pack(fill=X)

        ttk.Label(select_row, text="选择时钟源: ").pack(side=LEFT, padx=5)
        self.server_var = ttk.StringVar(value="AI训练平台")
        for name, ip in NTP_SERVERS.items():
            ttk.Radiobutton(
                select_row, text=f"{name} ({ip})",
                variable=self.server_var, value=name,
                command=self.on_server_change
            ).pack(side=LEFT, padx=5)

        self.selected_ip_label = ttk.Label(
            select_row,
            text=f"当前选择: {NTP_SERVERS.get('AI训练平台', 'N/A')}",
            bootstyle="info"
        )
        self.selected_ip_label.pack(side=LEFT, padx=10)

        # ---- 日志区 ----
        log_frame = ttk.LabelFrame(main_frame, text="操作日志")
        log_inner_frame = ttk.Frame(log_frame, padding=5)
        log_frame.pack(fill=BOTH, expand=True)
        log_inner_frame.pack(fill=BOTH, expand=True)

        # 使用 Frame + Scrollbar + Text
        log_inner = ttk.Frame(log_inner_frame)
        log_inner.pack(fill=BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_inner)
        scrollbar.pack(side=RIGHT, fill=Y)

        self.log_display = ttk.Text(
            log_inner,
            wrap=WORD,
            yscrollcommand=scrollbar.set,
            font=("Consolas", 9),
            state=DISABLED,
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white"
        )
        self.log_display.pack(fill=BOTH, expand=True)
        scrollbar.config(command=self.log_display.yview)

        # 配置文本标签颜色
        self.log_display.tag_config("info", foreground="#4fc3f7")
        self.log_display.tag_config("success", foreground="#66bb6a")
        self.log_display.tag_config("warning", foreground="#ffa726")
        self.log_display.tag_config("error", foreground="#ef5350")
        self.log_display.tag_config("cmd", foreground="#ab47bc")

    def on_server_change(self):
        """时钟源切换"""
        server_name = self.server_var.get()
        ip = NTP_SERVERS.get(server_name, "")
        self.selected_ip_label.config(text=f"当前选择: {ip}")
        self.config_btn_label.config(text=f"({server_name})")

    def log(self, message, tag=None):
        """添加日志"""
        self.log_display.config(state=NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}\n"
        if tag:
            self.log_display.insert(END, line, tag)
        else:
            self.log_display.insert(END, line)
        self.log_display.see(END)
        self.log_display.config(state=DISABLED)

    def set_button_states(self, normal=True):
        """设置按钮可用状态"""
        state = NORMAL if normal else DISABLED
        for btn in self.root.winfo_children():
            for child in btn.winfo_children():
                if isinstance(child, ttk.Button):
                    child.config(state=state)

    # ---- 功能方法 ----

    def check_status(self):
        """检测当前状态"""
        self.log("正在检测系统状态...", "info")
        threading.Thread(target=self._check_status_thread, daemon=True).start()

    def _check_status_thread(self):
        """后台检测状态"""
        # 1. 检查同步源
        rc, out, err = run_command('w32tm /query /source')
        if rc == 0:
            source = out.strip()
            self.root.after(0, lambda: self.source_label.config(
                text=source,
                bootstyle="success" if NTP_SERVER in source else "warning"
            ))
            self.log(f"当前同步源: {source}", "info")
        else:
            self.root.after(0, lambda: self.source_label.config(
                text="获取失败", bootstyle="danger"
            ))
            self.log(f"获取同步源失败: {err.strip()}", "error")

        # 2. 检查服务状态
        rc, out, err = run_command('sc query w32time')
        if rc == 0:
            if "RUNNING" in out:
                self.root.after(0, lambda: self.service_label.config(
                    text="运行中", bootstyle="success"
                ))
                self.log("w32time 服务: 运行中", "success")
            elif "STOPPED" in out:
                self.root.after(0, lambda: self.service_label.config(
                    text="已停止", bootstyle="warning"
                ))
                self.log("w32time 服务: 已停止", "warning")
            else:
                self.root.after(0, lambda: self.service_label.config(
                    text="未知状态", bootstyle="secondary"
                ))
        else:
            self.root.after(0, lambda: self.service_label.config(
                text="查询失败", bootstyle="danger"
            ))
            self.log(f"查询服务状态失败: {err.strip()}", "error")

        # 3. 检查详细状态
        rc, out, err = run_command('w32tm /query /status')
        if rc == 0:
            self.log("\n=== 详细同步状态 ===", "info")
            for line in out.strip().split('\n'):
                self.log(f"  {line}")
        else:
            self.log(f"获取详细状态失败: {err.strip()}", "error")

        # 4. 检查注册表
        rc, out, err = run_command(
            'reg query HKLM\\SYSTEM\\CurrentControlSet\\Services\\W32Time\\Parameters /v NtpServer'
        )
        if rc == 0:
            self.log("\n=== 注册表 NTP 配置 ===", "info")
            for line in out.strip().split('\n'):
                self.log(f"  {line}")

        self.log("\n✓ 状态检测完成", "success")

    def check_connectivity(self):
        """检查连通性"""
        server_name = self.server_var.get()
        ip = NTP_SERVERS.get(server_name, "")
        self.log(f"正在检查到 {server_name} ({ip}) 的 UDP {NTP_PORT} 端口连通性...", "info")
        threading.Thread(target=self._check_connectivity_thread, args=(ip,), daemon=True).start()

    def _check_connectivity_thread(self, ip):
        """后台检查连通性"""
        ok, msg = check_udp_connectivity(ip, NTP_PORT, timeout=5)
        if ok:
            self.root.after(0, lambda: self.conn_label.config(
                text=f"可达 ({msg})", bootstyle="success"
            ))
            self.log(f"✓ {ip}:{NTP_PORT} 连通性检查通过: {msg}", "success")
        else:
            self.root.after(0, lambda: self.conn_label.config(
                text=f"不可达 ({msg})", bootstyle="danger"
            ))
            self.log(f"✗ {ip}:{NTP_PORT} 连通性检查失败: {msg}", "error")
            self.log("  请检查防火墙是否放行 UDP 123 端口", "warning")

    def measure_offset(self):
        """测量时间偏移"""
        server_name = self.server_var.get()
        ip = NTP_SERVERS.get(server_name, "")
        self.log(f"正在测量与 {ip} 的时间偏移...", "info")
        threading.Thread(target=self._measure_offset_thread, args=(ip,), daemon=True).start()

    def _measure_offset_thread(self, ip):
        """后台测量偏移"""
        # 先确保服务运行
        run_command('sc start w32time')

        rc, out, err = run_command(
            f'w32tm /stripchart /computer:{ip} /samples:5 /dataonly'
        )
        if rc == 0:
            lines = out.strip().split('\n')
            offsets = []
            has_timeout = False
            for line in lines:
                # 格式1: d:+00.0032425s 或 d:-00.0012345s
                match = re.search(r'd:([+-]\d+\.\d+)s', line)
                if not match:
                    # 格式2: 14:49:58, -20.1567244s（中文系统输出）
                    match = re.search(r',\s*([+-]\d+\.\d+)s', line)
                if match:
                    offsets.append(float(match.group(1)))
                # 检测超时错误
                if '0x800705B4' in line or '超时' in line:
                    has_timeout = True

            self.log("\n=== 时间偏移采样 ===", "info")
            for line in lines:
                self.log(f"  {line.strip()}")

            if has_timeout:
                self.log(f"\n⚠ 与 {ip} 的 NTP 通信超时（错误 0x800705B4）", "error")
                self.log("  可能原因：防火墙阻止、跨网段不可达、或时钟源不在线", "warning")
                self.log("  建议：先使用「检查连通性」确认 UDP 123 端口可达", "warning")
                self.root.after(0, lambda: self.offset_label.config(
                    text="超时/不可达", bootstyle="danger"
                ))
            elif offsets:
                avg_offset = sum(offsets) / len(offsets)
                max_offset = max(abs(o) for o in offsets)
                self.log(f"\n平均偏移: {avg_offset*1000:.3f} ms", "info")
                self.log(f"最大偏移: {max_offset*1000:.3f} ms", "info")

                if max_offset < 0.05:
                    status = "优秀 (< 50ms)"
                    tag = "success"
                elif max_offset < 0.5:
                    status = "良好 (< 500ms)"
                    tag = "info"
                elif max_offset < 1.0:
                    status = "可接受 (< 1s)"
                    tag = "warning"
                else:
                    status = "较差 (>= 1s)"
                    tag = "error"

                self.root.after(0, lambda: self.offset_label.config(
                    text=f"{avg_offset*1000:.1f} ms ({status})",
                    bootstyle="success" if max_offset < 0.05 else
                              ("warning" if max_offset < 1.0 else "danger")
                ))
                self.log(f"同步质量: {status}", tag)
            else:
                self.log("未能解析偏移数据", "warning")
        else:
            self.log(f"测量失败: {err.strip()}", "error")

    def configure_ntp(self):
        """配置 NTP 服务器"""
        server_name = self.server_var.get()
        ip = NTP_SERVERS.get(server_name, "")

        if not is_admin():
            self.log("✗ 需要管理员权限才能配置 NTP 服务器", "error")
            return

        self.log(f"正在配置 NTP 服务器为 {server_name} ({ip})...", "info")
        threading.Thread(target=self._configure_ntp_thread, args=(ip, server_name), daemon=True).start()

    def _configure_ntp_thread(self, ip, server_name):
        """后台配置 NTP"""
        # 1. 配置 NTP 服务器
        cmd = f'w32tm /config /manualpeerlist:"{ip},0x9" /syncfromflags:manual /reliable:YES /update'
        rc, out, err = run_command(cmd)
        if rc == 0:
            self.log(f"✓ NTP 配置成功: {out.strip()}", "success")
        else:
            self.log(f"✗ NTP 配置失败: {err.strip()}", "error")
            self.root.after(0, lambda: None)
            return

        # 2. 重启 w32time 服务
        self.log("正在重启 w32time 服务...", "info")

        # 设置自动启动
        rc, out, err = run_command('sc config w32time start= auto')
        if rc == 0:
            self.log(f"  设置自动启动: {out.strip()}", "success")

        # 停止服务
        rc, out, err = run_command('net stop w32time')
        if rc == 0:
            self.log(f"  停止服务: {out.strip()}", "info")
        elif "没有启动" not in err and "3521" not in err:
            self.log(f"  停止服务警告: {err.strip()}", "warning")

        # 启动服务
        rc, out, err = run_command('net start w32time')
        if rc == 0:
            self.log(f"  启动服务: {out.strip()}", "success")
        else:
            self.log(f"  启动服务失败: {err.strip()}", "error")

        # 3. 强制同步
        self.log("正在强制同步...", "info")
        rc, out, err = run_command('w32tm /resync /rediscover')
        if rc == 0:
            self.log(f"✓ 强制同步成功: {out.strip()}", "success")
        else:
            self.log(f"⚠ 强制同步返回: {err.strip()}", "warning")

        # 4. 验证配置
        self.log("\n=== 验证配置 ===", "info")
        rc, out, err = run_command('w32tm /query /source')
        if rc == 0:
            source = out.strip()
            self.log(f"  当前同步源: {source}", "info")
            if ip in source:
                self.log(f"  ✓ 已成功锁定到 {server_name} 时钟源", "success")
            else:
                self.log(f"  ⚠ 同步源未指向预期服务器", "warning")

        self.log("\n✓ NTP 配置完成！", "success")

        # 刷新状态
        self.root.after(1000, self.check_status)

    def force_sync(self):
        """强制同步"""
        if not is_admin():
            self.log("✗ 需要管理员权限", "error")
            return

        self.log("正在强制同步时间...", "info")
        threading.Thread(target=self._force_sync_thread, daemon=True).start()

    def _force_sync_thread(self):
        """后台强制同步"""
        rc, out, err = run_command('w32tm /resync /rediscover')
        if rc == 0:
            self.log(f"✓ 同步成功: {out.strip()}", "success")
        else:
            self.log(f"✗ 同步失败: {err.strip()}", "error")

        # 同步后测量偏移
        server_name = self.server_var.get()
        ip = NTP_SERVERS.get(server_name, "")
        self.log(f"\n同步后测量与 {ip} 的偏移...", "info")
        rc, out, err = run_command(
            f'w32tm /stripchart /computer:{ip} /samples:3 /dataonly'
        )
        if rc == 0:
            lines = out.strip().split('\n')
            offsets = []
            has_timeout = False
            self.log("\n=== 同步后偏移采样 ===", "info")
            for line in lines:
                self.log(f"  {line.strip()}")
                # 格式1: d:+00.0032425s
                match = re.search(r'd:([+-]\d+\.\d+)s', line)
                if not match:
                    # 格式2: 14:49:58, -20.1567244s
                    match = re.search(r',\s*([+-]\d+\.\d+)s', line)
                if match:
                    offsets.append(float(match.group(1)))
                if '0x800705B4' in line or '超时' in line:
                    has_timeout = True

            if has_timeout:
                self.log(f"\n⚠ 与 {ip} 的 NTP 通信超时", "error")
            elif offsets:
                avg = sum(offsets) / len(offsets)
                self.log(f"\n同步后平均偏移: {avg*1000:.3f} ms", "success")
                self.root.after(0, lambda: self.offset_label.config(
                    text=f"{avg*1000:.1f} ms (同步后)",
                    bootstyle="success" if abs(avg) < 0.05 else "info"
                ))
        else:
            self.log(f"偏移测量失败: {err.strip()}", "error")


# ============== 主函数 ==============
def main():
    # 检查 Windows 系统
    if sys.platform != 'win32':
        print("错误: 本工具仅支持 Windows 系统")
        sys.exit(1)

    root = ttk.Window(
        title="同步时钟源配置工具",
        themename="cosmo",
        resizable=(True, True)
    )
    app = ClockSyncApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
