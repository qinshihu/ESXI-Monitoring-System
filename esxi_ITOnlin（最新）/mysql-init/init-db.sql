-- MySQL初始化脚本 - ESXI监控系统
-- 此脚本在MySQL容器首次启动时执行

-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS esxi_monitoring CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 切换到目标数据库
USE esxi_monitoring;

-- 创建用户并授权（如果不存在）
CREATE USER IF NOT EXISTS 'admin'@'%' IDENTIFIED WITH mysql_native_password BY 'password';
GRANT ALL PRIVILEGES ON esxi_monitoring.* TO 'admin'@'%';

-- 设置数据库连接参数优化
SET GLOBAL max_connections = 200;
SET GLOBAL wait_timeout = 3600;
SET GLOBAL interactive_timeout = 3600;
SET GLOBAL innodb_buffer_pool_size = 536870912;  -- 512MB
SET GLOBAL innodb_log_file_size = 67108864;  -- 64MB
SET GLOBAL innodb_flush_log_at_trx_commit = 2;  -- 性能优先的配置

-- 显示创建结果
SELECT '数据库初始化完成' AS status;
SELECT user, host FROM mysql.user WHERE user = 'admin';
SHOW DATABASES LIKE 'esxi_monitoring';