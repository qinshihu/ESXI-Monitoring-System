"""
API路由定义
实现所有RESTful接口端点
"""

import logging
import time
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from config import settings
from database import db_session, ESXIHost, VirtualMachine, Alert, get_influxdb_client, get_redis_client
from collectors.esxi_collector import ESXiCollector
from alerts.alert_manager import alert_manager
from tasks.scheduler import task_scheduler
from .models import *

logger = logging.getLogger(__name__)

# 创建API路由器
api_router = APIRouter(
    prefix="/api",
    tags=["监控系统API"],
    responses={404: {"description": "未找到"}},
)


def get_db():
    """数据库会话依赖"""
    with db_session() as db:
        yield db


# ===== 仪表盘相关API =====
@api_router.get("/dashboard/summary", response_model=DashboardSummary, summary="获取仪表盘摘要信息")
def get_dashboard_summary(db: Session = Depends(get_db)):
    """
    获取监控系统的总体摘要信息，包括：
    - 主机统计（总数、连接状态分布）
    - 虚拟机统计（总数、运行中数量）
    - 告警统计（严重、警告）
    - 系统负载
    - 数据采集状态
    """
    try:
        # 主机统计
        total_hosts = db.query(func.count(ESXIHost.id)).scalar() or 0
        connected_hosts = db.query(func.count(ESXIHost.id)).filter(
            ESXIHost.status == 'connected'
        ).scalar() or 0
        warning_hosts = db.query(func.count(ESXIHost.id)).filter(
            ESXIHost.status == 'warning'
        ).scalar() or 0
        error_hosts = db.query(func.count(ESXIHost.id)).filter(
            ESXIHost.status == 'error'
        ).scalar() or 0
        
        # 虚拟机统计
        total_vms = db.query(func.count(VirtualMachine.id)).filter(
            VirtualMachine.is_active == True
        ).scalar() or 0
        running_vms = db.query(func.count(VirtualMachine.id)).filter(
            VirtualMachine.is_active == True,
            VirtualMachine.power_state == 'poweredOn'
        ).scalar() or 0
        
        # 告警统计（24小时内）
        cutoff_time = datetime.utcnow() - timedelta(days=1)
        critical_alerts = db.query(func.count(Alert.id)).filter(
            Alert.level == 'critical',
            Alert.is_resolved == False,
            Alert.created_at >= cutoff_time
        ).scalar() or 0
        warning_alerts = db.query(func.count(Alert.id)).filter(
            Alert.level == 'warning',
            Alert.is_resolved == False,
            Alert.created_at >= cutoff_time
        ).scalar() or 0
        
        # 系统负载（从任务调度器获取）
        scheduler_info = task_scheduler.get_scheduler_info()
        data_collection_status = "running" if task_scheduler.scheduler.running else "stopped"
        
        # 系统负载 (如果psutil可用)
        system_load = None
        try:
            import psutil
            system_load = psutil.cpu_percent(interval=0.1)
        except ImportError:
            pass
        
        return DashboardSummary(
            total_hosts=total_hosts,
            connected_hosts=connected_hosts,
            warning_hosts=warning_hosts,
            error_hosts=error_hosts,
            total_vms=total_vms,
            running_vms=running_vms,
            critical_alerts=critical_alerts,
            warning_alerts=warning_alerts,
            system_load=system_load,
            data_collection_status=data_collection_status
        )
        
    except Exception as e:
        logger.error(f"获取仪表盘摘要失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取仪表盘摘要失败")


# ===== 主机管理API =====
@api_router.get("/hosts", response_model=List[HostStatusResponse], summary="获取所有主机列表")
def get_hosts(
    status: Optional[HostStatus] = Query(None, description="按状态过滤"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回记录数"),
    db: Session = Depends(get_db)
):
    """
    获取所有ESXi主机列表，支持按状态过滤
    """
    try:
        query = db.query(ESXIHost)
        
        if status:
            query = query.filter(ESXIHost.status == status)
        
        hosts = query.offset(skip).limit(limit).all()
        
        # 转换为响应模型
        host_responses = []
        for host in hosts:
            # 获取主机的虚拟机数量
            vm_count = db.query(func.count(VirtualMachine.id)).filter(
                VirtualMachine.host_id == host.id,
                VirtualMachine.is_active == True
            ).scalar() or 0
            
            host_response = HostStatusResponse(
                id=host.id,
                name=host.name,
                ip_address=host.ip_address,
                status=HostStatus(host.status),
                last_seen=host.last_seen,
                cpu_usage=host.cpu_usage,
                memory_usage=host.memory_usage,
                storage_usage=host.storage_usage,
                vm_count=vm_count,
                status_message=host.status_message
            )
            host_responses.append(host_response)
        
        return host_responses
        
    except Exception as e:
        logger.error(f"获取主机列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取主机列表失败")


@api_router.get("/hosts/{host_id}", response_model=HostResponse, summary="获取主机详细信息")
def get_host(host_id: int, db: Session = Depends(get_db)):
    """
    根据ID获取特定主机的详细信息
    """
    host = db.query(ESXIHost).filter(ESXIHost.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail="主机不存在")
    
    return HostResponse(
        id=host.id,
        name=host.name,
        ip_address=host.ip_address,
        port=host.port,
        status=HostStatus(host.status),
        description=host.description,
        last_seen=host.last_seen,
        cpu_usage=host.cpu_usage,
        memory_usage=host.memory_usage,
        storage_usage=host.storage_usage,
        vm_count=0,  # 这里可以查询虚拟机数量
        created_at=host.created_at,
        updated_at=host.updated_at
    )


@api_router.post("/hosts", response_model=HostResponse, status_code=status.HTTP_201_CREATED, summary="添加新主机")
def create_host(host: HostCreate, db: Session = Depends(get_db)):
    """
    添加新的ESXi主机到监控系统
    """
    try:
        # 检查主机名或IP是否已存在
        existing = db.query(ESXIHost).filter(
            (ESXIHost.name == host.name) | (ESXIHost.ip_address == host.ip_address)
        ).first()
        
        if existing:
            raise HTTPException(status_code=400, detail="主机名或IP地址已存在")
        
        # 创建新主机
        new_host = ESXIHost(
            name=host.name,
            ip_address=host.ip_address,
            port=host.port,
            username=host.username,
            password=host.password,
            description=host.description,
            status='disconnected',
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(new_host)
        db.commit()
        db.refresh(new_host)
        
        # 立即尝试连接并采集数据
        collector = ESXiCollector()
        try:
            metrics = collector.collect_host_metrics(
                host_name=new_host.name,
                host_ip=new_host.ip_address,
                username=new_host.username,
                password=new_host.password
            )
            if metrics:
                new_host.status = 'connected'
                new_host.last_seen = datetime.utcnow()
                db.commit()
        except Exception as e:
            logger.warning(f"首次连接主机 {new_host.name} 失败: {str(e)}")
        
        return HostResponse(
            id=new_host.id,
            name=new_host.name,
            ip_address=new_host.ip_address,
            port=new_host.port,
            status=HostStatus(new_host.status),
            description=new_host.description,
            last_seen=new_host.last_seen,
            cpu_usage=new_host.cpu_usage,
            memory_usage=new_host.memory_usage,
            storage_usage=new_host.storage_usage,
            vm_count=0,
            created_at=new_host.created_at,
            updated_at=new_host.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加主机失败: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="添加主机失败")


@api_router.put("/hosts/{host_id}", response_model=HostResponse, summary="更新主机信息")
def update_host(host_id: int, host_update: HostUpdate, db: Session = Depends(get_db)):
    """
    更新主机信息
    """
    try:
        host = db.query(ESXIHost).filter(ESXIHost.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail="主机不存在")
        
        # 检查名称或IP是否与其他主机冲突
        if host_update.name or host_update.ip_address:
            query = db.query(ESXIHost).filter(ESXIHost.id != host_id)
            if host_update.name:
                query = query.filter(ESXIHost.name == host_update.name)
            if host_update.ip_address:
                query = query.filter(ESXIHost.ip_address == host_update.ip_address)
            
            if query.first():
                raise HTTPException(status_code=400, detail="主机名或IP地址已被使用")
        
        # 更新字段
        update_data = host_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(host, field, value)
        
        host.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(host)
        
        return HostResponse(
            id=host.id,
            name=host.name,
            ip_address=host.ip_address,
            port=host.port,
            status=HostStatus(host.status),
            description=host.description,
            last_seen=host.last_seen,
            cpu_usage=host.cpu_usage,
            memory_usage=host.memory_usage,
            storage_usage=host.storage_usage,
            vm_count=0,
            created_at=host.created_at,
            updated_at=host.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新主机失败: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="更新主机失败")


@api_router.delete("/hosts/{host_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除主机")
def delete_host(host_id: int, db: Session = Depends(get_db)):
    """
    从监控系统中删除主机
    """
    try:
        host = db.query(ESXIHost).filter(ESXIHost.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail="主机不存在")
        
        # 删除相关的虚拟机记录
        db.query(VirtualMachine).filter(VirtualMachine.host_id == host_id).delete()
        
        # 删除主机
        db.delete(host)
        db.commit()
        
        # 断开连接（如果已连接）
        collector = ESXiCollector()
        collector.disconnect(host.name)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除主机失败: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="删除主机失败")


# ===== 虚拟机管理API =====
@api_router.get("/vms", response_model=List[VirtualMachineResponse], summary="获取所有虚拟机列表")
def get_virtual_machines(
    host_id: Optional[int] = Query(None, description="按主机ID过滤"),
    power_state: Optional[VMPowerState] = Query(None, description="按电源状态过滤"),
    is_active: Optional[bool] = Query(True, description="是否只显示活跃虚拟机"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """
    获取虚拟机列表，支持按主机和电源状态过滤
    """
    try:
        query = db.query(VirtualMachine)
        
        if host_id:
            query = query.filter(VirtualMachine.host_id == host_id)
        
        if power_state:
            query = query.filter(VirtualMachine.power_state == power_state)
        
        if is_active is not None:
            query = query.filter(VirtualMachine.is_active == is_active)
        
        vms = query.order_by(VirtualMachine.host_id, VirtualMachine.name).offset(skip).limit(limit).all()
        
        # 转换为响应模型
        vm_responses = []
        for vm in vms:
            vm_response = VirtualMachineResponse(
                id=vm.id,
                vm_id=vm.vm_id,
                host_id=vm.host_id,
                name=vm.name,
                power_state=VMPowerState(vm.power_state),
                guest_os=vm.guest_os,
                memory_mb=vm.memory_mb,
                num_cpu=vm.num_cpu,
                cpu_usage=vm.cpu_usage,
                memory_usage=vm.memory_usage,
                is_active=vm.is_active,
                created_at=vm.created_at,
                last_seen=vm.last_seen
            )
            vm_responses.append(vm_response)
        
        return vm_responses
        
    except Exception as e:
        logger.error(f"获取虚拟机列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取虚拟机列表失败")


@api_router.get("/vms/{vm_id}", response_model=VirtualMachineResponse, summary="获取虚拟机详细信息")
def get_virtual_machine(vm_id: int, db: Session = Depends(get_db)):
    """
    根据ID获取特定虚拟机的详细信息
    """
    vm = db.query(VirtualMachine).filter(VirtualMachine.id == vm_id).first()
    if not vm:
        raise HTTPException(status_code=404, detail="虚拟机不存在")
    
    return VirtualMachineResponse(
        id=vm.id,
        vm_id=vm.vm_id,
        host_id=vm.host_id,
        name=vm.name,
        power_state=VMPowerState(vm.power_state),
        guest_os=vm.guest_os,
        memory_mb=vm.memory_mb,
        num_cpu=vm.num_cpu,
        cpu_usage=vm.cpu_usage,
        memory_usage=vm.memory_usage,
        is_active=vm.is_active,
        created_at=vm.created_at,
        last_seen=vm.last_seen
    )


@api_router.get("/hosts/{host_id}/vms", response_model=List[VirtualMachineResponse], summary="获取主机的所有虚拟机")
def get_host_virtual_machines(host_id: int, db: Session = Depends(get_db)):
    """
    获取特定主机上的所有虚拟机
    """
    # 检查主机是否存在
    host = db.query(ESXIHost).filter(ESXIHost.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail="主机不存在")
    
    # 获取该主机的所有活跃虚拟机
    vms = db.query(VirtualMachine).filter(
        VirtualMachine.host_id == host_id,
        VirtualMachine.is_active == True
    ).all()
    
    # 转换为响应模型
    vm_responses = []
    for vm in vms:
        vm_response = VirtualMachineResponse(
            id=vm.id,
            vm_id=vm.vm_id,
            host_id=vm.host_id,
            name=vm.name,
            power_state=VMPowerState(vm.power_state),
            guest_os=vm.guest_os,
            memory_mb=vm.memory_mb,
            num_cpu=vm.num_cpu,
            cpu_usage=vm.cpu_usage,
            memory_usage=vm.memory_usage,
            is_active=vm.is_active,
            created_at=vm.created_at,
            last_seen=vm.last_seen
        )
        vm_responses.append(vm_response)
    
    return vm_responses


# ===== 告警管理API =====
@api_router.get("/alerts", response_model=List[AlertResponse], summary="获取告警列表")
def get_alerts(
    level: Optional[AlertLevel] = Query(None, description="按告警级别过滤"),
    is_resolved: Optional[bool] = Query(None, description="是否已解决"),
    host_id: Optional[int] = Query(None, description="按主机ID过滤"),
    vm_id: Optional[int] = Query(None, description="按虚拟机ID过滤"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """
    获取告警列表，支持多条件过滤和分页
    """
    try:
        query = db.query(Alert)
        
        if level:
            query = query.filter(Alert.level == level)
        
        if is_resolved is not None:
            query = query.filter(Alert.is_resolved == is_resolved)
        
        if host_id:
            query = query.filter(Alert.host_id == host_id)
        
        if vm_id:
            query = query.filter(Alert.vm_id == vm_id)
        
        if start_time:
            query = query.filter(Alert.created_at >= start_time)
        
        if end_time:
            query = query.filter(Alert.created_at <= end_time)
        
        # 按创建时间倒序排序
        alerts = query.order_by(desc(Alert.created_at)).offset(skip).limit(limit).all()
        
        # 转换为响应模型
        alert_responses = []
        for alert in alerts:
            alert_response = AlertResponse(
                id=alert.id,
                level=AlertLevel(alert.level),
                type=AlertType(alert.type),
                source=alert.source,
                message=alert.message,
                details=alert.details,
                is_resolved=alert.is_resolved,
                created_at=alert.created_at,
                resolved_at=alert.resolved_at,
                host_id=alert.host_id,
                vm_id=alert.vm_id
            )
            alert_responses.append(alert_response)
        
        return alert_responses
        
    except Exception as e:
        logger.error(f"获取告警列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取告警列表失败")


@api_router.get("/alerts/{alert_id}", response_model=AlertResponse, summary="获取告警详细信息")
def get_alert(alert_id: int, db: Session = Depends(get_db)):
    """
    根据ID获取特定告警的详细信息
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")
    
    return AlertResponse(
        id=alert.id,
        level=AlertLevel(alert.level),
        type=AlertType(alert.type),
        source=alert.source,
        message=alert.message,
        details=alert.details,
        is_resolved=alert.is_resolved,
        created_at=alert.created_at,
        resolved_at=alert.resolved_at,
        host_id=alert.host_id,
        vm_id=alert.vm_id
    )


@api_router.put("/alerts/{alert_id}/resolve", response_model=AlertResponse, summary="解决告警")
def resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    """
    将指定告警标记为已解决
    """
    try:
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="告警不存在")
        
        if alert.is_resolved:
            raise HTTPException(status_code=400, detail="告警已经被解决")
        
        alert.is_resolved = True
        alert.resolved_at = datetime.utcnow()
        db.commit()
        db.refresh(alert)
        
        return AlertResponse(
            id=alert.id,
            level=AlertLevel(alert.level),
            type=AlertType(alert.type),
            source=alert.source,
            message=alert.message,
            details=alert.details,
            is_resolved=alert.is_resolved,
            created_at=alert.created_at,
            resolved_at=alert.resolved_at,
            host_id=alert.host_id,
            vm_id=alert.vm_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"解决告警失败: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="解决告警失败")


@api_router.post("/alerts/test", response_model=AlertResponse, summary="创建测试告警")
def create_test_alert(alert_data: AlertCreate, db: Session = Depends(get_db)):
    """
    创建测试告警，用于验证告警功能
    """
    try:
        new_alert = Alert(
            level=alert_data.level,
            type=alert_data.type,
            source=alert_data.source,
            message=alert_data.message,
            details=alert_data.details,
            is_resolved=False,
            created_at=datetime.utcnow()
        )
        
        db.add(new_alert)
        db.commit()
        db.refresh(new_alert)
        
        return AlertResponse(
            id=new_alert.id,
            level=AlertLevel(new_alert.level),
            type=AlertType(new_alert.type),
            source=new_alert.source,
            message=new_alert.message,
            details=new_alert.details,
            is_resolved=new_alert.is_resolved,
            created_at=new_alert.created_at,
            resolved_at=new_alert.resolved_at,
            host_id=new_alert.host_id,
            vm_id=new_alert.vm_id
        )
        
    except Exception as e:
        logger.error(f"创建测试告警失败: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="创建测试告警失败")


# ===== 指标查询API =====
@api_router.post("/metrics/query", response_model=MetricResponse, summary="查询历史指标数据")
def query_metrics(metric_query: MetricQuery):
    """
    查询历史指标数据，支持时间范围和过滤条件
    """
    try:
        influxdb_client = get_influxdb_client()
        if not influxdb_client:
            raise HTTPException(status_code=503, detail="InfluxDB服务不可用")
        
        # 构建查询语句
        query = f"""from(bucket: \"{settings.INFLUXDB_BUCKET}\")
        |> range(start: {metric_query.start_time.isoformat()}, stop: {metric_query.end_time.isoformat()})
        |> filter(fn: (r) => r._measurement == \"{metric_query.metric_name}\")
        |> filter(fn: (r) => r.source == \"{metric_query.source}\")"""
        
        # 添加额外的过滤条件
        if metric_query.filters:
            for key, value in metric_query.filters.items():
                query += f"\n|> filter(fn: (r) => r.{key} == \"{value}\")"
        
        # 添加时间间隔聚合
        if metric_query.interval:
            query += f"\n|> aggregateWindow(every: {metric_query.interval}, fn: mean, createEmpty: false)"
        
        # 执行查询
        result = influxdb_client.query(query)
        
        # 处理查询结果
        data_points = []
        for table in result:
            for record in table.records:
                data_point = MetricData(
                    timestamp=record.get_time(),
                    value=record.get_value()
                )
                data_points.append(data_point)
        
        # 按时间排序
        data_points.sort(key=lambda x: x.timestamp)
        
        # 获取单位（如果有）
        unit = None
        if data_points and hasattr(result, 'get_column') and result.get_column('_field'):
            unit = result.get_column('_field')[0] if result.get_column('_field') else None
        
        return MetricResponse(
            metric_name=metric_query.metric_name,
            data_points=data_points,
            unit=unit,
            source=metric_query.source
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询指标数据失败: {str(e)}")
        raise HTTPException(status_code=500, detail="查询指标数据失败")


@api_router.get("/metrics/latest", response_model=Dict[str, float], summary="获取最新指标数据")
def get_latest_metrics(
    source: str = Query(..., description="数据源名称（主机名）"),
    metrics: str = Query(..., description="指标名称列表，用逗号分隔")
):
    """
    获取指定源的最新指标数据
    """
    try:
        redis_client = get_redis_client()
        if not redis_client:
            raise HTTPException(status_code=503, detail="Redis服务不可用")
        
        metric_names = [m.strip() for m in metrics.split(',')]
        latest_metrics = {}
        
        for metric in metric_names:
            key = f"metrics:{source}:{metric}"
            value = redis_client.get(key)
            if value:
                latest_metrics[metric] = float(value)
            else:
                latest_metrics[metric] = 0.0
        
        return latest_metrics
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取最新指标失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取最新指标失败")


# ===== 系统管理API =====
@api_router.get("/system/info", response_model=SystemInfo, summary="获取系统信息")
def get_system_info():
    """
    获取监控系统的详细信息
    """
    try:
        import sys
        
        # 计算系统运行时间
        if hasattr(task_scheduler, '_start_time'):
            uptime = int(time.time() - task_scheduler._start_time)
        else:
            uptime = 0
        
        # 检查数据库连接状态
        db_status = "connected" if check_db_connection() else "disconnected"
        
        # 检查InfluxDB连接状态
        influxdb_client = get_influxdb_client()
        influxdb_status = "connected" if influxdb_client else "disconnected"
        
        # 检查Redis连接状态
        redis_client = get_redis_client()
        redis_status = "connected" if redis_client else "disconnected"
        
        # 活跃采集任务数
        active_collections = len(task_scheduler.running_tasks) if hasattr(task_scheduler, 'running_tasks') else 0
        
        # 活跃连接数（从ESXiCollector获取）
        collector = ESXiCollector()
        active_connections = len(collector.connections) if hasattr(collector, 'connections') else 0
        
        return SystemInfo(
            version=settings.VERSION,
            uptime=uptime,
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            database_status=db_status,
            influxdb_status=influxdb_status,
            redis_status=redis_status,
            active_collections=active_collections,
            active_connections=active_connections
        )
        
    except Exception as e:
        logger.error(f"获取系统信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取系统信息失败")


@api_router.get("/system/health", response_model=APIResponse, summary="健康检查")
def health_check():
    """
    系统健康检查接口，返回各组件状态
    """
    try:
        components = {
            "database": "connected" if check_db_connection() else "disconnected",
            "influxdb": "connected" if get_influxdb_client() else "disconnected",
            "redis": "connected" if get_redis_client() else "disconnected",
            "scheduler": "running" if task_scheduler.scheduler.running else "stopped"
        }
        
        # 检查是否所有组件都正常
        all_healthy = all(status == "connected" or status == "running" for status in components.values())
        
        if all_healthy:
            return APIResponse(
                success=True,
                message="系统健康状态良好",
                data={"components": components}
            )
        else:
            return APIResponse(
                success=False,
                message="部分组件异常",
                data={"components": components}
            )
            
    except Exception as e:
        logger.error(f"健康检查失败: {str(e)}")
        raise HTTPException(status_code=500, detail="健康检查失败")


# ===== 任务管理API =====
@api_router.get("/tasks", response_model=List[TaskInfo], summary="获取任务列表")
def get_tasks():
    """
    获取所有调度任务的状态信息
    """
    try:
        jobs = task_scheduler.get_all_jobs()
        task_infos = []
        
        for job in jobs:
            # 确定任务状态
            if job['is_running']:
                status = TaskStatus.RUNNING
            elif job['is_paused']:
                status = TaskStatus.PAUSED
            else:
                status = TaskStatus.RUNNING
            
            task_info = TaskInfo(
                id=job['id'],
                name=job['name'],
                status=status,
                next_run_time=job['next_run_time'],
                last_run_time=job['stats'].get('last_run'),
                run_count=job['stats'].get('run_count', 0),
                error_count=job['stats'].get('error_count', 0)
            )
            task_infos.append(task_info)
        
        return task_infos
        
    except Exception as e:
        logger.error(f"获取任务列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取任务列表失败")


@api_router.get("/tasks/{task_id}", response_model=TaskInfo, summary="获取任务详情")
def get_task(task_id: str):
    """
    获取特定任务的详细状态信息
    """
    try:
        job_status = task_scheduler.get_job_status(task_id)
        if not job_status:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        # 确定任务状态
        if job_status['is_running']:
            status = TaskStatus.RUNNING
        elif job_status['is_paused']:
            status = TaskStatus.PAUSED
        else:
            status = TaskStatus.RUNNING
        
        return TaskInfo(
            id=job_status['id'],
            name=job_status['name'],
            status=status,
            next_run_time=job_status['next_run_time'],
            last_run_time=job_status['stats'].get('last_run'),
            run_count=job_status['stats'].get('run_count', 0),
            error_count=job_status['stats'].get('error_count', 0)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务详情失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取任务详情失败")


@api_router.post("/tasks/{task_id}/action", response_model=APIResponse, summary="执行任务操作")
def task_action(task_id: str, action: TaskAction):
    """
    对任务执行操作：暂停、恢复、立即触发
    """
    try:
        if action.action == 'pause':
            success = task_scheduler.pause_job(task_id)
            message = f"任务 {task_id} 已暂停" if success else f"暂停任务 {task_id} 失败"
        elif action.action == 'resume':
            success = task_scheduler.resume_job(task_id)
            message = f"任务 {task_id} 已恢复" if success else f"恢复任务 {task_id} 失败"
        elif action.action == 'trigger':
            success = task_scheduler.trigger_job(task_id)
            message = f"任务 {task_id} 已立即触发" if success else f"触发任务 {task_id} 失败"
        else:
            raise HTTPException(status_code=400, detail="无效的操作类型")
        
        if success:
            return APIResponse(success=True, message=message)
        else:
            raise HTTPException(status_code=400, detail=message)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"任务操作失败: {str(e)}")
        raise HTTPException(status_code=500, detail="任务操作失败")


@api_router.post("/tasks/start-all", response_model=APIResponse, summary="启动所有任务")
def start_all_tasks():
    """
    启动所有调度任务
    """
    try:
        success = task_scheduler.start()
        if success:
            return APIResponse(success=True, message="所有任务已启动")
        else:
            raise HTTPException(status_code=500, detail="启动任务失败")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动所有任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail="启动所有任务失败")


@api_router.post("/tasks/stop-all", response_model=APIResponse, summary="停止所有任务")
def stop_all_tasks():
    """
    停止所有调度任务
    """
    try:
        success = task_scheduler.stop()
        if success:
            return APIResponse(success=True, message="所有任务已停止")
        else:
            raise HTTPException(status_code=500, detail="停止任务失败")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"停止所有任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail="停止所有任务失败")


# ===== 配置管理API =====
@api_router.get("/settings/thresholds", response_model=ThresholdConfig, summary="获取告警阈值配置")
def get_threshold_settings():
    """
    获取当前的告警阈值配置
    """
    return ThresholdConfig(
        cpu_warning=settings.CPU_WARNING_THRESHOLD,
        cpu_critical=settings.CPU_CRITICAL_THRESHOLD,
        memory_warning=settings.MEMORY_WARNING_THRESHOLD,
        memory_critical=settings.MEMORY_CRITICAL_THRESHOLD,
        storage_warning=settings.STORAGE_WARNING_THRESHOLD,
        storage_critical=settings.STORAGE_CRITICAL_THRESHOLD,
        network_warning=settings.NETWORK_WARNING_THRESHOLD,
        network_critical=settings.NETWORK_CRITICAL_THRESHOLD,
        alert_cooldown=settings.ALERT_COOLDOWN,
        vm_inactive_threshold=settings.VM_INACTIVE_THRESHOLD
    )


@api_router.post("/collect/hosts/{host_id}", response_model=APIResponse, summary="立即采集指定主机数据")
def collect_host_data(host_id: int, db: Session = Depends(get_db)):
    """
    立即触发对指定主机的数据采集
    """
    try:
        host = db.query(ESXIHost).filter(ESXIHost.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail="主机不存在")
        
        # 立即采集数据
        collector = ESXiCollector()
        host_metrics = collector.collect_host_metrics(
            host_name=host.name,
            host_ip=host.ip_address,
            username=host.username,
            password=host.password
        )
        
        if host_metrics:
            # 更新主机状态
            host.status = 'connected'
            host.last_seen = datetime.utcnow()
            
            # 保存指标
            collector.save_host_metrics_to_influxdb(host.name, host_metrics)
            
            # 采集虚拟机数据
            vms_metrics = collector.collect_vms_metrics(
                host_name=host.name,
                host_ip=host.ip_address,
                username=host.username,
                password=host.password
            )
            
            db.commit()
            
            return APIResponse(
                success=True,
                message=f"成功采集主机 {host.name} 的数据",
                data={
                    "host_metrics": host_metrics,
                    "vm_count": len(vms_metrics) if vms_metrics else 0
                }
            )
        else:
            raise HTTPException(status_code=500, detail="采集主机数据失败")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"立即采集主机数据失败: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="采集主机数据失败")


# ===== 辅助函数 =====
def check_db_connection():
    """
    检查数据库连接状态
    """
    try:
        with db_session() as db:
            db.execute("SELECT 1")
        return True
    except Exception:
        return False


# ===== 错误处理 =====
# 异常处理已移至main.py中
# APIRouter对象没有exception_handler属性，异常处理应在FastAPI主应用程序中定义