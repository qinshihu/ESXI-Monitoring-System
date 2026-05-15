"""
API数据模型定义
使用Pydantic定义请求和响应的数据结构
"""

from enum import Enum
from typing import Dict, List, Optional, Union
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, ConfigDict


class HostStatus(str, Enum):
    """主机状态枚举"""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    WARNING = "warning"
    ERROR = "error"
    MAINTENANCE = "maintenance"


class VMPowerState(str, Enum):
    """虚拟机电源状态枚举"""
    POWERED_ON = "poweredOn"
    POWERED_OFF = "poweredOff"
    SUSPENDED = "suspended"
    UNKNOWN = "unknown"


class AlertLevel(str, Enum):
    """告警级别枚举"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """告警类型枚举"""
    CPU = "cpu"
    MEMORY = "memory"
    STORAGE = "storage"
    NETWORK = "network"
    POWER = "power"
    HOST = "host"
    VM = "vm"
    SYSTEM = "system"


class TaskStatus(str, Enum):
    """任务状态枚举"""
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    SUCCESS = "success"
    FAILED = "failed"


class HostBase(BaseModel):
    """主机基础模型"""
    name: str = Field(..., min_length=1, max_length=100, description="主机名称")
    ip_address: str = Field(..., description="IP地址")
    username: str = Field(..., min_length=1, max_length=50, description="用户名")
    password: str = Field(..., min_length=1, max_length=100, description="密码")
    port: int = Field(default=443, ge=1, le=65535, description="端口号")
    description: Optional[str] = Field(None, max_length=500, description="描述")

    @field_validator('ip_address')
    @classmethod
    def validate_ip(cls, v):
        """验证IP地址格式"""
        import re
        ip_pattern = r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
        hostname_pattern = r'^(([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9])\.)*([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9\-]*[A-Za-z0-9])$'
        
        if not re.match(ip_pattern, v) and not re.match(hostname_pattern, v):
            raise ValueError('无效的IP地址或主机名格式')
        return v


class HostCreate(HostBase):
    """创建主机请求模型"""
    pass


class HostUpdate(BaseModel):
    """更新主机请求模型"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    ip_address: Optional[str] = None
    username: Optional[str] = Field(None, min_length=1, max_length=50)
    password: Optional[str] = Field(None, min_length=1, max_length=100)
    port: Optional[int] = Field(None, ge=1, le=65535)
    description: Optional[str] = Field(None, max_length=500)
    status: Optional[HostStatus] = None


class HostStatusResponse(BaseModel):
    """主机状态响应模型"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    name: str
    ip_address: str
    status: HostStatus
    last_seen: Optional[datetime] = None
    cpu_usage: Optional[float] = Field(None, description="CPU使用率(%)")
    memory_usage: Optional[float] = Field(None, description="内存使用率(%)")
    storage_usage: Optional[float] = Field(None, description="存储使用率(%)")
    vm_count: Optional[int] = Field(None, description="虚拟机数量")
    status_message: Optional[str] = Field(None, description="状态消息")


class HostResponse(HostStatusResponse):
    """主机详细信息响应模型"""
    port: int
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class VirtualMachineBase(BaseModel):
    """虚拟机基础模型"""
    name: str = Field(..., min_length=1, max_length=100)
    vm_id: str = Field(..., min_length=1, max_length=100)
    guest_os: Optional[str] = Field(None, max_length=200)
    memory_mb: int = Field(default=0, ge=0)
    num_cpu: int = Field(default=1, ge=1)


class VirtualMachineResponse(BaseModel):
    """虚拟机响应模型"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    vm_id: str
    host_id: int
    name: str
    power_state: VMPowerState
    guest_os: Optional[str] = None
    memory_mb: int = Field(..., description="内存大小(MB)")
    num_cpu: int = Field(..., description="CPU核心数")
    cpu_usage: Optional[float] = Field(None, description="CPU使用率(%)")
    memory_usage: Optional[float] = Field(None, description="内存使用率(%)")
    is_active: bool
    created_at: datetime
    last_seen: datetime


class AlertBase(BaseModel):
    """告警基础模型"""
    level: AlertLevel
    type: AlertType
    source: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1, max_length=1000)
    details: Optional[Dict] = Field(None, description="详细信息")


class AlertCreate(AlertBase):
    """创建告警请求模型"""
    pass


class AlertResponse(BaseModel):
    """告警响应模型"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    level: AlertLevel
    type: AlertType
    source: str
    message: str
    details: Optional[Dict] = None
    is_resolved: bool
    created_at: datetime
    resolved_at: Optional[datetime] = None
    host_id: Optional[int] = None
    vm_id: Optional[int] = None


class MetricQuery(BaseModel):
    """指标查询请求模型"""
    source: str = Field(..., min_length=1, max_length=200, description="数据源名称")
    metric_name: str = Field(..., min_length=1, max_length=100, description="指标名称")
    start_time: datetime = Field(..., description="开始时间")
    end_time: datetime = Field(..., description="结束时间")
    interval: Optional[str] = Field("1m", description="时间间隔")
    filters: Optional[Dict[str, str]] = Field(None, description="过滤条件")


class MetricData(BaseModel):
    """单条指标数据"""
    timestamp: datetime
    value: float


class MetricResponse(BaseModel):
    """指标查询响应模型"""
    metric_name: str
    data_points: List[MetricData]
    unit: Optional[str] = None
    source: str


class DashboardSummary(BaseModel):
    """仪表盘摘要信息"""
    total_hosts: int
    connected_hosts: int
    warning_hosts: int
    error_hosts: int
    total_vms: int
    running_vms: int
    critical_alerts: int
    warning_alerts: int
    system_load: Optional[float] = None
    data_collection_status: str


class SystemInfo(BaseModel):
    """系统信息响应模型"""
    version: str
    uptime: int = Field(..., description="运行时间(秒)")
    python_version: str
    database_status: str
    influxdb_status: str
    redis_status: str
    active_collections: int
    active_connections: int


class TaskInfo(BaseModel):
    """任务信息响应模型"""
    id: str
    name: str
    status: TaskStatus
    next_run_time: Optional[datetime] = None
    last_run_time: Optional[datetime] = None
    run_count: int
    error_count: int


class TaskAction(BaseModel):
    """任务操作请求模型"""
    action: str = Field(..., description="操作类型: pause, resume, trigger")

    @field_validator('action')
    @classmethod
    def validate_action(cls, v):
        """验证操作类型"""
        if v not in ['pause', 'resume', 'trigger']:
            raise ValueError('操作类型必须是 pause, resume 或 trigger')
        return v


class APIResponse(BaseModel):
    """通用API响应模型"""
    success: bool = Field(..., description="操作是否成功")
    message: Optional[str] = Field(None, description="响应消息")
    data: Optional[Dict] = Field(None, description="响应数据")
    error: Optional[str] = Field(None, description="错误信息")


class LoginRequest(BaseModel):
    """登录请求模型"""
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=100)


class LoginResponse(BaseModel):
    """登录响应模型"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Dict[str, str]


class ThresholdConfig(BaseModel):
    """告警阈值配置模型"""
    cpu_warning: float = Field(default=80.0, ge=0, le=100, description="CPU警告阈值(%)")
    cpu_critical: float = Field(default=90.0, ge=0, le=100, description="CPU严重阈值(%)")
    memory_warning: float = Field(default=80.0, ge=0, le=100, description="内存警告阈值(%)")
    memory_critical: float = Field(default=90.0, ge=0, le=100, description="内存严重阈值(%)")
    storage_warning: float = Field(default=85.0, ge=0, le=100, description="存储警告阈值(%)")
    storage_critical: float = Field(default=95.0, ge=0, le=100, description="存储严重阈值(%)")
    network_warning: float = Field(default=80.0, ge=0, le=100, description="网络警告阈值(%)")
    network_critical: float = Field(default=90.0, ge=0, le=100, description="网络严重阈值(%)")
    alert_cooldown: int = Field(default=300, ge=0, description="告警冷却时间(秒)")
    vm_inactive_threshold: int = Field(default=5, ge=1, description="虚拟机非活跃阈值(分钟)")

    @field_validator('cpu_critical', 'memory_critical', 'storage_critical', 'network_critical')
    @classmethod
    def validate_critical_thresholds(cls, v, info):
        """验证严重阈值必须大于警告阈值"""
        if info.field_name == 'cpu_critical':
            if v <= info.data.get('cpu_warning', 0):
                raise ValueError('严重阈值必须大于警告阈值')
        elif info.field_name == 'memory_critical':
            if v <= info.data.get('memory_warning', 0):
                raise ValueError('严重阈值必须大于警告阈值')
        elif info.field_name == 'storage_critical':
            if v <= info.data.get('storage_warning', 0):
                raise ValueError('严重阈值必须大于警告阈值')
        elif info.field_name == 'network_critical':
            if v <= info.data.get('network_warning', 0):
                raise ValueError('严重阈值必须大于警告阈值')
        return v