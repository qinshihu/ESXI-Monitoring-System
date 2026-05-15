# 变更日志

所有重要的项目变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
项目版本遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [未发布]

### 新增

- 新增虚拟机网络流量监控功能
- 添加系统资源告警（CPU、内存、磁盘）
- 支持Webhook告警通知
- 添加任务调度器状态API
- 新增API文档（Swagger UI / ReDoc）

### 变更

- 重构数据采集器，支持批量处理
- 优化容器化部署配置
- 改进健康检查端点，支持容器化环境
- 更新依赖包版本

### 修复

- 修复数据库连接超时问题
- 修复告警阈值检查逻辑
- 修复虚拟机状态更新问题

## [1.0.0] - 2026-05-14

### 新增

- 初始版本发布
- ESXI主机监控功能
- 虚拟机监控功能
- MySQL数据库支持
- InfluxDB时序数据存储
- Redis缓存支持
- 告警系统
- 完整的RESTful API
- Docker容器化部署支持
