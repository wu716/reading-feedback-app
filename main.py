# -*- coding: utf-8 -*-
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
import logging
import os
import uvicorn

from app.config import settings
from app.database import ensure_schema, get_db
from app.legacy_origin import canonical_url, is_legacy_singapore, keep_on_legacy_origin
from app.scheduler import start_scheduler
from app.routers import auth, actions, practice, dashboard, ai_advice, today, app_download, owner, schedule, time_log, capture
from app.self_talk.router import router as self_talk_router
from app.routers.self_talk_reminders import router as self_talk_reminders_router
from app.ai_service import test_ai_connection

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动 / 关闭"""
    logger.info("正在启动应用...")
    os.makedirs("uploads/self_talks", exist_ok=True)
    os.makedirs("backups", exist_ok=True)
    ensure_schema()
    logger.info("数据库表创建完成")
    if settings.is_production and settings.is_insecure_secret:
        logger.error("生产环境 SECRET_KEY 过弱或仍是默认值，请立刻换成至少 32 位随机串")
    if settings.is_production and settings.CORS_ORIGINS == "*":
        logger.warning("生产环境 CORS_ORIGINS=* ，上线后应改成你的域名")
    start_scheduler(app)
    logger.info("应用启动完成")
    try:
        yield
    finally:
        logger.info("正在关闭应用...")
        if hasattr(app.state, "scheduler"):
            try:
                app.state.scheduler.shutdown(wait=False)
                logger.info("定时任务调度器已关闭")
            except Exception as e:
                logger.error(f"关闭定时任务调度器失败: {e}")
        logger.info("应用已关闭")


_docs_enabled = None if settings.is_production else "/docs"
_redoc_enabled = None if settings.is_production else "/redoc"
_openapi_enabled = None if settings.is_production else "/openapi.json"

# 创建 FastAPI 应用
app = FastAPI(
    title=settings.app_name,
    description="读书笔记实践反馈系统 - 从学习到行动的完整闭环",
    version="1.0.0",
    docs_url=_docs_enabled,
    redoc_url=_redoc_enabled,
    openapi_url=_openapi_enabled,
    lifespan=lifespan,
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


STATIC_UI_VERSION = "20260920later1"
NO_STORE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


def stale_ui_redirect(request: Request, path: str) -> RedirectResponse | None:
    """Old shells restore ?ui=18 and skip new HTML; any missing/old v must refresh."""
    if request.query_params.get("v") == STATIC_UI_VERSION:
        return None
    kept = [
        (key, value)
        for key, value in request.query_params.multi_items()
        if key not in ("v", "ui")
    ]
    url = f"{path}?v={STATIC_UI_VERSION}"
    if kept:
        extra = "&".join(f"{key}={value}" for key, value in kept)
        url = f"{url}&{extra}"
    return RedirectResponse(url=url, headers=NO_STORE_HEADERS)


@app.middleware("http")
async def redirect_legacy_singapore(request: Request, call_next):
    """1.3.4 仍打开新加坡。页面跳香港；健康检查、API、更新信息与 APK 留在旧机。"""
    if not is_legacy_singapore(request):
        return await call_next(request)
    path = request.url.path or "/"
    if keep_on_legacy_origin(path):
        return await call_next(request)
    if path in ("/", "/static/index.html"):
        dest = canonical_url("/", f"v={STATIC_UI_VERSION}")
    else:
        dest = canonical_url(path, request.url.query)
    return RedirectResponse(url=dest, status_code=302, headers=NO_STORE_HEADERS)


@app.middleware("http")
async def disable_page_cache(request: Request, call_next):
    """WebView 常把旧 HTML/JS 存下来，页面资源一律禁止缓存。"""
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".html", ".js", ".css")):
        response.headers["Cache-Control"] = NO_STORE_HEADERS["Cache-Control"]
        response.headers["Pragma"] = NO_STORE_HEADERS["Pragma"]
        response.headers["Expires"] = NO_STORE_HEADERS["Expires"]
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=(self)"
    return response

# 注册路由
app.include_router(auth.router)
app.include_router(owner.router)
app.include_router(actions.router, prefix="/api")
app.include_router(practice.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(ai_advice.router)  # AI建议路由（已有前缀 /api/ai-advice）
app.include_router(self_talk_router)
app.include_router(self_talk_reminders_router)  # Self-talk 提醒路由
app.include_router(today.router, prefix="/api")
app.include_router(schedule.router, prefix="/api")
app.include_router(time_log.router, prefix="/api")
app.include_router(capture.router, prefix="/api")
app.include_router(app_download.router)


@app.get("/static/index.html")
async def indexed_home(request: Request):
    """未带版本号的首页会 307 到新地址，逼 WebView 丢掉旧 HTML。

    不要带 Clear-Site-Data：Chromium/Android WebView 会因此中断进行中的
    fetch 和 iframe 导航，表现为添加待办失败 + net::ERR_CONNECTION_ABORTED。
    """
    redirected = stale_ui_redirect(request, "/static/index.html")
    if redirected is not None:
        return redirected
    return FileResponse(
        "static/index.html",
        media_type="text/html",
        headers=NO_STORE_HEADERS,
    )


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


@app.get("/")
async def root(request: Request):
    """未带当前 UI 版本号时 307 到新地址，逼 WebView 丢掉根路径上的旧 HTML。"""
    redirected = stale_ui_redirect(request, "/")
    if redirected is not None:
        return redirected
    return FileResponse(
        "static/index.html",
        media_type="text/html",
        headers=NO_STORE_HEADERS,
    )


@app.get("/health")
async def health_check():
    logger.info("健康检查被调用")
    return {"status": "healthy", "message": "服务就绪"}


@app.get("/api/time")
async def get_server_time():
    """返回服务器当前时间，供前端联网校准时钟（北京时间）"""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    now_utc = datetime.now(timezone.utc)
    beijing = now_utc.astimezone(ZoneInfo("Asia/Shanghai"))
    return {
        "timestamp_ms": int(now_utc.timestamp() * 1000),
        "utc_iso": now_utc.isoformat(),
        "beijing_iso": beijing.isoformat(),
        "beijing_formatted": beijing.strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": "Asia/Shanghai",
    }


# 请求验证错误处理
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """处理请求验证错误，返回友好的错误信息"""
    errors = exc.errors()
    error_messages = []
    
    for error in errors:
        field = ".".join(str(loc) for loc in error["loc"])
        error_type = error["type"]
        error_msg = error.get("msg", "")
        
        # 翻译错误信息
        if error_type == "value_error.missing":
            error_messages.append(f"缺少必填字段: {field}")
        elif error_type == "value_error.any_str.min_length":
            # 提取最小长度要求
            if "min_length" in str(error_msg):
                error_messages.append(f"{field} 长度不足：{error_msg}")
            else:
                error_messages.append(f"{field} 长度不符合要求")
        elif error_type == "value_error.any_str.max_length":
            error_messages.append(f"{field} 长度过长：{error_msg}")
        elif error_type == "type_error.str":
            error_messages.append(f"{field} 必须是字符串类型")
        else:
            error_messages.append(f"{field}: {error_msg}")
    
    detail_message = "；".join(error_messages) if error_messages else "请求数据验证失败"
    
    logger.warning(f"请求验证失败: {detail_message}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": detail_message,
            "errors": errors
        }
    )


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    path = str(getattr(getattr(request, "url", None), "path", "") or "")
    logger.error("全局异常 path=%s: %s", path, exc, exc_info=True)
    detail = "上传失败，请稍后重试" if "self_talks" in path else "服务器内部错误"
    return JSONResponse(
        status_code=500,
        content={"detail": detail}
    )


if __name__ == "__main__":
    # reload=True 时 Ctrl+C 可能出现 asyncio.CancelledError 日志，属正常停止行为
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
