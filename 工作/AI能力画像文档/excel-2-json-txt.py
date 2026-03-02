import pandas as pd
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import threading


def excel_to_json(excel_path, output_json_path=None, format_type='json', selected_columns=None, data_format='raw'):
    """
    将Excel文件的指定列转换为JSON或TXT格式
    
    Args:
        excel_path: Excel文件路径
        output_json_path: 输出文件路径
        format_type: 输出格式 'json' 或 'txt'
        selected_columns: 选中的列索引列表，如果为None则使用默认列
        data_format: 数据格式 'raw'(原始), 'qa'(问答对), 'chat'(对话格式), 'instruction'(指令格式)
    
    Returns:
        转换后的数据列表
    """
    # 所有可用的列定义（Excel中的C-L列）
    all_columns = [
        ('C', '项目名称'),
        ('D', '工厂名称'),
        ('E', '项目目标'),
        ('F', '收益描述'),
        ('G', 'OK图片描述'),
        ('H', 'NG图片描述'),
        ('I', '应用场景简述'),
        ('J', '处理对象(输入)'),
        ('K', '核心功能'),
        ('L', '输出形式/接口')
    ]
    
    # 如果没有指定列，使用所有列
    if selected_columns is None:
        selected_columns = list(range(len(all_columns)))
    
    # 根据选中的列构建usecols参数
    selected_excel_cols = [all_columns[i][0] for i in selected_columns]
    selected_col_names = [all_columns[i][1] for i in selected_columns]
    
    # 读取Excel文件，只读取选中的列
    df = pd.read_excel(
        excel_path,
        usecols=','.join(selected_excel_cols),
        engine='openpyxl'
    )
    
    # 设置列名
    df.columns = selected_col_names
    
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


class ExcelConverterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Excel转JSON/TXT转换器")
        self.root.geometry("800x600")
        self.root.resizable(True, True)
        
        # 设置样式
        style = ttk.Style()
        style.theme_use('clam')
        
        # 所有可用的列
        self.all_columns = [
            '项目名称',
            '工厂名称',
            '项目目标',
            '收益描述',
            'OK图片描述',
            'NG图片描述',
            '应用场景简述',
            '处理对象(输入)',
            '核心功能',
            '输出形式/接口'
        ]
        
        # 列选择状态（默认全选）
        self.column_vars = [tk.BooleanVar(value=True) for _ in self.all_columns]
        
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
        
        # 列选择框
        columns_frame = ttk.LabelFrame(main_frame, text="选择要转换的列", padding="10")
        columns_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        
        # 创建两列布局的复选框
        for i, col_name in enumerate(self.all_columns):
            row = i // 2
            col = i % 2
            ttk.Checkbutton(
                columns_frame,
                text=col_name,
                variable=self.column_vars[i]
            ).grid(row=row, column=col, sticky=tk.W, padx=20, pady=3)
        
        # 快捷按钮
        button_frame = ttk.Frame(columns_frame)
        button_frame.grid(row=(len(self.all_columns) + 1) // 2, column=0, columnspan=2, pady=10)
        
        ttk.Button(
            button_frame,
            text="全选",
            command=self.select_all_columns,
            width=10
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame,
            text="取消全选",
            command=self.deselect_all_columns,
            width=10
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame,
            text="反选",
            command=self.invert_selection,
            width=10
        ).pack(side=tk.LEFT, padx=5)
        
        # 转换按钮
        self.convert_btn = ttk.Button(
            main_frame, 
            text="开始转换", 
            command=self.convert,
            style='Accent.TButton'
        )
        self.convert_btn.grid(row=5, column=0, columnspan=3, pady=20, ipadx=20, ipady=5)
        
        # 进度和状态显示
        self.progress = ttk.Progressbar(
            main_frame, 
            mode='indeterminate', 
            length=400
        )
        self.progress.grid(row=6, column=0, columnspan=3, pady=5)
        
        # 状态文本框
        status_frame = ttk.LabelFrame(main_frame, text="转换日志", padding="10")
        status_frame.grid(row=7, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        main_frame.rowconfigure(7, weight=1)
        
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
    
    def on_format_change(self):
        """当输出格式改变时，更新输出文件路径的扩展名"""
        current_path = self.output_path.get()
        if current_path:
            path = Path(current_path)
            new_ext = '.txt' if self.format_type.get() == 'txt' else '.json'
            new_path = path.parent / (path.stem + new_ext)
            self.output_path.set(str(new_path))
    
    def select_all_columns(self):
        """全选所有列"""
        for var in self.column_vars:
            var.set(True)
    
    def deselect_all_columns(self):
        """取消全选"""
        for var in self.column_vars:
            var.set(False)
    
    def invert_selection(self):
        """反选"""
        for var in self.column_vars:
            var.set(not var.get())
    
    def get_selected_columns(self):
        """获取选中的列索引"""
        return [i for i, var in enumerate(self.column_vars) if var.get()]
        
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
            selected_names = [self.all_columns[i] for i in selected]
            self.log(f"选中的列 ({len(selected)}): {', '.join(selected_names)}")
            self.log("=" * 50)
            
            # 执行转换
            result = excel_to_json(
                self.input_path.get(),
                self.output_path.get(),
                self.format_type.get(),
                selected,
                'custom'
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