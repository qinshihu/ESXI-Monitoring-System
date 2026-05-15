# ESXI监控系统

![License](https://img.shields.io/github/license/yourusername/esxi-monitoring)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.95%2B-green)
![Docker](https://img.shields.io/badge/docker-compose-blue)

一个基于FastAPI构建的ESXI主机和虚拟机监控系统，支持容器化部署和全面的健康检查。

## 功能特性

- **ESXI主机监控** - 实时监控ESXI主机的CPU、内存、磁盘、网络等指标
- **虚拟机监控** - 监控虚拟机的性能指标和电源状态
- **告警系统** - 多级告警（critical/warning/info），支持Webhook通知
- **数据可视化** - 支持InfluxDB时序数据存储，便于趋势分析
- **RESTful API** - 完整的API接口，支持主机、虚拟机、告警管理
- **容器化部署** - 支持Docker和Docker Compose一键部署
- **健康检查** - 完善的健康检查端点，支持容器化环境

## 技术栈

| 组件 | 技术 | 版本要求 |
|------|------|----------|
| 后端框架 | FastAPI | >=0.95.0 |
| 数据库 | MySQL 8.0 / SQLite | - |
| 时序数据库 | InfluxDB 2.x | >=2.6 |
| 缓存 | Redis | >=7.0 |
| 虚拟化API | PyVMOMI | >=8.0.0 |
| 任务调度 | APScheduler | - |

## 快速开始

### 方式一：Docker Compose（推荐）

```bash
# 克隆仓库
git clone https://github.com/yourusername/esxi-monitoring.git
cd esxi-monitoring

# 配置ESXI主机（可选，也可通过API添加）
# 编辑 .env 文件或 docker-compose.yml

# 启动服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f app
```

### 方式二：手动部署

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
export DATABASE_URL=sqlite:///./esxi_monitor.db
export ESXI_HOSTS=esxi-01:192.168.1.100:root:password

# 启动服务
python main.py
```

## 访问服务

启动后访问以下地址：

| 服务 | 地址 |
|------|------|
| 应用主页 | http://localhost:8080 |
| API文档 | http://localhost:8080/docs |
| ReDoc文档 | http://localhost:8080/redoc |
| 健康检查 | http://localhost:8080/health |

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
| REDIS_ENABLED | 是否启用Redis | false |
| CONTAINERIZED | 是否容器化运行 | false |

### ESXI主机配置格式

```bash
ESXI_HOSTS=name1:ip1:username1:password1,name2:ip2:username2:password2
```

### 告警阈值配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| HOST_CPU_WARNING_THRESHOLD | 主机CPU警告阈值 | 70% |
| HOST_CPU_CRITICAL_THRESHOLD | 主机CPU严重阈值 | 85% |
| HOST_MEMORY_WARNING_THRESHOLD | 主机内存警告阈值 | 75% |
| HOST_MEMORY_CRITICAL_THRESHOLD | 主机内存严重阈值 | 90% |

## API接口

### 仪表盘
- `GET /api/dashboard/summary` - 获取仪表盘摘要

### 主机管理
- `GET /api/hosts` - 获取主机列表
- `POST /api/hosts` - 添加主机
- `GET /api/hosts/{id}` - 获取主机详情
- `PUT /api/hosts/{id}` - 更新主机
- `DELETE /api/hosts/{id}` - 删除主机

### 虚拟机管理
- `GET /api/vms` - 获取虚拟机列表
- `GET /api/vms/{id}` - 获取虚拟机详情
- `GET /api/hosts/{id}/vms` - 获取主机的虚拟机

### 告警管理
- `GET /api/alerts` - 获取告警列表
- `GET /api/alerts/{id}` - 获取告警详情
- `PUT /api/alerts/{id}/resolve` - 解决告警

### 系统管理
- `GET /api/system/info` - 获取系统信息
- `GET /api/system/health` - 健康检查

### 任务管理
- `GET /api/tasks` - 获取任务列表
- `POST /api/tasks/{id}/action` - 任务操作

## 项目结构

```
esxi_monitoring/
├── main.py              # 应用入口
├── config.py            # 配置管理
├── database.py          # 数据库连接和ORM模型
├── api/                 # API模块
│   ├── routes.py        # 路由定义
│   └── models.py        # 数据模型
├── collectors/          # 数据采集器
│   └── esxi_collector.py
├── alerts/              # 告警管理
│   └── alert_manager.py
├── tasks/               # 任务调度
│   └── scheduler.py
├── docs/                # 文档
├── docker-compose.yml   # Docker配置
└── requirements.txt     # 依赖清单
```

## 文档

- [API文档](docs/API.md) - API接口详细说明
- [部署指南](docs/DEPLOYMENT.md) - 部署和配置说明
- [开发指南](docs/DEVELOPMENT.md) - 开发和调试指南
- [常见问题](docs/FAQ.md) - 常见问题解答

## 贡献

欢迎贡献代码！请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解贡献指南。

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 安全

请阅读 [SECURITY.md](SECURITY.md) 了解安全最佳实践。

## 联系方式

如有问题或建议，请创建Issue或发送邮件。
