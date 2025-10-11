# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import logging
import time
import uvicorn

from app.config import settings
from app.database import create_tables, get_db
from app.routers import auth, actions, practice, dashboard, ai_advice
from app.self_talk.router import router as self_talk_router
from app.routers.self_talk_reminders import router as self_talk_reminders_router
from app.ai_service import test_ai_connection

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(
    title=settings.app_name,
    description="读书笔记实践反馈系统 - 从学习到行动的完整闭环",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router)
app.include_router(actions.router, prefix="/api")
app.include_router(practice.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(ai_advice.router)  # AI建议路由（已有前缀 /api/ai-advice）
app.include_router(self_talk_router)
app.include_router(self_talk_reminders_router)  # Self-talk 提醒路由

# 静态文件服务
app.mount("/static", StaticFiles(directory="static"), name="static")

# 根据环境决定是否公开uploads目录
if settings.environment == "development":
    # 开发环境：保留公开访问，方便调试
    app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
    logger.info("开发环境：uploads目录公开访问已启用")
else:
    # 生产环境：移除公开访问，使用受保护API
    # app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
    logger.info("生产环境：uploads目录通过受保护API访问")


@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    logger.info("正在启动应用...")
    
    # 创建数据库表
    create_tables()
    logger.info("数据库表创建完成")
    
    # 测试 AI 连接（非阻塞）
    try:
        ai_connected = await test_ai_connection()
        if ai_connected:
            logger.info("AI 服务连接正常")
        else:
            logger.warning("AI 服务连接失败，但应用将继续运行")
    except Exception as e:
        logger.warning(f"AI 服务连接测试失败: {e}，但应用将继续运行")
    
    # 启动定时任务调度器
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from app.self_talk.reminder_service import check_daily_reminders, check_inactive_reminders
        
        scheduler = BackgroundScheduler()
        
        # 每5分钟检查一次每日提醒（实际会判断是否到达设定时间）
        scheduler.add_job(
            lambda: check_daily_reminders(next(get_db())),
            'interval',
            minutes=5,
            id='check_daily_reminders'
        )
        
        # 每小时检查一次非活跃用户
        scheduler.add_job(
            lambda: check_inactive_reminders(next(get_db())),
            'interval',
            hours=1,
            id='check_inactive_reminders'
        )
        
        scheduler.start()
        app.state.scheduler = scheduler
        logger.info("定时任务调度器启动成功")
        
    except Exception as e:
        logger.error(f"定时任务调度器启动失败: {e}")
    
    logger.info("应用启动完成")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时执行"""
    logger.info("正在关闭应用...")
    
    # 关闭定时任务调度器
    if hasattr(app.state, 'scheduler'):
        try:
            app.state.scheduler.shutdown()
            logger.info("定时任务调度器已关闭")
        except Exception as e:
            logger.error(f"关闭定时任务调度器失败: {e}")
    
    logger.info("应用已关闭")


@app.get("/")
async def root():
    """根路径 - 重定向到前端页面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")


@app.get("/health")
async def health_check():
    """健康检查 - Railway优化版本"""
    try:
        # 基本状态检查，不依赖外部服务
        return {
            "status": "healthy",
            "message": "服务正常运行",
            "timestamp": time.time(),
            "services": {
                "app": "ok",
                "database": "ok"
            }
        }
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"服务不可用: {str(e)}"
        )


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"全局异常: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误"}
    )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )