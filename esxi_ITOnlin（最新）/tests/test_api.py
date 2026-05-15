"""
ESXI监控系统API测试文件
"""

import pytest
from fastapi.testclient import TestClient
import sys
import os

# 添加项目路径到sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

client = TestClient(app)


def test_health_check():
    """测试健康检查接口"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "components" in data


def test_dashboard_summary():
    """测试仪表盘摘要接口"""
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    data = response.json()
    assert "total_hosts" in data
    assert "connected_hosts" in data
    assert "total_vms" in data
    assert "running_vms" in data
    assert "critical_alerts" in data
    assert "warning_alerts" in data


def test_get_hosts():
    """测试获取主机列表接口"""
    response = client.get("/api/hosts")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_vms():
    """测试获取虚拟机列表接口"""
    response = client.get("/api/vms")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_alerts():
    """测试获取告警列表接口"""
    response = client.get("/api/alerts")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_system_info():
    """测试获取系统信息接口"""
    response = client.get("/api/system/info")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "uptime" in data
    assert "python_version" in data


def test_get_tasks():
    """测试获取任务列表接口"""
    response = client.get("/api/tasks")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_threshold_settings():
    """测试获取阈值配置接口"""
    response = client.get("/api/settings/thresholds")
    assert response.status_code == 200


def test_api_404():
    """测试不存在的接口"""
    response = client.get("/api/nonexistent")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
