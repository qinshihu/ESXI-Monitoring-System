#!/bin/bash
# 增强的错误处理，但在容器环境中不完全退出，保证服务尽可能可用
set -Eeo pipefail

# 等待依赖服务就绪
wait_for_service() {
    local service=$1
    local host=$2
    local port=$3
    local retries=${4:-30}
    
    # 检查host和port是否有效
    if [[ -z "$host" || -z "$port" ]]; then
        echo "警告: ${service}服务配置无效，跳过连接检查"
        return 0
    fi
    
    echo "等待${service}启动..."
    for i in $(seq 1 $retries); do
        if nc -z "$host" "$port" 2>/dev/null; then
            echo "${service}服务已就绪！"
            return 0
        fi
        echo "尝试连接${service} (${i}/${retries})..."
        sleep 1
    done
    echo "警告: 无法连接到${service}服务，将在运行时重试"
    return 0
}

# 准备启动应用
cd /app

# 确保必要的目录存在并设置权限
mkdir -p /app/locks /app/logs /app/data
chmod -R 755 /app/locks /app/logs /app/data

# 如果启用了MySQL，等待MySQL服务就绪
if [[ "$DATABASE_URL" == *"mysql"* ]]; then
    # 使用更健壮的URL解析方式
    DB_HOST=$(echo "$DATABASE_URL" | sed -n 's/.*@\([^:]*\):.*/\1/p' || echo "db")
    # 验证解析结果是否有效
    if [[ -z "$DB_HOST" ]]; then
        DB_HOST="db"  # 默认值
        echo "警告: 无法从DATABASE_URL解析主机名，使用默认值: $DB_HOST"
    fi
    wait_for_service "MySQL" "$DB_HOST" "3306"
fi

# 如果启用了InfluxDB，等待InfluxDB服务就绪
if [[ "$INFLUXDB_ENABLED" == "true" ]]; then
    # 设置默认值，避免环境变量未设置时出错
    INFLUXDB_HOST=${INFLUXDB_HOST:-influxdb}
    INFLUXDB_PORT=${INFLUXDB_PORT:-8086}
    # 尝试从URL解析，如果URL存在
    if [[ -n "$INFLUXDB_URL" ]]; then
        INFLUXDB_HOST=$(echo "$INFLUXDB_URL" | sed -n 's|http://\(.*\):.*|\1|p' || echo "$INFLUXDB_HOST")
        INFLUXDB_PORT=$(echo "$INFLUXDB_URL" | sed -n 's|.*:\([0-9]*\).*|\1|p' || echo "$INFLUXDB_PORT")
    fi
    wait_for_service "InfluxDB" "$INFLUXDB_HOST" "$INFLUXDB_PORT"
fi

# 如果启用了Redis，等待Redis服务就绪
if [[ "$REDIS_ENABLED" == "true" ]]; then
    # 设置默认值，避免环境变量未设置时出错
    REDIS_HOST=${REDIS_HOST:-redis}
    REDIS_PORT=${REDIS_PORT:-6379}
    # 尝试从URL解析，如果URL存在
    if [[ -n "$REDIS_URL" ]]; then
        REDIS_HOST=$(echo "$REDIS_URL" | sed -n 's|redis://\(.*\):.*|\1|p' || echo "$REDIS_HOST")
        REDIS_PORT=$(echo "$REDIS_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p' || echo "$REDIS_PORT")
    fi
    wait_for_service "Redis" "$REDIS_HOST" "$REDIS_PORT"
fi

# 初始化数据（如果需要）
echo "初始化应用..."
# 使用更健壮的初始化方法，添加超时控制
if python3 -c "import sys; import signal; signal.signal(signal.SIGALRM, lambda *args: sys.exit(1)); signal.alarm(60); from database import init_database; init_database()" 2>&1; then
    echo "数据库初始化成功"
else
    echo "警告: 数据库初始化遇到问题，将在运行时重试"
    # 检查是否在容器环境中，如果是，确保不会因为初始化失败而退出容器
    if [[ "$CONTAINERIZED" == "true" || -f /proc/1/cgroup && grep -q 'docker' /proc/1/cgroup ]]; then
        echo "容器环境中，继续启动应用..."
    fi
fi

# 显示配置信息（不包含敏感数据）
echo "应用配置:"
echo "  - 环境: ${ENVIRONMENT:-production}"
echo "  - 容器化: ${CONTAINERIZED:-false}"
echo "  - 工作进程数: ${API_WORKERS:-2}"
echo "  - 数据库类型: ${DATABASE_URL%%://*}"
echo "  - 监听端口: ${API_PORT:-8000}"
# 显示主机信息，便于调试
if [[ -f /etc/os-release ]]; then
    OS_INFO=$(grep PRETTY_NAME /etc/os-release | cut -d'=' -f2 | tr -d '"')
    echo "  - 操作系统: ${OS_INFO}"
fi

# 确保虚拟环境路径正确设置
if [[ -n "$VIRTUAL_ENV" && -d "$VIRTUAL_ENV/bin" ]]; then
    echo "使用虚拟环境: $VIRTUAL_ENV"
    # 确保PATH包含虚拟环境
    export PATH="$VIRTUAL_ENV/bin:$PATH"
fi

# 执行主应用
echo "启动应用..."
exec python3 main.py