README.md 文档

以下是为你项目准备的工程化 README 文档。

```markdown
# OpenClaw 离线环境容器化部署方案

## 1. 架构概述
本项目旨在无公网接入的飞牛 NAS (`10.30.43.199`) 上部署 OpenClaw AI 智能体应用。
依赖 `10.30.44.154:1111` 提供的正向代理进行镜像拉取，并接入部署于企业内部 K8s 集群（由 Istio 提供网关路由）的 `ds-v3` 模型。

## 2. 环境信息
* **宿主机**: 飞牛 NAS (10.30.43.199)
* **部署路径**: `/vol1/1000/docker/openclaw`
* **访问控制**: 允许 `10.30.44.154` 等局域网设备通过网页访问。
* **模型接口**: `http://ds.scc.com.cn/v1/chat/completions` (API Key: `0`)

## 3. 部署前置条件
由于宿主机无外网，**必须先配置 Docker Daemon 代理**，否则 `docker pull` 会直接超时。

### 3.1 配置系统与 Docker 代理
通过 SSH 登录 `admin@10.30.43.199` 后，执行以下命令使 Docker 支持代理：

```bash
# 1. 声明 Shell 临时代理
export HTTP_PROXY="[http://10.30.44.154:1111](http://10.30.44.154:1111)"
export HTTPS_PROXY="[http://10.30.44.154:1111](http://10.30.44.154:1111)"

# 2. 为 Docker 创建 systemd 代理目录
sudo mkdir -p /etc/systemd/system/docker.service.d

# 3. 写入代理配置
sudo tee /etc/systemd/system/docker.service.d/http-proxy.conf > /dev/null <<EOF
[Service]
Environment="HTTP_PROXY=[http://10.30.44.154:1111](http://10.30.44.154:1111)"
Environment="HTTPS_PROXY=[http://10.30.44.154:1111](http://10.30.44.154:1111)"
Environment="NO_PROXY=localhost,127.0.0.1,10.30.0.0/16,ds.scc.com.cn"
EOF

# 4. 重载并重启 Docker
sudo systemctl daemon-reload
sudo systemctl restart docker

```

## 4. 目录结构与 Compose 配置

在目标目录创建文件体系：

```bash
sudo mkdir -p /vol1/1000/docker/openclaw
cd /vol1/1000/docker/openclaw

```

在目录下创建 `docker-compose.yml`，**关键**：通过环境变量将企业内部大模型注入。

```yaml
version: '3.8'

services:
  openclaw:
    image: openclaw/openclaw:latest  # 视实际 OpenClaw 镜像名而定
    container_name: openclaw_agent
    ports:
      - "3000:3000"  # 假设 OpenClaw 网页端口为 3000，映射到宿主机，使外网可访问
    volumes:
      - ./data:/app/data  # 挂载工作区和记忆数据
    environment:
      # 模型基础配置
      - OPENAI_API_BASE=[http://ds.scc.com.cn/v1/chat/completions](http://ds.scc.com.cn/v1/chat/completions)
      - OPENAI_API_KEY=0
      - DEFAULT_MODEL=ds-v3
      # 若应用内部需要访问网络抓取信息，同时将代理传给容器内部
      - HTTP_PROXY=[http://10.30.44.154:1111](http://10.30.44.154:1111)
      - HTTPS_PROXY=[http://10.30.44.154:1111](http://10.30.44.154:1111)
      - NO_PROXY=localhost,127.0.0.1,10.30.0.0/16,ds.scc.com.cn
    restart: unless-stopped
    network_mode: "bridge"

```

## 5. 启动与验证

```bash
# 启动服务
docker compose up -d

# 查看日志确保模型对接无误
docker compose logs -f

```

## 6. 使用说明

部署完成后，在 `10.30.44.154` 的浏览器中访问 `http://10.30.43.199:3000` 即可进入 OpenClaw 的控制面板界面。

```

```