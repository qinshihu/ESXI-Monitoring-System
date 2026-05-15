import logging
import ssl
import time
from typing import Dict, Any, List, Optional, Tuple
from pyVim import connect
from pyVmomi import vim, vmodl
from datetime import datetime
import hashlib

from config import settings
from database import (
    db_session,
    ESXIHost,
    VirtualMachine,
    write_metrics,
    set_cache,
    get_cache
)

logger = logging.getLogger(__name__)


class ESXiCollector:
    """ESXI数据采集器"""
    
    def __init__(self, max_retries=3, retry_delay=2):
        """初始化采集器
        
        Args:
            max_retries: 最大重试次数
            retry_delay: 重试间隔时间（秒）
        """
        self.connections: Dict[str, Tuple[vim.ServiceInstance, float]] = {}
        self.max_connection_age = settings.ESXI_CONNECTION_REUSE
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        # 最大连接数限制，从配置或默认值获取
        self.max_connections = getattr(settings, 'ESXI_MAX_CONNECTIONS', 10)
        # 批量操作大小，优化内存使用
        self.batch_size = getattr(settings, 'COLLECTION_BATCH_SIZE', 5)
    
    def _get_connection(self, host_info: Dict[str, str]) -> Optional[vim.ServiceInstance]:
        """获取或创建ESXI连接，支持超时控制和更健壮的错误处理
        
        Args:
            host_info: 主机信息字典，包含name, ip, username, password, timeout等
            
        Returns:
            vim.ServiceInstance对象或None
        """
        import socket
        from pyVim.connect import Disconnect

        host = host_info.get('ip')
        user = host_info.get('username')
        password = host_info.get('password')
        port = host_info.get('port', 443)
        timeout = host_info.get('timeout', 30)  # 默认超时30秒
        host_name = host_info.get('name', host)
        
        # 使用更完整的连接键
        host_key = f"{host}:{port}:{user}"
        current_time = time.time()
        
        # 检查现有连接
        if host_key in self.connections:
            conn, created_time = self.connections[host_key]
            age = current_time - created_time
            # 如果连接未过期，直接返回
            if age < self.max_connection_age:
                try:
                    # 测试连接是否有效
                    content = conn.RetrieveContent()
                    logger.debug(f"重用缓存的连接到 {host_name} ({host}:{port})")
                    # 更新连接时间戳，实现LRU机制
                    self.connections[host_key] = (conn, current_time)
                    return conn
                except Exception as e:
                    logger.warning(f"连接无效，重新连接: {host_name}, 错误: {str(e)}")
            else:
                logger.info(f"连接已过期 ({age:.1f}秒 > {self.max_connection_age}秒)，重新连接: {host_name}")
                # 关闭过期连接
                try:
                    Disconnect(conn)
                except:
                    pass
                del self.connections[host_key]
        
        # 检查连接池大小，如果超过限制，清理最早的连接
        if len(self.connections) >= self.max_connections:
            # 找出最早创建的连接
            oldest_key = min(self.connections, key=lambda k: self.connections[k][1])
            oldest_conn, _ = self.connections[oldest_key]
            try:
                Disconnect(oldest_conn)
                logger.info(f"连接池达到最大限制，关闭最早的连接: {oldest_key}")
            except Exception as e:
                logger.warning(f"关闭旧连接失败: {str(e)}")
            finally:
                del self.connections[oldest_key]
        
        # 创建新连接
        try:
            logger.info(f"正在连接到ESXI主机: {host_name} ({host}:{port})")
            
            # 设置SSL上下文
            if hasattr(ssl, '_create_unverified_context'):
                context = ssl._create_unverified_context()
            else:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            
            # 使用超时参数连接主机
            original_connect = socket.socket.connect
            
            def connect_with_timeout(self, address):
                self.settimeout(timeout)
                return original_connect(self, address)
            
            # 临时替换socket连接方法以添加超时
            socket.socket.connect = connect_with_timeout
            
            try:
                # 连接主机
                conn = connect.SmartConnect(
                    host=host,
                    user=user,
                    pwd=password,
                    sslContext=context,
                    port=port
                )
                
                if not conn:
                    logger.error(f"无法连接到主机: {host_name} ({host}:{port})")
                    return None
                
                # 验证会话
                content = conn.RetrieveContent()
                if not content:
                    logger.error(f"连接到主机失败: {host_name}, 无法获取内容")
                    Disconnect(conn)
                    return None
                
                # 添加连接到连接池
                self.connections[host_key] = (conn, current_time)
                logger.info(f"成功连接到ESXI主机: {host_name}")
                return conn
                
            except socket.timeout:
                logger.error(f"连接超时: {host_name} ({host}:{port}), 超过 {timeout} 秒")
                return None
            except vim.fault.InvalidLogin:
                logger.error(f"登录失败: {host_name} ({host}:{port}), 用户名或密码错误")
                return None
            except vim.fault.HostConnectFault as e:
                logger.error(f"连接失败: {host_name} ({host}:{port}), 主机连接错误: {str(e)}")
                return None
            except ssl.SSLError as e:
                logger.error(f"SSL错误: {host_name} ({host}:{port}), 可能是证书问题: {str(e)}")
                return None
            finally:
                # 恢复原始的socket连接方法
                socket.socket.connect = original_connect
                
        except Exception as e:
            logger.error(f"连接ESXI主机失败: {host_name} ({host}:{port}), 错误: {str(e)}")
            return None
    
    def _disconnect_all(self):
        """断开所有ESXI连接"""
        for host_key, (conn, _) in self.connections.items():
            try:
                conn.Disconnect()
            except:
                pass
        self.connections.clear()
        logger.info("所有ESXI连接已断开")
    
    def collect_host_metrics(self, host: vim.HostSystem) -> Dict[str, float]:
        """收集主机指标
        
        Args:
            host: vim.HostSystem对象
            
        Returns:
            包含主机指标的字典
        """
        metrics = {}
        
        try:
            # CPU指标
            if hasattr(host, 'summary') and hasattr(host.summary, 'quickStats'):
                quick_stats = host.summary.quickStats
                if hasattr(quick_stats, 'overallCpuUsage') and hasattr(host.hardware, 'cpuInfo'):
                    total_cpu = host.hardware.cpuInfo.numCpuCores * host.hardware.cpuInfo.hz / 1000000  # MHz
                    used_cpu = quick_stats.overallCpuUsage  # MHz
                    metrics['cpu_usage_percent'] = (used_cpu / total_cpu) * 100 if total_cpu > 0 else 0
            
            # 内存指标
            if hasattr(host, 'summary') and hasattr(host.summary, 'quickStats'):
                quick_stats = host.summary.quickStats
                if hasattr(quick_stats, 'overallMemoryUsage') and hasattr(host.hardware, 'memorySize'):
                    total_memory_gb = host.hardware.memorySize / (1024 ** 3)
                    used_memory_mb = quick_stats.overallMemoryUsage
                    used_memory_gb = used_memory_mb / 1024
                    metrics['memory_usage_percent'] = (used_memory_gb / total_memory_gb) * 100 if total_memory_gb > 0 else 0
                    metrics['memory_total_gb'] = total_memory_gb
                    metrics['memory_used_gb'] = used_memory_gb
            
            # 网络指标
            if hasattr(host, 'summary') and hasattr(host.summary, 'quickStats'):
                quick_stats = host.summary.quickStats
                if hasattr(quick_stats, 'netTx') and hasattr(quick_stats, 'netRx'):
                    metrics['network_tx_kbps'] = quick_stats.netTx / 1024  # KB/s
                    metrics['network_rx_kbps'] = quick_stats.netRx / 1024  # KB/s
            
            # 磁盘指标
            if hasattr(host.config, 'storageDevice') and hasattr(host.config.storageDevice, 'scsiLuns'):
                total_space_gb = 0
                free_space_gb = 0
                
                for lun in host.config.storageDevice.scsiLuns:
                    if hasattr(lun, 'capacity') and hasattr(lun.capacity, 'blockSize') and hasattr(lun.capacity, 'block'):
                        total_space_gb += (lun.capacity.block * lun.capacity.blockSize) / (1024 ** 3)
                
                # 获取数据存储信息
                for datastore in host.datastore:
                    if hasattr(datastore.summary, 'capacity') and hasattr(datastore.summary, 'freeSpace'):
                        total_space_gb += datastore.summary.capacity / (1024 ** 3)
                        free_space_gb += datastore.summary.freeSpace / (1024 ** 3)
                
                if total_space_gb > 0:
                    metrics['disk_usage_percent'] = ((total_space_gb - free_space_gb) / total_space_gb) * 100
                    metrics['disk_total_gb'] = total_space_gb
                    metrics['disk_free_gb'] = free_space_gb
        
        except Exception as e:
            logger.error(f"收集主机指标失败: {str(e)}")
        
        return metrics
    
    def collect_vm_metrics(self, vm: vim.VirtualMachine) -> Dict[str, float]:
        """收集虚拟机指标
        
        Args:
            vm: vim.VirtualMachine对象
            
        Returns:
            包含虚拟机指标的字典
        """
        metrics = {}
        
        try:
            # 跳过模板
            if hasattr(vm, 'config') and hasattr(vm.config, 'template') and vm.config.template:
                return metrics
            
            # CPU指标
            if hasattr(vm, 'summary') and hasattr(vm.summary, 'quickStats'):
                quick_stats = vm.summary.quickStats
                if hasattr(quick_stats, 'overallCpuUsage') and hasattr(vm.config, 'hardware'):
                    num_cpu = vm.config.hardware.numCPU
                    used_cpu_mhz = quick_stats.overallCpuUsage
                    # 假设每个vCPU最大频率为2GHz（根据实际情况调整）
                    max_cpu_mhz = num_cpu * 2000
                    metrics['cpu_usage_percent'] = (used_cpu_mhz / max_cpu_mhz) * 100 if max_cpu_mhz > 0 else 0
                    metrics['cpu_usage_mhz'] = used_cpu_mhz
            
            # 内存指标
            if hasattr(vm, 'summary') and hasattr(vm.summary, 'quickStats') and hasattr(vm, 'config'):
                quick_stats = vm.summary.quickStats
                if hasattr(quick_stats, 'guestMemoryUsage') and hasattr(vm.config, 'hardware'):
                    total_memory_mb = vm.config.hardware.memoryMB
                    used_memory_mb = quick_stats.guestMemoryUsage
                    metrics['memory_usage_percent'] = (used_memory_mb / total_memory_mb) * 100 if total_memory_mb > 0 else 0
                    metrics['memory_total_mb'] = total_memory_mb
                    metrics['memory_used_mb'] = used_memory_mb
            
            # 磁盘指标
            if hasattr(vm, 'summary') and hasattr(vm.summary, 'storage'):
                storage = vm.summary.storage
                if hasattr(storage, 'committed') and hasattr(storage, 'unshared'):
                    metrics['disk_usage_gb'] = (storage.committed + storage.unshared) / (1024 ** 3)
            
            # 网络指标
            if hasattr(vm, 'summary') and hasattr(vm.summary, 'quickStats'):
                quick_stats = vm.summary.quickStats
                if hasattr(quick_stats, 'netTx') and hasattr(quick_stats, 'netRx'):
                    metrics['network_tx_kbps'] = quick_stats.netTx / 1024  # KB/s
                    metrics['network_rx_kbps'] = quick_stats.netRx / 1024  # KB/s
        
        except Exception as e:
            logger.error(f"收集虚拟机指标失败: {vm.name}, 错误: {str(e)}")
        
        return metrics
    
    def update_host_info(self, host_info: Dict[str, str], host: vim.HostSystem):
        """更新主机信息到数据库
        
        Args:
            host_info: 主机配置信息
            host: vim.HostSystem对象
        """
        try:
            with db_session() as db:
                # 查找或创建主机记录
                db_host = db.query(ESXIHost).filter(
                    (ESXIHost.name == host_info['name']) | (ESXIHost.ip_address == host_info['ip'])
                ).first()
                
                if not db_host:
                    db_host = ESXIHost(
                        name=host_info['name'],
                        ip_address=host_info['ip'],
                        username=host_info['username'],
                        password=host_info['password']
                    )
                    db.add(db_host)
                
                # 更新主机信息
                db_host.status = 'connected'
                db_host.last_seen = datetime.utcnow()
                
                # 更新硬件信息
                if hasattr(host, 'config') and hasattr(host.config, 'product'):
                    db_host.version = host.config.product.version
                    db_host.build = host.config.product.build
                
                if hasattr(host, 'hardware') and hasattr(host.hardware, 'cpuInfo'):
                    db_host.cpu_cores = host.hardware.cpuInfo.numCpuCores
                    db_host.cpu_sockets = host.hardware.cpuInfo.numCpuPackages
                
                if hasattr(host, 'hardware') and hasattr(host.hardware, 'memorySize'):
                    db_host.total_memory_gb = host.hardware.memorySize / (1024 ** 3)
                
                db.commit()
                logger.info(f"更新主机信息成功: {host_info['name']}")
        
        except Exception as e:
            logger.error(f"更新主机信息失败: {host_info['name']}, 错误: {str(e)}")
    
    def update_vm_info(self, host_id: int, vms: List[vim.VirtualMachine]):
        """更新虚拟机信息到数据库
        
        Args:
            host_id: 主机ID
            vms: 虚拟机列表
        """
        try:
            with db_session() as db:
                # 获取当前主机的所有虚拟机ID
                current_vm_ids = {vm.vm_id for vm in db.query(VirtualMachine).filter(VirtualMachine.host_id == host_id).all()}
                seen_vm_ids = set()
                
                for vm in vms:
                    # 跳过模板
                    if hasattr(vm, 'config') and hasattr(vm.config, 'template') and vm.config.template:
                        continue
                    
                    vm_moid = vm._moId
                    seen_vm_ids.add(vm_moid)
                    
                    # 查找或创建虚拟机记录
                    db_vm = db.query(VirtualMachine).filter(VirtualMachine.vm_id == vm_moid).first()
                    
                    if not db_vm:
                        db_vm = VirtualMachine(
                            vm_id=vm_moid,
                            host_id=host_id,
                        )
                        db.add(db_vm)
                    
                    # 更新虚拟机信息
                    db_vm.name = vm.name
                    db_vm.power_state = vm.runtime.powerState if hasattr(vm, 'runtime') and hasattr(vm.runtime, 'powerState') else 'unknown'
                    
                    if hasattr(vm, 'config'):
                        if hasattr(vm.config, 'guestFullName'):
                            db_vm.guest_os = vm.config.guestFullName
                        if hasattr(vm.config, 'hardware'):
                            db_vm.num_cpu = vm.config.hardware.numCPU
                            db_vm.memory_gb = vm.config.hardware.memoryMB / 1024
                    
                    if hasattr(vm, 'guest') and hasattr(vm.guest, 'ipAddress'):
                        db_vm.ip_address = vm.guest.ipAddress
                    
                    db_vm.is_active = True
                    db_vm.last_seen = datetime.utcnow()
                
                # 标记不再存在的虚拟机为非活动
                for vm_id in current_vm_ids - seen_vm_ids:
                    old_vm = db.query(VirtualMachine).filter(VirtualMachine.vm_id == vm_id).first()
                    if old_vm:
                        old_vm.is_active = False
                
                db.commit()
                logger.info(f"更新虚拟机信息成功，主机ID: {host_id}, 虚拟机数量: {len(seen_vm_ids)}")
        
        except Exception as e:
            logger.error(f"更新虚拟机信息失败，主机ID: {host_id}, 错误: {str(e)}")
    
    def disconnect(self, host_name: str):
        """断开指定主机的连接
        
        Args:
            host_name: 主机名称
        """
        try:
            # 遍历连接池，查找匹配的主机连接
            for host_key, (conn, _) in list(self.connections.items()):
                if host_name in host_key:
                    try:
                        conn.Disconnect()
                        del self.connections[host_key]
                        logger.info(f"成功断开主机连接: {host_name}")
                    except Exception as e:
                        logger.warning(f"断开主机连接失败: {host_name}, 错误: {str(e)}")
        except Exception as e:
            logger.error(f"处理主机断开连接时出错: {host_name}, 错误: {str(e)}")

    def _get_esxi_hosts(self) -> list:
        """获取所有ESXi主机配置，包括数据库和配置文件中的主机
        
        Returns:
            ESXi主机配置列表，去重且格式统一
        """
        all_hosts = []
        seen_identifiers = set()  # 用于去重的标识符集合
        
        try:
            # 从配置文件获取主机
            if hasattr(settings, 'esxi_hosts_list') and settings.esxi_hosts_list:
                for host_info in settings.esxi_hosts_list:
                    # 验证必要字段
                    if not all(k in host_info for k in ['ip', 'username', 'password']):
                        logger.warning(f"配置文件中的主机信息不完整，跳过: {host_info}")
                        continue
                    
                    # 统一格式
                    host_config = {
                        'name': host_info.get('name', host_info['ip']),
                        'ip': host_info['ip'],
                        'username': host_info['username'],
                        'password': host_info['password'],
                        'port': host_info.get('port', 443)
                    }
                    
                    # 生成唯一标识符（IP和端口组合）
                    identifier = f"{host_config['ip']}:{host_config['port']}"
                    if identifier not in seen_identifiers:
                        seen_identifiers.add(identifier)
                        all_hosts.append(host_config)
                        logger.debug(f"从配置文件添加主机: {host_config['name']} ({host_config['ip']}:{host_config['port']})")
            else:
                logger.debug("配置文件中没有定义ESXi主机")
            
            # 从数据库获取已注册的主机
            with db_session() as db:
                db_hosts = db.query(ESXIHost).all()
                for host in db_hosts:
                    # 检查主机是否已在列表中
                    identifier = f"{host.ip_address}:{host.port or 443}"
                    if identifier not in seen_identifiers:
                        # 尝试从配置获取凭证，如果没有则使用默认值
                        host_config = {
                            'id': host.id,
                            'name': host.name,
                            'ip': host.ip_address,
                            'username': getattr(settings, 'ESXI_DEFAULT_USERNAME', 'root'),
                            'password': getattr(settings, 'ESXI_DEFAULT_PASSWORD', ''),
                            'port': host.port or 443
                        }
                        
                        # 从配置中查找可能存在的凭证
                        if hasattr(settings, 'esxi_hosts_list'):
                            for config_host in settings.esxi_hosts_list:
                                if config_host.get('ip') == host.ip_address:
                                    host_config['username'] = config_host.get('username', host_config['username'])
                                    host_config['password'] = config_host.get('password', host_config['password'])
                                    break
                        
                        seen_identifiers.add(identifier)
                        all_hosts.append(host_config)
                        logger.debug(f"从数据库添加主机: {host.name} ({host.ip_address}:{host.port or 443})")
        
        except Exception as e:
            logger.error(f"获取ESXi主机列表时出错: {str(e)}")
        
        logger.debug(f"总共获取到 {len(all_hosts)} 台ESXi主机")
        return all_hosts
    
    def collect_all(self) -> int:
        """采集所有ESXi主机的数据
        
        Returns:
            成功采集的主机数量
        """
        logger.info("开始执行数据采集任务")
        collected_hosts = 0
        failed_hosts = 0
        
        # 获取所有主机配置
        esxi_hosts = self._get_esxi_hosts()
        total_hosts = len(esxi_hosts)
        
        if not esxi_hosts:
            logger.warning("没有配置ESXi主机，跳过数据采集")
            return 0
        
        logger.info(f"开始采集 {total_hosts} 台ESXi主机数据，批量大小: {self.batch_size}")
        
        # 实现批量处理，优化内存使用和性能
        for i in range(0, len(esxi_hosts), self.batch_size):
            batch_hosts = esxi_hosts[i:i + self.batch_size]
            logger.debug(f"处理主机批次: {i+1}-{min(i+self.batch_size, total_hosts)} / {total_hosts}")
            
            # 处理当前批次的主机
            for host_info in batch_hosts:
                host_ip = host_info.get('ip', 'unknown')
                retry_count = 0
                success = False
                last_error = None
                
                # 添加超时参数
                host_info['timeout'] = getattr(settings, 'ESXI_CONNECTION_TIMEOUT', 30)
                
                # 重试机制
                while retry_count < self.max_retries and not success:
                    retry_count += 1
                    try:
                        # 获取连接
                        conn = self._get_connection(host_info)
                        if not conn:
                            last_error = "无法建立连接"
                            logger.warning(f"无法连接到主机 {host_info['name']} (尝试 {retry_count}/{self.max_retries})")
                            if retry_count < self.max_retries:
                                time.sleep(self.retry_delay)
                            continue
                        
                        # 获取内容
                        content = conn.RetrieveContent()
                        root_folder = content.rootFolder
                        view_manager = content.viewManager
                        container_view = view_manager.CreateContainerView(
                            container=root_folder,
                            type=[vim.HostSystem],
                            recursive=True
                        )
                        
                        hosts = container_view.view
                        container_view.Destroy()
                        
                        for host in hosts:
                            # 采集主机指标
                            host_metrics = self.collect_host_metrics(host)
                            if host_metrics:
                                # 写入InfluxDB
                                write_metrics(
                                    bucket=settings.INFLUXDB_BUCKET,
                                    host_name=host_info['name'],
                                    metrics=host_metrics,
                                    tags={'type': 'host'}
                                )
                                
                                # 缓存主机指标
                                cache_key = f"host_metrics:{host_info['name']}"
                                set_cache(cache_key, str(host_metrics), expire=60)
                            
                            # 更新主机信息
                            self.update_host_info(host_info, host)
                            
                            # 获取主机ID
                            with db_session() as db:
                                db_host = db.query(ESXIHost).filter(ESXIHost.name == host_info['name']).first()
                                host_id = db_host.id if db_host else None
                            
                            # 采集虚拟机指标
                            if host_id and hasattr(host, 'vm'):
                                for vm in host.vm:
                                    vm_metrics = self.collect_vm_metrics(vm)
                                    if vm_metrics:
                                        # 写入InfluxDB
                                        write_metrics(
                                            bucket=settings.INFLUXDB_BUCKET,
                                            host_name=host_info['name'],
                                            metrics=vm_metrics,
                                            tags={
                                                'type': 'vm',
                                                'vm_name': vm.name,
                                                'vm_id': vm._moId
                                            }
                                        )
                                        
                                        # 缓存虚拟机指标
                                        cache_key = f"vm_metrics:{host_info['name']}:{vm._moId}"
                                        set_cache(cache_key, str(vm_metrics), expire=60)
                                
                                # 更新虚拟机信息
                                self.update_vm_info(host_id, host.vm)
                            
                            collected_hosts += 1
                            success = True
                            logger.info(f"成功采集主机 {host_info['name']} 数据")
                            
                            # 更新主机状态为连接成功
                            with db_session() as db:
                                host = db.query(ESXIHost).filter(
                                    (ESXIHost.ip_address == host_ip) | 
                                    (ESXIHost.name == host_info.get('name'))
                                ).first()
                                if host:
                                    host.status = "connected"
                                    host.last_seen = datetime.utcnow()
                                    db.commit()
                    except Exception as e:
                        last_error = str(e)
                        error_msg = f"采集主机 {host_info['name']} 数据失败 (尝试 {retry_count}/{self.max_retries}): {str(e)}"
                        
                        if retry_count < self.max_retries:
                            logger.warning(error_msg + f"，将在 {self.retry_delay} 秒后重试")
                            time.sleep(self.retry_delay)
                        else:
                            logger.error(error_msg)
                            failed_hosts += 1
                    
                    # 如果所有重试都失败，更新主机状态
                    if not success and retry_count >= self.max_retries:
                        with db_session() as db:
                            db_host = db.query(ESXIHost).filter(
                                (ESXIHost.name == host_info['name']) | (ESXIHost.ip_address == host_info['ip'])
                            ).first()
                            if db_host:
                                db_host.status = 'disconnected'
                                try:
                                    db_host.status_message = f"连接失败: {last_error}"
                                except:
                                    pass
                                db.commit()
                                logger.error(f"已将主机 {host_info['name']} 标记为断开连接")
        
        logger.info(f"数据采集任务完成 - 成功: {collected_hosts} 台, 失败: {failed_hosts} 台, 总共: {total_hosts} 台")
        return collected_hosts
    
    def __del__(self):
        """析构函数，断开所有连接"""
        self._disconnect_all()


# 创建全局采集器实例
esxi_collector = ESXiCollector()