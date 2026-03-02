import subprocess
import os

# OFD 文件路径
ofd_path = r"C:\Users\Lane\Documents\WXWork\1688855574607410\Cache\File\2025-12\高德打车电子发票-8.62.ofd"

# 输出 PDF 路径
pdf_path = ofd_path.replace(".ofd", ".pdf")

# 本地 OFD 转换工具路径（示例：数科 OFD 工具）
ofd_tool = r"C:\Program Files\OFDReader\ofd2pdf.exe"

# 检查文件是否存在
if not os.path.exists(ofd_path):
    raise FileNotFoundError("OFD 文件不存在")

# 调用外部命令转换
subprocess.run([
    ofd_tool,
    ofd_path,
    pdf_path
], check=True)

print("转换完成：", pdf_path)
