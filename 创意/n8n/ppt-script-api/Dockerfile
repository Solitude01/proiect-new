# 使用官方的 Python 基础镜像
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 1. 临时设置代理 (仅供 pip 使用)
ENV HTTP_PROXY="http://10.30.44.154:7897"
ENV HTTPS_PROXY="http://10.30.44.154:7897"

# 2. 安装依赖
RUN pip install --no-cache-dir \
    fastapi uvicorn "pydantic[email]" \
    "python-multipart" 

# 3. 🎯【核心修复】构建完成后，必须清除代理变量！
# 否则容器运行时，任何网络请求都会尝试走这个代理，导致连不通局域网
ENV HTTP_PROXY=""
ENV HTTPS_PROXY=""

# 复制 app 目录下的所有文件
COPY app/ .

# 暴露端口
EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]