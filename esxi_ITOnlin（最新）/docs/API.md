# ESXI监控系统 API文档

## 概述

本文档描述ESXI监控系统的RESTful API接口。

### 基础URL

```
http://localhost:8000/api/
```

### 认证

当前版本暂未实现认证机制。生产环境建议添加OAuth2或API Key认证。

---

## 仪表盘接口

### 获取仪表盘摘要

**GET** `/dashboard/summary`

获取监控系统的总体摘要信息。

**响应示例**:
```json
{
  "total_hosts": 3,
  "connected_hosts": 2,
  "warning_hosts": 1,
  "error_hosts": 0,
  "total_vms": 15,
  "running_vms": 12,
  "critical_alerts": 0,
  "warning_alerts": 2,
  "system_load": 45.5,
  "data_collection_status": "running"
}
```

---

## 主机管理接口

### 获取主机列表

**GET** `/hosts`

**查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| status | string | 按状态过滤（connected/disconnected/warning/error） |
| skip | int | 跳过记录数 |
| limit | int | 返回记录数 |

**响应示例**:
```json
[
  {
    "id": 1,
    "name": "esxi-01",
    "ip_address": "192.168.1.100",
    "status": "connected",
    "last_seen": "2024-01-15T10:30:00Z",
    "cpu_usage": 45.2,
    "memory_usage": 67.8,
    "storage_usage": 72.5,
    "vm_count": 5,
    "status_message": null
  }
]
```

### 获取主机详情

**GET** `/hosts/{host_id}`

**路径参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| host_id | int | 主机ID |

### 创建主机

**POST** `/hosts`

**请求体**:
```json
{
  "name": "esxi-01",
  "ip_address": "192.168.1.100",
  "username": "root",
  "password": "your_password",
  "port": 443,
  "description": "Production ESXI Host"
}
```

**字段说明**:
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 主机名称 |
| ip_address | string | 是 | IP地址或主机名 |
| username | string | 是 | ESXI用户名 |
| password | string | 是 | ESXI密码 |
| port | int | 否 | 端口号，默认443 |
| description | string | 否 | 描述信息 |

### 更新主机

**PUT** `/hosts/{host_id}`

**请求体**: 同创建主机，但所有字段均为可选。

### 删除主机

**DELETE** `/hosts/{host_id}`

---

## 虚拟机管理接口

### 获取虚拟机列表

**GET** `/vms`

**查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| host_id | int | 按主机ID过滤 |
| power_state | string | 按电源状态过滤 |
| is_active | bool | 是否只显示活跃虚拟机 |
| skip | int | 跳过记录数 |
| limit | int | 返回记录数 |

### 获取虚拟机详情

**GET** `/vms/{vm_id}`

### 获取主机的虚拟机

**GET** `/hosts/{host_id}/vms`

---

## 告警管理接口

### 获取告警列表

**GET** `/alerts`

**查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| level | string | 按级别过滤（critical/warning/info/error） |
| is_resolved | bool | 是否已解决 |
| host_id | int | 按主机ID过滤 |
| vm_id | int | 按虚拟机ID过滤 |
| start_time | datetime | 开始时间 |
| end_time | datetime | 结束时间 |
| skip | int | 跳过记录数 |
| limit | int | 返回记录数 |

**响应示例**:
```json
[
  {
    "id": 1,
    "level": "warning",
    "type": "cpu_usage",
    "source": "主机",
    "message": "主机 esxi-01 CPU使用率较高: 85.2%",
    "details": null,
    "is_resolved": false,
    "created_at": "2024-01-15T10:30:00Z",
    "resolved_at": null,
    "host_id": 1,
    "vm_id": null
  }
]
```

### 获取告警详情

**GET** `/alerts/{alert_id}`

### 解决告警

**PUT** `/alerts/{alert_id}/resolve`

---

## 指标查询接口

### 查询历史指标

**POST** `/metrics/query`

**请求体**:
```json
{
  "source": "esxi-01",
  "metric_name": "cpu_usage",
  "start_time": "2024-01-15T00:00:00Z",
  "end_time": "2024-01-15T23:59:59Z",
  "interval": "5m",
  "filters": {}
}
```

### 获取最新指标

**GET** `/metrics/latest`

**查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| source | string | 数据源名称 |
| metrics | string | 指标名称列表，逗号分隔 |

---

## 系统管理接口

### 获取系统信息

**GET** `/system/info`

**响应示例**:
```json
{
  "version": "1.0.0",
  "uptime": 3600,
  "python_version": "3.9.10",
  "database_status": "connected",
  "influxdb_status": "connected",
  "redis_status": "connected",
  "active_collections": 2,
  "active_connections": 3
}
```

### 健康检查

**GET** `/system/health`

---

## 任务管理接口

### 获取任务列表

**GET** `/tasks`

### 获取任务详情

**GET** `/tasks/{task_id}`

### 任务操作

**POST** `/tasks/{task_id}/action`

**请求体**:
```json
{
  "action": "pause"
}
```

**action可选值**: pause, resume, trigger

### 启动所有任务

**POST** `/tasks/start-all`

### 停止所有任务

**POST** `/tasks/stop-all`

---

## 配置接口

### 获取告警阈值配置

**GET** `/settings/thresholds`

---

## 错误响应格式

所有错误响应遵循以下格式：

```json
{
  "success": false,
  "error": "错误描述",
  "code": 404
}
```

### 常见HTTP状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 204 | 删除成功（无内容） |
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |
