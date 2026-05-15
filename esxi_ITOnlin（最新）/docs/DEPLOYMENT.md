# 部署指南

本文档介绍如何部署ESXI监控系统。

## 目录

1. [环境要求](#环境要求)
2. [快速开始](#快速开始)
3. [Docker Compose部署](#docker-compose部署)
4. [手动部署](#手动部署)
5. [配置说明](#配置说明)
6. [生产环境建议](#生产环境建议)

---

## 环境要求

### 硬件要求

| 配置 | 最低要求 | 推荐配置 |
|------|----------|----------|
| CPU | 2核 | 4核 |
| 内存 | 4GB | 8GB |
| 存储 | 50GB | 100GB |

### 软件要求

- Docker 20.10+
- Docker Compose 2.0+
- Python 3.9+（手动部署）

---

## 快速开始

### 使用Docker Compose（推荐）

```bash
# 克隆仓库
git clone https://github.com/yourusername/esxi-monitoring.git
cd esxi-monitoring

# 启动服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f app
```

服务启动后访问：
- 应用主页: http://localhost:8080
- API文档: http://localhost:8080/docs
- 健康检查: http://localhost:8080/health

---

## Docker Compose部署

### 配置环境变量

编辑 `.env` 文件或在 `docker-compose.yml` 中修改环境变量：

```yaml
environment:
  - ENVIRONMENT=production
  - API_HOST=0.0.0.0
  - API_PORT=8000
  - DATABASE_URL=mysql+pymysql://admin:password@db:3306/esxi_monitoring
  - ESXI_HOSTS=esxi1:192.168.1.10:root:password
```

### 启动服务

```bash
# 启动所有服务（后台模式）
docker-compose up -d

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 查看日志
docker-compose logs -f
```

### 服务说明

| 服务 | 端口 | 说明 |
|------|------|------|
| app | 8080 | 主应用服务 |
| db | 3306 | MySQL数据库 |
| influxdb | 8086 | 时序数据库 |
| redis | 6379 | 缓存服务 |

---

## 手动部署

### 环境准备

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows: venv\Scripts\activate
# Linux/Mac: source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 数据库配置

#### MySQL配置

```bash
# 创建数据库
mysql -u root -p
CREATE DATABASE esxi_monitoring CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'admin'@'%' IDENTIFIED BY 'password';
GRANT ALL PRIVILEGES ON esxi_monitoring.* TO 'admin'@'%';
FLUSH PRIVILEGES;
```

#### SQLite配置（开发环境）

无需额外配置，系统会自动创建SQLite数据库文件。

### 启动应用

```bash
# 设置环境变量
export DATABASE_URL=mysql+pymysql://admin:password@localhost:3306/esxi_monitoring
export ESXI_HOSTS=esxi1:192.168.1.10:root:password

# 启动开发服务器
python main.py
```

### 使用Gunicorn（生产环境）

```bash
# 安装gunicorn
pip install gunicorn

# 启动生产服务器
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app
```

---

## 配置说明

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| ENVIRONMENT | 运行环境 | production |
| API_HOST | API监听地址 | 0.0.0.0 |
| API_PORT | API监听端口 | 8000 |
| API_DEBUG | 调试模式 | false |
| DATABASE_URL | 数据库连接URL | sqlite:///./esxi_monitor.db |
| ESXI_HOSTS | ESXI主机列表 | - |
| INFLUXDB_ENABLED | 是否启用InfluxDB | false |
| INFLUXDB_URL | InfluxDB地址 | http://localhost:8086 |
| REDIS_ENABLED | 是否启用Redis | false |
| REDIS_URL | Redis地址 | redis://localhost:6379/0 |
| CONTAINERIZED | 是否容器化运行 | false |

### ESXI主机配置格式

```bash
ESXI_HOSTS=name1:ip1:username1:password1,name2:ip2:username2:password2
```

格式：`主机名:IP地址:用户名:密码`

### 告警阈值配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| HOST_CPU_WARNING_THRESHOLD | 主机CPU警告阈值 | 70% |
| HOST_CPU_CRITICAL_THRESHOLD | 主机CPU严重阈值 | 85% |
| HOST_MEMORY_WARNING_THRESHOLD | 主机内存警告阈值 | 75% |
| HOST_MEMORY_CRITICAL_THRESHOLD | 主机内存严重阈值 | 90% |
| HOST_DISK_WARNING_THRESHOLD | 主机磁盘警告阈值 | 70% |
| HOST_DISK_CRITICAL_THRESHOLD | 主机磁盘严重阈值 | 85% |

---

## 生产环境建议

### 安全配置

1. **启用HTTPS**
   - 使用Nginx反向代理
   - 配置SSL证书（推荐使用Let's Encrypt）

2. **添加认证**
   - 实现OAuth2认证
   - 配置API Key

3. **限制访问**
   - 配置防火墙规则
   - 限制数据库访问IP

### 性能优化

1. **数据库优化**
   - 定期清理历史数据
   - 创建适当的索引
   - 配置连接池

2. **缓存策略**
   - 使用Redis缓存频繁访问的数据
   - 设置合理的缓存过期时间

3. **日志管理**
   - 配置日志轮转
   - 集中日志收集（如ELK Stack）

### 监控与告警

1. **健康检查**
   - 配置Docker健康检查
   - 使用监控工具（如Prometheus + Grafana）

2. **告警通知**
   - 配置Webhook通知
   - 设置邮件告警

### 备份策略

1. **数据库备份**
   ```bash
   # MySQL备份
   mysqldump -u admin -p esxi_monitoring > backup.sql
   
   # SQLite备份
   cp esxi_monitor.db esxi_monitor.db.backup
   ```

2. **定时备份**
   - 使用cron定时执行备份脚本
   - 备份文件存储到外部存储

---

## 故障排除

### 常见问题

1. **数据库连接失败**
   - 检查数据库服务是否运行
   - 验证连接字符串是否正确
   - 检查数据库用户权限

2. **ESXI连接失败**
   - 验证ESXI主机地址和凭证
   - 确保网络连通性
   - 检查ESXI的API服务是否启用

3. **容器启动失败**
   - 查看容器日志：`docker-compose logs app`
   - 检查端口是否被占用
   - 验证环境变量配置

### 日志位置

- 应用日志：`/app/logs/`（容器内）
- MySQL日志：`/var/lib/mysql/`
- Docker日志：使用 `docker-compose logs`

---

## 升级指南

### 版本升级

```bash
# 停止服务
docker-compose down

# 拉取最新代码
git pull origin main

# 更新镜像
docker-compose build

# 启动服务
docker-compose up -d
```

### 数据库迁移

如果数据库schema有变更，需要执行数据库迁移：

```bash
# 进入容器
docker exec -it esxi-monitoring-system bash

# 执行迁移（如果有迁移脚本）
python migrate.py
```
