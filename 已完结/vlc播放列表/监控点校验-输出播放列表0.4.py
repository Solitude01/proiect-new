import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pandas as pd
import os
import requests
from requests.auth import HTTPDigestAuth
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import queue
import time

# 常量配置
DEFAULT_THREAD_COUNT = 50
MIN_THREAD_COUNT = 5
MAX_THREAD_COUNT = 100


class ExcelToM3UConverter:
    def __init__(self, root):
        self.root = root
        self.root.title("Excel转M3U播放列表生成器")
        self.root.geometry("850x900")
        self.root.resizable(True, True)
        
        self.camera_data = []
        self.verified_data = []

        # 新增：并发控制和取消机制
        self.result_queue = queue.Queue()
        self.cancel_flag = threading.Event()
        self.is_verifying = False
        self.session = None
        self.start_time = None
        self.success_count = 0
        self.failed_count = 0
        self.processed_count = 0
        
        # 设置样式
        style = ttk.Style()
        style.theme_use('clam')
        
        # 创建主框架
        main_frame = ttk.Frame(root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(6, weight=1)
        
        # 标题
        title_label = ttk.Label(main_frame, text="监控点M3U文件生成器", 
                                font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # 输入文件选择
        ttk.Label(main_frame, text="输入Excel文件:", font=('Arial', 10)).grid(
            row=1, column=0, sticky=tk.W, pady=10)
        
        self.input_file_var = tk.StringVar()
        input_entry = ttk.Entry(main_frame, textvariable=self.input_file_var, 
                               width=50, state='readonly')
        input_entry.grid(row=1, column=1, padx=10, pady=10, sticky=(tk.W, tk.E))
        
        browse_btn = ttk.Button(main_frame, text="浏览", command=self.browse_file)
        browse_btn.grid(row=1, column=2, pady=10)
        
        # 配置框架
        config_frame = ttk.LabelFrame(main_frame, text="RTSP配置", padding="10")
        config_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        config_frame.columnconfigure(1, weight=1)
        
        ttk.Label(config_frame, text="RTSP端口:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.port_var = tk.StringVar(value="554")
        ttk.Entry(config_frame, textvariable=self.port_var, width=20).grid(
            row=0, column=1, padx=10, pady=5, sticky=tk.W)
        
        ttk.Label(config_frame, text="RTSP路径:").grid(row=0, column=2, sticky=tk.W, pady=5, padx=(20, 0))
        self.path_var = tk.StringVar(value="/Streaming/Channels/101")
        ttk.Entry(config_frame, textvariable=self.path_var, width=30).grid(
            row=0, column=3, padx=10, pady=5, sticky=tk.W)
        
        ttk.Label(config_frame, text="输出文件名:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.output_name_var = tk.StringVar(value="playlist.m3u")
        ttk.Entry(config_frame, textvariable=self.output_name_var, width=20).grid(
            row=1, column=1, padx=10, pady=5, sticky=tk.W)
        
        ttk.Label(config_frame, text="超时时间(秒):").grid(row=1, column=2, sticky=tk.W, pady=5, padx=(20, 0))
        self.timeout_var = tk.StringVar(value="3")
        ttk.Entry(config_frame, textvariable=self.timeout_var, width=10).grid(
            row=1, column=3, padx=10, pady=5, sticky=tk.W)

        # 新增：并发线程数配置
        ttk.Label(config_frame, text="并发线程数:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.thread_count_var = tk.IntVar(value=DEFAULT_THREAD_COUNT)
        thread_spinbox = ttk.Spinbox(config_frame, from_=MIN_THREAD_COUNT, to=MAX_THREAD_COUNT,
                                     textvariable=self.thread_count_var, width=8)
        thread_spinbox.grid(row=2, column=1, padx=10, pady=5, sticky=tk.W)

        # 线程数快捷预设按钮
        thread_preset_frame = ttk.Frame(config_frame)
        thread_preset_frame.grid(row=2, column=2, columnspan=2, sticky=tk.W, padx=(20, 0))
        for count in [10, 30, 50, 100]:
            btn = ttk.Button(thread_preset_frame, text=str(count), width=4,
                           command=lambda c=count: self.thread_count_var.set(c))
            btn.pack(side=tk.LEFT, padx=2)
        
        # 按钮框架
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=3, column=0, columnspan=3, pady=10)
        
        self.verify_btn = ttk.Button(btn_frame, text="1. 校验摄像头", 
                                     command=self.verify_cameras)
        self.verify_btn.grid(row=0, column=0, padx=5)
        
        self.export_btn = ttk.Button(btn_frame, text="2. 导出校验结果", 
                                    command=self.export_verification, state='disabled')
        self.export_btn.grid(row=0, column=1, padx=5)
        
        self.generate_btn = ttk.Button(btn_frame, text="3. 生成M3U文件",
                                      command=self.generate_m3u, state='disabled')
        self.generate_btn.grid(row=0, column=2, padx=5)

        # 新增：取消验证按钮
        self.cancel_btn = ttk.Button(btn_frame, text="取消验证",
                                    command=self.cancel_verification, state='disabled')
        self.cancel_btn.grid(row=0, column=3, padx=5)
        
        # 进度条
        self.progress = ttk.Progressbar(main_frame, mode='determinate')
        self.progress.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)

        # 新增：统计信息显示
        self.stats_frame = ttk.Frame(main_frame)
        self.stats_frame.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 5))

        self.stats_var = tk.StringVar(value="")
        self.stats_label = ttk.Label(self.stats_frame, textvariable=self.stats_var,
                                     font=('Arial', 9))
        self.stats_label.pack(side=tk.LEFT)

        # 结果显示框架
        result_frame = ttk.LabelFrame(main_frame, text="校验结果", padding="10")
        result_frame.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(0, weight=1)
        
        # 创建Treeview
        columns = ('序号', '名称', 'IP地址', '状态', '说明')
        self.tree = ttk.Treeview(result_frame, columns=columns, show='headings', height=15)
        
        # 定义列
        self.tree.heading('序号', text='序号')
        self.tree.heading('名称', text='监控点名称')
        self.tree.heading('IP地址', text='IP地址')
        self.tree.heading('状态', text='状态')
        self.tree.heading('说明', text='说明')
        
        self.tree.column('序号', width=50, anchor='center')
        self.tree.column('名称', width=200)
        self.tree.column('IP地址', width=120, anchor='center')
        self.tree.column('状态', width=80, anchor='center')
        self.tree.column('说明', width=300)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(result_frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # 配置标签颜色
        self.tree.tag_configure('success', foreground='green')
        self.tree.tag_configure('error', foreground='red')
        self.tree.tag_configure('warning', foreground='orange')
        
        # 状态栏
        self.status_var = tk.StringVar(value="请选择Excel文件并点击校验")
        status_label = ttk.Label(main_frame, textvariable=self.status_var,
                                relief=tk.SUNKEN, anchor=tk.W)
        status_label.grid(row=7, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(10, 0))

        # 说明文字
        info_text = "说明: Excel文件需包含A列(监控点名称)、B列(IP地址)、C列(密码)。操作步骤: 1.校验→2.导出结果→3.生成M3U"
        info_label = ttk.Label(main_frame, text=info_text,
                              font=('Arial', 8), foreground='gray')
        info_label.grid(row=8, column=0, columnspan=3, pady=(5, 0))
        
    def browse_file(self):
        filename = filedialog.askopenfilename(
            title="选择Excel文件",
            filetypes=[("Excel文件", "*.xlsx"), ("所有文件", "*.*")]
        )
        if filename:
            self.input_file_var.set(filename)
            self.status_var.set(f"已选择: {os.path.basename(filename)}")
            self.generate_btn.config(state='disabled')
            self.export_btn.config(state='disabled')
            self.tree.delete(*self.tree.get_children())

    def init_session(self):
        """初始化带连接池的Session"""
        self.session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=50,
            pool_maxsize=50,
            max_retries=Retry(total=1, backoff_factor=0.1)
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def cancel_verification(self):
        """取消正在进行的验证"""
        self.cancel_flag.set()
        self.status_var.set("正在取消验证...")
        self.cancel_btn.config(state='disabled')

    def _update_tree_item(self, result):
        """更新单个树节点"""
        # 确定状态和标签
        if result['status'] == 'success':
            tag = 'success'
            status_text = '✓ 正常'
            self.success_count += 1
            self.verified_data.append(result)
        elif result['status'] == 'auth_failed':
            tag = 'error'
            status_text = '✗ 密码错误'
            self.failed_count += 1
        elif result['status'] == 'timeout':
            tag = 'warning'
            status_text = '⚠ 超时'
            self.failed_count += 1
        elif result['status'] == 'cancelled':
            tag = 'warning'
            status_text = '⊘ 已取消'
            self.failed_count += 1
        else:
            tag = 'error'
            status_text = '✗ 失败'
            self.failed_count += 1

        # 插入到表格
        self.tree.insert('', 'end', values=(
            result['index'],
            result['name'],
            result['ip'],
            status_text,
            result['message']
        ), tags=(tag,))

        self.processed_count += 1

    def _update_statistics(self):
        """更新统计信息显示"""
        total = len(self.camera_data)
        remaining = total - self.processed_count

        # 计算速度
        elapsed = time.time() - self.start_time if self.start_time else 0
        speed = self.processed_count / elapsed if elapsed > 0 else 0

        # 更新进度条
        self.progress['value'] = self.processed_count

        # 更新统计显示
        self.stats_var.set(
            f"总数: {total}  |  "
            f"成功: {self.success_count}  |  "
            f"失败: {self.failed_count}  |  "
            f"剩余: {remaining}  |  "
            f"速度: {speed:.1f}/秒"
        )

        # 更新状态栏
        self.status_var.set(
            f"校验中... {self.processed_count}/{total}"
        )

    def process_result_queue(self):
        """批量处理结果队列（非阻塞）"""
        batch = []
        try:
            while len(batch) < 10:
                batch.append(self.result_queue.get_nowait())
        except queue.Empty:
            pass

        for result in batch:
            self._update_tree_item(result)

        if batch:
            self._update_statistics()

        if self.is_verifying:
            self.root.after(100, self.process_result_queue)

    def on_verification_complete(self):
        """验证完成回调"""
        self.is_verifying = False

        # 处理队列中剩余的结果
        while True:
            try:
                result = self.result_queue.get_nowait()
                self._update_tree_item(result)
            except queue.Empty:
                break

        self._update_statistics()

        # 关闭session
        if self.session:
            self.session.close()
            self.session = None

        # 恢复按钮状态
        self.verify_btn.config(state='normal')
        self.cancel_btn.config(state='disabled')

        total = len(self.camera_data)

        if self.cancel_flag.is_set():
            self.status_var.set(
                f"验证已取消! 已处理: {self.processed_count}/{total}, "
                f"成功: {self.success_count}, 失败: {self.failed_count}"
            )
            if self.success_count > 0:
                self.export_btn.config(state='normal')
                self.generate_btn.config(state='normal')
        elif self.success_count > 0:
            self.export_btn.config(state='normal')
            self.generate_btn.config(state='normal')
            self.status_var.set(
                f"校验完成! 成功: {self.success_count}, 失败: {self.failed_count}. "
                f"可以导出校验结果或生成M3U文件(仅包含成功的{self.success_count}个)"
            )
            messagebox.showinfo(
                "校验完成",
                f"校验完成!\n\n"
                f"成功: {self.success_count} 个\n"
                f"失败: {self.failed_count} 个\n\n"
                f"可以点击'导出校验结果'保存完整报告\n"
                f"或点击'生成M3U文件'继续"
            )
        else:
            self.export_btn.config(state='normal')
            self.status_var.set(f"校验完成! 所有 {total} 个摄像头都连接失败")
            messagebox.showerror("错误", "所有摄像头都连接失败,请检查网络和配置!")
    
    def check_camera(self, index, name, ip, password, timeout):
        """检查单个摄像头的连接状态"""
        result = {
            'index': index,
            'name': name,
            'ip': ip,
            'password': password,
            'status': 'unknown',
            'message': ''
        }

        # 检查是否已取消
        if self.cancel_flag.is_set():
            result['status'] = 'cancelled'
            result['message'] = '验证已取消'
            return result

        try:
            # 使用Digest认证检查设备状态
            url = f"http://{ip}:80/ISAPI/System/status"
            # 使用session（如果可用）或requests
            http_client = self.session if self.session else requests
            response = http_client.get(
                url,
                auth=HTTPDigestAuth('admin', password),
                timeout=timeout
            )

            if response.status_code == 200:
                result['status'] = 'success'
                result['message'] = '连接成功,密码正确'
            elif response.status_code == 401:
                result['status'] = 'auth_failed'
                result['message'] = '认证失败,密码错误'
            else:
                result['status'] = 'error'
                result['message'] = f'HTTP状态码: {response.status_code}'

        except requests.exceptions.Timeout:
            result['status'] = 'timeout'
            result['message'] = '连接超时,无法ping 通'
        except requests.exceptions.ConnectionError:
            result['status'] = 'connection_error'
            result['message'] = '无法连接,请检查IP地址和网络'
        except Exception as e:
            result['status'] = 'error'
            result['message'] = f'错误: {str(e)}'

        return result
    
    def verify_cameras(self):
        """校验所有摄像头"""
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

            if df.shape[1] < 3:
                messagebox.showerror("错误", "Excel文件列数不足!需要至少3列(名称、IP、密码)")
                return

            # 清空之前的结果
            self.tree.delete(*self.tree.get_children())
            self.camera_data = []
            self.verified_data = []

            # 重置计数器和标志
            self.success_count = 0
            self.failed_count = 0
            self.processed_count = 0
            self.cancel_flag.clear()
            self.is_verifying = True

            # 清空结果队列
            while not self.result_queue.empty():
                try:
                    self.result_queue.get_nowait()
                except queue.Empty:
                    break

            # 准备数据
            for i in range(len(df)):
                name = df.iloc[i, 0]
                ip = df.iloc[i, 1]
                password = df.iloc[i, 2]

                if pd.isna(name) or pd.isna(ip):
                    continue

                password = password if not pd.isna(password) else ""
                self.camera_data.append({
                    'index': i + 1,
                    'name': name,
                    'ip': ip,
                    'password': password
                })

            total = len(self.camera_data)
            if total == 0:
                self.is_verifying = False
                messagebox.showwarning("警告", "没有找到有效的摄像头数据!")
                return

            self.status_var.set(f"开始校验 {total} 个摄像头...")
            self.progress['maximum'] = total
            self.progress['value'] = 0
            self.stats_var.set(f"总数: {total}  |  成功: 0  |  失败: 0  |  剩余: {total}  |  速度: 0.0/秒")

            # 禁用验证按钮，启用取消按钮
            self.verify_btn.config(state='disabled')
            self.export_btn.config(state='disabled')
            self.generate_btn.config(state='disabled')
            self.cancel_btn.config(state='normal')

            # 初始化session和计时器
            self.init_session()
            self.start_time = time.time()

            # 获取用户配置的线程数和超时时间
            timeout = int(self.timeout_var.get())
            thread_count = self.thread_count_var.get()

            # 后台线程执行验证
            def run_verification():
                try:
                    with ThreadPoolExecutor(max_workers=thread_count) as executor:
                        futures = {}
                        for cam in self.camera_data:
                            if self.cancel_flag.is_set():
                                break
                            future = executor.submit(
                                self.check_camera,
                                cam['index'],
                                cam['name'],
                                cam['ip'],
                                cam['password'],
                                timeout
                            )
                            futures[future] = cam

                        for future in as_completed(futures):
                            if self.cancel_flag.is_set():
                                # 取消剩余的任务
                                for f in futures:
                                    f.cancel()
                                break
                            try:
                                result = future.result()
                                self.result_queue.put(result)
                            except Exception as e:
                                cam = futures[future]
                                self.result_queue.put({
                                    'index': cam['index'],
                                    'name': cam['name'],
                                    'ip': cam['ip'],
                                    'password': cam['password'],
                                    'status': 'error',
                                    'message': f'执行错误: {str(e)}'
                                })
                except Exception as e:
                    print(f"验证线程错误: {e}")
                finally:
                    # 通知主线程验证完成
                    self.root.after(0, self.on_verification_complete)

            # 启动后台验证线程
            threading.Thread(target=run_verification, daemon=True).start()

            # 启动UI更新定时器
            self.root.after(100, self.process_result_queue)

        except Exception as e:
            self.status_var.set("校验失败")
            self.verify_btn.config(state='normal')
            self.cancel_btn.config(state='disabled')
            self.is_verifying = False
            messagebox.showerror("错误", f"校验摄像头时出错:\n{str(e)}")
    
    def export_verification(self):
        """导出校验结果到Excel"""
        if not self.camera_data:
            messagebox.showwarning("警告", "没有校验数据,请先进行校验!")
            return
        
        try:
            input_file = self.input_file_var.get()
            
            # 生成新的文件名(在原文件名后添加_校验结果)
            base_name = os.path.splitext(os.path.basename(input_file))[0]
            dir_name = os.path.dirname(input_file)
            output_file = os.path.join(dir_name, f"{base_name}_校验结果.xlsx")
            
            # 确保文件名唯一
            counter = 1
            while os.path.exists(output_file):
                output_file = os.path.join(dir_name, f"{base_name}_校验结果_{counter}.xlsx")
                counter += 1
            
            self.status_var.set("正在导出校验结果...")
            self.root.update()
            
            # 读取原始Excel文件
            df_original = pd.read_excel(input_file)
            
            # 创建状态和说明的映射字典
            status_map = {}
            message_map = {}
            
            # 从tree中获取所有结果
            for item in self.tree.get_children():
                values = self.tree.item(item)['values']
                index = values[0]
                status = values[3]
                message = values[4]
                status_map[index] = status
                message_map[index] = message
            
            # 添加状态和说明列
            df_original['校验状态'] = ''
            df_original['校验说明'] = ''
            
            # 填充校验结果
            for i in range(len(df_original)):
                index = i + 1
                if index in status_map:
                    df_original.at[i, '校验状态'] = status_map[index]
                    df_original.at[i, '校验说明'] = message_map[index]
                else:
                    df_original.at[i, '校验状态'] = '未校验'
                    df_original.at[i, '校验说明'] = '数据为空,跳过校验'
            
            # 保存到新文件
            df_original.to_excel(output_file, index=False, engine='openpyxl')
            
            self.status_var.set(f"校验结果已导出: {os.path.basename(output_file)}")
            messagebox.showinfo(
                "导出成功",
                f"校验结果已成功导出!\n\n"
                f"文件路径:\n{output_file}\n\n"
                f"包含原始数据及校验状态和说明列"
            )
            
        except Exception as e:
            self.status_var.set("导出失败")
            messagebox.showerror("错误", f"导出校验结果时出错:\n{str(e)}")
    
    def generate_m3u(self):
        """生成M3U文件"""
        if not self.verified_data:
            messagebox.showwarning("警告", "没有可用的摄像头数据,请先进行校验!")
            return
        
        try:
            input_file = self.input_file_var.get()
            port = self.port_var.get()
            path = self.path_var.get()
            output_name = self.output_name_var.get()
            
            self.status_var.set("正在生成M3U文件...")
            self.root.update()
            
            # 按原始序号排序，确保输出顺序与Excel一致
            sorted_data = sorted(self.verified_data, key=lambda x: x['index'])
            
            # 生成M3U内容
            m3u_content = "#EXTM3U\n"
            
            for cam in sorted_data:
                name = cam['name']
                ip = cam['ip']
                password = cam['password']
                
                # 生成RTSP链接
                rtsp_url = f"rtsp://admin:{password}@{ip}:{port}{path}"
                
                # 添加到M3U内容
                m3u_content += f"#EXTINF:-1,{name}\n"
                m3u_content += f"{rtsp_url}\n"
            
            # 保存文件
            output_path = os.path.join(os.path.dirname(input_file), output_name)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(m3u_content)
            
            self.status_var.set(f"成功生成: {output_name} (包含{len(sorted_data)}个监控点,已按Excel顺序排序)")
            messagebox.showinfo(
                "成功",
                f"M3U文件已生成!\n\n"
                f"路径: {output_path}\n"
                f"包含: {len(sorted_data)} 个已验证的监控点\n"
                f"顺序: 按Excel原始顺序排列"
            )
            
        except Exception as e:
            self.status_var.set("生成失败")
            messagebox.showerror("错误", f"生成M3U文件时出错:\n{str(e)}")


def main():
    root = tk.Tk()
    app = ExcelToM3UConverter(root)
    root.mainloop()


if __name__ == "__main__":
    main()