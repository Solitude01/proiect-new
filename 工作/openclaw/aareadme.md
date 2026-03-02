# OpenClaw 飞牛 NAS 部署总结

## 部署概览

在无公网的飞牛 NAS (10.30.43.199) 上成功部署 OpenClaw AI 智能体，对接企业内部 K8s 集群的 ds-v3 大模型。

| 项目 | 值 |
|------|-----|
| NAS 地址 | 10.30.43.199 |
| SSH 用户 | admin (密码: Nas6688) |
| Web 访问地址 | http://10.30.43.199:3000 |
| Gateway Token | dc38ec2269ce8ef0dacd2c42bd7216d6029fb75bc6ae919e2dbc04f8ea5e3fd8 |
| 模型 API | http://ds.scc.com.cn/v1 |
| 模型名称 | ds-v3 |
| API Key | 0 |
| 代理地址 | http://10.30.44.154:1111 |
| 部署路径 | /vol1/1000/docker/openclaw |

## 架构

```
浏览器 (10.30.44.154)
    |
    | HTTP :3000
    v
Nginx 容器 (openclaw_nginx)
    |
    | 反向代理 (Host: 127.0.0.1:18789)
    v
OpenClaw Gateway 容器 (openclaw_gateway)
    |
    | HTTP (OpenAI-compatible API)
    v
ds-v3 模型 (ds.scc.com.cn/v1)
```

## 部署过程中解决的问题

### 1. SSH 配置文件语法错误
- `~/.ssh/config` 第 1 行有无效内容 `10.30.44.159`
- 修复为 `Host 10.30.44.159\n  User admin`

### 2. SSH 免密登录
- NAS 上没有公钥，本机也没有密钥对
- 生成 ed25519 密钥: `ssh-keygen -t ed25519`
- 通过 Python paramiko 库将公钥部署到 NAS

### 3. sudo 需要密码
- 非交互式 SSH 执行 sudo 命令需要 `-S` 参数从 stdin 读取密码
- `echo 'password' | sudo -S bash -c 'command'`

### 4. Docker 镜像名错误
- README 中写的 `openclaw/openclaw:latest` 不存在
- 正确镜像: `alpine/openclaw:latest` (社区预构建镜像，基于 ghcr.io/openclaw/openclaw)

### 5. Gateway 绑定地址
- 默认绑定 `127.0.0.1`，外部无法访问
- 需要在 `openclaw.json` 中设置 `gateway.bind: "lan"` (不是 `0.0.0.0`)
- 同时需要 `gateway.controlUi.allowedOrigins` 和 `gateway.controlUi.allowInsecureAuth: true`

### 6. HTTP 不安全上下文限制
- OpenClaw Control UI 在 HTTP 下无法生成设备标识 (需要 Web Crypto API 安全上下文)
- `allowInsecureAuth: true` 只允许本地客户端 (`isLocalClient`)
- 解决方案: Nginx 反向代理，Host 头伪装为 `127.0.0.1:18789`，配合 `trustedProxies`

### 7. 自定义模型注册
- ds-v3 不在 OpenClaw 内置模型目录中，直接使用会报 `Unknown model`
- 需要在 `openclaw.json` 的 `models.providers` 中注册自定义 provider 和模型定义
- auth-profiles.json 中的 provider 也需对应

## 部署文件清单

### /vol1/1000/docker/openclaw/docker-compose.yml

```yaml
services:
  openclaw-gateway:
    image: alpine/openclaw:latest
    container_name: openclaw_gateway
    init: true
    expose:
      - "18789"
      - "18790"
    volumes:
      - ./config:/home/node/.openclaw
      - ./workspace:/home/node/.openclaw/workspace
    environment:
      HOME: /home/node
      TERM: xterm-256color
      OPENCLAW_GATEWAY_TOKEN: ${OPENCLAW_GATEWAY_TOKEN}
      OPENAI_API_KEY: "0"
      OPENAI_API_BASE: http://ds.scc.com.cn/v1
      DEFAULT_MODEL: ds-v3
      HTTP_PROXY: http://10.30.44.154:1111
      HTTPS_PROXY: http://10.30.44.154:1111
      NO_PROXY: localhost,127.0.0.1,10.30.0.0/16,ds.scc.com.cn
    restart: unless-stopped

  nginx:
    image: nginx:latest
    container_name: openclaw_nginx
    ports:
      - "3000:3000"
    volumes:
      - ./nginx/default.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      - openclaw-gateway
    restart: unless-stopped
```

### /vol1/1000/docker/openclaw/.env

```
OPENCLAW_GATEWAY_TOKEN=dc38ec2269ce8ef0dacd2c42bd7216d6029fb75bc6ae919e2dbc04f8ea5e3fd8
OPENCLAW_GATEWAY_PORT=18789
OPENCLAW_BRIDGE_PORT=18790
```

### /vol1/1000/docker/openclaw/config/openclaw.json

```json
{
  "gateway": {
    "bind": "lan",
    "controlUi": {
      "allowedOrigins": [
        "http://10.30.43.199:3000",
        "http://10.30.43.199:18789",
        "http://10.30.44.154:3000",
        "http://127.0.0.1:18789"
      ],
      "allowInsecureAuth": true
    },
    "trustedProxies": ["172.16.0.0/12", "10.30.0.0/16"]
  },
  "agents": {
    "defaults": {
      "model": "ds-v3/ds-v3"
    }
  },
  "auth": {
    "profiles": {
      "default": {
        "provider": "ds-v3",
        "mode": "api_key"
      }
    }
  },
  "models": {
    "providers": {
      "ds-v3": {
        "baseUrl": "http://ds.scc.com.cn/v1",
        "apiKey": "0",
        "api": "openai-completions",
        "models": [
          {
            "id": "ds-v3",
            "name": "DeepSeek V3 (Internal)",
            "reasoning": false,
            "input": ["text"],
            "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 },
            "contextWindow": 65536,
            "maxTokens": 8192
          }
        ]
      }
    }
  }
}
```

### /vol1/1000/docker/openclaw/config/agents/main/agent/auth-profiles.json

```json
{
  "version": 1,
  "profiles": {
    "default": {
      "type": "api_key",
      "provider": "ds-v3",
      "key": "0"
    }
  }
}
```

### /vol1/1000/docker/openclaw/nginx/default.conf

```nginx
server {
    listen 3000;

    location / {
        proxy_pass http://openclaw-gateway:18789;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host 127.0.0.1:18789;
        proxy_set_header X-Real-IP 127.0.0.1;
        proxy_set_header X-Forwarded-For 127.0.0.1;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
}
```

## 常用运维命令

```bash
# SSH 登录 NAS
ssh admin@10.30.43.199

# 查看容器状态
ssh admin@10.30.43.199 'docker ps --filter name=openclaw'

# 查看实时日志
ssh admin@10.30.43.199 'cd /vol1/1000/docker/openclaw && docker compose logs -f'

# 重启服务
ssh admin@10.30.43.199 'cd /vol1/1000/docker/openclaw && docker compose restart'

# 停止服务
ssh admin@10.30.43.199 'cd /vol1/1000/docker/openclaw && docker compose down'

# 启动服务
ssh admin@10.30.43.199 'cd /vol1/1000/docker/openclaw && docker compose up -d'

# 更新镜像
ssh admin@10.30.43.199 'cd /vol1/1000/docker/openclaw && docker compose pull && docker compose up -d'

# 查看 Gateway 应用日志
ssh admin@10.30.43.199 'docker exec openclaw_gateway cat /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log'
```

## 访问方式

浏览器打开 (确保不走代理):

```
http://10.30.43.199:3000/?token=dc38ec2269ce8ef0dacd2c42bd7216d6029fb75bc6ae919e2dbc04f8ea5e3fd8
```

> 注意: 浏览器代理设置中需排除 `10.30.43.199`，否则内网请求会走代理导致连接失败。

## 目录结构

```
/vol1/1000/docker/openclaw/
├── docker-compose.yml
├── .env
├── config/
│   ├── openclaw.json
│   ├── canvas/
│   ├── cron/
│   └── agents/
│       └── main/
│           ├── agent/
│           │   └── auth-profiles.json
│           └── sessions/
├── workspace/
└── nginx/
    └── default.conf
```
