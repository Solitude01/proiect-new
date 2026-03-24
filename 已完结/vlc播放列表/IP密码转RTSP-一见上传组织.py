#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Excel数据处理工具 - GUI版本
功能1: IP密码转RTSP
功能2: 双列组合格式
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import pandas as pd


class ExcelDataProcessor:
    def __init__(self, root):
        self.root = root
        self.root.title("Excel数据处理工具")
        self.root.geometry("780x720")
        self.root.resizable(True, True)

        # 数据存储
        self.df = None

        self.create_widgets()

    def create_widgets(self):
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 配置行列权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)

        # 标题
        title_label = ttk.Label(main_frame, text="Excel数据处理工具", font=("微软雅黑", 16, "bold"))
        title_label.grid(row=0, column=0, pady=(0, 10))

        # 文件选择区域（共用）
        file_frame = ttk.LabelFrame(main_frame, text="Excel文件", padding="10")
        file_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        file_frame.columnconfigure(0, weight=1)

        self.file_entry = ttk.Entry(file_frame, width=60)
        self.file_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        ttk.Button(file_frame, text="浏览...", command=self.browse_file).grid(row=0, column=1)

        # Notebook (Tab容器)
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        main_frame.rowconfigure(2, weight=1)

        # ========== Tab 1: IP转RTSP ==========
        self.tab1 = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.tab1, text="  IP转RTSP  ")
        self.tab1.columnconfigure(1, weight=1)

        # Tab 1 - 列配置区域
        column_frame = ttk.LabelFrame(self.tab1, text="列配置 (支持列字母如A、B、C或列名)", padding="10")
        column_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        column_frame.columnconfigure(1, weight=1)
        column_frame.columnconfigure(3, weight=1)

        # IP列
        ttk.Label(column_frame, text="IP列:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.ip_column = ttk.Entry(column_frame, width=15)
        self.ip_column.insert(0, "A")
        self.ip_column.grid(row=0, column=1, sticky=tk.W, pady=5, padx=(5, 20))

        # 密码列
        ttk.Label(column_frame, text="密码列:").grid(row=0, column=2, sticky=tk.W, pady=5)
        self.pwd_column = ttk.Entry(column_frame, width=15)
        self.pwd_column.insert(0, "B")
        self.pwd_column.grid(row=0, column=3, sticky=tk.W, pady=5, padx=(5, 0))

        # 输出列
        ttk.Label(column_frame, text="输出列:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.output_column = ttk.Entry(column_frame, width=15)
        self.output_column.insert(0, "C")
        self.output_column.grid(row=1, column=1, sticky=tk.W, pady=5, padx=(5, 20))

        # Tab 1 - 行范围区域
        row_frame = ttk.LabelFrame(self.tab1, text="行范围 (1表示第1行，包含表头)", padding="10")
        row_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        row_frame.columnconfigure(1, weight=1)
        row_frame.columnconfigure(3, weight=1)

        # 起始行
        ttk.Label(row_frame, text="起始行:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.start_row = ttk.Entry(row_frame, width=15)
        self.start_row.insert(0, "2")
        self.start_row.grid(row=0, column=1, sticky=tk.W, pady=5, padx=(5, 20))

        # 结束行
        ttk.Label(row_frame, text="结束行:").grid(row=0, column=2, sticky=tk.W, pady=5)
        self.end_row = ttk.Entry(row_frame, width=15)
        self.end_row.insert(0, "")
        self.end_row.grid(row=0, column=3, sticky=tk.W, pady=5, padx=(5, 0))
        ttk.Label(row_frame, text="(留空表示处理到最后一行)").grid(row=0, column=4, sticky=tk.W, pady=5, padx=(5, 0))

        # Tab 1 - RTSP配置区域
        rtsp_frame = ttk.LabelFrame(self.tab1, text="RTSP配置", padding="10")
        rtsp_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        rtsp_frame.columnconfigure(1, weight=1)

        # 用户名
        ttk.Label(rtsp_frame, text="用户名:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.username = ttk.Entry(rtsp_frame, width=20)
        self.username.insert(0, "admin")
        self.username.grid(row=0, column=1, sticky=tk.W, pady=5, padx=(5, 0))

        # Tab 1 - 按钮区域
        btn_frame1 = ttk.Frame(self.tab1)
        btn_frame1.grid(row=3, column=0, columnspan=3, pady=15)

        self.convert_btn = ttk.Button(btn_frame1, text="开始转换", command=self.start_convert, width=15)
        self.convert_btn.grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame1, text="清空", command=self.clear_tab1, width=10).grid(row=0, column=1, padx=5)

        # ========== Tab 2: 双列组合 ==========
        self.tab2 = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.tab2, text="  双列组合  ")
        self.tab2.columnconfigure(1, weight=1)

        # Tab 2 - 源列配置区域
        source_frame = ttk.LabelFrame(self.tab2, text="源列配置 (支持列字母如A、B、C或列名)", padding="10")
        source_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        source_frame.columnconfigure(1, weight=1)
        source_frame.columnconfigure(3, weight=1)

        # 第一列
        ttk.Label(source_frame, text="第一列:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.tab2_col1 = ttk.Entry(source_frame, width=15)
        self.tab2_col1.insert(0, "A")
        self.tab2_col1.grid(row=0, column=1, sticky=tk.W, pady=5, padx=(5, 20))

        # 第二列
        ttk.Label(source_frame, text="第二列:").grid(row=0, column=2, sticky=tk.W, pady=5)
        self.tab2_col2 = ttk.Entry(source_frame, width=15)
        self.tab2_col2.insert(0, "B")
        self.tab2_col2.grid(row=0, column=3, sticky=tk.W, pady=5, padx=(5, 0))

        # 输出列
        ttk.Label(source_frame, text="输出列:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.tab2_output = ttk.Entry(source_frame, width=15)
        self.tab2_output.insert(0, "C")
        self.tab2_output.grid(row=1, column=1, sticky=tk.W, pady=5, padx=(5, 20))

        # Tab 2 - 行范围区域
        row2_frame = ttk.LabelFrame(self.tab2, text="行范围 (1表示第1行，包含表头)", padding="10")
        row2_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        row2_frame.columnconfigure(1, weight=1)
        row2_frame.columnconfigure(3, weight=1)

        # 起始行
        ttk.Label(row2_frame, text="起始行:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.tab2_start_row = ttk.Entry(row2_frame, width=15)
        self.tab2_start_row.insert(0, "2")
        self.tab2_start_row.grid(row=0, column=1, sticky=tk.W, pady=5, padx=(5, 20))

        # 结束行
        ttk.Label(row2_frame, text="结束行:").grid(row=0, column=2, sticky=tk.W, pady=5)
        self.tab2_end_row = ttk.Entry(row2_frame, width=15)
        self.tab2_end_row.insert(0, "")
        self.tab2_end_row.grid(row=0, column=3, sticky=tk.W, pady=5, padx=(5, 0))
        ttk.Label(row2_frame, text="(留空表示处理到最后一行)").grid(row=0, column=4, sticky=tk.W, pady=5, padx=(5, 0))

        # Tab 2 - 格式说明区域
        format_frame = ttk.LabelFrame(self.tab2, text="组合格式", padding="10")
        format_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        format_frame.columnconfigure(0, weight=1)

        format_text = '格式: root\\第一列的值\\第二列的值\n示例: 第一列=abc, 第二列=def → 输出 root\\abc\\def'
        ttk.Label(format_frame, text=format_text, foreground="gray").grid(row=0, column=0, sticky=tk.W, pady=5)

        # Tab 2 - 按钮区域
        btn_frame2 = ttk.Frame(self.tab2)
        btn_frame2.grid(row=3, column=0, columnspan=3, pady=15)

        self.combine_btn = ttk.Button(btn_frame2, text="开始组合", command=self.start_combine, width=15)
        self.combine_btn.grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame2, text="清空", command=self.clear_tab2, width=10).grid(row=0, column=1, padx=5)

        # ========== 共用组件 ==========
        # 进度显示（共用）
        progress_frame = ttk.Frame(main_frame)
        progress_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=5)
        progress_frame.columnconfigure(1, weight=1)

        ttk.Label(progress_frame, text="处理进度:").grid(row=0, column=0, sticky=tk.W)
        self.progress = ttk.Progressbar(progress_frame, mode='determinate', length=400)
        self.progress.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5)
        self.progress_label = ttk.Label(progress_frame, text="0%")
        self.progress_label.grid(row=0, column=2, sticky=tk.W)

        # 日志显示区域（共用）
        ttk.Label(main_frame, text="处理日志:").grid(row=4, column=0, sticky=tk.W, pady=5)
        log_frame = ttk.Frame(main_frame)
        log_frame.grid(row=5, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, width=80)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 退出按钮
        exit_frame = ttk.Frame(main_frame)
        exit_frame.grid(row=6, column=0, pady=10)
        ttk.Button(exit_frame, text="退出", command=self.root.quit, width=15).grid(row=0, column=0)

        # 配置权重
        main_frame.rowconfigure(5, weight=1)

    def browse_file(self):
        """浏览选择Excel文件"""
        file_types = [
            ("Excel文件", "*.xlsx;*.xls"),
            ("所有文件", "*.*")
        ]
        filename = filedialog.askopenfilename(
            title="选择Excel文件",
            filetypes=file_types
        )
        if filename:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, filename)
            self.log(f"已选择文件: {filename}")

    def log(self, message):
        """在日志区域添加消息"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update()

    def get_column_index(self, col_str, df_columns):
        """将列标识转换为列索引"""
        col_str = col_str.strip()

        # 尝试作为列字母处理（A-Z）
        if len(col_str) == 1 and col_str.upper() in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            return ord(col_str.upper()) - ord('A')

        # 尝试作为列名查找
        try:
            if col_str in df_columns:
                return df_columns.get_loc(col_str)
        except:
            pass

        # 尝试作为数字索引
        try:
            idx = int(col_str) - 1  # 用户输入1-based，转为0-based
            if 0 <= idx < len(df_columns):
                return idx
        except:
            pass

        return None

    def read_excel(self, file_path):
        """读取Excel文件"""
        file_extension = os.path.splitext(file_path)[1].lower()
        if file_extension == '.xls':
            return pd.read_excel(file_path, engine='xlrd')
        else:
            return pd.read_excel(file_path, engine='openpyxl')

    def validate_file(self):
        """验证文件输入"""
        file_path = self.file_entry.get().strip()
        if not file_path:
            messagebox.showerror("错误", "请选择Excel文件")
            return None

        if not os.path.exists(file_path):
            messagebox.showerror("错误", f"文件不存在: {file_path}")
            return None

        return file_path

    def validate_row_range(self, start_entry, end_entry):
        """验证行范围输入"""
        try:
            start = int(start_entry.get().strip())
            if start < 1:
                messagebox.showerror("错误", "起始行必须大于等于1")
                return None, None
        except ValueError:
            messagebox.showerror("错误", "起始行必须是有效的数字")
            return None, None

        end_str = end_entry.get().strip()
        if end_str:
            try:
                end = int(end_str)
                if end < 1:
                    messagebox.showerror("错误", "结束行必须大于等于1")
                    return None, None
                if end < start:
                    messagebox.showerror("错误", "结束行不能小于起始行")
                    return None, None
            except ValueError:
                messagebox.showerror("错误", "结束行必须是有效的数字")
                return None, None
        else:
            end = None

        return start, end

    # ========== Tab 1 功能 ==========
    def start_convert(self):
        """Tab 1: 开始RTSP转换"""
        file_path = self.validate_file()
        if not file_path:
            return

        start, end = self.validate_row_range(self.start_row, self.end_row)
        if start is None:
            return

        # 清空日志和进度
        self.log_text.delete(1.0, tk.END)
        self.progress['value'] = 0
        self.progress_label.config(text="0%")

        try:
            self.log("=" * 50)
            self.log("[IP转RTSP] 开始处理...")
            self.log(f"读取文件: {file_path}")

            self.df = self.read_excel(file_path)
            total_rows = len(self.df)
            self.log(f"成功读取，共 {total_rows} 行数据")
            self.log(f"列名: {list(self.df.columns)}")

            # 获取列索引
            ip_col_idx = self.get_column_index(self.ip_column.get(), self.df.columns)
            pwd_col_idx = self.get_column_index(self.pwd_column.get(), self.df.columns)
            out_col_idx = self.get_column_index(self.output_column.get(), self.df.columns)

            if ip_col_idx is None:
                raise Exception(f"无法识别IP列: {self.ip_column.get()}")
            if pwd_col_idx is None:
                raise Exception(f"无法识别密码列: {self.pwd_column.get()}")
            if out_col_idx is None:
                raise Exception(f"无法识别输出列: {self.output_column.get()}")

            self.log(f"IP列: {self.df.columns[ip_col_idx]} (索引{ip_col_idx})")
            self.log(f"密码列: {self.df.columns[pwd_col_idx]} (索引{pwd_col_idx})")
            self.log(f"输出列: {self.df.columns[out_col_idx]} (索引{out_col_idx})")

            # 转换为0-based索引
            start_idx = start - 1
            end_idx = end - 1 if end else total_rows - 1
            end_idx = min(end_idx, total_rows - 1)

            self.log(f"处理行范围: 第{start_idx + 1}行 到 第{end_idx + 1}行")
            self.log("=" * 50)

            username = self.username.get().strip() or "admin"
            processed_count = 0
            skipped_count = 0
            total_process = end_idx - start_idx + 1

            for idx in range(start_idx, end_idx + 1):
                row_num = idx + 1

                try:
                    ip = str(self.df.iloc[idx, ip_col_idx]) if pd.notna(self.df.iloc[idx, ip_col_idx]) else ""
                    password = str(self.df.iloc[idx, pwd_col_idx]) if pd.notna(self.df.iloc[idx, pwd_col_idx]) else ""

                    ip = ip.strip()
                    password = password.strip()

                    if not ip or not password:
                        self.log(f"第{row_num}行: 跳过 (IP或密码为空)")
                        skipped_count += 1
                        continue

                    rtsp_url = f"rtsp://{username}:{password}@{ip}"
                    self.df.iloc[idx, out_col_idx] = rtsp_url

                    self.log(f"第{row_num}行: {ip} -> {rtsp_url}")
                    processed_count += 1

                except Exception as e:
                    self.log(f"第{row_num}行: 处理失败 - {str(e)}")
                    skipped_count += 1

                progress = ((idx - start_idx + 1) / total_process) * 100
                self.progress['value'] = progress
                self.progress_label.config(text=f"{int(progress)}%")
                self.root.update()

            # 保存文件
            base_name = os.path.splitext(file_path)[0]
            output_path = f"{base_name}_RTSP.xlsx"

            counter = 1
            while os.path.exists(output_path):
                output_path = f"{base_name}_RTSP_{counter}.xlsx"
                counter += 1

            self.df.to_excel(output_path, index=False, engine='openpyxl')

            self.progress['value'] = 100
            self.progress_label.config(text="100%")

            self.log("\n" + "=" * 50)
            self.log("[IP转RTSP] 转换完成!")
            self.log(f"成功处理: {processed_count} 行")
            self.log(f"跳过: {skipped_count} 行")
            self.log(f"输出文件: {output_path}")

            messagebox.showinfo("完成", f"RTSP转换完成!\n\n成功处理: {processed_count} 行\n跳过: {skipped_count} 行\n\n输出文件: {output_path}")

        except Exception as e:
            self.log(f"错误: {str(e)}")
            messagebox.showerror("错误", f"转换过程中发生错误:\n{str(e)}")
            self.progress['value'] = 0
            self.progress_label.config(text="0%")

    def clear_tab1(self):
        """清空Tab 1"""
        self.ip_column.delete(0, tk.END)
        self.ip_column.insert(0, "A")
        self.pwd_column.delete(0, tk.END)
        self.pwd_column.insert(0, "B")
        self.output_column.delete(0, tk.END)
        self.output_column.insert(0, "C")
        self.start_row.delete(0, tk.END)
        self.start_row.insert(0, "2")
        self.end_row.delete(0, tk.END)
        self.username.delete(0, tk.END)
        self.username.insert(0, "admin")
        self.log_text.delete(1.0, tk.END)
        self.progress['value'] = 0
        self.progress_label.config(text="0%")

    # ========== Tab 2 功能 ==========
    def start_combine(self):
        """Tab 2: 开始双列组合"""
        file_path = self.validate_file()
        if not file_path:
            return

        start, end = self.validate_row_range(self.tab2_start_row, self.tab2_end_row)
        if start is None:
            return

        # 清空日志和进度
        self.log_text.delete(1.0, tk.END)
        self.progress['value'] = 0
        self.progress_label.config(text="0%")

        try:
            self.log("=" * 50)
            self.log("[双列组合] 开始处理...")
            self.log(f"读取文件: {file_path}")

            self.df = self.read_excel(file_path)
            total_rows = len(self.df)
            self.log(f"成功读取，共 {total_rows} 行数据")
            self.log(f"列名: {list(self.df.columns)}")

            # 获取列索引
            col1_idx = self.get_column_index(self.tab2_col1.get(), self.df.columns)
            col2_idx = self.get_column_index(self.tab2_col2.get(), self.df.columns)
            out_idx = self.get_column_index(self.tab2_output.get(), self.df.columns)

            if col1_idx is None:
                raise Exception(f"无法识别第一列: {self.tab2_col1.get()}")
            if col2_idx is None:
                raise Exception(f"无法识别第二列: {self.tab2_col2.get()}")
            if out_idx is None:
                raise Exception(f"无法识别输出列: {self.tab2_output.get()}")

            self.log(f"第一列: {self.df.columns[col1_idx]} (索引{col1_idx})")
            self.log(f"第二列: {self.df.columns[col2_idx]} (索引{col2_idx})")
            self.log(f"输出列: {self.df.columns[out_idx]} (索引{out_idx})")

            # 转换为0-based索引
            start_idx = start - 1
            end_idx = end - 1 if end else total_rows - 1
            end_idx = min(end_idx, total_rows - 1)

            self.log(f"处理行范围: 第{start_idx + 1}行 到 第{end_idx + 1}行")
            self.log(r"格式: root\第一列的值\第二列的值")
            self.log("=" * 50)

            processed_count = 0
            skipped_count = 0
            total_process = end_idx - start_idx + 1

            for idx in range(start_idx, end_idx + 1):
                row_num = idx + 1

                try:
                    value1 = str(self.df.iloc[idx, col1_idx]) if pd.notna(self.df.iloc[idx, col1_idx]) else ""
                    value2 = str(self.df.iloc[idx, col2_idx]) if pd.notna(self.df.iloc[idx, col2_idx]) else ""

                    value1 = value1.strip()
                    value2 = value2.strip()

                    if not value1 or not value2:
                        self.log(f"第{row_num}行: 跳过 (值为空)")
                        skipped_count += 1
                        continue

                    # 组合格式: root\value1\value2
                    result = f'root\\{value1}\\{value2}'
                    self.df.iloc[idx, out_idx] = result

                    self.log(f"第{row_num}行: {value1} + {value2} -> {result}")
                    processed_count += 1

                except Exception as e:
                    self.log(f"第{row_num}行: 处理失败 - {str(e)}")
                    skipped_count += 1

                progress = ((idx - start_idx + 1) / total_process) * 100
                self.progress['value'] = progress
                self.progress_label.config(text=f"{int(progress)}%")
                self.root.update()

            # 保存文件
            base_name = os.path.splitext(file_path)[0]
            output_path = f"{base_name}_组合.xlsx"

            counter = 1
            while os.path.exists(output_path):
                output_path = f"{base_name}_组合_{counter}.xlsx"
                counter += 1

            self.df.to_excel(output_path, index=False, engine='openpyxl')

            self.progress['value'] = 100
            self.progress_label.config(text="100%")

            self.log("\n" + "=" * 50)
            self.log("[双列组合] 处理完成!")
            self.log(f"成功处理: {processed_count} 行")
            self.log(f"跳过: {skipped_count} 行")
            self.log(f"输出文件: {output_path}")

            messagebox.showinfo("完成", f"双列组合完成!\n\n成功处理: {processed_count} 行\n跳过: {skipped_count} 行\n\n输出文件: {output_path}")

        except Exception as e:
            self.log(f"错误: {str(e)}")
            messagebox.showerror("错误", f"处理过程中发生错误:\n{str(e)}")
            self.progress['value'] = 0
            self.progress_label.config(text="0%")

    def clear_tab2(self):
        """清空Tab 2"""
        self.tab2_col1.delete(0, tk.END)
        self.tab2_col1.insert(0, "A")
        self.tab2_col2.delete(0, tk.END)
        self.tab2_col2.insert(0, "B")
        self.tab2_output.delete(0, tk.END)
        self.tab2_output.insert(0, "C")
        self.tab2_start_row.delete(0, tk.END)
        self.tab2_start_row.insert(0, "2")
        self.tab2_end_row.delete(0, tk.END)
        self.log_text.delete(1.0, tk.END)
        self.progress['value'] = 0
        self.progress_label.config(text="0%")


def main():
    root = tk.Tk()
    app = ExcelDataProcessor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
