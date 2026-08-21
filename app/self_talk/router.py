# -*- coding: utf-8 -*-
"""
Self-talk API 路由
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional
import os
import uuid
import logging
from datetime import datetime, date
from zoneinfo import ZoneInfo

from app.database import get_db
from app.auth import get_current_user
from app.models import User, SelfTalk, SelfTalkPlaybackLog
from app.self_talk.schemas import (
    SelfTalkCreate,
    SelfTalkResponse,
    SelfTalkListResponse,
    SelfTalkTranscriptUpdate,
    PlaybackLogCreate,
    PlaybackLogResponse,
)
from app.config import settings
from app.self_talk.speech_recognition import transcribe_audio_file, is_speech_recognition_available

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/self_talks", tags=["self-talk"])

# 音频文件存储目录
UPLOAD_DIR = "uploads/self_talks"
ALLOWED_EXTENSIONS = {'.wav', '.mp3', '.m4a', '.ogg', '.webm', '.mp4'}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
CONTENT_TYPE_EXT = {
    'audio/mp4': '.m4a',
    'audio/x-m4a': '.m4a',
    'audio/m4a': '.m4a',
    'audio/aac': '.m4a',
    'audio/mpeg': '.mp3',
    'audio/mp3': '.mp3',
    'audio/wav': '.wav',
    'audio/x-wav': '.wav',
    'audio/wave': '.wav',
    'audio/webm': '.webm',
    'video/webm': '.webm',
    'audio/ogg': '.ogg',
    'audio/opus': '.ogg',
    'video/mp4': '.mp4',
}
AUDIO_MEDIA_TYPES = {
    '.wav': 'audio/wav',
    '.mp3': 'audio/mpeg',
    '.webm': 'audio/webm',
    '.ogg': 'audio/ogg',
    '.m4a': 'audio/mp4',
    '.mp4': 'audio/mp4',
}


def ensure_upload_dir():
    """确保上传目录存在"""
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def is_allowed_file(filename: str) -> bool:
    """检查文件扩展名是否允许"""
    return any(filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS)


def safe_audio_ext(filename: Optional[str], content_type: Optional[str]) -> str:
    """从文件名或 Content-Type 得到安全的小写扩展名；无法识别则返回空串。"""
    if filename:
        ext = os.path.splitext(filename)[1].lower()
        if ext in ALLOWED_EXTENSIONS:
            return ext
    if content_type:
        ct = content_type.split(";")[0].strip().lower()
        mapped = CONTENT_TYPE_EXT.get(ct)
        if mapped:
            return mapped
    return ""


def sniff_audio_ext(header: bytes) -> str:
    """文件名缺失或被手机改成无扩展名时，用文件头判断格式。"""
    if not header or len(header) < 12:
        return ""
    if header.startswith(b"ID3") or header[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xe3"}:
        return ".mp3"
    if header[4:8] == b"ftyp":
        brand = header[8:12]
        if brand in {b"M4A ", b"M4B ", b"M4P "}:
            return ".m4a"
        return ".mp4" if brand in {b"mp42", b"isom", b"iso2", b"mp41"} else ".m4a"
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return ".wav"
    if header.startswith(b"OggS"):
        return ".ogg"
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return ".webm"
    return ""


def get_audio_full_path(audio_path: str) -> str:
    """根据存储文件名构建完整路径"""
    return os.path.join(UPLOAD_DIR, os.path.basename(audio_path))


def parse_form_flag(value: Optional[str]) -> bool:
    """解析 multipart 里的开关。未传或 false/0 都视为关闭，避免把字符串 'false' 当成真。"""
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def usable_transcript(text: Optional[str]) -> Optional[str]:
    """过滤识别模块返回的失败提示，避免写进转写栏。"""
    if not text:
        return None
    transcript = text.strip()
    if not transcript:
        return None
    if transcript.startswith("语音识别失败") or transcript.startswith("语音识别结果为空"):
        return None
    return transcript


def audio_media_type(audio_path: str) -> str:
    ext = os.path.splitext(audio_path)[1].lower()
    return AUDIO_MEDIA_TYPES.get(ext, "application/octet-stream")


def to_self_talk_response(self_talk: SelfTalk) -> SelfTalkResponse:
    """ORM 转 API 响应（含最新 transcript）"""
    return SelfTalkResponse(
        id=self_talk.id,
        user_id=self_talk.user_id,
        action_id=self_talk.action_id,
        audio_path=self_talk.audio_path,
        transcript=self_talk.transcript,
        created_at=self_talk.created_at,
        updated_at=self_talk.updated_at,
    )


def delete_audio_file(audio_path: str) -> bool:
    """删除磁盘上的音频文件，成功或文件不存在时返回 True"""
    full_path = get_audio_full_path(audio_path)
    if not os.path.isfile(full_path):
        return True
    try:
        os.remove(full_path)
        logger.info(f"已删除音频文件: {full_path}")
        return True
    except OSError as e:
        logger.error(f"删除音频文件失败 {full_path}: {e}")
        return False


def save_audio_bytes(content: bytes, user_id: int, file_extension: str) -> str:
    """保存音频字节到本地。磁盘文件名只用 uuid。"""
    if not content:
        raise HTTPException(status_code=400, detail="音频文件为空")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="文件大小不能超过 50MB")

    unique_filename = f"{user_id}_{uuid.uuid4().hex}{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    try:
        with open(file_path, "wb") as buffer:
            buffer.write(content)
    except OSError as e:
        logger.exception("保存音频文件失败: %s", file_path)
        raise HTTPException(status_code=500, detail="无法保存音频文件，请稍后重试") from e

    logger.info("音频文件保存成功: %s (%s bytes)", file_path, len(content))
    return unique_filename


@router.post("/", response_model=SelfTalkResponse)
async def upload_self_talk(
    file: UploadFile = File(...),
    action_id: Optional[int] = Form(None),
    recognize_text: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    上传 Self-talk 音频文件。默认只保存音频；recognize_text=true 时才识别文字。
    """
    try:
        content = await file.read()
        file_ext = (
            safe_audio_ext(file.filename, file.content_type)
            or sniff_audio_ext(content[:64])
        )
        logger.info(
            "收到 Self-talk 上传: user=%s filename=%r content_type=%s size=%s ext=%s",
            current_user.id,
            file.filename,
            file.content_type,
            len(content) if content else 0,
            file_ext,
        )
        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型。支持的格式: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )

        ensure_upload_dir()
        audio_path = save_audio_bytes(content, current_user.id, file_ext)
        actual_file_path = os.path.join(UPLOAD_DIR, audio_path)
        want_transcript = parse_form_flag(recognize_text)

        if action_id:
            from app.models import Action
            action = db.query(Action).filter(
                Action.id == action_id,
                Action.user_id == current_user.id,
                Action.deleted_at.is_(None)
            ).first()
            if not action:
                raise HTTPException(status_code=404, detail="指定的行动项不存在")

        # 先落库，保证上传后立刻能在历史里播放；识别失败或超时也不能吞掉音频
        self_talk = SelfTalk(
            user_id=current_user.id,
            action_id=action_id,
            audio_path=audio_path,
            transcript=None,
        )
        db.add(self_talk)
        db.commit()
        db.refresh(self_talk)
        logger.info("Self-talk 创建成功: ID=%s recognize_text=%s", self_talk.id, want_transcript)

        if want_transcript:
            try:
                if not is_speech_recognition_available():
                    logger.warning("语音识别服务不可用，跳过转写")
                else:
                    logger.info("开始语音识别: %s", actual_file_path)
                    transcript = usable_transcript(transcribe_audio_file(actual_file_path))
                    if transcript:
                        self_talk.transcript = transcript
                        self_talk.updated_at = datetime.utcnow()
                        db.commit()
                        db.refresh(self_talk)
                        logger.info("语音识别成功: %s", transcript[:200])
                    else:
                        logger.warning("语音识别无结果（音频已保存，可播放）")
            except Exception:
                logger.exception("语音识别异常，音频仍可播放")

        return to_self_talk_response(self_talk)

    except HTTPException:
        raise
    except OSError as e:
        logger.exception("上传 Self-talk 失败（无法写入文件）: %s", e)
        raise HTTPException(status_code=500, detail="无法保存音频文件，请稍后重试")
    except Exception as e:
        logger.exception("上传 Self-talk 失败: %s", e)
        raise HTTPException(status_code=500, detail="上传失败，请稍后重试")


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
            self_talk_responses.append(to_self_talk_response(self_talk))
        
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
        
        return to_self_talk_response(self_talk)
        
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
        
        # 软删除并移除磁盘文件
        self_talk.deleted_at = datetime.utcnow()
        db.commit()
        delete_audio_file(self_talk.audio_path)
        
        logger.info(f"Self-talk 删除成功: ID={self_talk_id}")
        
        return {"message": "Self-talk 删除成功"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除 Self-talk 失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.patch("/{self_talk_id}", response_model=SelfTalkResponse)
async def update_self_talk_transcript(
    self_talk_id: int,
    body: SelfTalkTranscriptUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新 Self-talk 转写文字（支持修改识别结果、添加标点）"""
    try:
        self_talk = db.query(SelfTalk).filter(
            SelfTalk.id == self_talk_id,
            SelfTalk.user_id == current_user.id,
            SelfTalk.deleted_at.is_(None),
        ).first()

        if not self_talk:
            raise HTTPException(status_code=404, detail="Self-talk 记录不存在")

        transcript = body.transcript.strip()
        if not transcript:
            raise HTTPException(status_code=400, detail="转写文字不能为空")

        self_talk.transcript = transcript
        self_talk.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(self_talk)

        logger.info(
            "Self-talk 转写已保存到数据库: id=%s user_id=%s transcript=%s",
            self_talk_id,
            current_user.id,
            transcript[:200] + ("…" if len(transcript) > 200 else ""),
        )

        return to_self_talk_response(self_talk)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新 Self-talk 转写失败: {e}")
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
        actual_file_path = get_audio_full_path(self_talk.audio_path)
        
        if not os.path.isfile(actual_file_path):
            logger.error("音频文件不存在: %s", actual_file_path)
            raise HTTPException(status_code=404, detail="音频文件不存在")

        filename = os.path.basename(self_talk.audio_path)
        return FileResponse(
            actual_file_path,
            media_type=audio_media_type(self_talk.audio_path),
            filename=filename,
            content_disposition_type="inline",
            headers={
                "Cache-Control": "private, max-age=3600",
                "Accept-Ranges": "bytes",
                "X-Content-Type-Options": "nosniff",
            },
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取音频文件失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


def beijing_today() -> date:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


@router.post("/playback-log", response_model=PlaybackLogResponse, status_code=201)
async def log_playback(
    body: PlaybackLogCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """记录 Self-talk 播放（用于今日概况统计）"""
    self_talk = db.query(SelfTalk).filter(
        SelfTalk.id == body.self_talk_id,
        SelfTalk.user_id == current_user.id,
        SelfTalk.deleted_at.is_(None),
    ).first()
    if not self_talk:
        raise HTTPException(status_code=404, detail="Self-talk 记录不存在")

    row = SelfTalkPlaybackLog(
        user_id=current_user.id,
        self_talk_id=body.self_talk_id,
        play_date=beijing_today(),
        duration_seconds=body.duration_seconds,
        loops_completed=body.loops_completed,
        loop_mode=body.loop_mode,
        loop_target=body.loop_target,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "Self-talk 播放记录: user=%s talk=%s duration=%ss loops=%s",
        current_user.id,
        body.self_talk_id,
        body.duration_seconds,
        body.loops_completed,
    )
    return row


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
