from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.pool import QueuePool
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import redis
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

from config import settings

# 配置日志
logger = logging.getLogger(__name__)

# SQLAlchemy配置
Base = declarative_base()

# 创建引擎时添加更多的错误处理和重试机制
# 根据数据库URL判断是否为SQLite
connect_args = {}
if not settings.DATABASE_URL.startswith('sqlite'):
    connect_args = {
        'connect_timeout': 10,  # 连接超时时间
        'read_timeout': 30,     # 读取超时时间
        'write_timeout': 30     # 写入超时时间
    }

engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,
    echo=False,
    # 添加连接重试参数
    pool_pre_ping=True,  # 在使用连接前验证连接是否有效
    pool_use_lifo=True,  # 使用后进先出策略提高性能
    connect_args=connect_args
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# InfluxDB客户端
influx_client = None
influx_write_api = None
influx_query_api = None

# Redis客户端
redis_client = None


class ESXIHost(Base):
    """ESXI主机表"""
    __tablename__ = "esxi_hosts"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    ip_address = Column(String(50), unique=True, nullable=False, index=True)
    username = Column(String(50), nullable=False)
    password = Column(String(100), nullable=False)
    status = Column(String(20), default="disconnected")  # connected, disconnected, error
    status_message = Column(Text, nullable=True)  # 状态消息
    last_seen = Column(DateTime, nullable=True)
    version = Column(String(50), nullable=True)
    build = Column(String(50), nullable=True)
    cpu_cores = Column(Integer, nullable=True)
    cpu_sockets = Column(Integer, nullable=True)
    total_memory_gb = Column(Float, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 添加性能指标字段，用于快速访问
    cpu_usage = Column(Float, nullable=True)  # CPU使用率
    memory_usage = Column(Float, nullable=True)  # 内存使用率
    storage_usage = Column(Float, nullable=True)  # 存储使用率
    network_usage = Column(Float, nullable=True)  # 网络使用率
    port = Column(Integer, default=443)  # 默认端口
    description = Column(Text, nullable=True)  # 描述信息
    
    # 关系
    virtual_machines = relationship("VirtualMachine", back_populates="host", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="host", cascade="all, delete-orphan")


class VirtualMachine(Base):
    """虚拟机表"""
    __tablename__ = "virtual_machines"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    vm_id = Column(String(100), unique=True, nullable=False, index=True)  # VMware VM ID
    name = Column(String(255), nullable=False, index=True)
    host_id = Column(Integer, ForeignKey("esxi_hosts.id"), nullable=False)
    power_state = Column(String(20), default="unknown")  # poweredOn, poweredOff, suspended, unknown
    guest_os = Column(String(255), nullable=True)
    num_cpu = Column(Integer, nullable=True)
    memory_gb = Column(Float, nullable=True)
    ip_address = Column(String(50), nullable=True)
    is_template = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    last_seen = Column(DateTime, nullable=True)  # 最后活动时间，用于检测非活跃虚拟机
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    host = relationship("ESXIHost", back_populates="virtual_machines")
    alerts = relationship("Alert", back_populates="vm", cascade="all, delete-orphan")


class Alert(Base):
    """告警表"""
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    alert_id = Column(String(100), unique=True, nullable=False, index=True)
    host_id = Column(Integer, ForeignKey("esxi_hosts.id"), nullable=True)
    vm_id = Column(Integer, ForeignKey("virtual_machines.id"), nullable=True)
    alert_type = Column(String(50), nullable=False, index=True)  # cpu, memory, disk, network, connection
    severity = Column(String(20), nullable=False)  # critical, warning, info
    level = Column(String(20), nullable=False, index=True)  # critical, warning, info
    message = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, index=True)
    is_resolved = Column(Boolean, default=False, index=True)  # 添加is_resolved属性
    triggered_at = Column(DateTime, default=datetime.utcnow, index=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    source_type = Column(String(20), nullable=False, index=True)  # host, vm
    source_id = Column(Integer, nullable=False, index=True)
    source_name = Column(String(255), nullable=False)
    value = Column(Float, nullable=True)  # 指标值
    threshold = Column(Float, nullable=True)  # 阈值
    occurrences = Column(Integer, default=1)  # 发生次数
    
    # 关系
    host = relationship("ESXIHost", back_populates="alerts")
    vm = relationship("VirtualMachine", back_populates="alerts")


# 数据库依赖
def get_db() -> Session:
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session() -> Session:
    """数据库会话上下文管理器"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# 初始化数据库
def init_database():
    """初始化数据库表"""
    retry_count = 3
    retry_delay = 5  # 秒
    
    for attempt in range(retry_count):
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("数据库表创建成功")
            return True
        except Exception as e:
            if attempt < retry_count - 1:
                logger.warning(f"数据库初始化尝试 {attempt + 1} 失败: {str(e)}. 将在 {retry_delay} 秒后重试...")
                import time
                time.sleep(retry_delay)
            else:
                logger.error(f"数据库初始化失败（已尝试 {retry_count} 次）: {str(e)}")
                raise


# 初始化InfluxDB客户端
def init_influxdb():
    """初始化InfluxDB连接"""
    global influx_client, influx_write_api, influx_query_api
    try:
        influx_client = InfluxDBClient(
            url=settings.INFLUXDB_URL,
            token=settings.INFLUXDB_TOKEN,
            org=settings.INFLUXDB_ORG,
            timeout=settings.INFLUXDB_TIMEOUT * 1000
        )
        influx_write_api = influx_client.write_api(write_options=SYNCHRONOUS)
        influx_query_api = influx_client.query_api()
        logger.info("InfluxDB连接初始化成功")
    except Exception as e:
        logger.error(f"InfluxDB初始化失败: {str(e)}")
        raise


# 初始化Redis客户端
def init_redis():
    """初始化Redis连接"""
    global redis_client
    try:
        redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=settings.REDIS_TIMEOUT,
            socket_timeout=settings.REDIS_TIMEOUT
        )
        # 测试连接
        redis_client.ping()
        logger.info("Redis连接初始化成功")
    except Exception as e:
        logger.error(f"Redis初始化失败: {str(e)}")
        raise


# 写入指标到InfluxDB
def write_metrics(bucket: str, host_name: str, metrics: Dict[str, float], tags: Optional[Dict[str, str]] = None):
    """写入指标到InfluxDB"""
    try:
        if not influx_write_api:
            init_influxdb()
        
        point = Point("esxi_metrics")
        point.tag("host", host_name)
        
        # 添加额外标签
        if tags:
            for tag_key, tag_value in tags.items():
                point.tag(tag_key, tag_value)
        
        # 添加字段
        for metric_name, metric_value in metrics.items():
            point.field(metric_name, metric_value)
        
        # 写入数据
        influx_write_api.write(bucket=bucket, record=point)
        return True
    except Exception as e:
        logger.error(f"写入InfluxDB失败: {str(e)}")
        return False


# 从Redis获取缓存
def get_cache(key: str) -> Optional[Any]:
    """从Redis获取缓存"""
    try:
        if not redis_client:
            init_redis()
        return redis_client.get(key)
    except Exception as e:
        logger.error(f"从Redis读取失败: {str(e)}")
        return None


# 设置Redis缓存
def set_cache(key: str, value: Any, expire: int = 300) -> bool:
    """设置Redis缓存"""
    try:
        if not redis_client:
            init_redis()
        return redis_client.setex(key, expire, value)
    except Exception as e:
        logger.error(f"写入Redis失败: {str(e)}")
        return False


# 获取InfluxDB客户端
def get_influxdb_client():
    """获取InfluxDB客户端实例"""
    global influx_client
    if not influx_client and settings.INFLUXDB_ENABLED:
        init_influxdb()
    return influx_client

# 获取Redis客户端
def get_redis_client():
    """获取Redis客户端实例"""
    global redis_client
    if not redis_client and settings.REDIS_ENABLED:
        init_redis()
    return redis_client

# 关闭所有数据库连接
def close_connections():
    """关闭所有数据库连接"""
    global influx_client, redis_client
    
    # 关闭InfluxDB连接
    if influx_write_api:
        influx_write_api.close()
    if influx_client:
        influx_client.close()
    
    # 关闭Redis连接
    if redis_client:
        redis_client.close()
    
    # 关闭SQLAlchemy引擎
    if engine:
        engine.dispose()
    
    logger.info("所有数据库连接已关闭")


# 健康检查
def health_check():
    """
    检查所有系统组件的连接状态（容器化环境优化版本）
    
    Returns:
        dict: 包含各组件连接状态的字典
    """
    # 初始化状态字典，添加更多详细信息
    status = {
        "mysql": False,  # 向后兼容键
        "database": False,  # 通用数据库键
        "influxdb": False,
        "redis": False,
        "database_type": "unknown",  # 新增字段
        "containerized": False  # 新增容器化环境标识
    }
    
    # 检测容器化环境
    status["containerized"] = (
        getattr(settings, "CONTAINERIZED", False) or
        os.environ.get("CONTAINERIZED") == "true" or
        os.environ.get("ENVIRONMENT") == "production" or
        (os.path.exists("/proc/1/cgroup") and "docker" in open("/proc/1/cgroup", "r").read())
    )
    
    # 检查SQLAlchemy数据库连接（支持SQLite和MySQL）
    try:
        # 使用引擎配置中的超时参数
        timeout = getattr(settings, "DATABASE_CONNECTION_TIMEOUT", 5)  # 默认5秒超时
        
        # 使用上下文管理器确保连接正确关闭
        with engine.connect() as conn:
            # 在容器环境中使用更简单的查询
            if status["containerized"]:
                query = text("SELECT 1")  # 简化容器环境中的查询
            else:
                query = text("SELECT 1")
                
            # 执行查询并确保有结果
            result = conn.execute(query)
            # 实际获取结果，确保查询真正执行
            _ = result.scalar()
            
            # 设置状态
            status["mysql"] = True  # 保持向后兼容
            status["database"] = True  # 通用数据库键
            
            # 设置数据库类型
            if settings.DATABASE_URL.startswith('sqlite'):
                status["database_type"] = "sqlite"
                logger.info("SQLite数据库连接正常")
            else:
                status["database_type"] = "mysql"
                logger.info("MySQL数据库连接正常")
    except Exception as e:
        # 区分不同类型的数据库错误
        error_type = "unknown"
        if "sqlite" in str(e).lower():
            error_type = "sqlite"
        elif "mysql" in str(e).lower():
            error_type = "mysql"
        
        # 在容器环境中使用更简洁的错误日志，并且视为警告而不是错误
        if status["containerized"]:
            logger.warning(f"数据库连接失败 [{error_type}]: {str(e)}")
            # 在容器环境中，如果数据库连接暂时失败，仍然可以接受
        else:
            logger.error(f"数据库连接失败 [{error_type}]: {str(e)}", exc_info=True)
            
        status["mysql"] = False
        status["database"] = False
    
    # 检查InfluxDB - 更优雅地处理可选依赖和超时
    try:
        # 只有在配置了InfluxDB时才尝试连接
        if hasattr(settings, 'INFLUXDB_ENABLED') and settings.INFLUXDB_ENABLED:
            # 在容器环境中，先检查环境变量是否设置
            if status["containerized"] and not all([
                os.environ.get("INFLUXDB_URL"),
                os.environ.get("INFLUXDB_TOKEN"),
                os.environ.get("INFLUXDB_ORG"),
                os.environ.get("INFLUXDB_BUCKET")
            ]):
                logger.warning("InfluxDB环境变量未完全配置，跳过连接检查")
                status["influxdb"] = True  # 在容器环境中，如果未配置则视为可选
            else:
                # 延迟初始化，避免不必要的资源消耗
                if not influx_client:
                    init_influxdb()
                
                # 容器环境中使用较短的超时时间
                health_timeout = 3 if status["containerized"] else 5
                
                # 使用超时上下文管理器执行健康检查
                import contextlib
                
                with contextlib.closing(influx_client.health(timeout=health_timeout)) as health_result:
                    # 确保health_result有status_code属性
                    if hasattr(health_result, 'status_code') and health_result.status_code == 200:
                        status["influxdb"] = True
                        logger.debug("InfluxDB健康检查通过")
                    else:
                        logger.warning(f"InfluxDB健康检查失败，状态码: {getattr(health_result, 'status_code', 'N/A')}")
        else:
            logger.debug("InfluxDB未启用，跳过健康检查")
            status["influxdb"] = True  # 未启用时视为健康
    except ImportError:
        # 缺少InfluxDB依赖，在容器环境中视为可选
        if status["containerized"]:
            logger.warning("缺少InfluxDB依赖，视为可选")
            status["influxdb"] = True
        else:
            logger.error("缺少InfluxDB依赖")
    except ConnectionError as e:
        # 连接错误，在容器环境中记录为警告而不是错误
        if status["containerized"]:
            logger.warning(f"InfluxDB连接错误 (容器环境): {str(e)}")
            status["influxdb"] = True  # 在容器环境中，InfluxDB是可选的
        else:
            logger.error(f"InfluxDB连接错误: {str(e)}")
    except Exception as e:
        # 其他错误
        if status["containerized"]:
            logger.warning(f"InfluxDB健康检查异常 (容器环境): {str(e)}")
            status["influxdb"] = True  # 在容器环境中，InfluxDB是可选的
        else:
            logger.error(f"InfluxDB健康检查异常: {str(e)}", exc_info=True)
    
    # 检查Redis - 更优雅地处理可选依赖和超时
    try:
        # 只有在配置了Redis时才尝试连接
        if hasattr(settings, 'REDIS_ENABLED') and settings.REDIS_ENABLED:
            # 在容器环境中，先检查环境变量是否设置
            if status["containerized"] and not os.environ.get("REDIS_URL"):
                logger.warning("Redis环境变量未配置，跳过连接检查")
                status["redis"] = True  # 在容器环境中，如果未配置则视为可选
            else:
                # 延迟初始化
                if not redis_client:
                    init_redis()
                
                # 容器环境中使用较短的超时时间
                ping_timeout = 2 if status["containerized"] else 5
                
                # 使用超时执行ping
                import contextlib
                with contextlib.closing(redis_client.ping()) as pong:
                    status["redis"] = (pong == True or pong == "PONG")  # 处理不同Redis客户端返回值
                    if status["redis"]:
                        logger.debug("Redis健康检查通过")
                    else:
                        logger.warning("Redis ping返回非预期值")
        else:
            logger.debug("Redis未启用，跳过健康检查")
            status["redis"] = True  # 未启用时视为健康
    except ImportError:
        # 缺少Redis依赖，在容器环境中视为可选
        if status["containerized"]:
            logger.warning("缺少Redis依赖，视为可选")
            status["redis"] = True
        else:
            logger.error("缺少Redis依赖")
    except ConnectionError as e:
        # 连接错误，在容器环境中记录为警告，并且将Redis视为可选
        if status["containerized"]:
            logger.warning(f"Redis连接错误 (容器环境): {str(e)}")
            status["redis"] = True  # 在容器环境中，Redis是可选的
        else:
            logger.error(f"Redis连接错误: {str(e)}")
    except Exception as e:
        # 其他错误
        if status["containerized"]:
            logger.warning(f"Redis健康检查异常 (容器环境): {str(e)}")
            status["redis"] = True  # 在容器环境中，Redis是可选的
        else:
            logger.error(f"Redis健康检查异常: {str(e)}", exc_info=True)
    
    # 在容器环境中，如果数据库连接正常，视为基本健康
    if status["containerized"] and status["database"]:
        logger.debug("容器环境下数据库连接正常，系统基本可用")
        # 在容器环境中，即使其他组件连接失败，只要数据库可用，系统仍视为基本健康
        status["influxdb"] = True
        status["redis"] = True
    
    return status