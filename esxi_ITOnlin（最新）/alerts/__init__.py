"""
告警模块

该模块负责管理系统告警，包括：
1. 告警阈值检查
2. 告警通知发送
3. 告警状态管理
"""

from .alert_manager import AlertManager, alert_manager

__all__ = [
    "AlertManager",
    "alert_manager"
]

__version__ = "1.0.0"