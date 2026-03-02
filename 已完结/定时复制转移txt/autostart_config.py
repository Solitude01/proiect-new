#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
开机自启动配置工具
用于配置TXT文件同步工具的开机自启动
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import configparser

try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False
    print("警告: 此脚本只能在Windows系统上运行")


class AutoStartManager:
    """开机自启动管理器"""

    def __init__(self):
        self.app_name = "TXT文件同步工具"
        self.registry_key = r"Software\Microsoft\Windows\CurrentVersion\Run"

    def get_startup_path(self):
        """获取当前的开机启动路径"""
        if not HAS_WINREG:
            return None

        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.registry_key, 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, self.app_name)
            winreg.CloseKey(key)
            return value
        except FileNotFoundError:
            return None
        except Exception as e:
            print(f"读取开机启动项失败: {e}")
            return None

    def set_startup_path(self, exe_path):
        """设置开机启动路径"""
        if not HAS_WINREG:
            return False

        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.registry_key, 0, winreg.KEY_WRITE)
            winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ, exe_path)
            winreg.CloseKey(key)
            return True
        except Exception as e:
            print(f"设置开机启动项失败: {e}")
            return False

    def remove_startup(self):
        """移除开机启动项"""
        if not HAS_WINREG:
            return False

        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.registry_key, 0, winreg.KEY_WRITE)
            winreg.DeleteValue(key, self.app_name)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            return True  # 本来就不存在
        except Exception as e:
            print(f"移除开机启动项失败: {e}")
            return False

    def is_startup_enabled(self):
        """检查是否已启用开机启动"""
        return self.get_startup_path() is not None


class AutoStartGUI:
    """开机自启动配置界面"""

    def __init__(self, root):
        self.root = root
        self.root.title("开机自启动配置")
        self.root.geometry("500x400")
        self.root.minsize(400, 300)

        self.manager = AutoStartManager()
        self.exe_path_var = tk.StringVar()

        self.create_widgets()
        self.load_current_settings()

    def create_widgets(self):
        """创建界面组件"""
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 标题
        title_label = ttk.Label(
            main_frame,
            text="🎯 TXT文件同步工具 - 开机自启动配置",
            font=("微软雅黑", 14, "bold")
        )
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))

        # 当前状态
        status_frame = ttk.LabelFrame(main_frame, text="📊 当前状态", padding="10")
        status_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 20))

        self.status_var = tk.StringVar(value="检查中...")
        status_label = ttk.Label(status_frame, textvariable=self.status_var, font=("微软雅黑", 10))
        status_label.grid(row=0, column=0, sticky=tk.W)

        # 执行文件路径设置
        path_frame = ttk.LabelFrame(main_frame, text="📁 执行文件路径", padding="10")
        path_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 20))

        ttk.Label(path_frame, text="EXE文件路径:", font=("微软雅黑", 10)).grid(
            row=0, column=0, sticky=tk.W, pady=5
        )

        path_entry = ttk.Entry(
            path_frame, textvariable=self.exe_path_var, width=50, font=("Consolas", 9)
        )
        path_entry.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)

        ttk.Button(path_frame, text="📁 浏览", command=self.browse_exe, width=10).grid(
            row=1, column=1, padx=(10, 0), pady=5
        )

        # 操作按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=(0, 20))

        self.enable_btn = ttk.Button(
            button_frame, text="✅ 启用开机启动", command=self.enable_startup, width=20
        )
        self.enable_btn.grid(row=0, column=0, padx=5)

        self.disable_btn = ttk.Button(
            button_frame, text="❌ 禁用开机启动", command=self.disable_startup, width=20
        )
        self.disable_btn.grid(row=0, column=1, padx=5)

        # 说明文本
        info_frame = ttk.LabelFrame(main_frame, text="ℹ️ 说明", padding="10")
        info_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E))

        info_text = """
1. 启用开机启动后，电脑启动时会自动运行TXT文件同步工具
2. 建议将工具封装为exe文件后使用此功能
3. 工具启动后会最小化到系统托盘，不会显示主界面
4. 可以通过系统托盘图标右键菜单控制工具

使用方法：
• 点击"浏览"选择您的TXT文件同步工具exe文件
• 点击"启用开机启动"设置自动启动
• 点击"禁用开机启动"取消自动启动
"""
        info_label = ttk.Label(
            info_frame,
            text=info_text.strip(),
            font=("微软雅黑", 9),
            foreground="#666666"
        )
        info_label.grid(row=0, column=0)

        # 配置列权重
        main_frame.columnconfigure(0, weight=1)

    def load_current_settings(self):
        """加载当前设置"""
        current_path = self.manager.get_startup_path()

        if current_path:
            self.exe_path_var.set(current_path)
            self.status_var.set(f"✅ 已启用开机启动\n路径: {current_path}")
            self.enable_btn.configure(state=tk.DISABLED)
        else:
            self.status_var.set("❌ 未启用开机启动")
            self.disable_btn.configure(state=tk.DISABLED)

    def browse_exe(self):
        """浏览exe文件"""
        file_path = tk.filedialog.askopenfilename(
            title="选择TXT文件同步工具exe文件",
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")]
        )
        if file_path:
            self.exe_path_var.set(file_path)
            self.update_buttons()

    def enable_startup(self):
        """启用开机启动"""
        exe_path = self.exe_path_var.get().strip()

        if not exe_path:
            messagebox.showwarning("警告", "请选择exe文件路径")
            return

        if not os.path.exists(exe_path):
            messagebox.showwarning("警告", "指定的文件不存在")
            return

        if self.manager.set_startup_path(exe_path):
            messagebox.showinfo("成功", "✅ 已启用开机启动")
            self.load_current_settings()
        else:
            messagebox.showerror("错误", "❌ 启用开机启动失败")

    def disable_startup(self):
        """禁用开机启动"""
        if self.manager.remove_startup():
            messagebox.showinfo("成功", "✅ 已禁用开机启动")
            self.load_current_settings()
        else:
            messagebox.showerror("错误", "❌ 禁用开机启动失败")

    def update_buttons(self):
        """更新按钮状态"""
        exe_path = self.exe_path_var.get().strip()
        current_path = self.manager.get_startup_path()

        if exe_path and exe_path != current_path:
            self.enable_btn.configure(state=tk.NORMAL)
        else:
            self.enable_btn.configure(state=tk.DISABLED)


def main():
    """主函数"""
    if not HAS_WINREG:
        print("此脚本只能在Windows系统上运行")
        return

    root = tk.Tk()
    app = AutoStartGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()