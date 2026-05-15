# 开发指南

本文档介绍如何在本地环境中开发和调试ESXI监控系统。

## 目录

1. [环境搭建](#环境搭建)
2. [项目结构](#项目结构)
3. [开发流程](#开发流程)
4. [代码规范](#代码规范)
5. [测试](#测试)
6. [调试技巧](#调试技巧)
7. [常见问题](#常见问题)

---

## 环境搭建

### 安装依赖

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows: venv\Scripts\activate
# Linux/Mac: source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 安装开发依赖（可选）
pip install pytest pytest-asyncio httpx black flake8 isort
```

### 配置开发环境

创建 `.env` 文件：

```bash
# .env 文件内容
ENVIRONMENT=development
API_HOST=0.0.0.0
API_PORT=8000
API_DEBUG=true
DATABASE_URL=sqlite:///./esxi_monitor.db
ESXI_HOSTS=esxi-01:192.168.1.100:root:password
```

### 启动开发服务器

```bash
# 启动开发服务器（带热重载）
python main.py
```

开发服务器启动后：
- 访问地址: http://localhost:8000
- API文档: http://localhost:8000/docs
- ReDoc文档: http://localhost:8000/redoc

---

## 项目结构

```
esxi_monitoring/
├── main.py              # 应用入口
├── config.py            # 配置管理
├── database.py          # 数据库连接和ORM模型
├── api/
│   ├── __init__.py
│   ├── routes.py        # API路由定义
│   └── models.py        # Pydantic数据模型
├── collectors/
│   ├── __init__.py
│   └── esxi_collector.py # ESXI数据采集器
├── alerts/
│   ├── __init__.py
│   └── alert_manager.py  # 告警管理器
├── tasks/
│   ├── __init__.py
│   └── scheduler.py      # 任务调度器
├── tests/               # 测试文件（需创建）
├── docs/                # 文档
├── static/              # 静态文件
└── docker-compose.yml    # Docker配置
```

### 模块职责

| 模块 | 职责 |
|------|------|
| `main.py` | FastAPI应用初始化、中间件配置、路由注册 |
| `config.py` | 配置管理，从环境变量加载配置 |
| `database.py` | SQLAlchemy模型定义、数据库连接管理 |
| `api/routes.py` | RESTful API端点定义 |
| `api/models.py` | Pydantic请求/响应模型 |
| `collectors/esxi_collector.py` | ESXI主机数据采集 |
| `alerts/alert_manager.py` | 告警规则检查和通知 |
| `tasks/scheduler.py` | 定时任务调度 |

---

## 开发流程

### 新增功能

1. **定义数据模型**（如果需要）
   - 在 `database.py` 中添加SQLAlchemy模型
   - 在 `api/models.py` 中添加Pydantic模型

2. **实现业务逻辑**
   - 在相应的模块中实现功能
   - 确保代码符合PEP 8规范

3. **添加API端点**
   - 在 `api/routes.py` 中添加路由
   - 使用正确的HTTP方法和状态码

4. **编写测试**
   - 在 `tests/` 目录下创建测试文件
   - 确保测试覆盖新增功能

### 修改现有功能

1. **理解现有代码**
   - 阅读相关代码，理解实现逻辑
   - 查看测试文件，了解预期行为

2. **进行修改**
   - 保持代码风格一致
   - 更新相关文档

3. **运行测试**
   - 确保所有测试通过

---

## 代码规范

### Python代码规范

1. **遵循PEP 8**
   - 使用4空格缩进
   - 每行不超过80字符
   - 使用snake_case命名变量和函数
   - 使用PascalCase命名类

2. **代码格式化**
   ```bash
   # 使用black格式化代码
   black .

   # 使用isort整理import
   isort .

   # 使用flake8检查代码
   flake8 .
   ```

3. **类型提示**
   - 所有函数和方法都应该有类型提示
   - 使用Optional、Union等类型

4. **注释规范**
   - 复杂逻辑需要注释说明
   - 函数和类需要docstring
   - docstring使用Google风格或NumPy风格

### Git提交规范

```
<类型>: <简短描述>

<详细描述（可选）>
```

类型说明：
- `feat`: 新功能
- `fix`: 修复bug
- `docs`: 文档更新
- `style`: 代码风格调整
- `refactor`: 重构代码
- `test`: 测试代码
- `chore`: 构建/工具相关

---

## 测试

### 运行测试

```bash
# 安装测试依赖
pip install pytest pytest-asyncio httpx

# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_api.py

# 生成测试覆盖率报告
pytest --cov=app --cov-report=html
```

### 编写测试

#### 单元测试示例

```python
# tests/test_api.py
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_get_dashboard_summary():
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    data = response.json()
    assert "total_hosts" in data
    assert "total_vms" in data
```

#### 集成测试

集成测试需要数据库连接，建议使用测试数据库：

```python
@pytest.fixture
def db_session():
    # 创建测试数据库会话
    pass
```

---

## 调试技巧

### 使用调试器

```python
# 在代码中添加断点
import pdb; pdb.set_trace()

# 或者使用logging
import logging
logger = logging.getLogger(__name__)
logger.debug("调试信息")
```

### 使用FastAPI调试工具

开发模式下，可以使用：
- `/docs` - Swagger UI，可测试API
- `/redoc` - ReDoc文档
- `/health` - 健康检查端点

### 查看日志

```bash
# 查看应用日志
python main.py

# 或者使用grep过滤
python main.py | grep ERROR
```

---

## 常见问题

### 1. 依赖安装失败

**问题**: 某些依赖包安装失败

**解决方案**:
```bash
# 使用国内镜像源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 或者升级pip
pip install --upgrade pip
```

### 2. 数据库连接失败

**问题**: 无法连接到数据库

**解决方案**:
- 检查数据库服务是否运行
- 验证连接字符串是否正确
- 确保数据库用户有访问权限

### 3. ESXI连接失败

**问题**: 无法连接到ESXI主机

**解决方案**:
- 验证ESXI主机地址和凭证
- 确保ESXI主机的API服务已启用
- 检查网络连通性

### 4. 端口被占用

**问题**: 启动时提示端口已被占用

**解决方案**:
```bash
# 查找占用端口的进程（Windows）
netstat -ano | findstr :8000

# 查找占用端口的进程（Linux/Mac）
lsof -i :8000

# 杀死进程
kill -9 <PID>
```

### 5. 虚拟环境问题

**问题**: 虚拟环境不生效

**解决方案**:
```bash
# 重新创建虚拟环境
rm -rf venv
python -m venv venv
```

---

## 开发工具推荐

### IDE推荐

- **Visual Studio Code**
  - 安装Python扩展
  - 安装Pylance扩展
  - 配置settings.json

### 插件推荐

| 插件 | 用途 |
|------|------|
| Python | Python语言支持 |
| Pylance | 类型检查和智能提示 |
| Black Formatter | 代码格式化 |
| isort | import整理 |
| GitLens | Git历史查看 |

### 配置示例

```json
// .vscode/settings.json
{
  "python.pythonPath": "./venv/bin/python",
  "python.formatting.provider": "black",
  "python.sortImports.args": ["--profile", "black"],
  "python.linting.enabled": true,
  "python.linting.flake8Enabled": true
}
```
