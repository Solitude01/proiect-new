#!/bin/bash

# AI能力画像系统 - 服务器部署脚本
# 目标服务器: 10.30.43.199

set -e

echo "========================================="
echo "AI能力画像系统 - 服务器部署脚本"
echo "========================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查是否在正确的目录
if [ ! -f "docker-compose.yml" ]; then
    echo -e "${RED}错误: 请在项目根目录运行此脚本${NC}"
    exit 1
fi

# 1. 检查Docker和Docker Compose
echo -e "${YELLOW}步骤1: 检查Docker环境...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker未安装，请先安装Docker${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}Docker Compose未安装，请先安装${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Docker环境检查通过${NC}"

# 2. 配置环境变量
echo -e "${YELLOW}步骤2: 配置环境变量...${NC}"
if [ ! -f ".env" ]; then
    echo "创建.env配置文件..."
    cp .env.example .env
    echo -e "${YELLOW}请编辑.env文件配置数据库连接和API密钥${NC}"
    echo "按回车键继续..."
    read
fi

# 3. 创建必要目录
echo -e "${YELLOW}步骤3: 创建必要目录...${NC}"
mkdir -p uploads outputs logs static

# 4. 拉取最新代码（如果是git仓库）
if [ -d ".git" ]; then
    echo -e "${YELLOW}步骤4: 拉取最新代码...${NC}"
    git pull origin main
fi

# 5. 构建和启动服务
echo -e "${YELLOW}步骤5: 构建Docker镜像...${NC}"
docker-compose build

echo -e "${YELLOW}步骤6: 启动服务...${NC}"
docker-compose up -d

# 6. 检查服务状态
echo -e "${YELLOW}步骤7: 检查服务状态...${NC}"
docker-compose ps

# 7. 查看日志
echo -e "${YELLOW}步骤8: 查看应用日志（按Ctrl+C退出）...${NC}"
docker-compose logs -f web &
sleep 5

# 8. 健康检查
echo -e "${YELLOW}步骤9: 执行健康检查...${NC}"
sleep 3
if curl -f http://localhost:8000/health &> /dev/null; then
    echo -e "${GREEN}✓ 应用启动成功${NC}"
else
    echo -e "${RED}✗ 应用健康检查失败${NC}"
fi

echo ""
echo "========================================="
echo -e "${GREEN}部署完成！${NC}"
echo "========================================="
echo ""
echo "访问地址:"
echo "  - Web应用: http://10.30.43.199"
echo "  - API文档: http://10.30.43.199:8000/docs"
echo "  - 健康检查: http://10.30.43.199:8000/health"
echo ""
echo "管理命令:"
echo "  - 查看日志: docker-compose logs -f"
echo "  - 重启服务: docker-compose restart"
echo "  - 停止服务: docker-compose down"
echo "  - 进入容器: docker exec -it ai_capability_web sh"
echo ""
