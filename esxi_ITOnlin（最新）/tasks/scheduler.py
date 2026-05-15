import logging
import threading
import time
import os
import signal
import traceback
from datetime import datetime
from typing import Dict, List, Optional, Set, Any, Union

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.executors.pool import ThreadPoolExecutor

from config import settings
from collectors.esxi_collector import ESXiCollector
from alerts.alert_manager import alert_manager
from database import db_session, ESXIHost, VirtualMachine, Alert

logger = logging.getLogger(__name__)


class TaskScheduler:
    """任务调度器"""
    
    def __init__(self):
        """初始化任务调度器"""
        # 检测容器化环境
        self._in_container = (
            getattr(settings, "CONTAINERIZED", False) or
            os.environ.get("CONTAINERIZED") == "true" or
            os.environ.get("ENVIRONMENT") == "production" or
            (os.path.exists("/proc/1/cgroup") and "docker" in open("/proc/1/cgroup", "r").read())
        )
        
        # 根据环境调整工作线程数
        workers = settings.SCHEDULER_WORKERS
        if self._in_container:
            # 在容器环境中，减少默认线程数以避免资源竞争
            workers = max(2, min(workers, 4))  # 容器环境限制在2-4个工作线程
            logger.info(f"容器环境中调整工作线程数为: {workers}")
        
        # 创建线程池执行器
        executors = {
            'default': ThreadPoolExecutor(max_workers=workers)
        }
        
        # 配置调度器
        self.scheduler = BackgroundScheduler(
            executors=executors,
            job_defaults={
                'coalesce': True,
                'max_instances': 1,
                'misfire_grace_time': 60 if self._in_container else 30  # 容器环境增加容错时间
            }
        )
        
        # 初始化ESXi采集器
        self.esxi_collector = ESXiCollector()
        
        # 任务状态跟踪
        self.running_tasks: Set[str] = set()
        self.task_locks: Dict[str, threading.RLock] = {
            'data_collection': threading.RLock(),
            'system_maintenance': threading.RLock(),
            'alert_check': threading.RLock()
        }
        
        # 任务超时控制
        self.task_timeouts: Dict[str, int] = {
            'data_collection': 300,  # 5分钟
            'alert_check': 120,      # 2分钟
            'system_maintenance': 600  # 10分钟
        }
        
        # 任务超时时间戳
        self.task_start_times: Dict[str, float] = {}
        
        # 任务统计信息
        self.task_stats: Dict[str, Dict] = {
            'data_collection': {
                'last_run': None,
                'last_success': None,
                'last_error': None,
                'run_count': 0,
                'error_count': 0
            },
            'system_maintenance': {
                'last_run': None,
                'last_success': None,
                'last_error': None,
                'run_count': 0,
                'error_count': 0
            },
            'alert_check': {
                'last_run': None,
                'last_success': None,
                'last_error': None,
                'run_count': 0,
                'error_count': 0
            }
        }
    
    def start(self):
        """启动任务调度器"""
        try:
            # 根据容器化环境调整任务间隔
            collection_interval = settings.DATA_COLLECTION_INTERVAL
            alert_interval = settings.ALERT_CHECK_INTERVAL
            
            if self._in_container:
                # 容器环境中稍微延长任务间隔，避免资源竞争
                collection_interval = max(collection_interval, 60)  # 至少60秒
                alert_interval = max(alert_interval, 30)  # 至少30秒
                logger.info(f"容器环境中调整任务间隔 - 数据采集: {collection_interval}s, 告警检查: {alert_interval}s")
            
            # 添加数据采集任务
            self.scheduler.add_job(
                func=self._data_collection_task,
                trigger=IntervalTrigger(seconds=collection_interval),
                id='data_collection',
                name='ESXi数据采集',
                replace_existing=True,
                max_instances=1
            )
            
            # 添加告警检查任务
            self.scheduler.add_job(
                func=self._alert_check_task,
                trigger=IntervalTrigger(seconds=alert_interval),
                id='alert_check',
                name='告警阈值检查',
                replace_existing=True,
                max_instances=1
            )
            
            # 添加系统维护任务
            self.scheduler.add_job(
                func=self._system_maintenance_task,
                trigger=CronTrigger(minute=0),  # 每小时执行一次
                id='system_maintenance',
                name='系统维护',
                replace_existing=True,
                max_instances=1
            )
            
            # 启动调度器
            self.scheduler.start()
            logger.info(f"任务调度器启动成功 - 容器环境: {self._in_container}")
            
            # 启动任务超时检查线程
            self._start_timeout_checker()
            
            return True
        except Exception as e:
            logger.error(f"启动任务调度器失败: {str(e)}", exc_info=True)
            return False
    
    def _start_timeout_checker(self):
        """启动任务超时检查线程"""
        def timeout_checker():
            while True:
                try:
                    current_time = time.time()
                    for task_id, start_time in list(self.task_start_times.items()):
                        if task_id in self.task_locks and task_id in self.task_timeouts:
                            if current_time - start_time > self.task_timeouts[task_id]:
                                logger.warning(f"任务 {task_id} 执行超时，可能存在问题")
                except Exception as e:
                    logger.error(f"任务超时检查失败: {str(e)}")
                time.sleep(30)  # 每30秒检查一次
        
        # 启动超时检查线程
        self._timeout_thread = threading.Thread(target=timeout_checker, daemon=True)
        self._timeout_thread.start()
        logger.debug("任务超时检查线程已启动")
    
    def stop(self):
        """停止任务调度器（容器友好的停止方法）"""
        try:
            logger.info("开始停止任务调度器...")
            
            # 先暂停所有任务，防止新任务开始
            for job in self.scheduler.get_jobs():
                try:
                    self.scheduler.pause_job(job.id)
                    logger.debug(f"已暂停任务: {job.id}")
                except Exception as pause_e:
                    logger.warning(f"暂停任务 {job.id} 失败: {str(pause_e)}")
            
            # 等待正在运行的任务完成，但设置最大等待时间
            max_wait_time = 30  # 最大等待30秒
            wait_start = time.time()
            
            while self.running_tasks and time.time() - wait_start < max_wait_time:
                logger.info(f"等待 {len(self.running_tasks)} 个正在运行的任务完成...")
                time.sleep(2)
            
            # 强制停止调度器
            if self.scheduler.running:
                # 在容器环境中，使用较短的等待时间，避免容器停止超时
                wait = not self._in_container  # 非容器环境等待任务完成，容器环境不等待
                self.scheduler.shutdown(wait=wait)
                logger.info(f"任务调度器已停止 (等待完成: {wait})")
            
            # 清空任务状态
            self.running_tasks.clear()
            self.task_start_times.clear()
            
            logger.info("任务调度器停止完成")
            return True
        except Exception as e:
            logger.error(f"停止任务调度器失败: {str(e)}", exc_info=True)
            return False
    
    def pause_job(self, job_id: str) -> bool:
        """暂停指定任务
        
        Args:
            job_id: 任务ID
            
        Returns:
            是否成功暂停
        """
        try:
            self.scheduler.pause_job(job_id)
            logger.info(f"任务 {job_id} 已暂停")
            return True
        except Exception as e:
            logger.error(f"暂停任务 {job_id} 失败: {str(e)}")
            return False
    
    def resume_job(self, job_id: str) -> bool:
        """恢复指定任务
        
        Args:
            job_id: 任务ID
            
        Returns:
            是否成功恢复
        """
        try:
            self.scheduler.resume_job(job_id)
            logger.info(f"任务 {job_id} 已恢复")
            return True
        except Exception as e:
            logger.error(f"恢复任务 {job_id} 失败: {str(e)}")
            return False
    
    def trigger_job(self, job_id: str) -> bool:
        """立即触发指定任务
        
        Args:
            job_id: 任务ID
            
        Returns:
            是否成功触发
        """
        try:
            self.scheduler.trigger_job(job_id)
            logger.info(f"任务 {job_id} 已立即触发")
            return True
        except Exception as e:
            logger.error(f"立即触发任务 {job_id} 失败: {str(e)}")
            return False
    
    def get_job_status(self, job_id: str) -> Optional[Dict]:
        """获取任务状态
        
        Args:
            job_id: 任务ID
            
        Returns:
            任务状态信息
        """
        job = self.scheduler.get_job(job_id)
        if not job:
            return None
        
        return {
            'id': job.id,
            'name': job.name,
            'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
            'trigger': str(job.trigger),
            'misfire_grace_time': job.misfire_grace_time,
            'coalesce': job.coalesce,
            'max_instances': job.max_instances,
            'is_paused': self.scheduler.get_job(job_id).next_run_time is None,
            'is_running': job_id in self.running_tasks,
            'stats': self.task_stats.get(job_id, {})
        }
    
    def get_all_jobs(self) -> List[Dict]:
        """获取所有任务信息
        
        Returns:
            所有任务的状态信息列表
        """
        jobs = []
        for job in self.scheduler.get_jobs():
            job_info = {
                'id': job.id,
                'name': job.name,
                'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger),
                'misfire_grace_time': job.misfire_grace_time,
                'coalesce': job.coalesce,
                'max_instances': job.max_instances,
                'is_paused': job.next_run_time is None,
                'is_running': job.id in self.running_tasks,
                'stats': self.task_stats.get(job.id, {})
            }
            jobs.append(job_info)
        return jobs
    
    def _data_collection_task(self):
        """数据采集任务"""
        task_id = 'data_collection'
        
        # 使用锁确保任务不会并发执行
        if not self.task_locks[task_id].acquire(blocking=False):
            logger.warning(f"任务 {task_id} 仍在运行，跳过本次执行")
            return
        
        try:
            # 更新任务状态
            self.running_tasks.add(task_id)
            self.task_start_times[task_id] = time.time()
            self.task_stats[task_id]['last_run'] = datetime.utcnow()
            self.task_stats[task_id]['run_count'] += 1
            
            logger.info("开始执行数据采集任务")
            
            # 在容器环境中，限制单次采集的主机数量，避免资源占用过高
            if hasattr(self.esxi_collector, 'batch_size'):
                original_batch_size = self.esxi_collector.batch_size
                if self._in_container:
                    # 容器环境中减小批处理大小
                    self.esxi_collector.batch_size = max(2, min(original_batch_size, 4))
                    logger.debug(f"容器环境中调整批处理大小为: {self.esxi_collector.batch_size}")
            
            # 使用esxi_collector的collect_all方法执行所有采集工作
            collected_hosts = self.esxi_collector.collect_all()
            
            # 恢复原始批处理大小
            if hasattr(self.esxi_collector, 'batch_size'):
                self.esxi_collector.batch_size = original_batch_size
            
            # 标记长时间未更新的虚拟机为非活跃
            try:
                with db_session() as db:
                    from datetime import timedelta
                    inactive_threshold = datetime.utcnow() - timedelta(minutes=settings.VM_INACTIVE_THRESHOLD)
                    inactive_vms = db.query(VirtualMachine).filter(
                        VirtualMachine.is_active == True,
                        VirtualMachine.last_seen < inactive_threshold
                    ).all()
                    
                    for vm in inactive_vms:
                        vm.is_active = False
                        logger.info(f"标记虚拟机 {vm.name} 为非活跃状态")
                    
                    # 提交数据库更改
                    db.commit()
            except Exception as db_e:
                logger.error(f"更新虚拟机状态失败: {str(db_e)}")
            
            logger.info(f"数据采集任务执行完成，成功采集 {collected_hosts} 台主机数据")
            
            # 更新任务统计
            self.task_stats[task_id]['last_success'] = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"数据采集任务执行失败: {str(e)}", exc_info=True)
            self.task_stats[task_id]['last_error'] = datetime.utcnow()
            self.task_stats[task_id]['error_count'] += 1
            
            # 在容器环境中，减少错误时的详细日志以避免日志膨胀
            if not self._in_container:
                logger.debug(f"数据采集任务异常详情: {traceback.format_exc()}")
        finally:
            # 清理任务状态
            if task_id in self.running_tasks:
                self.running_tasks.remove(task_id)
            if task_id in self.task_start_times:
                del self.task_start_times[task_id]
            self.task_locks[task_id].release()
    
    def _alert_check_task(self):
        """告警检查任务"""
        task_id = 'alert_check'
        
        # 使用锁确保任务不会并发执行
        if not self.task_locks[task_id].acquire(blocking=False):
            logger.warning(f"任务 {task_id} 仍在运行，跳过本次执行")
            return
        
        try:
            # 更新任务状态
            self.running_tasks.add(task_id)
            self.task_stats[task_id]['last_run'] = datetime.utcnow()
            self.task_stats[task_id]['run_count'] += 1
            
            logger.info("开始执行告警检查任务")
            
            # 使用告警管理器检查所有告警
            alert_manager.check_all_alerts()
            
            # 调用系统资源检查功能
            logger.info("执行系统资源检查")
            self._check_system_resources()
            
            logger.info("告警检查任务执行完成")
            
            # 更新任务统计
            self.task_stats[task_id]['last_success'] = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"告警检查任务执行失败: {str(e)}")
            self.task_stats[task_id]['last_error'] = datetime.utcnow()
            self.task_stats[task_id]['error_count'] += 1
        finally:
            # 清理任务状态
            if task_id in self.running_tasks:
                self.running_tasks.remove(task_id)
            self.task_locks[task_id].release()
    
    def _system_maintenance_task(self):
        """系统维护任务"""
        task_id = 'system_maintenance'
        
        # 使用锁确保任务不会并发执行
        if not self.task_locks[task_id].acquire(blocking=False):
            logger.warning(f"任务 {task_id} 仍在运行，跳过本次执行")
            return
        
        try:
            # 更新任务状态
            self.running_tasks.add(task_id)
            self.task_stats[task_id]['last_run'] = datetime.utcnow()
            self.task_stats[task_id]['run_count'] += 1
            
            logger.info("开始执行系统维护任务")
            
            # 执行数据库清理
            self._cleanup_database()
            
            # 执行缓存清理
            self._cleanup_cache()
            
            # 检查系统资源
            self._check_system_resources()
            
            logger.info("系统维护任务执行完成")
            
            # 更新任务统计
            self.task_stats[task_id]['last_success'] = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"系统维护任务执行失败: {str(e)}")
            self.task_stats[task_id]['last_error'] = datetime.utcnow()
            self.task_stats[task_id]['error_count'] += 1
        finally:
            # 清理任务状态
            if task_id in self.running_tasks:
                self.running_tasks.remove(task_id)
            self.task_locks[task_id].release()
    
    def _cleanup_database(self):
        """增强版数据库清理，清理过期告警、僵尸虚拟机和历史数据"""
        try:
            logger.info("开始执行增强版数据库清理任务")
            from datetime import timedelta
            
            with db_session() as db:
                # 获取配置的保留天数
                alert_retention_days = getattr(settings, 'ALERT_RETENTION_DAYS', 30)
                vm_retention_days = getattr(settings, 'VM_RETENTION_DAYS', 7)  # 僵尸虚拟机保留天数
                
                # 1. 清理过期告警记录
                cutoff_date = datetime.utcnow() - timedelta(days=alert_retention_days)
                
                # 删除已解决的旧告警
                deleted_alerts = db.query(Alert).filter(
                    Alert.is_resolved == True,
                    Alert.created_at < cutoff_date
                ).delete(synchronize_session=False)
                
                logger.info(f"已清理 {deleted_alerts} 条过期告警记录")
                
                # 2. 清理长时间未更新的僵尸虚拟机记录
                vm_cutoff_date = datetime.utcnow() - timedelta(days=vm_retention_days)
                deleted_vms = db.query(VirtualMachine).filter(
                    VirtualMachine.last_seen < vm_cutoff_date
                ).delete(synchronize_session=False)
                
                if deleted_vms > 0:
                    logger.warning(f"已清理 {deleted_vms} 条僵尸虚拟机记录（超过{vm_retention_days}天未更新）")
                
                # 3. 清理长时间未连接的主机记录（如果超过配置的保留期）
                host_retention_days = getattr(settings, 'HOST_RETENTION_DAYS', 14)
                host_cutoff_date = datetime.utcnow() - timedelta(days=host_retention_days)
                
                # 先查找这些主机，然后更新状态为"abandoned"而不是直接删除
                abandoned_hosts = db.query(ESXIHost).filter(
                    ESXIHost.last_seen < host_cutoff_date
                ).all()
                
                for host in abandoned_hosts:
                    host.status = "abandoned"
                    host.status_message = f"超过{host_retention_days}天未连接"
                
                if abandoned_hosts:
                    logger.warning(f"已将 {len(abandoned_hosts)} 台长时间未连接的主机标记为废弃状态")
                
                db.commit()
                logger.info("数据库清理任务完成")
                
        except Exception as e:
            logger.error(f"清理数据库失败: {str(e)}")
            # 尝试创建一个数据库清理失败的告警
            try:
                from alerts.alert_manager import AlertType
                alert_manager.create_alert(
                    source_type="system",
                    source_id="database",
                    source_name="数据库",
                    alert_type=AlertType.SYSTEM_CPU_HIGH,  # 使用系统类型告警
                    level="error",
                    message=f"数据库清理任务失败: {str(e)}"
                )
            except:
                pass
    
    def _cleanup_cache(self):
        """清理过期缓存"""
        try:
            # 这里可以实现清理Redis缓存的逻辑
            # 例如删除过期的指标缓存等
            logger.info("缓存清理完成")
        except Exception as e:
            logger.error(f"清理缓存失败: {str(e)}")
    
    def _check_system_resources(self):
        """检查系统资源使用情况并创建具体的资源类型告警（容器化环境适配）"""
        from alerts.alert_manager import AlertType
        
        try:
            import psutil
            
            # 获取系统资源信息
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            # 在容器环境中，使用适当的磁盘挂载点
            disk_path = '/'  # 默认路径
            if self._in_container:
                # 检查容器挂载卷的磁盘使用情况
                if os.path.exists('/app'):
                    disk_path = '/app'  # 应用目录，通常在容器中是一个挂载卷
                logger.debug(f"容器环境中使用磁盘路径: {disk_path}")
            
            disk = psutil.disk_usage(disk_path)
            
            # 记录系统资源使用情况
            logger.info(f"系统资源使用情况 - CPU: {cpu_percent}%, 内存: {memory.percent}%, 磁盘({disk_path}): {disk.percent}%")
            
            # 获取告警阈值配置
            cpu_threshold = getattr(settings, 'SYSTEM_CPU_WARNING_THRESHOLD', 80)
            memory_threshold = getattr(settings, 'SYSTEM_MEMORY_WARNING_THRESHOLD', 85)
            disk_threshold = getattr(settings, 'SYSTEM_DISK_WARNING_THRESHOLD', 90)
            
            # 使用alert_manager创建CPU告警
            if cpu_percent > cpu_threshold:
                warning_message = f"系统CPU使用率过高: {cpu_percent}% (阈值: {cpu_threshold}%)"
                logger.warning(warning_message)
                alert_manager.create_alert(
                    source_type="system",
                    source_id="host_system",
                    source_name="系统",
                    alert_type=AlertType.SYSTEM_CPU_HIGH,
                    level="warning",
                    message=warning_message,
                    value=cpu_percent,
                    threshold=cpu_threshold
                )
            else:
                # 如果使用率恢复正常，解除告警
                alert_manager.resolve_alert(
                    source_type="system",
                    source_id="host_system",
                    alert_type=AlertType.SYSTEM_CPU_HIGH
                )
            
            # 使用alert_manager创建内存告警
            if memory.percent > memory_threshold:
                warning_message = f"系统内存使用率过高: {memory.percent}% (阈值: {memory_threshold}%), "
                warning_message += f"可用: {memory.available / 1024 / 1024:.1f} MB, "
                warning_message += f"总计: {memory.total / 1024 / 1024:.1f} MB"
                logger.warning(warning_message)
                alert_manager.create_alert(
                    source_type="system",
                    source_id="host_system",
                    source_name="系统",
                    alert_type=AlertType.SYSTEM_MEMORY_HIGH,
                    level="warning",
                    message=warning_message,
                    value=memory.percent,
                    threshold=memory_threshold
                )
            else:
                # 如果使用率恢复正常，解除告警
                alert_manager.resolve_alert(
                    source_type="system",
                    source_id="host_system",
                    alert_type=AlertType.SYSTEM_MEMORY_HIGH
                )
            
            # 使用alert_manager创建磁盘告警
            if disk.percent > disk_threshold:
                warning_message = f"系统磁盘使用率过高: {disk.percent}% (阈值: {disk_threshold}%), "
                warning_message += f"可用: {disk.free / 1024 / 1024 / 1024:.1f} GB, "
                warning_message += f"总计: {disk.total / 1024 / 1024 / 1024:.1f} GB"
                logger.warning(warning_message)
                alert_manager.create_alert(
                    source_type="system",
                    source_id="host_system",
                    source_name="系统",
                    alert_type=AlertType.SYSTEM_DISK_HIGH,
                    level="warning",
                    message=warning_message,
                    value=disk.percent,
                    threshold=disk_threshold
                )
            else:
                # 如果使用率恢复正常，解除告警
                alert_manager.resolve_alert(
                    source_type="system",
                    source_id="host_system",
                    alert_type=AlertType.SYSTEM_DISK_HIGH
                )
                
        except ImportError:
            logger.warning("psutil模块未安装，跳过系统资源检查")
        except Exception as e:
            logger.error(f"检查系统资源失败: {str(e)}")
            # 尝试创建一个通用的系统告警
            try:
                alert_manager.create_alert(
                    source_type="system",
                    source_id="host_system",
                    source_name="系统",
                    alert_type=AlertType.SYSTEM_CPU_HIGH,
                    level="error",
                    message=f"系统资源监控失败: {str(e)}"
                )
            except:
                pass
    
    def get_scheduler_info(self) -> Dict[str, Any]:
        """获取调度器信息（增强版，包含容器环境信息）
        
        Returns:
            调度器信息
        """
        # 计算任务执行统计
        task_metrics = {}
        for task_id, stats in self.task_stats.items():
            task_metrics[task_id] = {
                'last_run': stats.get('last_run', None),
                'run_count': stats.get('run_count', 0),
                'error_count': stats.get('error_count', 0),
                'error_rate': stats.get('error_count', 0) / max(stats.get('run_count', 1), 1) * 100
            }
        
        return {
            'running': self.scheduler.running,
            'in_container': self._in_container,
            'jobs_count': len(self.scheduler.get_jobs()),
            'running_tasks': list(self.running_tasks),
            'executors': dict(self.scheduler._executors),
            'task_metrics': task_metrics,
            'uptime': time.time() - getattr(self, '_start_time', time.time())
        }


# 创建全局任务调度器实例
task_scheduler = TaskScheduler()