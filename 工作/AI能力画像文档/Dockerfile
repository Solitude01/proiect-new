# 多阶段构建 - AI能力画像文档系统

# 构建阶段
FROM python:3.9-slim as builder

WORKDIR /app

# 安装构建依赖
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir --user -r requirements.txt

# 运行阶段
FROM python:3.9-slim

WORKDIR /app

# 安装运行时依赖
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get purge -y --auto-remove

# 从构建阶段复制Python包
COPY --from=builder /root/.local /root/.local

# 确保Python可以找到用户安装的包
ENV PATH=/root/.local/bin:$PATH

# 复制应用代码
COPY app/ ./app/
COPY .env.example .env

# 创建必要的目录
RUN mkdir -p uploads outputs logs

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
