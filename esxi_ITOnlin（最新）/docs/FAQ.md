# 常见问题

本文档收集了使用ESXI监控系统时常见的问题和解决方案。

---

## 安装与部署

### Q1: 如何安装依赖？

**A**: 使用pip安装依赖：

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows: venv\Scripts\activate
# Linux/Mac: source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### Q2: Docker Compose启动失败？

**A**: 请检查以下几点：

1. 确保Docker和Docker Compose已正确安装
2. 检查端口是否被占用（默认使用8080、3306、8086、6379）
3. 查看日志定位问题：
   ```bash
   docker-compose logs -f app
   ```

### Q3: 如何配置ESXI主机？

**A**: 有两种配置方式：

**方式1**: 通过环境变量配置（推荐用于Docker部署）
```bash
ESXI_HOSTS=esxi-01:192.168.1.100:root:password,esxi-02:192.168.1.101:root:password
```

**方式2**: 通过API添加
```bash
curl -X POST http://localhost:8000/api/hosts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "esxi-01",
    "ip_address": "192.168.1.100",
    "username": "root",
    "password": "your_password"
  }'
```

---

## 数据采集

### Q1: 数据采集失败？

**A**: 检查以下内容：

1. **网络连通性**
   - 确保监控服务器能访问ESXI主机的443端口
   - 检查防火墙规则

2. **ESXI凭证**
   - 验证用户名和密码是否正确
   - 确保用户有足够的权限（推荐使用root或具有管理员权限的用户）

3. **ESXI配置**
   - 确保ESXI主机的API服务已启用
   - 检查ESXI主机是否允许远程访问

### Q2: 采集间隔可以调整吗？

**A**: 可以通过环境变量调整：

```bash
# 修改数据采集间隔（秒）
DATA_COLLECTION_INTERVAL=60
```

### Q3: 虚拟机状态不更新？

**A**: 检查以下内容：

1. ESXI主机连接状态是否正常
2. 虚拟机是否被正确识别
3. 查看采集日志：
   ```bash
   docker-compose logs -f app | grep collect
   ```

---

## 告警系统

### Q1: 如何配置告警阈值？

**A**: 在 `config.py` 中配置或通过环境变量设置：

```bash
# 设置主机CPU告警阈值
HOST_CPU_WARNING_THRESHOLD=70
HOST_CPU_CRITICAL_THRESHOLD=85
```

### Q2: 如何接收告警通知？

**A**: 目前支持Webhook通知：

```bash
# 启用Webhook通知
ENABLE_WEBHOOK_NOTIFICATIONS=true
WEBHOOK_URL=https://your-webhook-endpoint.com
```

### Q3: 告警重复发送？

**A**: 系统有告警冷却机制，可以调整冷却时间：

```bash
# 设置告警冷却时间（秒）
ALERT_COOLDOWN_PERIOD=300
```

---

## 数据库

### Q1: 数据库连接失败？

**A**: 检查以下内容：

1. **MySQL服务状态**
   ```bash
   docker-compose ps db
   ```

2. **连接字符串**
   ```bash
   # 确保格式正确
   DATABASE_URL=mysql+pymysql://username:password@host:port/database
   ```

3. **数据库权限**
   - 确保数据库用户有访问权限
   - 检查防火墙是否允许连接

### Q2: 如何备份数据库？

**A**: 

**MySQL备份**:
```bash
docker exec -it esxi-monitoring-db mysqldump -u admin -p esxi_monitoring > backup.sql
```

**SQLite备份**:
```bash
cp esxi_monitor.db esxi_monitor.db.backup
```

### Q3: 数据库文件过大？

**A**: 系统会自动清理过期数据，可以调整保留天数：

```bash
# 设置告警记录保留天数
ALERT_RETENTION_DAYS=30

# 设置虚拟机记录保留天数
VM_RETENTION_DAYS=7
```

---

## API

### Q1: 如何访问API？

**A**: 启动服务后访问：
- API基础地址: http://localhost:8000/api/
- API文档: http://localhost:8000/docs

### Q2: API返回404错误？

**A**: 检查以下内容：

1. 确保API路径正确
2. 检查API前缀配置（默认为 `/api`）
3. 查看服务是否正常运行

### Q3: API返回500错误？

**A**: 查看日志定位问题：

```bash
docker-compose logs -f app | grep ERROR
```

---

## 性能问题

### Q1: 系统响应慢？

**A**: 尝试以下优化：

1. **增加Worker数量**
   ```bash
   API_WORKERS=4
   ```

2. **调整采集间隔**
   ```bash
   DATA_COLLECTION_INTERVAL=60
   ```

3. **启用缓存**
   ```bash
   REDIS_ENABLED=true
   ```

### Q2: 内存占用高？

**A**: 检查以下内容：

1. 查看内存使用情况
   ```bash
   docker stats esxi-monitoring-system
   ```

2. 减少采集频率
3. 清理过期数据

---

## Docker相关

### Q1: 如何查看容器日志？

**A**: 

```bash
# 查看所有服务日志
docker-compose logs

# 查看特定服务日志
docker-compose logs -f app

# 查看最近的日志
docker-compose logs --tail=100 app
```

### Q2: 如何更新服务？

**A**: 

```bash
# 停止服务
docker-compose down

# 更新代码
git pull origin main

# 重新构建并启动
docker-compose up -d --build
```

### Q3: 如何进入容器？

**A**: 

```bash
# 进入应用容器
docker exec -it esxi-monitoring-system bash

# 进入数据库容器
docker exec -it esxi-monitoring-db bash
```

---

## 安全

### Q1: 如何保护敏感信息？

**A**: 

1. 使用环境变量存储敏感信息
2. 不要将 `.env` 文件提交到版本控制
3. 使用Docker Secrets（生产环境）

### Q2: 如何启用HTTPS？

**A**: 使用反向代理（如Nginx）配置HTTPS：

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 其他问题

### Q1: 如何获取帮助？

**A**: 

1. 查看项目文档（`docs/`目录）
2. 检查GitHub Issues
3. 创建新Issue描述问题

### Q2: 如何贡献代码？

**A**: 请查看 `CONTRIBUTING.md` 文件了解贡献指南。

### Q3: 项目支持哪些操作系统？

**A**: 

- Linux（推荐）
- Windows
- macOS

容器化部署支持任何支持Docker的系统。
