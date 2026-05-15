#!/bin/bash

# ESXI监控系统启动脚本（CentOS 8优化版）
# 用于简化在CentOS 8系统上的部署流程

echo "==========================================="
echo "ESXI监控系统启动脚本 (CentOS 8优化版)"
echo "==========================================="

# 检查Docker是否安装
if ! command -v docker &> /dev/null; then
    echo "错误: Docker未安装，请先安装Docker。"
    echo "可以使用以下命令安装Docker:"
    echo "sudo dnf install -y docker-ce docker-ce-cli containerd.io"
    exit 1
fi

# 检查Docker Compose是否安装
if ! command -v docker-compose &> /dev/null; then
    echo "警告: docker-compose未安装，尝试安装..."
    sudo dnf install -y python3-pip
    sudo pip3 install docker-compose
    if [ $? -ne 0 ]; then
        echo "错误: 无法安装docker-compose，请手动安装。"
        exit 1
    fi
fi

# 检查Docker服务是否运行
if ! systemctl is-active --quiet docker; then
    echo "警告: Docker服务未运行，尝试启动..."
    sudo systemctl start docker
    sudo systemctl enable docker
    if [ $? -ne 0 ]; then
        echo "错误: 无法启动Docker服务，请手动启动。"
        exit 1
    fi
fi

# 检查是否在正确的目录中
if [ ! -f "docker-compose.yml" ]; then
    echo "错误: 找不到docker-compose.yml文件，请确保在正确的目录中。"
    exit 1
fi

# 创建.env文件（如果不存在）
if [ ! -f ".env" ]; then
    echo "提示: 未找到.env文件，从.env.example复制..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "提示: 请根据需要编辑.env文件配置ESXI主机信息。"
    else
        echo "错误: 找不到.env.example文件。"
        exit 1
    fi
fi

# 创建静态文件和日志目录
echo "创建必要的目录..."
mkdir -p static logs
chmod 777 logs  # 确保容器可以写入日志

# 构建并启动服务
echo "==========================================="
echo "开始构建并启动服务..."
echo "==========================================="
docker-compose up -d --build

if [ $? -eq 0 ]; then
    echo "==========================================="
    echo "服务启动成功！"
    echo "==========================================="
    echo "服务信息:"
    echo "- 主页面: http://服务器IP:8000"
    echo "- API文档: http://服务器IP:8000/docs"
    echo "- 健康检查: http://服务器IP:8000/health"
    echo ""
    echo "查看服务状态: docker-compose ps"
    echo "查看应用日志: docker-compose logs -f app"
    echo "==========================================="
else
    echo "==========================================="
    echo "服务启动失败！"
    echo "请检查日志了解详情: docker-compose logs"
    echo "==========================================="
    exit 1
fi