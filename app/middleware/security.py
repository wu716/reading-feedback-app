# 增强安全中间件
from fastapi import Request, HTTPException
import os
import re

class EnhancedSecurityMiddleware:
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            request = Request(scope, receive)
            
            # 1. 生产环境阻止开发路由
            if request.url.path.startswith("/dev") and os.getenv("ENV") == "production":
                raise HTTPException(status_code=404, detail="Not Found")
            
            # 2. 防止路径遍历攻击
            if ".." in request.url.path or "//" in request.url.path:
                raise HTTPException(status_code=400, detail="Invalid path")
            
            # 3. 检查敏感路径访问
            sensitive_paths = ["/admin", "/internal", "/config"]
            for path in sensitive_paths:
                if request.url.path.startswith(path) and os.getenv("ENV") == "production":
                    raise HTTPException(status_code=404, detail="Not Found")
        
        return await self.app(scope, receive, send)
