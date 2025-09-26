# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import logging
import uvicorn

from app.config import settings
from app.database import create_tables
from app.routers import auth, actions, practice, dashboard
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
app.include_router(actions.router)
app.include_router(practice.router)
app.include_router(dashboard.router)

# 静态文件服务
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    logger.info("正在启动应用...")
    
    # 创建数据库表
    create_tables()
    logger.info("数据库表创建完成")
    
    # 测试 AI 连接
    ai_connected = await test_ai_connection()
    if ai_connected:
        logger.info("AI 服务连接正常")
    else:
        logger.error("AI 服务连接失败，应用无法正常工作")
        raise Exception("AI 服务连接失败")
    
    logger.info("应用启动完成")


@app.get("/")
async def root():
    """根路径 - 重定向到前端页面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": "2024-01-01T00:00:00Z",
        "environment": settings.environment
    }


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
        reload=True,  # 可以直接写 True，方便开发
        log_level="info"
    )
