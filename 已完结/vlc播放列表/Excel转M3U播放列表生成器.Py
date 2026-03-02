import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pandas as pd
import os


class ExcelToM3UConverter:
    def __init__(self, root):
        self.root = root
        self.root.title("Excel转M3U播放列表生成器")
        self.root.geometry("600x400")
        self.root.resizable(False, False)
        
        # 设置样式
        style = ttk.Style()
        style.theme_use('clam')
        
        # 创建主框架
        main_frame = ttk.Frame(root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 标题
        title_label = ttk.Label(main_frame, text="监控点M3U文件生成器", 
                                font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # 输入文件选择
        ttk.Label(main_frame, text="输入Excel文件:", font=('Arial', 10)).grid(
            row=1, column=0, sticky=tk.W, pady=10)
        
        self.input_file_var = tk.StringVar()
        input_entry = ttk.Entry(main_frame, textvariable=self.input_file_var, 
                               width=40, state='readonly')
        input_entry.grid(row=1, column=1, padx=10, pady=10)
        
        browse_btn = ttk.Button(main_frame, text="浏览", command=self.browse_file)
        browse_btn.grid(row=1, column=2, pady=10)
        
        # RTSP端口和路径设置
        ttk.Label(main_frame, text="RTSP端口:", font=('Arial', 10)).grid(
            row=2, column=0, sticky=tk.W, pady=10)
        
        self.port_var = tk.StringVar(value="554")
        port_entry = ttk.Entry(main_frame, textvariable=self.port_var, width=40)
        port_entry.grid(row=2, column=1, padx=10, pady=10)
        
        ttk.Label(main_frame, text="RTSP路径:", font=('Arial', 10)).grid(
            row=3, column=0, sticky=tk.W, pady=10)
        
        self.path_var = tk.StringVar(value="/Streaming/Channels/101")
        path_entry = ttk.Entry(main_frame, textvariable=self.path_var, width=40)
        path_entry.grid(row=3, column=1, padx=10, pady=10)
        
        # 输出文件名设置
        ttk.Label(main_frame, text="输出文件名:", font=('Arial', 10)).grid(
            row=4, column=0, sticky=tk.W, pady=10)
        
        self.output_name_var = tk.StringVar(value="playlist.m3u")
        output_entry = ttk.Entry(main_frame, textvariable=self.output_name_var, width=40)
        output_entry.grid(row=4, column=1, padx=10, pady=10)
        
        # 生成按钮
        generate_btn = ttk.Button(main_frame, text="生成M3U文件", 
                                 command=self.generate_m3u, 
                                 style='Accent.TButton')
        generate_btn.grid(row=5, column=0, columnspan=3, pady=20)
        
        # 状态栏
        self.status_var = tk.StringVar(value="请选择Excel文件")
        status_label = ttk.Label(main_frame, textvariable=self.status_var, 
                                relief=tk.SUNKEN, anchor=tk.W)
        status_label.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(10, 0))
        
        # 说明文字
        info_text = "说明: Excel文件需包含A列(监控点名称)、B列(IP地址)、C列(密码)"
        info_label = ttk.Label(main_frame, text=info_text, 
                              font=('Arial', 8), foreground='gray')
        info_label.grid(row=7, column=0, columnspan=3, pady=(5, 0))
        
    def browse_file(self):
        filename = filedialog.askopenfilename(
            title="选择Excel文件",
            filetypes=[("Excel文件", "*.xlsx"), ("所有文件", "*.*")]
        )
        if filename:
            self.input_file_var.set(filename)
            self.status_var.set(f"已选择: {os.path.basename(filename)}")
    
    def generate_m3u(self):
        input_file = self.input_file_var.get()
        
        if not input_file:
            messagebox.showwarning("警告", "请先选择Excel文件!")
            return
        
        if not os.path.exists(input_file):
            messagebox.showerror("错误", "选择的文件不存在!")
            return
        
        try:
            # 读取Excel文件
            self.status_var.set("正在读取Excel文件...")
            self.root.update()
            
            df = pd.read_excel(input_file)
            
            # 检查列数
            if df.shape[1] < 3:
                messagebox.showerror("错误", "Excel文件列数不足!需要至少3列(名称、IP、密码)")
                return
            
            # 获取列数据
            names = df.iloc[:, 0]  # A列:名称
            ips = df.iloc[:, 1]    # B列:IP
            passwords = df.iloc[:, 2]  # C列:密码
            
            # 获取配置参数
            port = self.port_var.get()
            path = self.path_var.get()
            output_name = self.output_name_var.get()
            
            # 生成M3U内容
            self.status_var.set("正在生成M3U文件...")
            self.root.update()
            
            m3u_content = "#EXTM3U\n"
            
            for i in range(len(df)):
                name = names.iloc[i]
                ip = ips.iloc[i]
                password = passwords.iloc[i]
                
                # 跳过空行
                if pd.isna(name) or pd.isna(ip):
                    continue
                
                # 处理密码为空的情况
                password = password if not pd.isna(password) else ""
                
                # 生成RTSP链接
                rtsp_url = f"rtsp://admin:{password}@{ip}:{port}{path}"
                
                # 添加到M3U内容
                m3u_content += f"#EXTINF:-1,{name}\n"
                m3u_content += f"{rtsp_url}\n"
            
            # 保存文件
            output_path = os.path.join(os.path.dirname(input_file), output_name)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(m3u_content)
            
            self.status_var.set(f"成功生成: {output_name}")
            messagebox.showinfo("成功", 
                              f"M3U文件已生成!\n路径: {output_path}\n共生成 {len(df)} 个监控点")
            
        except Exception as e:
            self.status_var.set("生成失败")
            messagebox.showerror("错误", f"生成M3U文件时出错:\n{str(e)}")


def main():
    root = tk.Tk()
    app = ExcelToM3UConverter(root)
    root.mainloop()


if __name__ == "__main__":
    main()