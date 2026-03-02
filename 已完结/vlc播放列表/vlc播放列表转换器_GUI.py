#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VLC播放列表转换器 - GUI版本
支持处理Markdown文件和Excel文件，自动清理格式并生成M3U播放列表
"""

import os
import sys
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import pandas as pd
from urllib.parse import urlparse, urlunparse


class VLCPlaylistConverter:
    def __init__(self, root):
        self.root = root
        self.root.title("VLC播放列表转换器")
        self.root.geometry("800x700")
        self.root.resizable(True, True)

        # 数据存储
        self.input_file = ""
        self.output_file = ""
        self.processed_data = []

        self.create_widgets()

    def create_widgets(self):
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 配置行列权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        # 标题
        title_label = ttk.Label(main_frame, text="VLC播放列表转换器", font=("微软雅黑", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))

        # 文件选择区域
        ttk.Label(main_frame, text="输入文件:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.input_entry = ttk.Entry(main_frame, width=50)
        self.input_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=5, padx=(5, 0))
        ttk.Button(main_frame, text="浏览...", command=self.browse_input).grid(row=1, column=2, pady=5, padx=(5, 0))

        ttk.Label(main_frame, text="输出文件:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.output_entry = ttk.Entry(main_frame, width=50)
        self.output_entry.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=5, padx=(5, 0))
        ttk.Button(main_frame, text="浏览...", command=self.browse_output).grid(row=2, column=2, pady=5, padx=(5, 0))

        # 文件类型选择
        ttk.Label(main_frame, text="文件类型:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.file_type = tk.StringVar(value="excel")
        ttk.Radiobutton(main_frame, text="Markdown (.md)", variable=self.file_type, value="markdown").grid(row=3, column=1, sticky=tk.W, padx=(5, 0))
        ttk.Radiobutton(main_frame, text="Excel (.xlsx/.xls)", variable=self.file_type, value="excel").grid(row=3, column=1, sticky=tk.E)

        # 格式清理选项
        ttk.Label(main_frame, text="格式清理:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.clean_spaces = tk.BooleanVar(value=True)
        self.clean_newlines = tk.BooleanVar(value=True)
        ttk.Checkbutton(main_frame, text="删除多余空格", variable=self.clean_spaces).grid(row=4, column=1, sticky=tk.W, padx=(5, 0))
        ttk.Checkbutton(main_frame, text="删除换行符", variable=self.clean_newlines).grid(row=4, column=1, sticky=tk.E)

        # Excel列配置（仅当选择Excel时显示）
        self.excel_frame = ttk.LabelFrame(main_frame, text="Excel列配置", padding="5")
        self.excel_frame.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        self.excel_frame.grid_remove()  # 默认隐藏

        ttk.Label(self.excel_frame, text="监控点名称列:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.name_column = ttk.Entry(self.excel_frame, width=10)
        self.name_column.insert(0, "A")
        self.name_column.grid(row=0, column=1, padx=5)

        ttk.Label(self.excel_frame, text="流地址列:").grid(row=0, column=2, sticky=tk.W, padx=5)
        self.url_column = ttk.Entry(self.excel_frame, width=10)
        self.url_column.insert(0, "B")
        self.url_column.grid(row=0, column=3, padx=5)

        # 处理按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=6, column=0, columnspan=3, pady=15)

        self.process_btn = ttk.Button(button_frame, text="开始转换", command=self.process_file)
        self.process_btn.grid(row=0, column=0, padx=5)

        ttk.Button(button_frame, text="清空", command=self.clear_all).grid(row=0, column=1, padx=5)
        ttk.Button(button_frame, text="退出", command=self.root.quit).grid(row=0, column=2, padx=5)

        # 进度显示
        ttk.Label(main_frame, text="处理进度:").grid(row=7, column=0, sticky=tk.W, pady=5)
        self.progress = ttk.Progressbar(main_frame, mode='determinate', length=400)
        self.progress.grid(row=7, column=1, sticky=(tk.W, tk.E), pady=5, padx=(5, 0))

        # 日志显示区域
        ttk.Label(main_frame, text="处理日志:").grid(row=8, column=0, sticky=tk.W, pady=5)
        log_frame = ttk.Frame(main_frame)
        log_frame.grid(row=9, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, width=80)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 配置权重
        main_frame.rowconfigure(9, weight=1)
        main_frame.columnconfigure(1, weight=1)

        # 绑定文件类型变化事件
        self.file_type.trace('w', self.on_file_type_change)

    def on_file_type_change(self, *args):
        """文件类型改变时的处理"""
        if self.file_type.get() == "excel":
            self.excel_frame.grid()
        else:
            self.excel_frame.grid_remove()

    def browse_input(self):
        """浏览输入文件"""
        file_types = [
            ("所有支持的文件", "*.md;*.xlsx;*.xls;*.txt"),
            ("Excel文件", "*.xlsx;*.xls"),
            ("Markdown文件", "*.md"),
            ("文本文件", "*.txt"),
            ("所有文件", "*.*")
        ]
        filename = filedialog.askopenfilename(
            title="选择输入文件",
            filetypes=file_types
        )
        if filename:
            self.input_entry.delete(0, tk.END)
            self.input_entry.insert(0, filename)

            # 自动生成输出文件名
            output_name = os.path.splitext(filename)[0] + "_processed.m3u"
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, output_name)

    def browse_output(self):
        """浏览输出文件"""
        filename = filedialog.asksaveasfilename(
            title="选择输出文件",
            defaultextension=".m3u",
            filetypes=[("M3U播放列表", "*.m3u"), ("所有文件", "*.*")]
        )
        if filename:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, filename)

    def log(self, message):
        """在日志区域添加消息"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update()

    def clean_text(self, text):
        """清理文本格式"""
        if not text:
            return ""

        # 删除换行符
        if self.clean_newlines.get():
            text = text.replace('\n', '').replace('\r', '')

        # 删除多余空格
        if self.clean_spaces.get():
            # 删除首尾空格
            text = text.strip()
            # 将多个连续空格替换为单个空格
            text = re.sub(r'\s+', ' ', text)

        return text

    def process_markdown(self, file_path):
        """处理Markdown文件"""
        processed_lines = []
        line_count = 0
        processed_count = 0

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line_count += 1
                    line = self.clean_text(line)

                    # 跳过空行
                    if not line:
                        continue

                    # 查找 'rtsp://' 作为名称和 URL 的分割点
                    split_index = line.find("rtsp://")

                    if split_index == -1:
                        self.log(f"警告: 第 {line_count} 行格式不符，已跳过: {line}")
                        continue

                    # 提取名称和 URL
                    name = self.clean_text(line[:split_index])
                    full_url = self.clean_text(line[split_index:])

                    try:
                        # 解析并简化 URL
                        parsed_url = urlparse(full_url)

                        # 重建 netloc (网络位置)，只使用 username, password 和 hostname
                        new_netloc = parsed_url.hostname
                        if parsed_url.username:
                            if parsed_url.password:
                                new_netloc = f"{parsed_url.username}:{parsed_url.password}@{new_netloc}"
                            else:
                                new_netloc = f"{parsed_url.username}@{new_netloc}"

                        # 重建 URL，只保留 scheme(rtsp) 和 new_netloc
                        new_url_parts = (parsed_url.scheme, new_netloc, '', '', '', '')
                        final_url = urlunparse(new_url_parts)

                        processed_lines.append((name, final_url))
                        processed_count += 1

                    except Exception as e:
                        self.log(f"错误: 第 {line_count} 行 URL 解析失败: {full_url} - {e}")
                        continue

            return processed_lines, line_count, processed_count

        except Exception as e:
            raise Exception(f"处理Markdown文件时发生错误: {e}")

    def process_excel(self, file_path):
        """处理Excel文件"""
        processed_lines = []
        line_count = 0
        processed_count = 0

        try:
            # 读取Excel文件，支持.xls和.xlsx格式
            file_extension = os.path.splitext(file_path)[1].lower()
            if file_extension == '.xls':
                # 对于.xls文件，使用xlrd引擎
                df = pd.read_excel(file_path, engine='xlrd')
            else:
                # 对于.xlsx文件，使用openpyxl引擎
                df = pd.read_excel(file_path, engine='openpyxl')

            # 获取列索引
            name_col = self.name_column.get().upper()
            url_col = self.url_column.get().upper()

            # 转换列字母为数字索引
            name_idx = ord(name_col) - ord('A')
            url_idx = ord(url_col) - ord('A')

            if name_idx < 0 or name_idx >= len(df.columns):
                raise Exception(f"监控点名称列 '{name_col}' 不存在")
            if url_idx < 0 or url_idx >= len(df.columns):
                raise Exception(f"流地址列 '{url_col}' 不存在")

            # 处理每一行
            for idx, row in df.iterrows():
                line_count += 1

                try:
                    name = str(row.iloc[name_idx]) if pd.notna(row.iloc[name_idx]) else ""
                    url = str(row.iloc[url_idx]) if pd.notna(row.iloc[url_idx]) else ""

                    name = self.clean_text(name)
                    url = self.clean_text(url)

                    # 跳过空行
                    if not name or not url:
                        self.log(f"警告: 第 {line_count} 行数据不完整，已跳过")
                        continue

                    # 验证URL格式
                    if not url.startswith(('rtsp://', 'http://', 'https://')):
                        self.log(f"警告: 第 {line_count} 行URL格式不正确，已跳过: {url}")
                        continue

                    processed_lines.append((name, url))
                    processed_count += 1

                except Exception as e:
                    self.log(f"错误: 第 {line_count} 行处理失败: {e}")
                    continue

            return processed_lines, line_count, processed_count

        except Exception as e:
            raise Exception(f"处理Excel文件时发生错误: {e}")

    def process_file(self):
        """处理文件"""
        input_file = self.input_entry.get().strip()
        output_file = self.output_entry.get().strip()

        if not input_file:
            messagebox.showerror("错误", "请选择输入文件")
            return

        if not output_file:
            messagebox.showerror("错误", "请选择输出文件")
            return

        # 检查输入文件是否存在
        if not os.path.exists(input_file):
            messagebox.showerror("错误", f"输入文件不存在: {input_file}")
            return

        # 清空日志
        self.log_text.delete(1.0, tk.END)

        try:
            # 确定文件处理方法
            file_type = self.file_type.get()

            self.log(f"开始处理文件: {input_file}")
            self.log(f"文件类型: {file_type}")
            self.log("=" * 50)

            # 更新进度条
            self.progress['value'] = 0
            self.root.update()

            # 根据文件类型处理
            if file_type == "markdown":
                processed_lines, total_lines, processed_count = self.process_markdown(input_file)
            elif file_type == "excel":
                processed_lines, total_lines, processed_count = self.process_excel(input_file)
            else:
                raise Exception(f"不支持的文件类型: {file_type}")

            # 更新进度条
            self.progress['value'] = 50
            self.root.update()

            # 写入M3U文件
            if processed_lines:
                with open(output_file, 'w', encoding='utf-8') as f:
                    # 写入M3U文件头
                    f.write("#EXTM3U\n")
                    # 写入播放列表条目
                    for name, url in processed_lines:
                        f.write(f"#EXTINF:-1,{name}\n")
                        f.write(f"{url}\n")

                self.progress['value'] = 100
                self.root.update()

                self.log("\n" + "=" * 50)
                self.log("处理完成! 🚀")
                self.log(f"总共读取: {total_lines} 行")
                self.log(f"成功处理: {processed_count} 条记录")
                self.log(f"输出文件: {output_file}")

                # 显示成功消息
                messagebox.showinfo("完成", f"处理完成!\n成功处理 {processed_count} 条记录\n输出文件: {output_file}")

            else:
                self.log("警告: 没有找到有效的数据")
                messagebox.showwarning("警告", "没有找到有效的数据")

        except Exception as e:
            self.log(f"错误: {e}")
            messagebox.showerror("错误", str(e))
            self.progress['value'] = 0

    def clear_all(self):
        """清空所有内容"""
        self.input_entry.delete(0, tk.END)
        self.output_entry.delete(0, tk.END)
        self.log_text.delete(1.0, tk.END)
        self.progress['value'] = 0
        self.processed_data = []


def main():
    root = tk.Tk()
    app = VLCPlaylistConverter(root)
    root.mainloop()


if __name__ == "__main__":
    main()