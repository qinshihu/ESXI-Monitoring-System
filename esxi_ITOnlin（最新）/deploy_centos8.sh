#!/bin/bash

# ESXI监控系统 - CentOS 8容器化部署脚本
# 此脚本用于在CentOS 8系统上安装Docker并部署ESXI监控系统

set -e

echo "================================================"
echo "ESXI监控系统 - CentOS 8容器化部署脚本"
echo "================================================"

# 检查操作系统
if [ ! -f /etc/centos-release ]; then
    echo "错误：此脚本仅适用于CentOS 8系统"
    exit 1
fi

OS_VERSION=$(cat /etc/centos-release | grep -o '\([0-9]\+\)\.' | head -1 | tr -d '.')
if [ "$OS_VERSION" != "8" ]; then
    echo "警告：此脚本针对CentOS 8优化，当前系统版本可能不完全兼容"
fi

# 安装必要的系统依赖
echo "安装系统依赖..."
dnf install -y yum-utils device-mapper-persistent-data lvm2 curl wget

# 安装Docker CE
echo "安装Docker CE..."
dnf config-manager --add-repo=https://download.docker.com/linux/centos/docker-ce.repo
dnf install -y docker-ce docker-ce-cli containerd.io

# 启动Docker服务
echo "启动Docker服务..."
systemctl start docker
systemctl enable docker

# 验证Docker安装
echo "验证Docker安装..."
docker --version

# 安装Docker Compose
echo "安装Docker Compose..."
curl -L "https://github.com/docker/compose/releases/download/v2.15.1/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
ln -s /usr/local/bin/docker-compose /usr/bin/docker-compose

# 验证Docker Compose安装
echo "验证Docker Compose安装..."
docker-compose --version

# 配置Docker镜像加速（可选，根据实际情况修改）
echo "配置Docker镜像加速..."
mkdir -p /etc/docker
cat > /etc/docker/daemon.json << EOF
{
  "registry-mirrors": ["https://registry.docker-cn.com", "https://mirror.baidubce.com"]
}
EOF

# 重启Docker服务
echo "重启Docker服务..."
systemctl daemon-reload
systemctl restart docker

# 确保脚本有执行权限
echo "设置脚本执行权限..."
chmod +x entrypoint.sh deploy_centos8.sh

# 创建数据目录
echo "创建数据目录..."
mkdir -p ./logs ./locks ./data
chmod -R 755 ./logs ./locks ./data

# 根据.env.example创建.env文件（如果不存在）
if [ ! -f .env ]; then
    echo "创建.env配置文件..."
    if [ -f .env.example ]; then
        cp .env.example .env
    else
        cat > .env << EOF
# 应用配置
API_PORT=8080
API_DEBUG=false
ENVIRONMENT=production

# 数据库配置
DATABASE_URL=mysql+pymysql://admin:password@db:3306/esxi_monitoring

# ESXI配置
ESXI_HOSTS=esxi-01:192.168.1.100:root:password

# 数据采集间隔（秒）
DATA_COLLECTION_INTERVAL=60

# 容器化环境
CONTAINERIZED=true
LOCK_DIR=/app/locks
DATA_DIR=/app/data
EOF
    fi
fi

echo "================================================"
echo "Docker和Docker Compose安装完成！"
echo "准备部署ESXI监控系统..."
echo "================================================"
echo ""
echo "执行以下命令启动服务："
echo "  docker-compose up -d"
echo ""
echo "查看服务状态："
echo "  docker-compose ps"
echo ""
echo "查看应用日志："
echo "  docker-compose logs -f app"
echo ""
echo "停止服务："
echo "  docker-compose down"
echo "================================================"