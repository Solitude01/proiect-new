import os
from urllib.parse import urlparse, urlunparse

# --- 配置 ---

# 1. 您的原始文件路径
# (Windows 路径中的 \ 建议使用 r"..." 或 \\)
input_file_path = r"D:\proiect\工作\vlc播放列表\G2待处理.md"

# 2. 处理后输出的新文件路径
# (我们将其保存在同一目录下，并命名为 .m3u 播放列表格式)
output_file_path = os.path.join(os.path.dirname(input_file_path), "G2_processed.m3u")

# --- 脚本开始 ---

processed_lines = []
line_count = 0
processed_count = 0

print(f"--- 开始处理: {input_file_path} ---")

try:
    with open(input_file_path, 'r', encoding='utf-8') as f_in:
        for line in f_in:
            line_count += 1
            line = line.strip()

            # 跳过空行
            if not line:
                continue

            # 查找 'rtsp://' 作为名称和 URL 的分割点
            split_index = line.find("rtsp://")

            if split_index == -1:
                print(f"警告: 第 {line_count} 行格式不符，已跳过: {line}")
                continue

            # 1. 提取名称和 URL
            # 名称是 'rtsp://' 之前的部分，并去除两端空格
            name = line[:split_index].strip()
            # URL 是 'rtsp://' 及之后的部分
            full_url = line[split_index:].strip()

            try:
                # 2. 解析并简化 URL
                #    (根据您的范例，我们去除端口和路径)
                
                parsed_url = urlparse(full_url)
                
                # 重建 netloc (网络位置)，只使用 username, password 和 hostname
                # 这样就自动丢弃了端口号
                new_netloc = parsed_url.hostname
                if parsed_url.username:
                    if parsed_url.password:
                        # 格式: username:password@hostname
                        new_netloc = f"{parsed_url.username}:{parsed_url.password}@{new_netloc}"
                    else:
                        # 格式: username@hostname
                        new_netloc = f"{parsed_url.username}@{new_netloc}"
                
                # 重建 URL，只保留 scheme(rtsp) 和 new_netloc
                # 格式: (scheme, netloc, path, params, query, fragment)
                new_url_parts = (parsed_url.scheme, new_netloc, '', '', '', '')
                final_url = urlunparse(new_url_parts)

                # 3. 按照 M3U 格式添加到结果列表
                processed_lines.append(f"#EXTINF:-1,{name}")
                processed_lines.append(final_url)
                processed_count += 1

            except Exception as e:
                print(f"错误: 第 {line_count} 行 URL 解析失败: {full_url} - {e}")
                continue

    # 4. 将处理好的内容写入新文件
    with open(output_file_path, 'w', encoding='utf-8') as f_out:
        # 写入M3U文件头
        f_out.write("#EXTM3U\n")
        # 使用 \n (换行符) 连接所有行
        f_out.write('\n'.join(processed_lines))

    print("\n--- 处理完成! 🚀 ---")
    print(f"总共读取: {line_count} 行")
    print(f"成功处理: {processed_count} 条记录")
    print(f"输出文件: {output_file_path}")

except FileNotFoundError:
    print(f"错误: 找不到输入文件! 路径: {input_file_path}")
except Exception as e:
    print(f"发生未知错误: {e}")