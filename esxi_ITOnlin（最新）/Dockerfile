# 使用多阶段构建减小镜像体积
# 第一阶段：构建环境
FROM centos:8 AS builder

# 安装Python 3.10
RUN dnf install -y epel-release && \
    dnf install -y python39 python39-devel gcc gcc-c++ make openssl-devel curl procps-ng && \
    alternatives --set python3 /usr/bin/python3.9 && \
    dnf clean all && \
    rm -rf /var/cache/dnf/*

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # 确保时区正确
    TZ=Asia/Shanghai \
    # 虚拟环境路径
    VIRTUAL_ENV=/opt/venv

# 安装CentOS 8系统依赖
RUN dnf install -y \
    gcc \
    python3-devel \
    gcc-c++ \
    make \
    openssl-devel \
    redhat-rpm-config \
    curl \
    procps-ng \
    && dnf clean all \
    && rm -rf /var/cache/dnf/*

# 确保使用正确的CentOS 8仓库源
RUN sed -i 's/mirrorlist/#mirrorlist/g' /etc/yum.repos.d/CentOS-* \
    && sed -i 's|#baseurl=http://mirror.centos.org|baseurl=http://vault.centos.org|g' /etc/yum.repos.d/CentOS-* \
    && dnf update -y && dnf clean all

# 添加EPEL仓库以获取更多软件包
RUN dnf install -y epel-release && dnf clean all

# 创建Python虚拟环境
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# 升级pip到最新版本
RUN pip install --upgrade pip setuptools wheel

# 复制requirements.txt文件并安装Python依赖
COPY requirements.txt .
# 先安装基础依赖，然后安装应用依赖，避免重复构建
RUN pip install --upgrade pip setuptools wheel \
    # 安装容器化环境优化所需的依赖
    && pip install gunicorn uvloop httptools \
    # 安装应用依赖
    && pip install -r requirements.txt \
    # 清理pip缓存
    && rm -rf /root/.cache/pip

# 复制应用程序代码
COPY . .

# 第二阶段：运行环境
FROM centos:8

# 安装运行时依赖
RUN dnf install -y python39 python39-pip curl procps-ng nmap-ncat && \
    alternatives --set python3 /usr/bin/python3.9 && \
    dnf clean all && \
    rm -rf /var/cache/dnf/*

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    VIRTUAL_ENV=/opt/venv \
    PATH="$VIRTUAL_ENV/bin:$PATH" \
    # 容器化环境标识
    CONTAINERIZED=true \
    # 优化运行时参数
    WORKERS=2 \
    LOG_LEVEL=warning \
    # 资源限制和性能优化
    UVICORN_BACKLOG=1000 \
    UVICORN_KEEPALIVE=60

# 从构建阶段复制虚拟环境和应用程序代码
COPY --from=builder $VIRTUAL_ENV $VIRTUAL_ENV
COPY --from=builder /app /app

# 安装运行时依赖，移除不必要的mysql包（应该使用pymysql）
RUN dnf install -y \
    curl \
    procps-ng \
    nmap-ncat \
    python39-libs \
    && dnf clean all \
    && rm -rf /var/cache/dnf/*

# 创建非root用户运行应用
RUN groupadd -r esxiuser && useradd -r -g esxiuser -m esxiuser

# 设置虚拟环境和应用目录权限
RUN chown -R esxiuser:esxiuser /app $VIRTUAL_ENV

# 创建必要的目录并设置权限
RUN mkdir -p /app/locks /app/logs /app/data \
    && chown -R esxiuser:esxiuser /app \
    && chmod -R 755 /app \
    # 确保日志目录可写
    && chmod 777 /app/logs

# 切换到非root用户
USER esxiuser

# 创建.env文件（如果不存在）
RUN if [ -f .env.example ]; then cp .env.example .env; else echo "ESXI_HOSTS=esxi1:192.168.1.10:root:password" > .env; fi

# 设置正确的时区
RUN ln -sf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 添加启动脚本
COPY --chmod=755 <<'EOF' /app/entrypoint.sh
#!/bin/bash
set -e

# 等待依赖服务就绪
wait_for_service() {
    local service=$1
    local host=$2
    local port=$3
    local retries=${4:-30}
    
    echo "等待${service}启动..."
    for i in $(seq 1 $retries); do
        if nc -z $host $port 2>/dev/null; then
            echo "${service}服务已就绪！"
            return 0
        fi
        echo "尝试连接${service} (${i}/${retries})..."
        sleep 1
    done
    echo "错误: 无法连接到${service}服务"
    return 1
}

# 如果启用了MySQL，等待MySQL服务就绪
if [[ "$DATABASE_URL" == *"mysql"* ]]; then
    DB_HOST=$(echo "$DATABASE_URL" | sed -n 's/.*@\([^:]*\):.*/\1/p')
    wait_for_service "MySQL" "$DB_HOST" "3306" || echo "警告: MySQL连接延迟，将在运行时重试"
fi

# 如果启用了InfluxDB，等待InfluxDB服务就绪
if [[ "$INFLUXDB_ENABLED" == "true" ]]; then
    INFLUXDB_HOST=$(echo "$INFLUXDB_URL" | sed -n 's|http://\(.*\):.*|\1|p')
    INFLUXDB_PORT=$(echo "$INFLUXDB_URL" | sed -n 's|.*:\([0-9]*\).*|\1|p')
    wait_for_service "InfluxDB" "$INFLUXDB_HOST" "$INFLUXDB_PORT" || echo "警告: InfluxDB连接延迟，将在运行时重试"
fi

# 如果启用了Redis，等待Redis服务就绪
if [[ "$REDIS_ENABLED" == "true" ]]; then
    REDIS_HOST=$(echo "$REDIS_URL" | sed -n 's|redis://\(.*\):.*|\1|p')
    REDIS_PORT=$(echo "$REDIS_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
    wait_for_service "Redis" "$REDIS_HOST" "$REDIS_PORT" || echo "警告: Redis连接延迟，将在运行时重试"
fi

# 准备启动应用
cd /app

# 初始化数据（如果需要）
echo "初始化应用..."
python -c "from database import init_database; init_database()" 2>/dev/null || echo "初始化数据库完成或已跳过"

# 显示配置信息（不包含敏感数据）
echo "应用配置:"
echo "  - 环境: ${ENVIRONMENT:-production}"
echo "  - 容器化: ${CONTAINERIZED}"
echo "  - 工作进程数: ${WORKERS:-2}"
echo "  - 数据库类型: ${DATABASE_URL%%://*}"
echo "  - 监听端口: ${API_PORT:-8000}"

# 执行主应用
echo "启动应用..."
exec python main.py
EOF

# 保持非root用户权限（已在前面切换）

# 设置暴露端口
EXPOSE 8000

# 添加健康检查（增强版）
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health | grep -q "200" || exit 1

# 使用入口点脚本启动，支持环境变量配置和优雅关闭
ENTRYPOINT ["/app/entrypoint.sh"]