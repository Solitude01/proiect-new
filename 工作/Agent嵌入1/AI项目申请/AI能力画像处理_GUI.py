#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI能力画像文档整理助手 - GUI版本
使用DeepSeek R1 API分析项目数据并生成标准化的能力画像字段
"""

import json
import time
import requests
import pandas as pd
from typing import Dict, Any
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import logging
from datetime import datetime


class AICapabilityProcessor:
    """AI能力画像处理器"""

    def __init__(self, api_base: str = "http://ds.scc.com.cn/v1",
                 api_key: str = "0",
                 model: str = "deepseek-r1",
                 log_callback=None):
        """
        初始化处理器

        Args:
            api_base: API基础URL
            api_key: API密钥
            model: 使用的模型名称
            log_callback: 日志回调函数
        """
        self.api_base = api_base.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.log_callback = log_callback

    def _log(self, message: str, level: str = "INFO"):
        """内部日志方法"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_msg = f"[{timestamp}] [{level}] {message}"
        if self.log_callback:
            self.log_callback(formatted_msg)
        else:
            print(formatted_msg)

        # 定义系统提示词
        self.system_prompt = """你是一名专业的AI能力文档整理助手。
你的任务是根据提供的项目基础信息(项目名称、工厂、目标、收益、图片描述),严格按照"图像AI能力画像"的客观、中立、描述性风格输出分析结果。

输入信息包含:
- 项目名称、工厂名称、项目目标
- 收益描述(辅助判断价值点)
- OK图片描述(良品特征)
- NG图片描述(不良品特征,用于推断检测功能)

请生成以下5个字段:
1. "applicationScenario": 用一句话总结该项目的实际应用场景,突出业务背景但避免主观价值评估(如"太棒了"等词汇)。
2. "processingObject": 说明该AI项目接收到的图像或视频来源,例如"工业相机拍摄的PCB板静态图像"。
3. "coreFunctions": 基于目标和NG/OK图片描述,拆解出具体功能点(如"划痕检测"、"异物识别"、"存在性验证"等)。必须是数组。
4. "outputFormat": 说明系统输出的形式,包括数据格式、接口协议(如TCP/Modbus)、联动设备(如PLC停机)等。
5. "deploymentMethod": 描述部署形态(如工控机、服务器、端侧设备)和硬件依赖。如无明确信息,返回"未明确"。

请严格返回JSON格式,不要包含任何其他文字说明。JSON格式示例:
{
  "applicationScenario": "...",
  "processingObject": "...",
  "coreFunctions": ["...", "..."],
  "outputFormat": "...",
  "deploymentMethod": "..."
}"""

    def call_api(self, project_name: str, factory: str, goal: str,
                 benefit: str, ok_desc: str, ng_desc: str,
                 max_retries: int = 3) -> Dict[str, Any]:
        """
        调用DeepSeek API分析项目

        Args:
            project_name: 项目名称
            factory: 工厂名称
            goal: 项目目标
            benefit: 收益描述
            ok_desc: OK图片描述
            ng_desc: NG图片描述
            max_retries: 最大重试次数

        Returns:
            包含分析结果的字典
        """
        self._log(f"开始调用API处理项目: {project_name}", "DEBUG")

        # 构建用户查询
        user_query = f"""分析以下项目:
- 项目名称: {project_name}
- 工厂名称: {factory}
- 项目目标: {goal}
- 收益描述: {benefit}
- OK图片描述: {ok_desc}
- NG图片描述: {ng_desc}"""

        self._log(f"用户查询内容:\n{user_query}", "DEBUG")

        # 构建请求payload
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_query}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }

        self._log(f"请求模型: {self.model}, Temperature: 0.1", "DEBUG")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        # 重试逻辑
        delay = 1
        for attempt in range(max_retries):
            try:
                self._log(f"发送API请求 (尝试 {attempt + 1}/{max_retries})...", "DEBUG")
                start_time = time.time()

                response = requests.post(
                    f"{self.api_base}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60
                )

                elapsed_time = time.time() - start_time
                self._log(f"API响应时间: {elapsed_time:.2f}秒", "DEBUG")

                if response.status_code == 200:
                    result = response.json()
                    self._log(f"API响应状态码: 200 OK", "DEBUG")

                    # 解析返回的JSON内容
                    if "choices" in result and len(result["choices"]) > 0:
                        content = result["choices"][0]["message"]["content"]
                        self._log(f"API返回内容长度: {len(content)} 字符", "DEBUG")
                        self._log(f"API返回内容:\n{content}", "DEBUG")

                        parsed_result = json.loads(content)
                        self._log(f"JSON解析成功", "DEBUG")
                        self._log(f"解析结果: {json.dumps(parsed_result, ensure_ascii=False, indent=2)}", "DEBUG")

                        return parsed_result
                    else:
                        error_msg = "API返回格式异常: 缺少choices字段"
                        self._log(error_msg, "ERROR")
                        raise Exception(error_msg)

                elif response.status_code == 429:
                    self._log(f"API限流 (429), 等待 {delay} 秒后重试...", "WARNING")
                    time.sleep(delay)
                    delay *= 2
                else:
                    error_msg = f"API错误: {response.status_code} {response.text}"
                    self._log(error_msg, "ERROR")
                    raise Exception(error_msg)

            except json.JSONDecodeError as e:
                error_msg = f"JSON解析失败: {str(e)}"
                self._log(error_msg, "ERROR")
                if attempt == max_retries - 1:
                    raise Exception(error_msg)
                time.sleep(delay)
                delay *= 2

            except requests.exceptions.Timeout:
                error_msg = "API请求超时"
                self._log(error_msg, "WARNING")
                if attempt == max_retries - 1:
                    raise Exception(error_msg)
                time.sleep(delay)
                delay *= 2

            except requests.exceptions.RequestException as e:
                error_msg = f"网络请求异常: {str(e)}"
                self._log(error_msg, "ERROR")
                if attempt == max_retries - 1:
                    raise Exception(error_msg)
                time.sleep(delay)
                delay *= 2

            except Exception as e:
                error_msg = f"未知错误: {str(e)}"
                self._log(error_msg, "ERROR")
                if attempt == max_retries - 1:
                    raise
                time.sleep(delay)
                delay *= 2

        error_msg = "超过最大重试次数"
        self._log(error_msg, "ERROR")
        raise Exception(error_msg)

    def process_row(self, row: pd.Series) -> Dict[str, Any]:
        """处理单行数据"""
        # 提取输入数据(支持多种列名格式)
        project_name = str(row.get('项目名称', row.get('A', row.get(0, ''))))
        factory = str(row.get('工厂名称', row.get('B', row.get(1, ''))))
        goal = str(row.get('项目目标', row.get('C', row.get(2, ''))))
        benefit = str(row.get('收益描述', row.get('D', row.get(3, ''))))
        ok_desc = str(row.get('OK图片描述', row.get('E', row.get(4, ''))))
        ng_desc = str(row.get('NG图片描述', row.get('F', row.get(5, ''))))

        self._log(f"开始处理行数据: {project_name}", "INFO")
        self._log(f"  工厂: {factory}", "DEBUG")
        self._log(f"  目标: {goal[:50]}{'...' if len(goal) > 50 else ''}", "DEBUG")

        try:
            # 调用API
            self._log("准备调用API...", "DEBUG")
            ai_result = self.call_api(
                project_name, factory, goal, benefit, ok_desc, ng_desc
            )

            # 合并输入和输出
            result = {
                'A-项目名称': project_name,
                'B-工厂名称': factory,
                'C-项目目标': goal,
                'D-收益描述': benefit,
                'E-OK图片描述': ok_desc,
                'F-NG图片描述': ng_desc,
                'G-应用场景简述': ai_result.get('applicationScenario', ''),
                'H-处理对象(输入)': ai_result.get('processingObject', ''),
                'I-核心功能': '; '.join(ai_result.get('coreFunctions', [])),
                'J-输出形式/接口': ai_result.get('outputFormat', ''),
                'K-部署方式': ai_result.get('deploymentMethod', '')
            }

            self._log(f"成功处理: {project_name}", "INFO")
            self._log(f"  应用场景: {result['G-应用场景简述'][:50]}{'...' if len(result['G-应用场景简述']) > 50 else ''}", "DEBUG")
            self._log(f"  核心功能: {result['I-核心功能']}", "DEBUG")

            return result

        except Exception as e:
            error_msg = f"处理失败: {str(e)}"
            self._log(f"处理行数据失败: {project_name} - {error_msg}", "ERROR")

            return {
                'A-项目名称': project_name,
                'B-工厂名称': factory,
                'C-项目目标': goal,
                'D-收益描述': benefit,
                'E-OK图片描述': ok_desc,
                'F-NG图片描述': ng_desc,
                'G-应用场景简述': f'错误: {str(e)}',
                'H-处理对象(输入)': '',
                'I-核心功能': '',
                'J-输出形式/接口': '',
                'K-部署方式': ''
            }


class AICapabilityGUI:
    """GUI界面类"""

    def __init__(self, root):
        self.root = root
        self.root.title("AI能力画像文档整理助手")
        self.root.geometry("900x700")

        # 设置样式
        self.style = ttk.Style()
        self.style.theme_use('clam')

        # 默认配置
        self.api_base = tk.StringVar(value="http://ds.scc.com.cn/v1")
        self.api_key = tk.StringVar(value="0")
        self.model = tk.StringVar(value="deepseek-r1")
        self.input_file = tk.StringVar()
        self.output_file = tk.StringVar()

        self.processor = None
        self.is_processing = False

        self.create_widgets()

    def create_widgets(self):
        """创建GUI组件"""
        # 主容器
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 标题
        title_label = ttk.Label(main_frame, text="AI能力画像文档整理助手",
                               font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 10))

        subtitle_label = ttk.Label(main_frame,
                                   text="使用DeepSeek R1 API自动生成标准化的能力画像字段",
                                   font=('Arial', 10))
        subtitle_label.grid(row=1, column=0, columnspan=3, pady=(0, 20))

        # API配置区域
        config_frame = ttk.LabelFrame(main_frame, text="API配置", padding="10")
        config_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Label(config_frame, text="API地址:").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(config_frame, textvariable=self.api_base, width=50).grid(
            row=0, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))

        ttk.Label(config_frame, text="API密钥:").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(config_frame, textvariable=self.api_key, width=50).grid(
            row=1, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))

        ttk.Label(config_frame, text="模型名称:").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Entry(config_frame, textvariable=self.model, width=50).grid(
            row=2, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))

        # 文件选择区域
        file_frame = ttk.LabelFrame(main_frame, text="文件选择", padding="10")
        file_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Label(file_frame, text="输入文件:").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(file_frame, textvariable=self.input_file, width=50).grid(
            row=0, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 5))
        ttk.Button(file_frame, text="选择", command=self.select_input_file).grid(
            row=0, column=2, pady=5)

        ttk.Label(file_frame, text="输出文件:").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(file_frame, textvariable=self.output_file, width=50).grid(
            row=1, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 5))
        ttk.Button(file_frame, text="选择", command=self.select_output_file).grid(
            row=1, column=2, pady=5)

        # 控制按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=3, pady=(0, 10))

        self.process_button = ttk.Button(button_frame, text="开始处理",
                                        command=self.start_processing,
                                        style='Accent.TButton')
        self.process_button.grid(row=0, column=0, padx=5)

        self.stop_button = ttk.Button(button_frame, text="停止",
                                      command=self.stop_processing,
                                      state=tk.DISABLED)
        self.stop_button.grid(row=0, column=1, padx=5)

        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var,
                                           mode='determinate', length=400)
        self.progress_bar.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))

        # 状态标签
        self.status_label = ttk.Label(main_frame, text="就绪", foreground='green')
        self.status_label.grid(row=6, column=0, columnspan=3, pady=(0, 10))

        # 日志区域
        log_frame = ttk.LabelFrame(main_frame, text="处理日志", padding="10")
        log_frame.grid(row=7, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))

        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(7, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        config_frame.columnconfigure(1, weight=1)
        file_frame.columnconfigure(1, weight=1)

    def select_input_file(self):
        """选择输入文件"""
        filename = filedialog.askopenfilename(
            title="选择输入Excel文件",
            filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")]
        )
        if filename:
            self.input_file.set(filename)
            # 自动生成输出文件名
            if not self.output_file.get():
                input_path = Path(filename)
                output_path = input_path.parent / f"{input_path.stem}_处理结果{input_path.suffix}"
                self.output_file.set(str(output_path))

    def select_output_file(self):
        """选择输出文件"""
        filename = filedialog.asksaveasfilename(
            title="选择输出Excel文件",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")]
        )
        if filename:
            self.output_file.set(filename)

    def log(self, message):
        """添加日志"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def update_status(self, message, color='black'):
        """更新状态"""
        self.status_label.config(text=message, foreground=color)
        self.root.update_idletasks()

    def start_processing(self):
        """开始处理"""
        if self.is_processing:
            return

        # 验证输入
        if not self.input_file.get():
            messagebox.showerror("错误", "请选择输入文件")
            return

        if not self.output_file.get():
            messagebox.showerror("错误", "请指定输出文件")
            return

        # 清空日志
        self.log_text.delete(1.0, tk.END)

        # 创建处理器,传入日志回调
        self.processor = AICapabilityProcessor(
            api_base=self.api_base.get(),
            api_key=self.api_key.get(),
            model=self.model.get(),
            log_callback=self.log
        )

        # 启动处理线程
        self.is_processing = True
        self.process_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)

        thread = threading.Thread(target=self.process_file)
        thread.daemon = True
        thread.start()

    def stop_processing(self):
        """停止处理"""
        self.is_processing = False
        self.update_status("已停止", 'red')

    def process_file(self):
        """处理文件(在后台线程中运行)"""
        try:
            self.log("=" * 60)
            self.log("开始处理...")
            self.log(f"输入文件: {self.input_file.get()}")
            self.log(f"输出文件: {self.output_file.get()}")
            self.log(f"API配置: {self.api_base.get()}")
            self.log(f"模型: {self.model.get()}")
            self.log("=" * 60)

            # 读取Excel文件
            self.update_status("正在读取文件...", 'blue')
            self.log("\n[INFO] 开始读取Excel文件...")
            start_time = time.time()

            df = pd.read_excel(self.input_file.get())

            elapsed_time = time.time() - start_time
            total_rows = len(df)
            self.log(f"[INFO] 读取成功! 耗时: {elapsed_time:.2f}秒")
            self.log(f"[INFO] 共读取 {total_rows} 行数据")
            self.log(f"[INFO] 列名: {', '.join(df.columns.tolist())}\n")

            # 处理每一行
            results = []
            success_count = 0
            failed_count = 0

            for idx, row in df.iterrows():
                if not self.is_processing:
                    self.log("\n[WARNING] 处理已被用户取消")
                    break

                # 更新进度
                progress = (idx / total_rows) * 100
                self.progress_var.set(progress)

                project_name = str(row.get('项目名称', row.get('A', row.get(0, ''))))
                self.update_status(f"正在处理: {project_name} ({idx + 1}/{total_rows})", 'blue')
                self.log(f"\n{'=' * 50}")
                self.log(f"[{idx + 1}/{total_rows}] 开始处理项目: {project_name}")

                try:
                    row_start_time = time.time()
                    result = self.processor.process_row(row)
                    row_elapsed_time = time.time() - row_start_time

                    # 检查是否成功
                    if not result['G-应用场景简述'].startswith('错误:'):
                        results.append(result)
                        success_count += 1
                        self.log(f"[INFO] ✓ 处理成功! 耗时: {row_elapsed_time:.2f}秒")
                    else:
                        results.append(result)
                        failed_count += 1
                        self.log(f"[ERROR] ✗ 处理失败: {result['G-应用场景简述']}")

                except Exception as e:
                    self.log(f"[ERROR] ✗ 处理异常: {str(e)}")
                    failed_count += 1
                    # 添加错误记录
                    result = self.processor.process_row(row)
                    results.append(result)

            # 保存结果
            if results and self.is_processing:
                self.update_status("正在保存结果...", 'blue')
                self.log(f"\n{'=' * 60}")
                self.log(f"[INFO] 开始保存结果到: {self.output_file.get()}")

                save_start_time = time.time()
                result_df = pd.DataFrame(results)
                result_df.to_excel(self.output_file.get(), index=False)
                save_elapsed_time = time.time() - save_start_time

                self.log(f"[INFO] 保存完成! 耗时: {save_elapsed_time:.2f}秒")

                self.progress_var.set(100)
                self.update_status("处理完成!", 'green')

                # 统计信息
                self.log("\n" + "=" * 60)
                self.log(f"处理完成统计:")
                self.log(f"  总计: {len(results)} 条记录")
                self.log(f"  成功: {success_count} 条")
                self.log(f"  失败: {failed_count} 条")
                self.log(f"  成功率: {(success_count/len(results)*100):.1f}%")
                self.log("=" * 60)

                messagebox.showinfo("成功",
                    f"处理完成!\n总计: {len(results)} 条\n成功: {success_count} 条\n失败: {failed_count} 条")

        except Exception as e:
            self.log(f"\n[ERROR] ✗ 致命错误: {str(e)}")
            import traceback
            self.log(f"[ERROR] 详细错误信息:\n{traceback.format_exc()}")
            self.update_status(f"错误: {str(e)}", 'red')
            messagebox.showerror("错误", f"处理失败:\n{str(e)}")

        finally:
            self.is_processing = False
            self.process_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)


def main():
    """主函数"""
    root = tk.Tk()
    app = AICapabilityGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
