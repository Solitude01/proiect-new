import pandas as pd
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import threading


def excel_to_json(excel_path, output_json_path=None, format_type='json', selected_columns=None, data_format='raw', column_mode='scan'):
    """
    将Excel文件的指定列转换为JSON或TXT格式
    
    Args:
        excel_path: Excel文件路径
        output_json_path: 输出文件路径
        format_type: 输出格式 'json' 或 'txt'
        selected_columns: 选中的列名列表（如['A', 'B', 'C']或['项目名称', '工厂名称']）
        data_format: 数据格式 'raw'(原始), 'custom'(自定义)
        column_mode: 列选择模式 'scan'(扫描) 或 'manual'(手动指定)
    
    Returns:
        转换后的数据列表
    """
    
    if column_mode == 'manual' and selected_columns:
        # 手动指定列名模式（如 A, B, C）
        usecols = ','.join(selected_columns)
        df = pd.read_excel(
            excel_path,
            usecols=usecols,
            engine='openpyxl',
            header=0  # 使用第一行作为列名
        )
        selected_col_names = df.columns.tolist()
    else:
        # 扫描模式：使用扫描到的列名
        if not selected_columns:
            raise ValueError("扫描模式下必须提供选中的列名")
        
        # 直接使用列名
        df = pd.read_excel(
            excel_path,
            usecols=selected_columns,
            engine='openpyxl'
        )
        selected_col_names = df.columns.tolist()
    
    # 将DataFrame转换为字典列表
    raw_data = df.to_dict(orient='records')
    
    # 根据指定格式转换数据
    if data_format == 'custom':
        data = convert_to_custom_format(raw_data, selected_col_names)
    else:
        data = raw_data
    
    # 如果指定了输出路径，保存文件
    if output_json_path:
        if format_type == 'txt':
            # 保存为TXT格式（内容与JSON相同）
            with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"✓ TXT文件已保存到: {output_json_path}")
        else:
            # 保存为JSON格式
            with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"✓ JSON文件已保存到: {output_json_path}")
        
        print(f"✓ 总共转换了 {len(data)} 条记录")
    
    return data


def convert_to_custom_format(data, columns):
    """转换为自定义训练格式"""
    custom_data = []
    for record in data:
        # 使用您指定的格式
        formatted_record = {}
        for col in columns:
            if col in record and pd.notna(record[col]):
                formatted_record[col] = record[col]
        custom_data.append(formatted_record)
    
    return custom_data


def scan_excel_columns(excel_path):
    """扫描Excel文件的所有列名"""
    try:
        df = pd.read_excel(excel_path, engine='openpyxl', nrows=0)
        return df.columns.tolist()
    except Exception as e:
        return []


class ExcelConverterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Excel转JSON/TXT转换器")
        self.root.geometry("850x700")
        self.root.resizable(True, True)
        
        # 设置样式
        style = ttk.Style()
        style.theme_use('clam')
        
        # 列选择模式
        self.column_mode = tk.StringVar(value='scan')
        
        # 扫描到的列
        self.scanned_columns = []
        self.scanned_column_vars = []
        
        self.create_widgets()
        
    def create_widgets(self):
        # 主框架
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # 标题
        title_label = ttk.Label(
            main_frame, 
            text="Excel数据转换工具",
            font=('Arial', 16, 'bold')
        )
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # 输入文件选择
        ttk.Label(main_frame, text="Excel文件:").grid(
            row=1, column=0, sticky=tk.W, pady=5
        )
        self.input_path = tk.StringVar()
        ttk.Entry(
            main_frame, 
            textvariable=self.input_path, 
            width=50
        ).grid(row=1, column=1, sticky=(tk.W, tk.E), pady=5, padx=5)
        ttk.Button(
            main_frame, 
            text="浏览...", 
            command=self.browse_input
        ).grid(row=1, column=2, pady=5)
        
        # 输出文件选择
        ttk.Label(main_frame, text="输出文件:").grid(
            row=2, column=0, sticky=tk.W, pady=5
        )
        self.output_path = tk.StringVar()
        ttk.Entry(
            main_frame, 
            textvariable=self.output_path, 
            width=50
        ).grid(row=2, column=1, sticky=(tk.W, tk.E), pady=5, padx=5)
        ttk.Button(
            main_frame, 
            text="浏览...", 
            command=self.browse_output
        ).grid(row=2, column=2, pady=5)
        
        # 格式选择
        format_frame = ttk.LabelFrame(main_frame, text="输出格式", padding="10")
        format_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=15)
        
        self.format_type = tk.StringVar(value='json')
        ttk.Radiobutton(
            format_frame, 
            text="JSON格式", 
            variable=self.format_type, 
            value='json',
            command=self.on_format_change
        ).pack(side=tk.LEFT, padx=20)
        ttk.Radiobutton(
            format_frame, 
            text="TXT格式 (内容同JSON)", 
            variable=self.format_type, 
            value='txt',
            command=self.on_format_change
        ).pack(side=tk.LEFT, padx=20)
        
        # 列选择模式
        mode_frame = ttk.LabelFrame(main_frame, text="列选择模式", padding="10")
        mode_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        
        ttk.Radiobutton(
            mode_frame, 
            text="扫描文件列名", 
            variable=self.column_mode, 
            value='scan',
            command=self.on_mode_change
        ).pack(side=tk.LEFT, padx=20)
        ttk.Radiobutton(
            mode_frame, 
            text="手动指定列名 (A,B,C...)", 
            variable=self.column_mode, 
            value='manual',
            command=self.on_mode_change
        ).pack(side=tk.LEFT, padx=20)
        
        ttk.Button(
            mode_frame,
            text="🔍 扫描列",
            command=self.scan_columns,
            width=12
        ).pack(side=tk.LEFT, padx=20)
        
        # 列选择框（容器）
        self.columns_container = ttk.Frame(main_frame)
        self.columns_container.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        
        # 初始提示
        self.show_initial_message()
        
        # 手动输入列名框（初始隐藏）
        self.manual_frame = ttk.LabelFrame(main_frame, text="手动指定列名", padding="10")
        self.manual_frame.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        self.manual_frame.grid_remove()  # 初始隐藏
        
        ttk.Label(
            self.manual_frame,
            text="请输入要提取的列名（用逗号分隔，如: A,B,C 或 A,C,E,G）:"
        ).pack(anchor=tk.W, pady=5)
        
        self.manual_columns_entry = ttk.Entry(self.manual_frame, width=60)
        self.manual_columns_entry.pack(fill=tk.X, pady=5)
        self.manual_columns_entry.insert(0, "C,D,E,F,G,H,I,J,K,L")  # 默认值
        
        # 转换按钮
        self.convert_btn = ttk.Button(
            main_frame, 
            text="开始转换", 
            command=self.convert,
            style='Accent.TButton'
        )
        self.convert_btn.grid(row=7, column=0, columnspan=3, pady=20, ipadx=20, ipady=5)
        
        # 进度和状态显示
        self.progress = ttk.Progressbar(
            main_frame, 
            mode='indeterminate', 
            length=400
        )
        self.progress.grid(row=8, column=0, columnspan=3, pady=5)
        
        # 状态文本框
        status_frame = ttk.LabelFrame(main_frame, text="转换日志", padding="10")
        status_frame.grid(row=9, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        main_frame.rowconfigure(9, weight=1)
        
        self.status_text = tk.Text(
            status_frame, 
            height=10, 
            width=70,
            wrap=tk.WORD,
            font=('Consolas', 9)
        )
        self.status_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(
            status_frame, 
            orient=tk.VERTICAL, 
            command=self.status_text.yview
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.status_text.config(yscrollcommand=scrollbar.set)
    
    def show_initial_message(self):
        """显示初始提示信息"""
        # 清空容器
        for widget in self.columns_container.winfo_children():
            widget.destroy()
        
        msg_frame = ttk.LabelFrame(self.columns_container, text="列选择", padding="20")
        msg_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(
            msg_frame,
            text="📋 请先选择Excel文件，然后点击 '🔍 扫描列' 按钮\n或切换到 '手动指定列名' 模式",
            font=('Arial', 10),
            foreground='#666',
            justify=tk.CENTER
        ).pack(expand=True)
    
    def show_preset_columns(self):
        """显示预设列选择框（已废弃，保留以防兼容性问题）"""
        pass
    
    def show_scanned_columns(self):
        """显示扫描到的列选择框"""
        # 清空容器
        for widget in self.columns_container.winfo_children():
            widget.destroy()
        
        columns_frame = ttk.LabelFrame(self.columns_container, text="扫描到的列（选择要转换的列）", padding="10")
        columns_frame.pack(fill=tk.BOTH, expand=True)
        
        if not self.scanned_columns:
            ttk.Label(
                columns_frame,
                text="请先点击 '🔍 扫描列' 按钮扫描Excel文件",
                foreground='orange'
            ).pack(pady=20)
            return
        
        # 创建滚动区域
        canvas = tk.Canvas(columns_frame, height=200)
        scrollbar = ttk.Scrollbar(columns_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 创建两列布局的复选框
        for i, col_name in enumerate(self.scanned_columns):
            row = i // 2
            col = i % 2
            ttk.Checkbutton(
                scrollable_frame,
                text=col_name,
                variable=self.scanned_column_vars[i]
            ).grid(row=row, column=col, sticky=tk.W, padx=20, pady=3)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 快捷按钮
        button_frame = ttk.Frame(columns_frame)
        button_frame.pack(pady=10)
        
        ttk.Button(
            button_frame,
            text="全选",
            command=self.select_all_scanned,
            width=10
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame,
            text="取消全选",
            command=self.deselect_all_scanned,
            width=10
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame,
            text="反选",
            command=self.invert_scanned,
            width=10
        ).pack(side=tk.LEFT, padx=5)
    
    def on_mode_change(self):
        """当列选择模式改变时"""
        if self.column_mode.get() == 'manual':
            self.columns_container.grid_remove()
            self.manual_frame.grid()
        else:
            self.manual_frame.grid_remove()
            self.columns_container.grid()
            if self.scanned_columns:
                self.show_scanned_columns()
            else:
                self.show_initial_message()
    
    def scan_columns(self):
        """扫描Excel文件的列"""
        input_file = self.input_path.get()
        if not input_file:
            messagebox.showwarning("警告", "请先选择Excel文件！")
            return
        
        self.log("正在扫描Excel文件列名...")
        columns = scan_excel_columns(input_file)
        
        if columns:
            self.scanned_columns = columns
            self.scanned_column_vars = [tk.BooleanVar(value=True) for _ in columns]
            self.column_mode.set('scan')
            self.show_scanned_columns()
            self.log(f"✓ 扫描成功！找到 {len(columns)} 列")
            self.log(f"列名: {', '.join(columns)}")
        else:
            messagebox.showerror("错误", "无法扫描文件列名，请检查文件是否正确")
            self.log("❌ 扫描失败")
    
    def on_format_change(self):
        """当输出格式改变时，更新输出文件路径的扩展名"""
        current_path = self.output_path.get()
        if current_path:
            path = Path(current_path)
            new_ext = '.txt' if self.format_type.get() == 'txt' else '.json'
            new_path = path.parent / (path.stem + new_ext)
            self.output_path.set(str(new_path))
    
    def select_all_columns(self):
        """全选所有列（已废弃）"""
        pass
    
    def deselect_all_columns(self):
        """取消全选（已废弃）"""
        pass
    
    def invert_selection(self):
        """反选（已废弃）"""
        pass
    
    def select_all_scanned(self):
        """全选扫描到的列"""
        for var in self.scanned_column_vars:
            var.set(True)
    
    def deselect_all_scanned(self):
        """取消全选扫描到的列"""
        for var in self.scanned_column_vars:
            var.set(False)
    
    def invert_scanned(self):
        """反选扫描到的列"""
        for var in self.scanned_column_vars:
            var.set(not var.get())
    
    def get_selected_columns(self):
        """获取选中的列"""
        mode = self.column_mode.get()
        
        if mode == 'manual':
            # 手动模式：返回列名列表
            cols_text = self.manual_columns_entry.get().strip()
            if not cols_text:
                return []
            return [col.strip().upper() for col in cols_text.split(',')]
        elif mode == 'scan' and self.scanned_columns:
            # 扫描模式：返回选中列的名称
            return [col for i, col in enumerate(self.scanned_columns) if self.scanned_column_vars[i].get()]
        else:
            # 未扫描
            return []
        
    def browse_input(self):
        filename = filedialog.askopenfilename(
            title="选择Excel文件",
            filetypes=[("Excel文件", "*.xlsx *.xls"), ("所有文件", "*.*")]
        )
        if filename:
            self.input_path.set(filename)
            # 自动设置输出路径
            path = Path(filename)
            ext = '.txt' if self.format_type.get() == 'txt' else '.json'
            default_output = path.parent / (path.stem + ext)
            self.output_path.set(str(default_output))
    
    def browse_output(self):
        ext = '.txt' if self.format_type.get() == 'txt' else '.json'
        
        # 根据当前选择的格式，设置文件类型过滤器
        if self.format_type.get() == 'txt':
            filetypes = [
                ("文本文件", "*.txt"),
                ("JSON文件", "*.json"), 
                ("所有文件", "*.*")
            ]
        else:
            filetypes = [
                ("JSON文件", "*.json"),
                ("文本文件", "*.txt"), 
                ("所有文件", "*.*")
            ]
        
        filename = filedialog.asksaveasfilename(
            title="保存为",
            defaultextension=ext,
            filetypes=filetypes
        )
        if filename:
            self.output_path.set(filename)
    
    def log(self, message):
        """在状态文本框中添加日志"""
        self.status_text.insert(tk.END, message + '\n')
        self.status_text.see(tk.END)
        self.root.update_idletasks()
    
    def convert(self):
        """执行转换"""
        input_file = self.input_path.get()
        output_file = self.output_path.get()
        
        if not input_file:
            messagebox.showwarning("警告", "请选择要转换的Excel文件！")
            return
        
        if not output_file:
            messagebox.showwarning("警告", "请指定输出文件路径！")
            return
        
        # 检查是否至少选中了一列
        selected = self.get_selected_columns()
        if not selected:
            messagebox.showwarning("警告", "请至少选择一列进行转换！")
            return
        
        # 在新线程中执行转换，避免界面卡顿
        thread = threading.Thread(target=self._do_convert)
        thread.daemon = True
        thread.start()
    
    def _do_convert(self):
        """实际执行转换的函数"""
        try:
            # 禁用按钮，显示进度条
            self.convert_btn.config(state='disabled')
            self.progress.start()
            
            self.status_text.delete(1.0, tk.END)
            self.log("=" * 50)
            self.log("开始转换...")
            self.log(f"输入文件: {self.input_path.get()}")
            self.log(f"输出文件: {self.output_path.get()}")
            self.log(f"输出格式: {self.format_type.get().upper()}")
            
            # 显示选中的列
            selected = self.get_selected_columns()
            mode = self.column_mode.get()
            
            if mode == 'manual':
                self.log(f"列选择模式: 手动指定")
                self.log(f"指定的列 ({len(selected)}): {', '.join(selected)}")
            else:
                self.log(f"列选择模式: 扫描选择")
                self.log(f"选中的列 ({len(selected)}): {', '.join(selected)}")
            
            self.log("=" * 50)
            
            # 执行转换
            result = excel_to_json(
                self.input_path.get(),
                self.output_path.get(),
                self.format_type.get(),
                selected,
                'custom',
                mode if mode in ['scan', 'manual'] else 'scan'
            )
            
            self.log(f"\n✓ 转换成功！")
            self.log(f"✓ 总共转换了 {len(result)} 条记录")
            
            # 显示第一条记录示例
            if result:
                self.log("\n第一条记录示例:")
                self.log("-" * 50)
                for key, value in result[0].items():
                    self.log(f"{key}: {value}")
            
            self.progress.stop()
            self.convert_btn.config(state='normal')
            
            messagebox.showinfo(
                "成功", 
                f"转换完成！\n共转换 {len(result)} 条记录\n\n文件已保存到:\n{self.output_path.get()}"
            )
            
        except Exception as e:
            self.progress.stop()
            self.convert_btn.config(state='normal')
            self.log(f"\n❌ 错误: {str(e)}")
            messagebox.showerror("错误", f"转换失败:\n{str(e)}")


def main():
    root = tk.Tk()
    app = ExcelConverterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()