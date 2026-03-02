# 基于官方镜像
FROM n8nio/n8n:latest

# 切换到 root 用户以安装软件
USER root

# 1. 替换 Alpine 软件源为阿里云（加速下载 apk）
# 2. 安装 Python3 和 pip
# 3. 安装 python-pptx (使用清华源，允许破坏系统包限制)
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.aliyun.com/g' /etc/apk/repositories && \
    apk add --update --no-cache python3 py3-pip && \
    pip3 install python-pptx --break-system-packages -i https://pypi.tuna.tsinghua.edu.cn/simple

# 切回 node 用户 (n8n 强制要求非 root 运行)
USER node