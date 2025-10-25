# ESXI Monitoring System
自己开发的 ESXI 监控系统

系统架构如下：
前端：基于 HTML/JavaScript 的 Web 界面，支持常规视图和大屏模式
后端：FastAPI 提供 API 服务
数据采集：PyVmomi 定时获取 ESXI 数据
数据存储：InfluxDB 存储时序数据，MySQL 存储元数据
缓存：Redis 优化查询性能

<img width="1920" height="1080" alt="屏幕截图 2025-10-25 155014" src="https://github.com/user-attachments/assets/b2992cd7-e6d9-4fb5-b542-4b8e728e02ea" />
