import logging
import time
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
from enum import Enum

from config import settings
from database import db_session, Alert, ESXIHost, VirtualMachine, get_cache, set_cache

logger = logging.getLogger(__name__)


class AlertLevel(str, Enum):
    """告警级别枚举"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """告警类型枚举"""
    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    DISK_USAGE = "disk_usage"
    NETWORK_USAGE = "network_usage"
    HOST_CONNECTION = "host_connection"
    VM_STATUS = "vm_status"
    VM_POWER = "vm_power"
    SYSTEM_CPU_HIGH = "system_cpu_high"  # 系统CPU告警
    SYSTEM_MEMORY_HIGH = "system_memory_high"  # 系统内存告警
    SYSTEM_DISK_HIGH = "system_disk_high"  # 系统磁盘告警


class AlertManager:
    """告警管理器"""
    
    def __init__(self):
        """初始化告警管理器"""
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_cooldowns: Dict[str, float] = {}
        self._load_active_alerts()
    
    def _load_active_alerts(self):
        """从数据库加载活跃的告警"""
        try:
            with db_session() as db:
                active_alerts = db.query(Alert).filter(
                    Alert.is_resolved == False,
                    Alert.resolved_at == None
                ).all()
                
                for alert in active_alerts:
                    alert_key = self._generate_alert_key(alert)
                    self.active_alerts[alert_key] = alert
                
                logger.info(f"加载了 {len(self.active_alerts)} 个活跃告警")
        except Exception as e:
            logger.error(f"加载活跃告警失败: {str(e)}")
    
    def _generate_alert_key(self, alert: Alert) -> str:
        """生成告警唯一键"""
        return f"{alert.source_type}:{alert.source_id}:{alert.alert_type}"
    
    def _should_create_alert(self, alert_key: str) -> bool:
        """检查是否应该创建告警（考虑冷却时间）"""
        if alert_key in self.alert_cooldowns:
            if time.time() - self.alert_cooldowns[alert_key] < settings.ALERT_COOLDOWN_PERIOD:
                return False
        return True
    
    def _set_alert_cooldown(self, alert_key: str):
        """设置告警冷却时间"""
        self.alert_cooldowns[alert_key] = time.time()
    
    def check_host_thresholds(self, host: ESXIHost, metrics: Dict[str, float]) -> List[Alert]:
        """检查主机指标是否超过阈值
        
        Args:
            host: 主机对象
            metrics: 主机指标
            
        Returns:
            新创建的告警列表
        """
        new_alerts = []
        
        # CPU使用率检查
        if 'cpu_usage_percent' in metrics:
            cpu_usage = metrics['cpu_usage_percent']
            if cpu_usage >= settings.HOST_CPU_CRITICAL_THRESHOLD:
                alert = self._create_or_update_alert(
                    source_type="host",
                    source_id=host.id,
                    source_name=host.name,
                    alert_type=AlertType.CPU_USAGE,
                    level=AlertLevel.CRITICAL,
                    message=f"主机 {host.name} CPU使用率过高: {cpu_usage:.1f}%",
                    value=cpu_usage,
                    threshold=settings.HOST_CPU_CRITICAL_THRESHOLD
                )
                if alert:
                    new_alerts.append(alert)
            elif cpu_usage >= settings.HOST_CPU_WARNING_THRESHOLD:
                alert = self._create_or_update_alert(
                    source_type="host",
                    source_id=host.id,
                    source_name=host.name,
                    alert_type=AlertType.CPU_USAGE,
                    level=AlertLevel.WARNING,
                    message=f"主机 {host.name} CPU使用率较高: {cpu_usage:.1f}%",
                    value=cpu_usage,
                    threshold=settings.HOST_CPU_WARNING_THRESHOLD
                )
                if alert:
                    new_alerts.append(alert)
            else:
                # 检查是否需要解除告警
                self._check_resolve_alert("host", host.id, AlertType.CPU_USAGE)
        
        # 内存使用率检查
        if 'memory_usage_percent' in metrics:
            memory_usage = metrics['memory_usage_percent']
            if memory_usage >= settings.HOST_MEMORY_CRITICAL_THRESHOLD:
                alert = self._create_or_update_alert(
                    source_type="host",
                    source_id=host.id,
                    source_name=host.name,
                    alert_type=AlertType.MEMORY_USAGE,
                    level=AlertLevel.CRITICAL,
                    message=f"主机 {host.name} 内存使用率过高: {memory_usage:.1f}%",
                    value=memory_usage,
                    threshold=settings.HOST_MEMORY_CRITICAL_THRESHOLD
                )
                if alert:
                    new_alerts.append(alert)
            elif memory_usage >= settings.HOST_MEMORY_WARNING_THRESHOLD:
                alert = self._create_or_update_alert(
                    source_type="host",
                    source_id=host.id,
                    source_name=host.name,
                    alert_type=AlertType.MEMORY_USAGE,
                    level=AlertLevel.WARNING,
                    message=f"主机 {host.name} 内存使用率较高: {memory_usage:.1f}%",
                    value=memory_usage,
                    threshold=settings.HOST_MEMORY_WARNING_THRESHOLD
                )
                if alert:
                    new_alerts.append(alert)
            else:
                # 检查是否需要解除告警
                self._check_resolve_alert("host", host.id, AlertType.MEMORY_USAGE)
        
        # 磁盘使用率检查
        if 'disk_usage_percent' in metrics:
            disk_usage = metrics['disk_usage_percent']
            if disk_usage >= settings.HOST_DISK_CRITICAL_THRESHOLD:
                alert = self._create_or_update_alert(
                    source_type="host",
                    source_id=host.id,
                    source_name=host.name,
                    alert_type=AlertType.DISK_USAGE,
                    level=AlertLevel.CRITICAL,
                    message=f"主机 {host.name} 磁盘使用率过高: {disk_usage:.1f}%",
                    value=disk_usage,
                    threshold=settings.HOST_DISK_CRITICAL_THRESHOLD
                )
                if alert:
                    new_alerts.append(alert)
            elif disk_usage >= settings.HOST_DISK_WARNING_THRESHOLD:
                alert = self._create_or_update_alert(
                    source_type="host",
                    source_id=host.id,
                    source_name=host.name,
                    alert_type=AlertType.DISK_USAGE,
                    level=AlertLevel.WARNING,
                    message=f"主机 {host.name} 磁盘使用率较高: {disk_usage:.1f}%",
                    value=disk_usage,
                    threshold=settings.HOST_DISK_WARNING_THRESHOLD
                )
                if alert:
                    new_alerts.append(alert)
            else:
                # 检查是否需要解除告警
                self._check_resolve_alert("host", host.id, AlertType.DISK_USAGE)
        
        # 网络使用率检查
        if 'network_tx_kbps' in metrics and 'network_rx_kbps' in metrics:
            total_network_kbps = metrics['network_tx_kbps'] + metrics['network_rx_kbps']
            if total_network_kbps >= settings.HOST_NETWORK_CRITICAL_THRESHOLD:
                alert = self._create_or_update_alert(
                    source_type="host",
                    source_id=host.id,
                    source_name=host.name,
                    alert_type=AlertType.NETWORK_USAGE,
                    level=AlertLevel.CRITICAL,
                    message=f"主机 {host.name} 网络流量过高: {total_network_kbps:.1f} KB/s",
                    value=total_network_kbps,
                    threshold=settings.HOST_NETWORK_CRITICAL_THRESHOLD
                )
                if alert:
                    new_alerts.append(alert)
            elif total_network_kbps >= settings.HOST_NETWORK_WARNING_THRESHOLD:
                alert = self._create_or_update_alert(
                    source_type="host",
                    source_id=host.id,
                    source_name=host.name,
                    alert_type=AlertType.NETWORK_USAGE,
                    level=AlertLevel.WARNING,
                    message=f"主机 {host.name} 网络流量较高: {total_network_kbps:.1f} KB/s",
                    value=total_network_kbps,
                    threshold=settings.HOST_NETWORK_WARNING_THRESHOLD
                )
                if alert:
                    new_alerts.append(alert)
            else:
                # 检查是否需要解除告警
                self._check_resolve_alert("host", host.id, AlertType.NETWORK_USAGE)
        
        # 主机连接状态检查
        if host.status == 'disconnected' or host.status == 'error':
            alert = self._create_or_update_alert(
                source_type="host",
                source_id=host.id,
                source_name=host.name,
                alert_type=AlertType.HOST_CONNECTION,
                level=AlertLevel.CRITICAL,
                message=f"主机 {host.name} 连接状态异常: {host.status}",
                value=0,
                threshold=1  # 简化阈值表示
            )
            if alert:
                new_alerts.append(alert)
        else:
            # 检查是否需要解除告警
            self._check_resolve_alert("host", host.id, AlertType.HOST_CONNECTION)
        
        return new_alerts
        
    def check_system_resources(self) -> List[Alert]:
        """检查监控系统自身的资源使用情况
        
        Returns:
            新创建的告警列表
        """
        new_alerts = []
        try:
            import psutil
            
            # 获取当前进程资源使用情况
            process = psutil.Process()
            with process.oneshot():
                # 检查CPU使用率
                cpu_percent = process.cpu_percent(interval=1.0)
                if cpu_percent >= settings.SYSTEM_CPU_WARNING_THRESHOLD:
                    alert = self._create_or_update_alert(
                        source_type="system",
                        source_id="monitoring_system",
                        source_name="监控系统",
                        alert_type=AlertType.CPU_USAGE,
                        level=AlertLevel.WARNING,
                        message=f"监控系统CPU使用率过高: {cpu_percent:.1f}%",
                        value=cpu_percent,
                        threshold=settings.SYSTEM_CPU_WARNING_THRESHOLD
                    )
                    if alert:
                        new_alerts.append(alert)
                else:
                    # 检查是否需要解除告警
                    self._check_resolve_alert("system", "monitoring_system", AlertType.CPU_USAGE)
                
                # 检查内存使用率
                memory_percent = process.memory_percent()
                if memory_percent >= settings.SYSTEM_MEMORY_WARNING_THRESHOLD:
                    alert = self._create_or_update_alert(
                        source_type="system",
                        source_id="monitoring_system",
                        source_name="监控系统",
                        alert_type=AlertType.MEMORY_USAGE,
                        level=AlertLevel.WARNING,
                        message=f"监控系统内存使用率过高: {memory_percent:.1f}%",
                        value=memory_percent,
                        threshold=settings.SYSTEM_MEMORY_WARNING_THRESHOLD
                    )
                    if alert:
                        new_alerts.append(alert)
                else:
                    # 检查是否需要解除告警
                    self._check_resolve_alert("system", "monitoring_system", AlertType.MEMORY_USAGE)
        
        except ImportError:
            logger.warning("psutil库未安装，无法监控系统资源")
        except Exception as e:
            logger.error(f"检查系统资源失败: {str(e)}")
        
        return new_alerts
    
    def check_vm_thresholds(self, vm: VirtualMachine, metrics: Dict[str, float]) -> List[Alert]:
        """检查虚拟机指标是否超过阈值
        
        Args:
            vm: 虚拟机对象
            metrics: 虚拟机指标
            
        Returns:
            新创建的告警列表
        """
        new_alerts = []
        
        # 虚拟机电源状态检查
        if vm.power_state != 'poweredOn' and vm.is_active:
            alert = self._create_or_update_alert(
                source_type="vm",
                source_id=vm.id,
                source_name=vm.name,
                alert_type=AlertType.VM_POWER,
                level=AlertLevel.WARNING if vm.power_state == 'suspended' else AlertLevel.CRITICAL,
                message=f"虚拟机 {vm.name} 电源状态异常: {vm.power_state}",
                value=0,
                threshold=1
            )
            if alert:
                new_alerts.append(alert)
        
        # 如果虚拟机已开启，检查性能指标
        if vm.power_state == 'poweredOn':
            # CPU使用率检查
            if 'cpu_usage_percent' in metrics:
                cpu_usage = metrics['cpu_usage_percent']
                if cpu_usage >= settings.VM_CPU_CRITICAL_THRESHOLD:
                    alert = self._create_or_update_alert(
                        source_type="vm",
                        source_id=vm.id,
                        source_name=vm.name,
                        alert_type=AlertType.CPU_USAGE,
                        level=AlertLevel.CRITICAL,
                        message=f"虚拟机 {vm.name} CPU使用率过高: {cpu_usage:.1f}%",
                        value=cpu_usage,
                        threshold=settings.VM_CPU_CRITICAL_THRESHOLD
                    )
                    if alert:
                        new_alerts.append(alert)
                elif cpu_usage >= settings.VM_CPU_WARNING_THRESHOLD:
                    alert = self._create_or_update_alert(
                        source_type="vm",
                        source_id=vm.id,
                        source_name=vm.name,
                        alert_type=AlertType.CPU_USAGE,
                        level=AlertLevel.WARNING,
                        message=f"虚拟机 {vm.name} CPU使用率较高: {cpu_usage:.1f}%",
                        value=cpu_usage,
                        threshold=settings.VM_CPU_WARNING_THRESHOLD
                    )
                    if alert:
                        new_alerts.append(alert)
                else:
                    # 检查是否需要解除告警
                    self._check_resolve_alert("vm", vm.id, AlertType.CPU_USAGE)
            
            # 内存使用率检查
            if 'memory_usage_percent' in metrics:
                memory_usage = metrics['memory_usage_percent']
                if memory_usage >= settings.VM_MEMORY_CRITICAL_THRESHOLD:
                    alert = self._create_or_update_alert(
                        source_type="vm",
                        source_id=vm.id,
                        source_name=vm.name,
                        alert_type=AlertType.MEMORY_USAGE,
                        level=AlertLevel.CRITICAL,
                        message=f"虚拟机 {vm.name} 内存使用率过高: {memory_usage:.1f}%",
                        value=memory_usage,
                        threshold=settings.VM_MEMORY_CRITICAL_THRESHOLD
                    )
                    if alert:
                        new_alerts.append(alert)
                elif memory_usage >= settings.VM_MEMORY_WARNING_THRESHOLD:
                    alert = self._create_or_update_alert(
                        source_type="vm",
                        source_id=vm.id,
                        source_name=vm.name,
                        alert_type=AlertType.MEMORY_USAGE,
                        level=AlertLevel.WARNING,
                        message=f"虚拟机 {vm.name} 内存使用率较高: {memory_usage:.1f}%",
                        value=memory_usage,
                        threshold=settings.VM_MEMORY_WARNING_THRESHOLD
                    )
                    if alert:
                        new_alerts.append(alert)
                else:
                    # 检查是否需要解除告警
                    self._check_resolve_alert("vm", vm.id, AlertType.MEMORY_USAGE)
            
            # 网络使用率检查
            if 'network_tx_kbps' in metrics and 'network_rx_kbps' in metrics:
                total_network_kbps = metrics['network_tx_kbps'] + metrics['network_rx_kbps']
                if total_network_kbps >= settings.VM_NETWORK_CRITICAL_THRESHOLD:
                    alert = self._create_or_update_alert(
                        source_type="vm",
                        source_id=vm.id,
                        source_name=vm.name,
                        alert_type=AlertType.NETWORK_USAGE,
                        level=AlertLevel.CRITICAL,
                        message=f"虚拟机 {vm.name} 网络流量过高: {total_network_kbps:.1f} KB/s",
                        value=total_network_kbps,
                        threshold=settings.VM_NETWORK_CRITICAL_THRESHOLD
                    )
                    if alert:
                        new_alerts.append(alert)
                elif total_network_kbps >= settings.VM_NETWORK_WARNING_THRESHOLD:
                    alert = self._create_or_update_alert(
                        source_type="vm",
                        source_id=vm.id,
                        source_name=vm.name,
                        alert_type=AlertType.NETWORK_USAGE,
                        level=AlertLevel.WARNING,
                        message=f"虚拟机 {vm.name} 网络流量较高: {total_network_kbps:.1f} KB/s",
                        value=total_network_kbps,
                        threshold=settings.VM_NETWORK_WARNING_THRESHOLD
                    )
                    if alert:
                        new_alerts.append(alert)
                else:
                    # 检查是否需要解除告警
                    self._check_resolve_alert("vm", vm.id, AlertType.NETWORK_USAGE)
        
        return new_alerts
    
    def _create_or_update_alert(self, **kwargs) -> Optional[Alert]:
        """创建或更新告警
        
        Args:
            kwargs: 告警属性
            
        Returns:
            创建的告警对象，如果不需要创建则返回None
        """
        alert_key = f"{kwargs['source_type']}:{kwargs['source_id']}:{kwargs['alert_type']}"
        
        # 检查是否需要创建告警（考虑冷却时间）
        if not self._should_create_alert(alert_key):
            return None
        
        try:
            with db_session() as db:
                # 查找是否存在相同的活跃告警
                existing_alert = db.query(Alert).filter(
                    Alert.source_type == kwargs['source_type'],
                    Alert.source_id == kwargs['source_id'],
                    Alert.alert_type == kwargs['alert_type'],
                    Alert.is_resolved == False
                ).first()
                
                if existing_alert:
                    # 更新现有告警
                    existing_alert.level = kwargs['level']
                    existing_alert.message = kwargs['message']
                    existing_alert.value = kwargs['value']
                    existing_alert.updated_at = datetime.utcnow()
                    existing_alert.occurrences += 1
                    
                    # 更新活跃告警缓存
                    self.active_alerts[alert_key] = existing_alert
                    db.commit()
                    return existing_alert
                else:
                    # 创建新告警
                    new_alert = Alert(
                        source_type=kwargs['source_type'],
                        source_id=kwargs['source_id'],
                        source_name=kwargs['source_name'],
                        alert_type=kwargs['alert_type'],
                        level=kwargs['level'],
                        message=kwargs['message'],
                        value=kwargs['value'],
                        threshold=kwargs['threshold'],
                        is_resolved=False,
                        occurrences=1,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    
                    db.add(new_alert)
                    db.commit()
                    
                    # 添加到活跃告警缓存
                    self.active_alerts[alert_key] = new_alert
                    
                    # 设置冷却时间
                    self._set_alert_cooldown(alert_key)
                    
                    # 发送告警通知
                    self._send_alert_notification(new_alert)
                    
                    return new_alert
        except Exception as e:
            logger.error(f"创建或更新告警失败: {str(e)}")
            return None
    
    def _check_resolve_alert(self, source_type: str, source_id: int, alert_type: AlertType):
        """检查是否需要解除告警
        
        Args:
            source_type: 源类型 (host/vm)
            source_id: 源ID
            alert_type: 告警类型
        """
        alert_key = f"{source_type}:{source_id}:{alert_type}"
        
        # 检查活跃告警中是否存在
        if alert_key in self.active_alerts:
            alert = self.active_alerts[alert_key]
            try:
                with db_session() as db:
                    # 从数据库中获取最新的告警
                    db_alert = db.query(Alert).filter(Alert.id == alert.id).first()
                    if db_alert and not db_alert.is_resolved:
                        # 解除告警
                        db_alert.is_resolved = True
                        db_alert.resolved_at = datetime.utcnow()
                        db.commit()
                        
                        # 从活跃告警缓存中移除
                        del self.active_alerts[alert_key]
                        
                        # 发送解除通知
                        self._send_resolution_notification(db_alert)
            except Exception as e:
                logger.error(f"解除告警失败: {str(e)}")
    
    def _send_alert_notification(self, alert: Alert):
        """发送告警通知
        
        Args:
            alert: 告警对象
        """
        # 根据配置决定通知方式
        if settings.ENABLE_EMAIL_NOTIFICATIONS:
            self._send_email_notification(alert)
        
        if settings.ENABLE_WEBHOOK_NOTIFICATIONS:
            self._send_webhook_notification(alert)
        
        # 记录通知发送
        logger.info(f"告警通知已发送: {alert.source_name} - {alert.message}")
    
    def _send_resolution_notification(self, alert: Alert):
        """发送告警解除通知
        
        Args:
            alert: 已解除的告警对象
        """
        # 构建解除通知消息
        resolution_message = f"告警已解除: {alert.source_name} - {alert.message}"
        
        # 根据配置决定通知方式
        if settings.ENABLE_EMAIL_NOTIFICATIONS:
            # 这里可以实现发送解除通知的逻辑
            pass
        
        if settings.ENABLE_WEBHOOK_NOTIFICATIONS:
            # 这里可以实现发送解除通知的逻辑
            pass
        
        logger.info(resolution_message)
    
    def _send_email_notification(self, alert: Alert):
        """发送邮件通知
        
        Args:
            alert: 告警对象
        """
        try:
            # 这里是邮件发送的示例实现
            # 实际使用时需要配置SMTP服务器
            logger.info(f"发送邮件通知: {alert.level} - {alert.message}")
            
            # 邮件发送逻辑可以在这里实现
            # import smtplib
            # from email.mime.text import MIMEText
            # 实现邮件发送代码
        except Exception as e:
            logger.error(f"发送邮件通知失败: {str(e)}")
    
    def _send_webhook_notification(self, alert: Alert):
        """发送Webhook通知，支持重试机制
        
        Args:
            alert: 告警对象
        """
        max_retries = getattr(settings, 'WEBHOOK_MAX_RETRIES', 3)
        retry_delay = getattr(settings, 'WEBHOOK_RETRY_DELAY', 2)  # 重试间隔（秒）
        
        for attempt in range(max_retries):
            try:
                import requests
                
                # 构建Webhook数据
                webhook_data = {
                    "event": "alert",
                    "level": alert.level,
                    "type": alert.alert_type,
                    "source": {
                        "type": alert.source_type,
                        "name": alert.source_name,
                        "id": alert.source_id
                    },
                    "message": alert.message,
                    "value": alert.value,
                    "threshold": alert.threshold,
                    "created_at": alert.created_at.isoformat()
                }
                
                # 发送Webhook请求
                response = requests.post(
                    settings.WEBHOOK_URL,
                    json=webhook_data,
                    headers={"Content-Type": "application/json"},
                    timeout=getattr(settings, 'WEBHOOK_TIMEOUT', 10)
                )
                
                response.raise_for_status()
                logger.info(f"Webhook通知已发送: {settings.WEBHOOK_URL} (尝试 {attempt + 1}/{max_retries})")
                return  # 成功发送后退出函数
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Webhook通知发送失败 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Webhook通知发送失败，已达到最大重试次数: {str(e)}")
            except Exception as e:
                logger.error(f"发送Webhook通知时发生未知错误: {str(e)}")
                break
    
    def check_all_alerts(self):
        """检查所有主机和虚拟机的告警"""
        logger.info("开始告警检查任务")
        new_alerts_count = 0
        
        try:
            with db_session() as db:
                # 检查所有主机
                hosts = db.query(ESXIHost).all()
                for host in hosts:
                    # 尝试从缓存获取主机指标
                    cache_key = f"host_metrics:{host.name}"
                    metrics_str = get_cache(cache_key)
                    
                    if metrics_str:
                        try:
                            import json
                            # 更健壮的缓存解析方式
                            try:
                                # 尝试直接解析
                                metrics = json.loads(metrics_str)
                            except json.JSONDecodeError:
                                # 如果直接解析失败，尝试清理字符串后再解析
                                cleaned_str = metrics_str.strip()
                                if cleaned_str.startswith('{') and cleaned_str.endswith('}'):
                                    # 替换单引号为双引号（但避免替换字符串内部的单引号）
                                    import re
                                    cleaned_str = re.sub(r"(?<!\\)'(?!\\)", '"', cleaned_str)
                                    metrics = json.loads(cleaned_str)
                                else:
                                    raise ValueError("缓存数据格式不正确，不是有效的JSON对象")
                            
                            # 转换指标值为浮点数
                            metrics = {k: float(v) if isinstance(v, str) and v.replace('.', '', 1).isdigit() else v for k, v in metrics.items()}
                            
                            # 检查告警阈值
                            new_alerts = self.check_host_thresholds(host, metrics)
                            new_alerts_count += len(new_alerts)
                        except Exception as e:
                            logger.error(f"解析主机 {host.name} 指标缓存失败: {str(e)}")
                            # 记录原始缓存内容用于调试（限制长度）
                            cache_sample = metrics_str[:200] + ('...' if len(metrics_str) > 200 else '')
                            logger.debug(f"原始缓存内容: {cache_sample}")
                    
                # 检查所有活跃的虚拟机
                vms = db.query(VirtualMachine).filter(VirtualMachine.is_active == True).all()
                for vm in vms:
                    # 获取主机信息
                    host = db.query(ESXIHost).filter(ESXIHost.id == vm.host_id).first()
                    if not host:
                        continue
                    
                    # 尝试从缓存获取虚拟机指标
                    cache_key = f"vm_metrics:{host.name}:{vm.vm_id}"
                    metrics_str = get_cache(cache_key)
                    
                    if metrics_str:
                        try:
                            import json
                            # 更健壮的缓存解析方式
                            try:
                                # 尝试直接解析
                                metrics = json.loads(metrics_str)
                            except json.JSONDecodeError:
                                # 如果直接解析失败，尝试清理字符串后再解析
                                cleaned_str = metrics_str.strip()
                                if cleaned_str.startswith('{') and cleaned_str.endswith('}'):
                                    # 替换单引号为双引号（但避免替换字符串内部的单引号）
                                    import re
                                    cleaned_str = re.sub(r"(?<!\\)'(?!\\)", '"', cleaned_str)
                                    metrics = json.loads(cleaned_str)
                                else:
                                    raise ValueError("缓存数据格式不正确，不是有效的JSON对象")
                            
                            # 转换指标值为浮点数
                            metrics = {k: float(v) if isinstance(v, str) and v.replace('.', '', 1).isdigit() else v for k, v in metrics.items()}
                            
                            # 检查告警阈值
                            new_alerts = self.check_vm_thresholds(vm, metrics)
                            new_alerts_count += len(new_alerts)
                        except Exception as e:
                            logger.error(f"解析虚拟机 {vm.name} 指标缓存失败: {str(e)}")
                            # 记录原始缓存内容用于调试（限制长度）
                            cache_sample = metrics_str[:200] + ('...' if len(metrics_str) > 200 else '')
                            logger.debug(f"原始缓存内容: {cache_sample}")
            
            logger.info(f"告警检查任务完成，新增告警 {new_alerts_count} 个")
        except Exception as e:
            logger.error(f"告警检查任务失败: {str(e)}")
    
    def get_active_alerts(self, limit: int = 100) -> List[Alert]:
        """获取活跃告警列表
        
        Args:
            limit: 返回的最大告警数量
            
        Returns:
            活跃告警列表
        """
        try:
            with db_session() as db:
                alerts = db.query(Alert).filter(
                    Alert.is_resolved == False
                ).order_by(
                    Alert.created_at.desc()
                ).limit(limit).all()
                
                # 更新活跃告警缓存
                for alert in alerts:
                    alert_key = self._generate_alert_key(alert)
                    self.active_alerts[alert_key] = alert
                
                return alerts
        except Exception as e:
            logger.error(f"获取活跃告警失败: {str(e)}")
            return []
    
    def get_recent_alerts(self, days: int = 7, limit: int = 100) -> List[Alert]:
        """获取最近的告警记录
        
        Args:
            days: 天数
            limit: 返回的最大告警数量
            
        Returns:
            最近的告警记录列表
        """
        try:
            with db_session() as db:
                start_date = datetime.utcnow() - timedelta(days=days)
                alerts = db.query(Alert).filter(
                    Alert.created_at >= start_date
                ).order_by(
                    Alert.created_at.desc()
                ).limit(limit).all()
                
                return alerts
        except Exception as e:
            logger.error(f"获取最近告警失败: {str(e)}")
            return []


# 创建全局告警管理器实例
alert_manager = AlertManager()