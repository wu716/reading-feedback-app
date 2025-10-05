# -*- coding: utf-8 -*-
"""
Self-talk API 路由
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
import os
import uuid
import logging
from datetime import datetime

from app.database import get_db
from app.auth import get_current_user
from app.models import User, SelfTalk
from app.self_talk.schemas import SelfTalkCreate, SelfTalkResponse, SelfTalkListResponse
from app.config import settings
from app.self_talk.speech_recognition import transcribe_audio_file, is_speech_recognition_available, is_valid_wav_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/self_talks", tags=["self-talk"])

# 音频文件存储目录
UPLOAD_DIR = "uploads/self_talks"
ALLOWED_EXTENSIONS = {'.wav', '.mp3', '.m4a', '.ogg', '.webm', '.mp4'}


def ensure_upload_dir():
    """确保上传目录存在"""
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def is_allowed_file(filename: str) -> bool:
    """检查文件扩展名是否允许"""
    return any(filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS)


def save_audio_file(file: UploadFile, user_id: int) -> str:
    """
    保存音频文件到本地
    
    Args:
        file: 上传的文件
        user_id: 用户ID
        
    Returns:
        保存的文件路径
    """
    # 生成唯一文件名
    file_extension = os.path.splitext(file.filename)[1].lower()
    if not file_extension:
        file_extension = '.wav'  # 默认扩展名
    
    unique_filename = f"{user_id}_{uuid.uuid4().hex}{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    
    # 保存文件
    with open(file_path, "wb") as buffer:
        content = file.file.read()
        buffer.write(content)
    
    logger.info(f"音频文件保存成功: {file_path}")
    # 返回相对路径，不暴露完整文件路径
    return unique_filename


@router.post("/", response_model=SelfTalkResponse)
async def upload_self_talk(
    file: UploadFile = File(...),
    action_id: Optional[int] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    上传 Self-talk 音频文件
    
    Args:
        file: 音频文件
        action_id: 可选的关联行动项ID
        current_user: 当前用户
        db: 数据库会话
        
    Returns:
        创建的 Self-talk 记录
    """
    try:
        # 检查文件类型
        if not file.filename or not is_allowed_file(file.filename):
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型。支持的格式: {', '.join(ALLOWED_EXTENSIONS)}"
            )
        
        # 检查文件大小 (限制为 50MB)
        file.file.seek(0, 2)  # 移动到文件末尾
        file_size = file.file.tell()
        file.file.seek(0)  # 重置到文件开头
        
        if file_size > 50 * 1024 * 1024:  # 50MB
            raise HTTPException(status_code=400, detail="文件大小不能超过 50MB")
        
        # 确保上传目录存在
        ensure_upload_dir()
        
        # 保存音频文件
        audio_path = save_audio_file(file, current_user.id)
        
        # 验证音频文件格式
        actual_file_path = os.path.join(UPLOAD_DIR, audio_path)
        logger.info(f"验证音频文件格式: {actual_file_path}")
        if not is_valid_wav_file(actual_file_path):
            logger.warning(f"音频文件格式可能有问题，但继续处理: {actual_file_path}")
        
        # 语音识别
        transcript = None
        if is_speech_recognition_available():
            logger.info("开始语音识别...")
            transcript = transcribe_audio_file(actual_file_path)
            if transcript:
                logger.info(f"语音识别成功: {transcript}")
            else:
                logger.warning("语音识别失败或结果为空")
        else:
            logger.warning("语音识别服务不可用")
        
        # 验证 action_id（如果提供）
        if action_id:
            from app.models import Action
            action = db.query(Action).filter(
                Action.id == action_id,
                Action.user_id == current_user.id,
                Action.deleted_at.is_(None)
            ).first()
            if not action:
                raise HTTPException(status_code=404, detail="指定的行动项不存在")
        
        # 创建数据库记录
        self_talk = SelfTalk(
            user_id=current_user.id,
            action_id=action_id,
            audio_path=audio_path,
            transcript=transcript
        )
        
        db.add(self_talk)
        db.commit()
        db.refresh(self_talk)
        
        logger.info(f"Self-talk 创建成功: ID={self_talk.id}")
        
        return SelfTalkResponse(
            id=self_talk.id,
            user_id=self_talk.user_id,
            action_id=self_talk.action_id,
            audio_path=self_talk.audio_path,
            transcript=self_talk.transcript,
            created_at=self_talk.created_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传 Self-talk 失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/", response_model=SelfTalkListResponse)
async def get_self_talks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 20
):
    """
    获取用户的 Self-talk 列表
    
    Args:
        current_user: 当前用户
        db: 数据库会话
        skip: 跳过的记录数
        limit: 限制返回的记录数
        
    Returns:
        Self-talk 列表
    """
    try:
        # 查询用户的 Self-talk 记录
        query = db.query(SelfTalk).filter(
            SelfTalk.user_id == current_user.id,
            SelfTalk.deleted_at.is_(None)
        ).order_by(SelfTalk.created_at.desc())
        
        # 获取总数
        total = query.count()
        
        # 分页查询
        self_talks = query.offset(skip).limit(limit).all()
        
        # 转换为响应格式
        self_talk_responses = []
        for self_talk in self_talks:
            self_talk_responses.append(SelfTalkResponse(
                id=self_talk.id,
                user_id=self_talk.user_id,
                action_id=self_talk.action_id,
                audio_path=self_talk.audio_path,
                transcript=self_talk.transcript,
                created_at=self_talk.created_at
            ))
        
        return SelfTalkListResponse(
            self_talks=self_talk_responses,
            total=total
        )
        
    except Exception as e:
        logger.error(f"获取 Self-talk 列表失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/{self_talk_id}", response_model=SelfTalkResponse)
async def get_self_talk(
    self_talk_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取单个 Self-talk 记录
    
    Args:
        self_talk_id: Self-talk ID
        current_user: 当前用户
        db: 数据库会话
        
    Returns:
        Self-talk 记录
    """
    try:
        self_talk = db.query(SelfTalk).filter(
            SelfTalk.id == self_talk_id,
            SelfTalk.user_id == current_user.id,
            SelfTalk.deleted_at.is_(None)
        ).first()
        
        if not self_talk:
            raise HTTPException(status_code=404, detail="Self-talk 记录不存在")
        
        return SelfTalkResponse(
            id=self_talk.id,
            user_id=self_talk.user_id,
            action_id=self_talk.action_id,
            audio_path=self_talk.audio_path,
            transcript=self_talk.transcript,
            created_at=self_talk.created_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取 Self-talk 失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.delete("/{self_talk_id}")
async def delete_self_talk(
    self_talk_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    删除 Self-talk 记录（软删除）
    
    Args:
        self_talk_id: Self-talk ID
        current_user: 当前用户
        db: 数据库会话
        
    Returns:
        删除结果
    """
    try:
        self_talk = db.query(SelfTalk).filter(
            SelfTalk.id == self_talk_id,
            SelfTalk.user_id == current_user.id,
            SelfTalk.deleted_at.is_(None)
        ).first()
        
        if not self_talk:
            raise HTTPException(status_code=404, detail="Self-talk 记录不存在")
        
        # 软删除
        self_talk.deleted_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"Self-talk 删除成功: ID={self_talk_id}")
        
        return {"message": "Self-talk 删除成功"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除 Self-talk 失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/{self_talk_id}/audio")
async def get_audio_file(
    self_talk_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取音频文件（带访问控制）
    """
    try:
        # 验证用户是否有权限访问该音频文件
        self_talk = db.query(SelfTalk).filter(
            SelfTalk.id == self_talk_id,
            SelfTalk.user_id == current_user.id,
            SelfTalk.deleted_at.is_(None)
        ).first()
        
        if not self_talk:
            raise HTTPException(status_code=404, detail="Self-talk 记录不存在")
        
        # 构建实际文件路径
        actual_file_path = os.path.join(UPLOAD_DIR, self_talk.audio_path)
        
        if not os.path.exists(actual_file_path):
            raise HTTPException(status_code=404, detail="音频文件不存在")
        
        # 返回文件流
        def iterfile():
            with open(actual_file_path, "rb") as file_like:
                yield from file_like
        
        # 根据文件扩展名设置媒体类型
        file_ext = os.path.splitext(self_talk.audio_path)[1].lower()
        media_type = {
            '.wav': 'audio/wav',
            '.mp3': 'audio/mpeg',
            '.webm': 'audio/webm',
            '.ogg': 'audio/ogg',
            '.m4a': 'audio/mp4',
            '.mp4': 'audio/mp4'
        }.get(file_ext, 'audio/wav')
        
        return StreamingResponse(
            iterfile(),
            media_type=media_type,
            headers={
                "Content-Disposition": f"inline; filename={self_talk.audio_path}",
                "Cache-Control": "private, max-age=3600"  # 1小时缓存
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取音频文件失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/health/recognition")
async def check_speech_recognition_health():
    """
    检查语音识别服务状态
    
    Returns:
        语音识别服务状态
    """
    try:
        is_available = is_speech_recognition_available()
        
        return {
            "speech_recognition_available": is_available,
            "message": "语音识别服务正常" if is_available else "语音识别服务不可用"
        }
        
    except Exception as e:
        logger.error(f"检查语音识别服务状态失败: {e}")
        return {
            "speech_recognition_available": False,
            "message": f"检查语音识别服务状态失败: {str(e)}"
        }
