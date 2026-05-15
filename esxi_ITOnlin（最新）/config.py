import os
from typing import List, Dict, Any, Optional
import dotenv

# 尝试加载.env文件，但允许失败（在Docker环境中可能通过环境变量设置）
try:
    dotenv.load_dotenv()
except Exception:
    pass


class Settings:
    """简化的应用配置类 - 增强版，更好地支持Docker部署"""
    # 基本配置
    VERSION = "1.0.0"
    API_PREFIX = "/api"
    ENVIRONMENT = "production"  # development, production, testing
    
    # 数据库配置 - 使用更通用的默认值，支持SQLite作为备选
    DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./esxi_monitor.db")
    
    # InfluxDB配置 - 添加启用标志，默认禁用
    INFLUXDB_ENABLED = os.environ.get("INFLUXDB_ENABLED", "false").lower() == "true"
    INFLUXDB_URL = os.environ.get("INFLUXDB_URL", "http://localhost:8086")
    INFLUXDB_TOKEN = os.environ.get("INFLUXDB_TOKEN", "your-token")
    INFLUXDB_ORG = os.environ.get("INFLUXDB_ORG", "your-org")
    INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "esxi_metrics")
    INFLUXDB_TIMEOUT = 30  # 秒
    
    # Redis配置 - 增强容器化支持
    REDIS_ENABLED = os.environ.get("REDIS_ENABLED", "false").lower() == "true"
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    REDIS_TIMEOUT = int(os.environ.get("REDIS_TIMEOUT", "10"))  # 秒
    REDIS_SOCKET_CONNECT_TIMEOUT = int(os.environ.get("REDIS_SOCKET_CONNECT_TIMEOUT", "5"))  # 连接超时
    REDIS_SOCKET_TIMEOUT = int(os.environ.get("REDIS_SOCKET_TIMEOUT", "5"))  # 读取超时
    REDIS_RETRY_ON_TIMEOUT = os.environ.get("REDIS_RETRY_ON_TIMEOUT", "true").lower() == "true"  # 超时是否重试
    
    # ESXI主机配置
    ESXI_HOSTS = "esxi-01:192.168.1.100:root:password,esxi-02:192.168.1.101:root:password,esxi-03:192.168.1.102:root:password"
    ESXI_CONNECTION_TIMEOUT = 60  # 连接超时时间（秒）
    ESXI_CONNECTION_RETRY = 3  # 连接重试次数
    ESXI_CONNECTION_REUSE = 300  # 连接复用时间（秒）
    
    # 告警配置 - 增强版，区分主机和虚拟机的告警阈值
    # 主机告警阈值
    HOST_CPU_WARNING_THRESHOLD = 70.0  # 主机CPU警告阈值
    HOST_CPU_CRITICAL_THRESHOLD = 85.0  # 主机CPU严重阈值
    HOST_MEMORY_WARNING_THRESHOLD = 75.0  # 主机内存警告阈值
    HOST_MEMORY_CRITICAL_THRESHOLD = 90.0  # 主机内存严重阈值
    HOST_DISK_WARNING_THRESHOLD = 70.0  # 主机磁盘警告阈值
    HOST_DISK_CRITICAL_THRESHOLD = 85.0  # 主机磁盘严重阈值
    HOST_NETWORK_WARNING_THRESHOLD = 8000  # 主机网络警告阈值 (KB/s)
    HOST_NETWORK_CRITICAL_THRESHOLD = 12000  # 主机网络严重阈值 (KB/s)
    
    # 虚拟机告警阈值
    VM_CPU_WARNING_THRESHOLD = 75.0  # 虚拟机CPU警告阈值
    VM_CPU_CRITICAL_THRESHOLD = 90.0  # 虚拟机CPU严重阈值
    VM_MEMORY_WARNING_THRESHOLD = 80.0  # 虚拟机内存警告阈值
    VM_MEMORY_CRITICAL_THRESHOLD = 95.0  # 虚拟机内存严重阈值
    VM_NETWORK_WARNING_THRESHOLD = 2000  # 虚拟机网络警告阈值 (KB/s)
    VM_NETWORK_CRITICAL_THRESHOLD = 5000  # 虚拟机网络严重阈值 (KB/s)
    
    # 通用告警配置
    ALERT_COOLDOWN_PERIOD = 300  # 告警冷却期（秒）
    
    # Webhook通知配置
    ENABLE_WEBHOOK_NOTIFICATIONS = os.environ.get("ENABLE_WEBHOOK_NOTIFICATIONS", "false").lower() == "true"
    WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
    WEBHOOK_MAX_RETRIES = int(os.environ.get("WEBHOOK_MAX_RETRIES", "3"))
    WEBHOOK_RETRY_DELAY = float(os.environ.get("WEBHOOK_RETRY_DELAY", "2.0"))  # 重试间隔（秒）
    WEBHOOK_TIMEOUT = int(os.environ.get("WEBHOOK_TIMEOUT", "10"))  # 超时时间（秒）
    WEBHOOK_VERIFY_SSL = os.environ.get("WEBHOOK_VERIFY_SSL", "true").lower() == "true"  # 是否验证SSL证书
    
    # 数据采集配置
    COLLECTION_INTERVAL = 30  # 数据采集间隔（秒）
    COLLECTION_TIMEOUT = 30  # 采集超时时间（秒）
    
    # API配置 - 优先从环境变量读取，与docker-compose.yml保持一致
    API_HOST = os.environ.get("API_HOST", "0.0.0.0")  # Docker环境中必须监听所有接口
    API_PORT = int(os.environ.get("API_PORT", 8000))  # 从环境变量读取并转换为整数
    API_DEBUG = os.environ.get("API_DEBUG", "false").lower() == "true"
    API_WORKERS = int(os.environ.get("API_WORKERS", 4))
    
    # CORS配置
    CORS_ORIGINS = ["*"]
    CORS_CREDENTIALS = True
    CORS_METHODS = ["*"]
    CORS_HEADERS = ["*"]
    
    # 日志配置
    LOG_LEVEL = "INFO"
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_FILE = None
    
    # 安全配置
    SECRET_KEY = "your-secret-key-change-in-production"
    
    # 监控配置
    ENABLE_PROMETHEUS = os.environ.get("ENABLE_PROMETHEUS", "true").lower() == "true"
    
    # 任务调度器配置
    SCHEDULER_WORKERS = 3
    DATA_COLLECTION_INTERVAL = 60  # 数据采集间隔，单位：秒
    ALERT_CHECK_INTERVAL = 120  # 告警检查间隔，单位：秒
    VM_INACTIVE_THRESHOLD = 30  # 虚拟机非活跃阈值（分钟）
    
    # 系统维护配置
    CLEANUP_ALERT_DAYS = 30  # 清理告警记录的天数
    SYSTEM_CPU_WARNING_THRESHOLD = 80.0  # 系统CPU警告阈值
    SYSTEM_MEMORY_WARNING_THRESHOLD = 85.0  # 系统内存警告阈值
    SYSTEM_DISK_WARNING_THRESHOLD = 80.0  # 系统磁盘警告阈值
    
    # 确保环境配置与Docker环境兼容
    # 从环境变量读取，如果没有设置则默认为production（Docker环境）
    ENVIRONMENT = os.environ.get("ENVIRONMENT", "production")
    
    # 容器化环境特定配置
    CONTAINERIZED = os.environ.get("CONTAINERIZED", "false").lower() == "true"
    LOCK_DIR = os.environ.get("LOCK_DIR", "/app/locks")  # 锁文件目录，Docker环境中应使用挂载卷
    DATA_DIR = os.environ.get("DATA_DIR", "/app/data")  # 数据目录，用于挂载卷
    
    @property
    def esxi_hosts_list(self) -> List[Dict[str, Any]]:
        """解析ESXI主机列表 - 增强版，添加错误处理"""
        hosts = []
        if self.ESXI_HOSTS:
            for i, host_str in enumerate(self.ESXI_HOSTS.split(",")):
                try:
                    parts = host_str.strip().split(":")
                    if len(parts) == 4:
                        hosts.append({
                            "name": parts[0].strip(),
                            "ip": parts[1].strip(),
                            "username": parts[2].strip(),
                            "password": parts[3].strip()
                        })
                    else:
                        print(f"警告: 第{i+1}个ESXI主机配置格式不正确: {host_str}")
                except Exception as e:
                    print(f"警告: 解析第{i+1}个ESXI主机配置时出错: {str(e)}")
        return hosts

    def __init__(self):
        """初始化配置，从环境变量加载配置（如果存在） - 增强版，更健壮的类型转换"""
        # 从环境变量加载配置
        for attr in dir(self):
            if not attr.startswith('_') and attr.isupper():
                env_value = os.environ.get(attr)
                if env_value is not None:
                    # 尝试转换类型
                    try:
                        # 获取当前值的类型
                        current_value = getattr(self, attr)
                        if isinstance(current_value, bool):
                            # 处理布尔值 - 支持多种布尔表示
                            env_value = env_value.lower() in ('true', '1', 'yes', 'y', 't', 'on')
                        elif isinstance(current_value, int):
                            env_value = int(env_value)
                        elif isinstance(current_value, float):
                            env_value = float(env_value)
                        elif isinstance(current_value, list):
                            # 假设列表是逗号分隔的字符串
                            env_value = [item.strip() for item in env_value.split(',') if item.strip()]
                    except (ValueError, TypeError):
                        # 如果转换失败，保留字符串值，但记录警告
                        print(f"警告: 无法将环境变量 {attr} 的值 '{env_value}' 转换为预期类型，保留为字符串")
                    
                    # 设置新值
                    setattr(self, attr, env_value)
        
        # 验证必要的配置项
        self._validate_config()
    
    def _validate_config(self):
        """验证配置的有效性"""
        # 确保数据库URL有效
        if not self.DATABASE_URL:
            print("警告: DATABASE_URL未设置，将使用SQLite默认值")
            self.DATABASE_URL = "sqlite:///./esxi_monitor.db"
        
        # 确保API主机和端口配置正确
        if not hasattr(self, 'API_HOST'):
            self.API_HOST = "0.0.0.0"  # Docker环境中必须监听所有接口
        
        if not hasattr(self, 'API_PORT'):
            self.API_PORT = 8000
        
        # 验证Webhook配置
        if self.ENABLE_WEBHOOK_NOTIFICATIONS and not self.WEBHOOK_URL:
            print("警告: ENABLE_WEBHOOK_NOTIFICATIONS为true但WEBHOOK_URL未设置")
            self.ENABLE_WEBHOOK_NOTIFICATIONS = False
        
        # 容器化环境下的配置调整
        if self.CONTAINERIZED:
            # 容器环境下自动调整一些默认值
            if not self.REDIS_URL.startswith("redis://"):
                print("警告: 在容器化环境中，建议使用Redis进行缓存")
            
            # 确保锁目录在挂载卷中
            if not os.path.isabs(self.LOCK_DIR):
                self.LOCK_DIR = os.path.join(self.DATA_DIR, "locks")
                print(f"调整锁目录路径: {self.LOCK_DIR}")


# 创建全局配置实例
settings = Settings()