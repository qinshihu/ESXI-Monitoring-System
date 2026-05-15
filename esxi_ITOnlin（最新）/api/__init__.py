"""
API模块
提供系统监控和管理的RESTful接口
"""

from fastapi import APIRouter
from fastapi.middleware.cors import CORSMiddleware

from .routes import api_router
from .models import *  # 导入所有数据模型

# 创建主API路由器
__all__ = ['api_router', 'setup_cors']

# 模块版本
__version__ = '1.0.0'


def setup_cors(app):
    """
    配置CORS中间件
    
    Args:
        app: FastAPI应用实例
    """
    from config import settings
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_CREDENTIALS,
        allow_methods=settings.CORS_METHODS,
        allow_headers=settings.CORS_HEADERS,
    )