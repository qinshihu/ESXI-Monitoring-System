"""
数据采集模块

该模块负责从ESXI主机和虚拟机收集监控数据，包括：
1. ESXI主机性能指标采集
2. 虚拟机状态监控
3. 连接池管理
"""

from .esxi_collector import ESXiCollector

__all__ = [
    "ESXiCollector"
]

__version__ = "1.0.0"