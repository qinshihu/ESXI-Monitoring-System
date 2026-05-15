"""
ESXI监控系统主应用程序

该模块是ESXI监控系统的入口点，负责：
1. 初始化FastAPI应用
2. 配置中间件（CORS、日志等）
3. 注册路由
4. 初始化数据库和依赖服务
5. 启动任务调度器
6. 提供应用生命周期管理
"""

import logging
import signal
import sys
import time
import uvicorn
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import (get_swagger_ui_html, get_redoc_html,
                                 get_swagger_ui_oauth2_redirect_html)
from datetime import datetime

from config import settings
from database import init_database, close_connections, health_check
from tasks.scheduler import task_scheduler
from alerts.alert_manager import alert_manager
from api import api_router, setup_cors

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format=settings.LOG_FORMAT,
    handlers=[
        logging.StreamHandler(),
    ]
)

if settings.LOG_FILE:
    file_handler = logging.FileHandler(settings.LOG_FILE)
    file_handler.setFormatter(logging.Formatter(settings.LOG_FORMAT))
    logging.getLogger().addHandler(file_handler)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    - 启动时：初始化数据库、启动任务调度器
    - 关闭时：停止任务调度器、关闭数据库连接
    """
    # 启动阶段
    logger.info(f"正在启动ESXI监控系统 v{settings.VERSION}...")
    
    # 启动调度器标志
    scheduler_started = False
    
    try:
        # 初始化数据库 - 确保即使连接失败也能启动应用（开发和测试环境）
        logger.info("初始化数据库连接...")
        db_initialized = False
        try:
            init_database()
            db_initialized = True
            logger.info("数据库初始化成功")
        except Exception as db_e:
            logger.error(f"数据库初始化失败: {str(db_e)}")
            logger.warning("应用将继续启动，但部分功能可能不可用")
        
        # 只有在数据库初始化成功后才初始化其他服务
        if db_initialized:
            # 检查所有服务连接
            logger.info("检查系统组件连接状态...")
            try:
                connection_status = health_check()
                
                # 修改健康检查逻辑，支持SQLite
                # 不再强制要求MySQL连接
                if "mysql" in connection_status and not connection_status["mysql"]:
                    logger.warning("MySQL数据库连接失败，将继续使用SQLite")
                
                if not connection_status["influxdb"]:
                    logger.warning("InfluxDB连接失败，历史数据存储功能将不可用")
                
                if not connection_status["redis"]:
                    logger.warning("Redis连接失败，缓存功能将不可用")
            except Exception as check_e:
                logger.error(f"服务健康检查失败: {str(check_e)}")
        
        # 启动任务调度器 - 加强检查避免重复启动
        logger.info("启动任务调度器...")
        try:
            # 检查调度器是否已运行，避免重复启动
            if not hasattr(task_scheduler, '_started') or not task_scheduler._started:
                # 确保任务调度器的scheduler属性存在且未运行
                if hasattr(task_scheduler, 'scheduler') and hasattr(task_scheduler.scheduler, 'running') and task_scheduler.scheduler.running:
                    logger.warning("任务调度器实例已在运行中")
                else:
                    # 尝试使用文件锁实现进程间互斥
                    lock_file = None
                    skip_start = False
                    try:
                        # 优先使用配置文件中的LOCK_DIR，更好地支持容器化部署
                        # 同时保留默认值作为后备
                        lock_dir = getattr(settings, "LOCK_DIR", None)
                        if not lock_dir or not os.path.isabs(lock_dir):
                            lock_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locks")
                        
                        # 确保锁目录存在
                        os.makedirs(lock_dir, exist_ok=True)
                        logger.debug(f"使用锁文件目录: {lock_dir}")
                        
                        # 在Windows环境中，fcntl不可用，使用简单的文件检查
                        if sys.platform == "win32":
                            lock_file_path = os.path.join(lock_dir, ".scheduler_lock")
                            if os.path.exists(lock_file_path):
                                # 检查锁文件是否超过5分钟，如果是则认为是旧锁，可以覆盖
                                lock_file_time = os.path.getmtime(lock_file_path)
                                if time.time() - lock_file_time < 300:
                                    logger.warning("检测到另一个进程可能正在运行任务调度器，跳过启动")
                                    skip_start = True
                                else:
                                    logger.warning("检测到旧的锁文件，将覆盖")
                            if not skip_start:
                                # 创建锁文件
                                lock_file = open(lock_file_path, "w")
                                lock_file.write(f"{os.getpid()}")
                                lock_file.flush()
                                os.fsync(lock_file.fileno())
                                
                                # 启动调度器
                                task_scheduler.start()
                                task_scheduler._started = True
                                scheduler_started = True
                                logger.info("任务调度器启动成功")
                        else:
                            # 在非Windows环境中使用fcntl
                            try:
                                import fcntl
                                lock_file_path = os.path.join(lock_dir, ".scheduler_lock")
                                lock_file = open(lock_file_path, "w")
                                try:
                                    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                                except BlockingIOError:
                                    logger.warning("检测到另一个进程正在运行任务调度器，跳过启动")
                                    skip_start = True
                                
                                if not skip_start:
                                    lock_file.write(f"{os.getpid()}")
                                    lock_file.flush()
                                    
                                    # 启动调度器
                                    task_scheduler.start()
                                    task_scheduler._started = True
                                    scheduler_started = True
                                    logger.info("任务调度器启动成功")
                            except ImportError:
                                logger.warning("fcntl模块不可用，跳过进程互斥检查")
                                # 继续启动调度器
                                task_scheduler.start()
                                task_scheduler._started = True
                                scheduler_started = True
                    except Exception as lock_e:
                        logger.warning(f"进程互斥锁创建失败，继续启动但可能导致重复执行: {str(lock_e)}")
                        # 即使锁创建失败，也尝试启动调度器
                        task_scheduler.start()
                        task_scheduler._started = True
                        scheduler_started = True
            else:
                logger.info("任务调度器已经在运行中")
                scheduler_started = True
        except Exception as scheduler_e:
            logger.error(f"任务调度器启动失败: {str(scheduler_e)}")
        
        logger.info("ESXI监控系统启动完成")
        
        # 注册信号处理，优雅关闭
        def handle_shutdown(sig, frame):
            logger.info("收到关闭信号，正在优雅关闭...")
            try:
                # 停止任务调度器
                task_scheduler.stop()
                # 关闭数据库连接
                close_connections()
            except Exception as shutdown_e:
                logger.error(f"优雅关闭过程中发生错误: {str(shutdown_e)}")
            finally:
                logger.info("系统已关闭")
                sys.exit(0)
        
        # 注册信号处理，优雅关闭
        # 对于Windows环境，也尝试基本的信号处理，但效果可能有限
        if sys.platform != "win32":
            signal.signal(signal.SIGINT, handle_shutdown)
            signal.signal(signal.SIGTERM, handle_shutdown)
            logger.debug("已注册SIGINT和SIGTERM信号处理器")
        else:
            try:
                # Windows下也尝试注册信号处理，尽管效果有限
                signal.signal(signal.SIGINT, handle_shutdown)
                logger.debug("在Windows环境下已注册SIGINT信号处理器")
            except:
                logger.warning("Windows环境下信号处理有限，可能无法优雅关闭")
        
        # 检测容器化环境并记录
        in_container = (
            getattr(settings, "CONTAINERIZED", False) or
            os.environ.get("CONTAINERIZED") == "true" or
            (os.path.exists("/proc/1/cgroup") and "docker" in open("/proc/1/cgroup", "r").read())
        )
        if in_container:
            logger.info("ESXI监控系统已在容器环境中启动")
        
    except Exception as e:
        logger.error(f"系统启动过程中发生错误: {str(e)}")
        # 在容器环境中，我们不应该直接抛出异常导致容器退出
        # 而是尝试继续运行，让容器可以保持运行状态
        logger.warning("系统将尝试继续运行，但某些功能可能不可用")
        
        # 检测容器化环境（支持多种检测方式）
        in_container = (
            getattr(settings, "CONTAINERIZED", False) or
            os.environ.get("CONTAINERIZED") == "true" or
            os.environ.get("ENVIRONMENT") == "production" or
            (os.path.exists("/proc/1/cgroup") and "docker" in open("/proc/1/cgroup", "r").read())
        )
        
        if in_container:
            logger.info("检测到容器环境，启用增强的错误恢复机制和容器化适配")
    
    yield
    
    # 关闭阶段
    logger.info("正在关闭ESXI监控系统...")
    
    try:
        # 停止任务调度器
        logger.info("停止任务调度器...")
        task_scheduler.stop()
        # 重置启动状态标志，确保下次启动正常
        if hasattr(task_scheduler, '_started'):
            task_scheduler._started = False
        
        # 清理锁文件
        try:
            # 优先使用配置文件中的LOCK_DIR
            lock_dir = getattr(settings, "LOCK_DIR", None)
            if not lock_dir or not os.path.isabs(lock_dir):
                lock_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locks")
            lock_file_path = os.path.join(lock_dir, ".scheduler_lock")
            if os.path.exists(lock_file_path):
                # 检查是否是当前进程创建的锁文件
                try:
                    with open(lock_file_path, "r") as f:
                        lock_pid = f.read().strip()
                    if lock_pid == str(os.getpid()):
                        os.remove(lock_file_path)
                        logger.info("已清理调度器锁文件")
                    else:
                        logger.warning(f"锁文件由进程 {lock_pid} 创建，当前进程 {os.getpid()} 不删除")
                except:
                    # 如果读取失败，直接尝试删除
                    os.remove(lock_file_path)
                    logger.info("已尝试清理调度器锁文件")
        except Exception as lock_cleanup_e:
            logger.warning(f"清理锁文件时出错: {str(lock_cleanup_e)}")
        
        # 关闭数据库连接
        logger.info("关闭数据库连接...")
        close_connections()
        
        logger.info("系统已成功关闭")
    except Exception as e:
        logger.error(f"系统关闭过程中出现错误: {str(e)}")


# 创建FastAPI应用实例
app = FastAPI(
    title="ESXI监控系统API",
    description="用于监控ESXI主机和虚拟机的RESTful API",
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url=None,  # 我们将自定义文档路径
    redoc_url=None,
    openapi_url=f"{settings.API_PREFIX}/openapi.json"
)

# 配置CORS中间件
setup_cors(app)

# 注册API路由
app.include_router(api_router)

# 配置静态文件目录（如果存在）
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception as e:
    logger.warning(f"无法挂载静态文件目录: {str(e)}")


# 自定义文档路由
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """自定义Swagger UI页面"""
    return get_swagger_ui_html(
        openapi_url=f"{settings.API_PREFIX}/openapi.json",
        title="ESXI监控系统API文档",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css",
    )


@app.get("/docs/oauth2-redirect", include_in_schema=False)
async def swagger_ui_redirect():
    """Swagger UI OAuth2重定向"""
    return get_swagger_ui_oauth2_redirect_html()


@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    """Redoc文档页面"""
    return get_redoc_html(
        openapi_url=f"{settings.API_PREFIX}/openapi.json",
        title="ESXI监控系统API文档",
        redoc_js_url="https://unpkg.com/redoc@next/bundles/redoc.standalone.js",
    )


# ===== 根路由和健康检查 =====
@app.get("/", include_in_schema=False)
async def root():
    """
    系统根路径，返回完整的仪表盘界面
    """
    try:
        # 尝试读取index.html文件内容
        with open("index.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except Exception as e:
        logger.error(f"无法读取index.html文件: {str(e)}")
        # 如果读取失败，返回简单的欢迎信息作为备用
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>ESXI监控系统</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        max-width: 800px;
                        margin: 0 auto;
                        padding: 20px;
                        text-align: center;
                        color: #333;
                    }
                    h1 {
                        color: #2c3e50;
                    }
                    .links {
                        margin-top: 30px;
                    }
                    .links a {
                        display: inline-block;
                        margin: 10px;
                        padding: 10px 20px;
                        background-color: #3498db;
                        color: white;
                        text-decoration: none;
                        border-radius: 4px;
                        font-weight: bold;
                    }
                    .links a:hover {
                        background-color: #2980b9;
                    }
                    .status {
                        margin-top: 20px;
                        padding: 10px;
                        background-color: #ecf0f1;
                        border-radius: 4px;
                    }
                    .error {
                        margin-top: 20px;
                        padding: 10px;
                        background-color: #ffebee;
                        color: #c62828;
                        border-radius: 4px;
                    }
                </style>
            </head>
            <body>
                <h1>ESXI监控系统</h1>
                <p>版本: {{version}}</p>
                <div class="status">
                    <p>系统正在运行中</p>
                </div>
                <div class="error">
                    <p>警告: 无法加载完整仪表盘界面，请检查index.html文件是否存在</p>
                </div>
                <div class="links">
                    <a href="/docs">API文档 (Swagger)</a>
                    <a href="/redoc">API文档 (ReDoc)</a>
                </div>
            </body>
            </html>
            """.replace("{{version}}", settings.VERSION)
        )


def get_task_error_rate():
    """
    获取任务执行错误率
    """
    try:
        # 从数据库获取最近的任务执行统计信息
        from database import SessionLocal
        from sqlalchemy import text
        
        with SessionLocal() as db:
            try:
                # 尝试查询任务表中的错误统计
                # 这里假设存在一个task_executions表记录任务执行情况
                result = db.execute(text("""
                    SELECT 
                        COUNT(*) as total_tasks,
                        SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_tasks
                    FROM task_executions
                    WHERE created_at > NOW() - INTERVAL 1 HOUR
                """))
                
                stats = result.mappings().first()
                if stats and stats.total_tasks > 0:
                    return (stats.error_tasks / stats.total_tasks) * 100
            except Exception:
                # 如果任务表不存在或查询失败，返回None
                pass
        
        # 如果没有任务统计数据，返回None
        return None
    except Exception as e:
        logger.error(f"获取任务错误率失败: {str(e)}")
        return None


@app.get("/health", include_in_schema=False)
async def health():
    """
    增强的健康检查端点，支持容器化环境和详细的组件状态报告
    遵循容器健康检查最佳实践，返回适当的HTTP状态码
    """
    try:
        # 初始化状态标志
        critical_failures = 0
        warnings = 0
        
        # 检查是否在容器化环境中
        containerized = (os.environ.get("CONTAINERIZED", "false").lower() == "true" or 
                         getattr(settings, "CONTAINERIZED", False))
        
        # 检查数据库连接
        connection_status = health_check()
        
        # 检查任务调度器状态和详细信息
        scheduler_status = {
            "running": False,
            "in_container": containerized,
            "jobs_count": 0,
            "running_tasks": [],
            "task_metrics": {}
        }
        
        if hasattr(task_scheduler, 'scheduler'):
            scheduler_status["running"] = task_scheduler.scheduler.running
            # 获取调度器详细信息（如果有）
            if hasattr(task_scheduler, 'get_scheduler_info'):
                try:
                    scheduler_info = task_scheduler.get_scheduler_info()
                    scheduler_status.update({
                        "in_container": scheduler_info.get("in_container", containerized),
                        "jobs_count": scheduler_info.get("jobs_count", 0),
                        "running_tasks": scheduler_info.get("running_tasks", []),
                        "task_metrics": scheduler_info.get("task_metrics", {})
                    })
                except Exception as scheduler_info_e:
                    logger.warning(f"获取调度器信息失败: {str(scheduler_info_e)}")
                    warnings += 1
        
        # 修改健康状态判断逻辑，支持SQLite并区分关键/非关键组件
        # 数据库连接是关键组件
        is_db_connected = connection_status.get("database", False) or connection_status.get("mysql", False)
        if not is_db_connected:
            critical_failures += 1
        
        # 任务调度器在容器环境中是关键组件
        if not scheduler_status["running"] and not containerized:
            critical_failures += 1
        
        # InfluxDB和Redis为非关键组件，失败时发出警告
        if not connection_status.get("influxdb", False):
            warnings += 1
        if not connection_status.get("redis", False):
            warnings += 1
        
        # 判断总体健康状态
        if critical_failures > 0:
            overall_status = "unhealthy"
            status_code = 503  # Service Unavailable
        elif warnings > 0:
            overall_status = "degraded"
            status_code = 200  # 仍然返回200，因为容器健康检查通常只关心存活状态
        else:
            overall_status = "healthy"
            status_code = 200
        
        # 构造详细响应
        response = {
            "status": overall_status,
            "version": settings.VERSION,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "critical_failures": critical_failures,
            "warnings": warnings,
            "containerized": getattr(settings, "CONTAINERIZED", False) or \
                             os.environ.get("CONTAINERIZED") == "true" or \
                             os.environ.get("ENVIRONMENT") == "production",
            "components": {
                "database": {
                    "status": "connected" if is_db_connected else "disconnected",
                    "type": "mysql" if connection_status.get("mysql", False) else "sqlite"
                },
                "influxdb": {
                    "status": "connected" if connection_status.get("influxdb", False) else "disconnected"
                },
                "redis": {
                    "status": "connected" if connection_status.get("redis", False) else "disconnected"
                },
                "scheduler": scheduler_status
            }
        }
        
        # 检查任务错误率
        task_error_rate = get_task_error_rate()
        if task_error_rate is not None:
            if task_error_rate > 50:
                warnings += 1
                # 添加告警
                if "alerts" not in response:
                    response["alerts"] = []
                response["alerts"].append({
                    "component": "task.execution",
                    "severity": "warning",
                    "message": f"任务错误率过高: {task_error_rate:.2f}%"
                })
            # 添加任务错误率到响应中
            response["task_error_rate"] = task_error_rate
        
        # 返回带有适当状态码的响应
        # 在容器环境中，优化状态码处理：数据库连接正常时返回200，确保容器不会被错误重启
        if containerized:
            final_status_code = 200 if is_db_connected else 503
        else:
            final_status_code = status_code
            
        return JSONResponse(content=response, status_code=final_status_code)
        
    except Exception as e:
        logger.error(f"健康检查失败: {str(e)}", exc_info=True)
        # 发生异常时返回不健康状态
        # 在容器环境中提供更详细的错误信息，便于调试
        error_response = {
            "status": "unhealthy",
            "error": str(e) if containerized else "健康检查服务暂时不可用",
            "version": settings.VERSION,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        return JSONResponse(
            content=error_response,
            status_code=503
        )


# ===== 全局异常处理 =====
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    全局异常处理，捕获所有未处理的异常
    """
    logger.error(f"全局异常: {str(exc)}", exc_info=True)
    
    # 判断是否为开发环境
    is_development = settings.ENVIRONMENT == "development"
    
    # 根据环境返回不同详细程度的错误信息
    error_detail = str(exc) if is_development else "服务器内部错误"
    
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": error_detail,
            "code": 500,
            "environment": settings.ENVIRONMENT
        }
    )

# 从fastapi导入HTTPException以支持HTTP异常处理
from fastapi import HTTPException

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    HTTP异常处理
    """
    logger.info(f"HTTP异常: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.detail,
            "code": exc.status_code
        }
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """
    404错误处理
    """
    return JSONResponse(
        status_code=404,
        content={
            "success": False,
            "error": "请求的资源不存在",
            "code": 404,
            "path": request.url.path
        }
    )


# ===== 启动命令 =====
if __name__ == "__main__":
    """
    直接运行时启动应用服务器
    """
    # 打印启动信息
    logger.info(f"启动ESXI监控系统服务...")
    logger.info(f"监听地址: {settings.API_HOST}:{settings.API_PORT}")
    logger.info(f"API文档: http://{settings.API_HOST}:{settings.API_PORT}/docs")
    
    # 启动uvicorn服务器
    # 确定worker数量，考虑容器环境和调试模式
    import sys
    
    # 判断是否在容器环境中（使用多种检测方式）
    in_container = (
        getattr(settings, "CONTAINERIZED", False) or
        os.environ.get("CONTAINERIZED") == "true" or
        os.environ.get("ENVIRONMENT") == "production" or
        (os.path.exists("/proc/1/cgroup") and "docker" in open("/proc/1/cgroup", "r").read())
    )
    
    if in_container:
        logger.info("检测到容器环境，优化服务器配置")
        # 在容器环境中，通常建议worker数量为CPU核心数 + 1，但不超过API_WORKERS配置
        try:
            import multiprocessing
            cpu_count = multiprocessing.cpu_count()
            container_workers = min(cpu_count + 1, settings.API_WORKERS)
            logger.info(f"容器CPU核心数: {cpu_count}, 设置worker数量: {container_workers}")
        except Exception:
            container_workers = 2  # 保守设置
    
    # 配置启动参数
    uvicorn_config = {
        "host": settings.API_HOST,
        "port": settings.API_PORT,
        "reload": settings.API_DEBUG,
        "log_level": settings.LOG_LEVEL.lower(),
        "lifespan": "on"
    }
    
    if sys.platform == "win32" or settings.API_DEBUG:
        # Windows环境或调试模式下使用单进程
        logger.info(f"{'Windows' if sys.platform == 'win32' else '调试'}环境，使用单进程模式运行")
        uvicorn_config["workers"] = 1
    elif in_container:
        # 容器环境使用优化的worker数量
        uvicorn_config["workers"] = container_workers
    else:
        # 非Windows、非容器环境下使用配置的worker数量
        uvicorn_config["workers"] = settings.API_WORKERS
    
    # 添加额外的容器环境优化参数
    if in_container and not settings.API_DEBUG:
        logger.info("应用容器环境优化参数")
        uvicorn_config["access_log"] = False  # 在容器环境中禁用访问日志以提高性能
        uvicorn_config["proxy_headers"] = True  # 启用代理头支持
        uvicorn_config["timeout_keep_alive"] = 120  # 增加keep-alive超时以适应容器网络
    
    # 启动服务器
    logger.info(f"启动ESXI监控系统服务...")
    logger.info(f"监听地址: {uvicorn_config['host']}:{uvicorn_config['port']}")
    logger.info(f"API文档: http://{uvicorn_config['host']}:{uvicorn_config['port']}/docs")
    logger.info(f"Worker数量: {uvicorn_config['workers']}")
    
    uvicorn.run("main:app", **uvicorn_config)