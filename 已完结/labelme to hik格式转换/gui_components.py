import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
from typing import Dict, List, Callable, Optional
from converter_core import LabelmeConverter, ConversionMode, LabelMapping

class BatchConfigDialog:
    """批量配置对话框"""
    
    def __init__(self, parent, label_entries, tree, update_callback):
        self.parent = parent
        self.label_entries = label_entries
        self.tree = tree
        self.update_callback = update_callback
        self.create_dialog()
    
    def create_dialog(self):
        """创建对话框"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("批量配置常用分类")
        self.dialog.geometry("500x400")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        # 居中显示
        self.dialog.geometry("+%d+%d" % (
            self.parent.winfo_rootx() + 100,
            self.parent.winfo_rooty() + 100
        ))
        
        # 说明文字
        ttk.Label(self.dialog, text="选择要批量应用的分类模板:", font=('', 10, 'bold')).pack(pady=10)
        
        # 模板选择区域
        template_frame = ttk.Frame(self.dialog)
        template_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        # 创建模板按钮
        templates = [
            ("交通工具类", "vehicle", ["car", "truck", "bus", "motorcycle", "bicycle", "bike"]),
            ("人物类", "human", ["person", "people", "man", "woman", "child"]),
            ("动物类", "animal", ["dog", "cat", "bird", "horse"]),
            ("交通设施类", "infrastructure", ["traffic_light", "stop_sign", "traffic_sign"]),
            ("建筑类", "structure", ["building", "house", "bridge"]),
            ("自然类", "nature", ["tree", "flower", "grass"])
        ]
        
        for i, (name, category, labels) in enumerate(templates):
            frame = ttk.LabelFrame(template_frame, text=name, padding="10")
            frame.grid(row=i//2, column=i%2, padx=10, pady=5, sticky='ew')
            
            ttk.Label(frame, text=f"一级分类: {category}").pack(anchor='w')
            ttk.Label(frame, text=f"适用标签: {', '.join(labels[:3])}{'...' if len(labels) > 3 else ''}").pack(anchor='w')
            
            ttk.Button(frame, text="应用此分类", 
                      command=lambda cat=category, lbls=labels: self.apply_template(cat, lbls)).pack(pady=5)
        
        # 配置grid权重
        template_frame.columnconfigure(0, weight=1)
        template_frame.columnconfigure(1, weight=1)
        
        # 按钮区域
        button_frame = ttk.Frame(self.dialog)
        button_frame.pack(pady=20)
        
        ttk.Button(button_frame, text="关闭", command=self.dialog.destroy).pack()
    
    def apply_template(self, primary_category, target_labels):
        """应用模板"""
        applied_count = 0
        
        for label, entry_vars in self.label_entries.items():
            if label.lower() in [l.lower() for l in target_labels]:
                # 从原标签中提取检测标签名（去掉状态后缀）
                detection_name = label
                if '_' in label:
                    # 如果标签包含下划线，取前半部分作为检测标签名
                    detection_name = label.split('_')[0]
                
                # 设置检测标签名
                entry_vars['detection_name'].set(detection_name)
                # 设置一级分类
                entry_vars['primary'].set(primary_category)
                # 设置二级分类为原标签名
                entry_vars['secondary'].set(label)
                applied_count += 1
        
        if applied_count > 0:
            self.update_callback()
            messagebox.showinfo("成功", f"已为 {applied_count} 个标签应用 '{primary_category}' 分类")
        else:
            messagebox.showinfo("提示", "没有找到匹配的标签")
        
        self.dialog.destroy()

class LabelConfigFrame(ttk.Frame):
    """标签配置框架"""
    
    def __init__(self, parent, converter: LabelmeConverter, gui_instance=None):
        super().__init__(parent)
        self.converter = converter
        self.gui_instance = gui_instance
        self.label_entries: Dict[str, Dict[str, tk.StringVar]] = {}
        self.setup_ui()
    
    def setup_ui(self):
        """设置UI"""
        # 顶部按钮区域
        button_frame = ttk.Frame(self)
        button_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Button(button_frame, text="扫描标签", command=self.scan_labels).pack(side='left', padx=(0, 5))
        ttk.Button(button_frame, text="导入配置", command=self.import_config).pack(side='left', padx=(0, 5))
        ttk.Button(button_frame, text="导出配置", command=self.export_config).pack(side='left', padx=(0, 5))
        ttk.Button(button_frame, text="清空配置", command=self.clear_config).pack(side='left', padx=(0, 5))
        
        # 创建表格区域
        self.create_table()
    
    def create_table(self):
        """创建标签配置表格"""
        # 说明文字
        info_frame = ttk.Frame(self)
        info_frame.pack(fill='x', pady=(0, 10))
        
        info_label = ttk.Label(info_frame, text="💡 提示：双击表格中的分类列可以编辑，或选中行后点击下方按钮快速配置", 
                              foreground="blue")
        info_label.pack(anchor='w')
        
        # 表格框架
        table_frame = ttk.Frame(self)
        table_frame.pack(fill='both', expand=True)
        
        # 创建Treeview用于显示标签表格
        columns = ('label', 'count', 'detection_name', 'primary', 'secondary', 'status')
        self.tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=12)
        
        # 设置列标题
        self.tree.heading('label', text='原标签名')
        self.tree.heading('count', text='使用次数')
        self.tree.heading('detection_name', text='检测标签名')
        self.tree.heading('primary', text='一级分类')
        self.tree.heading('secondary', text='二级分类')
        self.tree.heading('status', text='配置状态')
        
        # 设置列宽
        self.tree.column('label', width=120, minwidth=100)
        self.tree.column('count', width=70, minwidth=60)
        self.tree.column('detection_name', width=100, minwidth=80)
        self.tree.column('primary', width=100, minwidth=80)
        self.tree.column('secondary', width=100, minwidth=80)
        self.tree.column('status', width=70, minwidth=60)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # 布局
        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # 绑定事件
        self.tree.bind('<Double-1>', self.on_item_double_click)
        self.tree.bind('<<TreeviewSelect>>', self.on_selection_change)
        
        # 快速配置区域
        self.create_quick_config_area()
    
    def create_quick_config_area(self):
        """创建快速配置区域"""
        config_frame = ttk.LabelFrame(self, text="快速配置选中标签", padding="10")
        config_frame.pack(fill='x', pady=(10, 0))
        
        # 当前选中标签显示
        self.current_label_var = tk.StringVar(value="未选中标签")
        current_label_frame = ttk.Frame(config_frame)
        current_label_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(current_label_frame, text="当前标签:").pack(side='left')
        current_label_display = ttk.Label(current_label_frame, textvariable=self.current_label_var, 
                                         foreground="red", font=('', 10, 'bold'))
        current_label_display.pack(side='left', padx=(10, 0))
        
        # 配置输入区域
        input_frame = ttk.Frame(config_frame)
        input_frame.pack(fill='x', pady=(0, 10))
        
        # 检测标签名输入（从原标签中提取）
        ttk.Label(input_frame, text="检测标签名:").grid(row=0, column=0, sticky='w', padx=(0, 5))
        self.detection_name_var = tk.StringVar()
        detection_entry = ttk.Entry(input_frame, textvariable=self.detection_name_var, width=15)
        detection_entry.grid(row=0, column=1, padx=(0, 10), sticky='ew')
        
        # 一级分类输入
        ttk.Label(input_frame, text="一级分类:").grid(row=0, column=2, sticky='w', padx=(0, 5))
        self.primary_var = tk.StringVar()
        primary_entry = ttk.Entry(input_frame, textvariable=self.primary_var, width=15)
        primary_entry.grid(row=0, column=3, padx=(0, 10), sticky='ew')
        
        # 二级分类输入（原标签名）
        ttk.Label(input_frame, text="二级分类:").grid(row=0, column=4, sticky='w', padx=(0, 5))
        self.secondary_var = tk.StringVar()
        secondary_entry = ttk.Entry(input_frame, textvariable=self.secondary_var, width=15)
        secondary_entry.grid(row=0, column=5, padx=(0, 0), sticky='ew')
        
        # 配置输入框的权重
        input_frame.columnconfigure(1, weight=1)
        input_frame.columnconfigure(3, weight=1)
        input_frame.columnconfigure(5, weight=1)
        
        # 按钮区域
        button_frame = ttk.Frame(config_frame)
        button_frame.pack(fill='x')
        
        ttk.Button(button_frame, text="应用到选中标签", command=self.apply_quick_config).pack(side='left', padx=(0, 5))
        ttk.Button(button_frame, text="清空选中标签", command=self.clear_selected_config).pack(side='left', padx=(0, 5))
        ttk.Button(button_frame, text="批量应用常用分类", command=self.show_batch_config).pack(side='left', padx=(0, 5))
        ttk.Button(button_frame, text="智能推荐分类", command=self.smart_recommend).pack(side='left')
    
    def get_gui_instance(self):
        """获取GUI实例"""
        return self.gui_instance
    
    def get_config_status(self, label: str, detection_name: str, primary: str, secondary: str) -> str:
        """获取配置状态"""
        if detection_name and primary and secondary:
            return "完全配置"
        elif detection_name or primary or (secondary and secondary != label):
            return "部分配置"
        elif secondary == label:
            return "部分配置"  # 只有默认的二级分类
        else:
            return "未配置"
    
    def scan_labels(self):
        """扫描标签"""
        # 通过回调函数获取输入文件夹路径
        gui_instance = self.get_gui_instance()
        if not gui_instance:
            messagebox.showerror("错误", "无法获取GUI实例")
            return
            
        input_folder = gui_instance.input_folder_var.get()
        if not input_folder or not os.path.exists(input_folder):
            messagebox.showerror("错误", "请先选择有效的输入文件夹")
            return
        
        try:
            unique_labels, label_stats = self.converter.scan_labels_from_folder(input_folder)
            self.update_table(unique_labels, label_stats)
            messagebox.showinfo("成功", f"扫描完成，找到 {len(unique_labels)} 个唯一标签")
        except Exception as e:
            messagebox.showerror("错误", f"扫描标签失败: {str(e)}")
    
    def update_table(self, labels: List[str], stats: Dict[str, int]):
        """更新表格"""
        # 清空现有数据
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        self.label_entries.clear()
        
        # 添加新数据
        for label in labels:
            count = stats.get(label, 0)
            # 默认二级分类为原标签名，所以状态应该是"部分配置"
            status = "部分配置"
            item_id = self.tree.insert('', 'end', values=(label, count, '', '', label, status))
            
            # 存储变量引用
            self.label_entries[label] = {
                'detection_name': tk.StringVar(),
                'primary': tk.StringVar(),
                'secondary': tk.StringVar(value=label),  # 默认二级分类为原标签名
                'item_id': item_id
            }
    
    def on_item_double_click(self, event):
        """处理双击事件"""
        item = self.tree.selection()[0]
        column = self.tree.identify_column(event.x)
        
        if column in ('#3', '#4', '#5'):  # 检测标签名、一级分类或二级分类列
            self.edit_cell(item, column)
    
    def edit_cell(self, item, column):
        """编辑单元格"""
        # 获取当前值
        values = list(self.tree.item(item, 'values'))
        label = values[0]
        
        # 确定编辑的是哪一列
        col_index = int(column[1:]) - 1
        current_value = values[col_index]
        
        # 创建编辑窗口
        edit_window = tk.Toplevel(self)
        edit_window.title("编辑分类")
        edit_window.geometry("300x150")
        edit_window.transient(self)
        edit_window.grab_set()
        
        # 居中显示
        edit_window.geometry("+%d+%d" % (
            self.winfo_rootx() + 50,
            self.winfo_rooty() + 50
        ))
        
        ttk.Label(edit_window, text=f"标签: {label}").pack(pady=10)
        
        field_names = {2: "检测标签名", 3: "一级分类", 4: "二级分类"}
        field_name = field_names.get(col_index, "未知字段")
        ttk.Label(edit_window, text=f"{field_name}:").pack()
        
        entry_var = tk.StringVar(value=current_value)
        entry = ttk.Entry(edit_window, textvariable=entry_var, width=30)
        entry.pack(pady=5)
        entry.focus()
        entry.select_range(0, tk.END)
        
        def save_value():
            new_value = entry_var.get().strip()
            values[col_index] = new_value
            self.tree.item(item, values=values)
            
            # 更新内部存储
            if col_index == 2:
                self.label_entries[label]['detection_name'].set(new_value)
            elif col_index == 3:
                self.label_entries[label]['primary'].set(new_value)
            elif col_index == 4:
                self.label_entries[label]['secondary'].set(new_value)
            
            edit_window.destroy()
        
        def cancel_edit():
            edit_window.destroy()
        
        button_frame = ttk.Frame(edit_window)
        button_frame.pack(pady=10)
        
        ttk.Button(button_frame, text="保存", command=save_value).pack(side='left', padx=5)
        ttk.Button(button_frame, text="取消", command=cancel_edit).pack(side='left', padx=5)
        
        # 绑定回车键
        entry.bind('<Return>', lambda e: save_value())
        edit_window.bind('<Escape>', lambda e: cancel_edit())
    
    def on_selection_change(self, event):
        """处理选择变化"""
        selection = self.tree.selection()
        if selection:
            item = selection[0]
            values = self.tree.item(item, 'values')
            label = values[0]
            
            # 更新当前选中标签显示
            self.current_label_var.set(label)
            
            # 如果已有配置，显示在快速配置区域
            if label in self.label_entries:
                detection_name = self.label_entries[label]['detection_name'].get()
                primary = self.label_entries[label]['primary'].get()
                secondary = self.label_entries[label]['secondary'].get()
                self.detection_name_var.set(detection_name)
                self.primary_var.set(primary)
                self.secondary_var.set(secondary)
        else:
            self.current_label_var.set("未选中标签")
            self.detection_name_var.set("")
            self.primary_var.set("")
            self.secondary_var.set("")
    
    def apply_quick_config(self):
        """应用快速配置"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择一个标签")
            return
        
        item = selection[0]
        values = list(self.tree.item(item, 'values'))
        label = values[0]
        
        detection_name = self.detection_name_var.get().strip()
        primary = self.primary_var.get().strip()
        secondary = self.secondary_var.get().strip()
        
        if not detection_name and not primary and not secondary:
            messagebox.showwarning("警告", "请至少填写检测标签名、一级分类或二级分类")
            return
        
        # 更新表格显示
        values[2] = detection_name
        values[3] = primary
        values[4] = secondary
        
        # 使用帮助函数获取配置状态
        status = self.get_config_status(label, detection_name, primary, secondary)
        values[5] = status
        self.tree.item(item, values=values)
        
        # 更新内部存储
        self.label_entries[label]['detection_name'].set(detection_name)
        self.label_entries[label]['primary'].set(primary)
        self.label_entries[label]['secondary'].set(secondary)
        
        messagebox.showinfo("成功", f"标签 '{label}' 配置已更新")
    
    def clear_selected_config(self):
        """清空选中标签的配置"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择一个标签")
            return
        
        if not messagebox.askyesno("确认", "确定要清空选中标签的配置吗？"):
            return
        
        item = selection[0]
        values = list(self.tree.item(item, 'values'))
        label = values[0]
        
        # 清空配置，但保持二级分类为原标签名
        values[2] = ""
        values[3] = ""
        values[4] = label  # 重置二级分类为原标签名
        values[5] = "部分配置"  # 因为还有默认的二级分类
        self.tree.item(item, values=values)
        
        # 更新内部存储
        self.label_entries[label]['detection_name'].set("")
        self.label_entries[label]['primary'].set("")
        self.label_entries[label]['secondary'].set(label)  # 重置为原标签名
        
        # 清空输入框，但保持二级分类
        self.detection_name_var.set("")
        self.primary_var.set("")
        self.secondary_var.set(label)  # 显示原标签名
        
        messagebox.showinfo("成功", f"标签 '{label}' 配置已清空")
    
    def show_batch_config(self):
        """显示批量配置对话框"""
        BatchConfigDialog(self, self.label_entries, self.tree, self.update_table_status)
    
    def smart_recommend(self):
        """智能推荐分类"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择一个标签")
            return
        
        item = selection[0]
        values = self.tree.item(item, 'values')
        label = values[0].lower()
        
        # 智能推荐规则
        recommendations = {
            # 交通工具类
            'car': ('vehicle', 'car'),
            'truck': ('vehicle', 'truck'),
            'bus': ('vehicle', 'bus'),
            'motorcycle': ('vehicle', 'motorcycle'),
            'bicycle': ('vehicle', 'bicycle'),
            'bike': ('vehicle', 'bicycle'),
            
            # 人物类
            'person': ('human', 'pedestrian'),
            'people': ('human', 'pedestrian'),
            'man': ('human', 'pedestrian'),
            'woman': ('human', 'pedestrian'),
            'child': ('human', 'child'),
            
            # 动物类
            'dog': ('animal', 'mammal'),
            'cat': ('animal', 'mammal'),
            'bird': ('animal', 'bird'),
            'horse': ('animal', 'mammal'),
            
            # 交通设施类
            'traffic_light': ('infrastructure', 'traffic_control'),
            'stop_sign': ('infrastructure', 'traffic_control'),
            'traffic_sign': ('infrastructure', 'traffic_control'),
            
            # 建筑类
            'building': ('structure', 'building'),
            'house': ('structure', 'building'),
            'bridge': ('structure', 'bridge'),
            
            # 自然类
            'tree': ('nature', 'vegetation'),
            'flower': ('nature', 'vegetation'),
            'grass': ('nature', 'vegetation'),
        }
        
        if label in recommendations:
            primary, _ = recommendations[label]  # 忽略推荐的二级分类
            # 从原标签中提取检测标签名
            detection_name = values[0]
            if '_' in values[0]:
                detection_name = values[0].split('_')[0]
            
            self.detection_name_var.set(detection_name)
            self.primary_var.set(primary)
            self.secondary_var.set(values[0])  # 二级分类使用原标签名
            messagebox.showinfo("智能推荐", f"为标签 '{values[0]}' 推荐分类:\n检测标签名: {detection_name}\n一级分类: {primary}\n二级分类: {values[0]}")
        else:
            # 即使没有推荐，也设置默认的检测标签名和二级分类
            detection_name = values[0]
            if '_' in values[0]:
                detection_name = values[0].split('_')[0]
            
            self.detection_name_var.set(detection_name)
            self.secondary_var.set(values[0])  # 二级分类使用原标签名
            messagebox.showinfo("智能推荐", f"暂未找到标签 '{values[0]}' 的推荐分类，已设置默认配置:\n检测标签名: {detection_name}\n二级分类: {values[0]}\n请手动配置一级分类")
    
    def update_table_status(self):
        """更新表格状态显示"""
        for label, entry_vars in self.label_entries.items():
            item_id = entry_vars['item_id']
            values = list(self.tree.item(item_id, 'values'))
            
            detection_name = entry_vars['detection_name'].get()
            primary = entry_vars['primary'].get()
            secondary = entry_vars['secondary'].get()
            
            values[2] = detection_name
            values[3] = primary
            values[4] = secondary
            
            # 使用帮助函数获取配置状态
            status = self.get_config_status(label, detection_name, primary, secondary)
            values[5] = status
            self.tree.item(item_id, values=values)
    
    def get_label_mapping(self) -> LabelMapping:
        """获取标签映射"""
        mapping = LabelMapping()
        
        for label, entry_vars in self.label_entries.items():
            detection_name = entry_vars['detection_name'].get().strip()
            primary = entry_vars['primary'].get().strip()
            secondary = entry_vars['secondary'].get().strip()
            
            if detection_name or primary or secondary:
                mapping.add_mapping(label, detection_name, primary, secondary)
        
        return mapping
    
    def set_label_mapping(self, mapping: LabelMapping):
        """设置标签映射"""
        for label, mapping_data in mapping.mappings.items():
            if label in self.label_entries:
                detection_name = mapping_data.get('detection_name', '')
                primary = mapping_data.get('primary', '')
                secondary = mapping_data.get('secondary', '')
                
                self.label_entries[label]['detection_name'].set(detection_name)
                self.label_entries[label]['primary'].set(primary)
                self.label_entries[label]['secondary'].set(secondary)
                
                # 更新表格显示
                item_id = self.label_entries[label]['item_id']
                values = list(self.tree.item(item_id, 'values'))
                values[2] = detection_name
                values[3] = primary
                values[4] = secondary
                
                # 使用帮助函数获取配置状态
                status = self.get_config_status(label, detection_name, primary, secondary)
                values[5] = status
                self.tree.item(item_id, values=values)
    
    def import_config(self):
        """导入配置"""
        filename = filedialog.askopenfilename(
            title="导入标签映射配置",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")]
        )
        
        if filename:
            mapping = LabelMapping()
            if mapping.load_from_file(filename):
                self.set_label_mapping(mapping)
                messagebox.showinfo("成功", "配置导入成功")
            else:
                messagebox.showerror("错误", "配置文件格式错误或读取失败")
    
    def export_config(self):
        """导出配置"""
        if not self.label_entries:
            messagebox.showwarning("警告", "没有标签配置可导出")
            return
        
        filename = filedialog.asksaveasfilename(
            title="导出标签映射配置",
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")]
        )
        
        if filename:
            try:
                mapping = self.get_label_mapping()
                mapping.save_to_file(filename)
                messagebox.showinfo("成功", "配置导出成功")
            except Exception as e:
                messagebox.showerror("错误", f"导出失败: {str(e)}")
    
    def clear_config(self):
        """清空配置"""
        if messagebox.askyesno("确认", "确定要清空所有标签配置吗？"):
            for label, entry_vars in self.label_entries.items():
                entry_vars['detection_name'].set('')
                entry_vars['primary'].set('')
                entry_vars['secondary'].set(label)  # 重置为原标签名
                
                # 更新表格显示
                item_id = entry_vars['item_id']
                values = list(self.tree.item(item_id, 'values'))
                values[2] = ''
                values[3] = ''
                values[4] = label  # 重置二级分类为原标签名
                values[5] = '部分配置'  # 因为还有默认的二级分类
                self.tree.item(item_id, values=values)

class ConverterGUI:
    """转换器GUI主类"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.converter = LabelmeConverter()
        self.setup_variables()
        self.setup_ui()
        self.setup_bindings()
    
    def setup_variables(self):
        """设置变量"""
        self.input_folder_var = tk.StringVar()
        self.output_folder_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="single")
        self.is_converting = False
    
    def setup_ui(self):
        """设置UI"""
        self.root.title("Labelme标注转换工具 v2.0")
        self.root.geometry("800x700")
        
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill='both', expand=True)
        
        # 文件路径配置区域
        self.create_path_section(main_frame)
        
        # 转换模式选择
        self.create_mode_section(main_frame)
        
        # 标签配置区域（混合模式时显示）
        self.create_label_config_section(main_frame)
        
        # 控制按钮区域
        self.create_control_section(main_frame)
        
        # 日志信息区域
        self.create_log_section(main_frame)
        
        # 初始化界面状态
        self.on_mode_change()
    
    def create_path_section(self, parent):
        """创建路径配置区域"""
        path_frame = ttk.LabelFrame(parent, text="文件路径配置", padding="10")
        path_frame.pack(fill='x', pady=(0, 10))
        
        # 输入文件夹
        input_frame = ttk.Frame(path_frame)
        input_frame.pack(fill='x', pady=(0, 5))
        
        ttk.Label(input_frame, text="输入文件夹:", width=12).pack(side='left')
        ttk.Entry(input_frame, textvariable=self.input_folder_var, width=50).pack(side='left', padx=(5, 5), fill='x', expand=True)
        ttk.Button(input_frame, text="浏览...", command=self.browse_input_folder).pack(side='right')
        
        # 输出文件夹
        output_frame = ttk.Frame(path_frame)
        output_frame.pack(fill='x')
        
        ttk.Label(output_frame, text="输出文件夹:", width=12).pack(side='left')
        ttk.Entry(output_frame, textvariable=self.output_folder_var, width=50).pack(side='left', padx=(5, 5), fill='x', expand=True)
        ttk.Button(output_frame, text="浏览...", command=self.browse_output_folder).pack(side='right')
    
    def create_mode_section(self, parent):
        """创建模式选择区域"""
        mode_frame = ttk.LabelFrame(parent, text="转换模式", padding="10")
        mode_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Radiobutton(mode_frame, text="单检测模式", variable=self.mode_var, 
                       value="single", command=self.on_mode_change).pack(side='left', padx=(0, 20))
        ttk.Radiobutton(mode_frame, text="混合标注模式", variable=self.mode_var, 
                       value="mixed", command=self.on_mode_change).pack(side='left')
        
        # 添加说明标签
        ttk.Label(mode_frame, text="（混合标注模式支持多级分类标签）", 
                 foreground="gray").pack(side='left', padx=(20, 0))
    
    def create_label_config_section(self, parent):
        """创建标签配置区域"""
        self.label_config_frame = ttk.LabelFrame(parent, text="标签分类配置", padding="10")
        self.label_config_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        # 创建标签配置组件，传递GUI实例引用
        self.label_config = LabelConfigFrame(self.label_config_frame, self.converter, self)
        self.label_config.pack(fill='both', expand=True)
    
    def create_control_section(self, parent):
        """创建控制按钮区域"""
        control_frame = ttk.Frame(parent)
        control_frame.pack(fill='x', pady=(0, 10))
        
        # 居中放置按钮
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(expand=True)
        
        self.convert_button = ttk.Button(button_frame, text="开始转换", command=self.start_conversion)
        self.convert_button.pack(side='left', padx=5)
        
        ttk.Button(button_frame, text="重置", command=self.reset_form).pack(side='left', padx=5)
        ttk.Button(button_frame, text="退出", command=self.root.quit).pack(side='left', padx=5)
    
    def create_log_section(self, parent):
        """创建日志区域"""
        log_frame = ttk.LabelFrame(parent, text="处理日志", padding="10")
        log_frame.pack(fill='both', expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, wrap=tk.WORD)
        self.log_text.pack(fill='both', expand=True)
        
        # 初始化日志
        self.log_message("程序就绪，请选择输入文件夹...")
    
    def setup_bindings(self):
        """设置事件绑定"""
        # 文件夹路径变化时的验证
        self.input_folder_var.trace('w', self.validate_paths)
        self.output_folder_var.trace('w', self.validate_paths)
    
    def browse_input_folder(self):
        """浏览输入文件夹"""
        folder = filedialog.askdirectory(title="选择包含图片和标注文件的输入文件夹")
        if folder:
            self.input_folder_var.set(folder)
    
    def browse_output_folder(self):
        """浏览输出文件夹"""
        folder = filedialog.askdirectory(title="选择输出文件夹")
        if folder:
            self.output_folder_var.set(folder)
    
    def on_mode_change(self):
        """模式变化处理"""
        if self.mode_var.get() == "mixed":
            self.label_config_frame.pack(fill='both', expand=True, pady=(0, 10))
        else:
            self.label_config_frame.pack_forget()
    
    def validate_paths(self, *args):
        """验证路径"""
        input_folder = self.input_folder_var.get()
        output_folder = self.output_folder_var.get()
        
        if input_folder and not os.path.exists(input_folder):
            self.log_message(f"警告: 输入文件夹不存在: {input_folder}")
        elif input_folder and os.path.exists(input_folder):
            # 检查是否包含JSON文件
            import glob
            json_files = glob.glob(os.path.join(input_folder, "*.json"))
            if json_files:
                self.log_message(f"输入文件夹验证通过，发现 {len(json_files)} 个JSON文件")
            else:
                self.log_message("警告: 输入文件夹中未发现JSON标注文件")
    
    def log_message(self, message: str):
        """记录日志消息"""
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def start_conversion(self):
        """开始转换"""
        if self.is_converting:
            return
        
        # 验证输入
        input_folder = self.input_folder_var.get()
        output_folder = self.output_folder_var.get()
        
        if not input_folder or not os.path.exists(input_folder):
            messagebox.showerror("错误", "请选择有效的输入文件夹")
            return
        
        if not output_folder:
            messagebox.showerror("错误", "请选择输出文件夹")
            return
        
        # 确定转换模式
        mode = ConversionMode.MIXED_ANNOTATION if self.mode_var.get() == "mixed" else ConversionMode.SINGLE_DETECTION
        
        # 如果是混合模式，获取标签映射
        if mode == ConversionMode.MIXED_ANNOTATION:
            label_mapping = self.label_config.get_label_mapping()
            self.converter.set_label_mapping(label_mapping)
        
        # 清空日志
        self.log_text.delete(1.0, tk.END)
        self.log_message("开始转换...")
        
        # 禁用转换按钮
        self.is_converting = True
        self.convert_button.config(text="转换中...", state='disabled')
        
        # 在后台线程执行转换
        def conversion_thread():
            try:
                success, message = self.converter.convert_labelme_to_format(
                    input_folder, output_folder, mode, self.log_message
                )
                
                # 在主线程中更新UI
                self.root.after(0, lambda: self.conversion_complete(success, message))
            
            except Exception as e:
                error_msg = f"转换过程中发生异常: {str(e)}"
                self.root.after(0, lambda: self.conversion_complete(False, error_msg))
        
        thread = threading.Thread(target=conversion_thread, daemon=True)
        thread.start()
    
    def conversion_complete(self, success: bool, message: str):
        """转换完成处理"""
        self.is_converting = False
        self.convert_button.config(text="开始转换", state='normal')
        
        if success:
            messagebox.showinfo("成功", "转换完成！")
            self.log_message("=" * 50)
            self.log_message("转换完成！")
        else:
            messagebox.showerror("错误", f"转换失败: {message}")
    
    def reset_form(self):
        """重置表单"""
        if messagebox.askyesno("确认", "确定要重置所有设置吗？"):
            self.input_folder_var.set("")
            self.output_folder_var.set("")
            self.mode_var.set("single")
            self.log_text.delete(1.0, tk.END)
            self.log_message("程序就绪，请选择输入文件夹...")
            self.on_mode_change()
    
    def run(self):
        """运行GUI"""
        self.root.mainloop()

if __name__ == "__main__":
    app = ConverterGUI()
    app.run() 