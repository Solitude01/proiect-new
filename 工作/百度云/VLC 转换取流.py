#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Excel转M3U播放列表工具
将Excel文件中的摄像头名称和RTSP地址转换为M3U格式的播放列表
"""

import pandas as pd
import os
from pathlib import Path

def excel_to_m3u(excel_path, output_path):
    """
    将Excel文件转换为M3U播放列表
    
    Args:
        excel_path (str): Excel文件路径
        output_path (str): 输出M3U文件路径
    """
    try:
        # 读取Excel文件
        print(f"正在读取Excel文件: {excel_path}")
        df = pd.read_excel(excel_path)
        
        # 检查列数
        if len(df.columns) < 2:
            raise ValueError("Excel文件至少需要2列数据（A列：摄像头名称，B列：RTSP地址）")
        
        # 获取A列（摄像头名称）和B列（RTSP地址）
        camera_names = df.iloc[:, 0]  # 第一列
        rtsp_urls = df.iloc[:, 1]     # 第二列
        
        # 生成M3U内容
        m3u_content = ["#EXTM3U"]
        
        for name, url in zip(camera_names, rtsp_urls):
            # 跳过空行
            if pd.isna(name) or pd.isna(url):
                continue
                
            # 添加摄像头信息
            m3u_content.append(f"#EXTINF:-1,{name}")
            m3u_content.append(str(url))
        
        # 写入文件（UTF-8编码）
        print(f"正在生成M3U文件: {output_path}")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(m3u_content))
        
        print(f"转换完成！共处理 {len(m3u_content)//2} 个摄像头")
        print(f"输出文件: {output_path}")
        
    except FileNotFoundError:
        print(f"错误：找不到Excel文件 {excel_path}")
    except Exception as e:
        print(f"转换过程中出现错误: {str(e)}")

def main():
    """主函数"""
    # 文件路径
    excel_file = r"C:\Users\Administrator\Desktop\待转换.xlsx"
    output_file = r"C:\Users\Administrator\Desktop\播放列表.m3u"
    
    # 检查输入文件是否存在
    if not os.path.exists(excel_file):
        print(f"错误：Excel文件不存在: {excel_file}")
        return
    
    # 检查输出目录是否存在
    output_dir = os.path.dirname(output_file)
    if not os.path.exists(output_dir):
        print(f"错误：输出目录不存在: {output_dir}")
        return
    
    # 执行转换
    excel_to_m3u(excel_file, output_file)

if __name__ == "__main__":
    main()
