#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# OpenClaw 离线环境容器化部署脚本
# 目标: 通过 SSH 远程登录飞牛 NAS，完成 OpenClaw AI 智能体的容器化部署
###############################################################################

# ─── Step 1: 环境变量与连接参数 ──────────────────────────────────────────────
SSH_TARGET="admin@10.30.43.199"
SSH_OPTS="-o ConnectTimeout=10 -o StrictHostKeyChecking=no"
DEPLOY_DIR="/vol1/1000/docker/openclaw"
PROXY_HOST="10.30.44.154"
PROXY_PORT="1111"
PROXY_URL="http://${PROXY_HOST}:${PROXY_PORT}"
MODEL_API="http://ds.scc.com.cn/v1/chat/completions"
WEB_PORT="18789"
BRIDGE_PORT="18790"
SUDO_PASS="Nas6688"
OPENCLAW_IMAGE="alpine/openclaw:latest"

# ─── 彩色输出 ────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()    { echo -e "${RED}[FAIL]${NC}  $*"; }

# 在远程执行命令的辅助函数
remote() {
    ssh ${SSH_OPTS} "${SSH_TARGET}" "$@"
}

remote_sudo() {
    ssh ${SSH_OPTS} "${SSH_TARGET}" "echo '${SUDO_PASS}' | sudo -S bash -c '$*' 2>/dev/null"
}

# ─── 网络超时自动诊断函数 ────────────────────────────────────────────────────
diagnose_network() {
    echo ""
    warn "========== 网络诊断开始 =========="

    # 检测代理服务是否可达
    info "检测代理服务 ${PROXY_HOST}:${PROXY_PORT} ..."
    if remote "nc -zw3 ${PROXY_HOST} ${PROXY_PORT}" 2>/dev/null; then
        success "代理服务可达"
    else
        fail "代理服务不可达，请检查 ${PROXY_HOST}:${PROXY_PORT} 是否启动"
    fi

    # 检测 Docker daemon 代理配置
    info "检测 Docker 代理配置 ..."
    local proxy_info
    proxy_info=$(remote "docker info 2>/dev/null | grep -i proxy" || true)
    if [[ -n "${proxy_info}" ]]; then
        success "Docker 代理已配置:"
        echo "       ${proxy_info}"
    else
        fail "Docker 未配置代理，镜像拉取将超时"
    fi

    # 检测 DNS 解析
    info "检测 DNS 解析 ..."
    if remote "nslookup registry-1.docker.io" &>/dev/null; then
        success "DNS 解析正常"
    elif remote "ping -c1 -W3 registry-1.docker.io" &>/dev/null; then
        success "DNS 解析正常 (via ping)"
    else
        warn "DNS 解析失败，但通过代理仍可能正常工作"
    fi

    # 检测通过代理访问 Docker Registry
    info "检测通过代理访问 Docker Registry ..."
    local registry_test
    registry_test=$(remote "curl -s -o /dev/null -w '%{http_code}' --connect-timeout 10 -x ${PROXY_URL} https://registry-1.docker.io/v2/" 2>/dev/null || echo "000")
    if [[ "${registry_test}" == "401" || "${registry_test}" == "200" ]]; then
        success "通过代理可达 Docker Registry (HTTP ${registry_test})"
    else
        fail "通过代理无法访问 Docker Registry (HTTP ${registry_test})"
        echo "       建议: 检查代理 ${PROXY_URL} 是否允许 HTTPS 流量转发"
    fi

    warn "========== 网络诊断结束 =========="
    echo ""
}

###############################################################################
# Step 2: SSH 连通性检测
###############################################################################
echo ""
info "━━━ Step 1/5: SSH 连通性检测 ━━━"

if ssh ${SSH_OPTS} "${SSH_TARGET}" "echo ok" &>/dev/null; then
    success "SSH 连接成功: ${SSH_TARGET}"
else
    fail "SSH 连接失败: ${SSH_TARGET}"
    echo ""
    echo "  可能原因:"
    echo "    1) 网络不可达 — 请确认本机与 10.30.43.199 在同一网段或有路由"
    echo "    2) SSH 服务未启动 — 请在 NAS 管理面板开启 SSH"
    echo "    3) 用户名/密码错误 — 请确认 admin 账户可用"
    echo "    4) 防火墙阻断 — 请检查 22 端口是否开放"
    exit 1
fi

###############################################################################
# Step 3: 远程配置 Docker 代理
###############################################################################
info "━━━ Step 2/5: 配置 Docker 代理 ━━━"

remote_sudo "mkdir -p /etc/systemd/system/docker.service.d"

# 写入代理配置文件
remote_sudo "cat > /etc/systemd/system/docker.service.d/http-proxy.conf << 'PROXYEOF'
[Service]
Environment=\"HTTP_PROXY=${PROXY_URL}\"
Environment=\"HTTPS_PROXY=${PROXY_URL}\"
Environment=\"NO_PROXY=localhost,127.0.0.1,10.30.0.0/16,ds.scc.com.cn\"
PROXYEOF"

success "代理配置文件已写入"

# 重载并重启 Docker
info "重载 systemd 并重启 Docker ..."
remote_sudo "systemctl daemon-reload && systemctl restart docker"

# 等待 Docker 启动
sleep 3

if remote "docker info" &>/dev/null; then
    success "Docker 服务运行正常"
else
    fail "Docker 服务启动失败"
    warn "请手动检查: ssh ${SSH_TARGET} 'sudo systemctl status docker'"
    exit 1
fi

###############################################################################
# Step 4: 创建部署目录与 docker-compose.yml
###############################################################################
info "━━━ Step 3/5: 创建部署目录与配置文件 ━━━"

remote_sudo "mkdir -p ${DEPLOY_DIR}/config ${DEPLOY_DIR}/workspace"
success "部署目录已创建: ${DEPLOY_DIR}"

# 生成 Gateway Token
GATEWAY_TOKEN=$(remote "cat ${DEPLOY_DIR}/.env 2>/dev/null | grep OPENCLAW_GATEWAY_TOKEN | cut -d= -f2" || true)
if [[ -z "${GATEWAY_TOKEN}" ]]; then
    GATEWAY_TOKEN=$(openssl rand -hex 32)
    info "生成新的 Gateway Token"
fi

# 写入 .env
remote "cat > ${DEPLOY_DIR}/.env << ENVEOF
OPENCLAW_GATEWAY_TOKEN=${GATEWAY_TOKEN}
OPENCLAW_GATEWAY_PORT=${WEB_PORT}
OPENCLAW_BRIDGE_PORT=${BRIDGE_PORT}
ENVEOF"

success ".env 已写入 (Token: ${GATEWAY_TOKEN:0:8}...)"

# 写入 openclaw.json 配置（绑定 LAN + 允许内网访问）
remote "cat > ${DEPLOY_DIR}/config/openclaw.json << 'CONFIGEOF'
{
  \"gateway\": {
    \"bind\": \"lan\",
    \"controlUi\": {
      \"allowedOrigins\": [\"http://10.30.43.199:18789\", \"http://10.30.44.154:18789\"],
      \"allowInsecureAuth\": true
    }
  }
}
CONFIGEOF"

success "openclaw.json 已写入 (bind=lan)"

# 写入 docker-compose.yml
remote "cat > ${DEPLOY_DIR}/docker-compose.yml << 'COMPOSEEOF'
services:
  openclaw-gateway:
    image: alpine/openclaw:latest
    container_name: openclaw_gateway
    init: true
    ports:
      - \"18789:18789\"
      - \"18790:18790\"
    volumes:
      - ./config:/home/node/.openclaw
      - ./workspace:/home/node/.openclaw/workspace
    environment:
      HOME: /home/node
      TERM: xterm-256color
      OPENCLAW_GATEWAY_TOKEN: \${OPENCLAW_GATEWAY_TOKEN}
      OPENCLAW_GATEWAY_BIND: lan
      OPENAI_API_BASE: http://ds.scc.com.cn/v1
      OPENAI_API_KEY: \"0\"
      DEFAULT_MODEL: ds-v3
      HTTP_PROXY: http://10.30.44.154:1111
      HTTPS_PROXY: http://10.30.44.154:1111
      NO_PROXY: localhost,127.0.0.1,10.30.0.0/16,ds.scc.com.cn
    restart: unless-stopped
COMPOSEEOF"

success "docker-compose.yml 已写入"

###############################################################################
# Step 5: 拉取镜像并启动
###############################################################################
info "━━━ Step 4/5: 拉取镜像并启动容器 ━━━"

info "拉取镜像 ${OPENCLAW_IMAGE} (通过代理)，请耐心等待 ..."

if remote "cd ${DEPLOY_DIR} && timeout 300 docker compose pull" 2>&1; then
    success "镜像拉取完成"
else
    fail "镜像拉取失败或超时"
    diagnose_network
    echo "  建议操作:"
    echo "    1) 确认代理服务正常: curl -x ${PROXY_URL} https://registry-1.docker.io/v2/"
    echo "    2) 手动重试: ssh ${SSH_TARGET} 'cd ${DEPLOY_DIR} && docker compose pull'"
    exit 1
fi

# 启动容器
info "启动容器 ..."
if remote "cd ${DEPLOY_DIR} && docker compose up -d" 2>&1; then
    success "容器已启动"
else
    fail "容器启动失败"
    warn "查看日志: ssh ${SSH_TARGET} 'cd ${DEPLOY_DIR} && docker compose logs'"
    exit 1
fi

###############################################################################
# Step 6: 验证部署
###############################################################################
info "━━━ Step 5/5: 验证部署 ━━━"

# 等待容器完全启动
sleep 5

# 检查容器运行状态
info "检查容器运行状态 ..."
CONTAINER_STATUS=$(remote "docker inspect -f '{{.State.Status}}' openclaw_gateway 2>/dev/null" || echo "not_found")

if [[ "${CONTAINER_STATUS}" == "running" ]]; then
    success "容器 openclaw_gateway 运行中"
else
    fail "容器状态异常: ${CONTAINER_STATUS}"
    warn "查看日志: ssh ${SSH_TARGET} 'docker logs openclaw_gateway'"
fi

# 测试模型 API 连通性
info "测试模型 API 连通性 ..."
API_STATUS=$(remote "curl -s -o /dev/null -w '%{http_code}' --connect-timeout 10 ${MODEL_API}" 2>/dev/null || echo "000")

if [[ "${API_STATUS}" != "000" ]]; then
    success "模型 API 可达 (HTTP ${API_STATUS})"
else
    warn "模型 API 不可达 — 容器内部可能仍可通过 DNS 访问，请稍后在 Web UI 中测试"
fi

# 输出部署结果
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  OpenClaw 部署完成!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  访问地址:  ${CYAN}http://10.30.43.199:${WEB_PORT}/?token=${GATEWAY_TOKEN}${NC}"
echo -e "  模型接口:  ${CYAN}${MODEL_API}${NC}"
echo -e "  部署路径:  ${CYAN}${DEPLOY_DIR}${NC}"
echo -e "  Token:     ${CYAN}${GATEWAY_TOKEN}${NC}"
echo ""
echo -e "  常用命令:"
echo -e "    查看日志:  ssh ${SSH_TARGET} 'cd ${DEPLOY_DIR} && docker compose logs -f'"
echo -e "    重启服务:  ssh ${SSH_TARGET} 'cd ${DEPLOY_DIR} && docker compose restart'"
echo -e "    停止服务:  ssh ${SSH_TARGET} 'cd ${DEPLOY_DIR} && docker compose down'"
echo ""
