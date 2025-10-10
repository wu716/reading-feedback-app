from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from typing import List, Optional
import uuid
import json
import asyncio
from datetime import datetime

from app.database import get_db
from app.models import User, Action, AIAdviceSession, AIAdviceMessage, PracticeLog
from app.schemas import (
    AIAdviceSessionCreate, AIAdviceSessionResponse,
    AIAdviceMessageCreate, AIAdviceMessageResponse,
    AIAdviceChatRequest, AIAdviceChatResponse,
    AIModelType, MessageRole
)
from app.auth import get_current_active_user
from app.ai_service import call_deepseek_api, generate_action_advice

router = APIRouter(prefix="/api/ai-advice", tags=["AI建议"])


@router.post("/sessions", response_model=AIAdviceSessionResponse)
async def create_advice_session(
    session_data: AIAdviceSessionCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """创建AI建议会话"""
    
    # 验证行动项是否存在且属于当前用户
    action = db.query(Action).filter(
        Action.id == session_data.action_id,
        Action.user_id == current_user.id,
        Action.deleted_at.is_(None)
    ).first()
    
    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="行动项不存在"
        )
    
    # 生成会话ID
    session_id = str(uuid.uuid4())
    
    # 创建会话
    advice_session = AIAdviceSession(
        session_id=session_id,
        user_id=current_user.id,
        action_id=session_data.action_id,
        model_type=session_data.model_type.value,
        web_search_enabled=session_data.web_search_enabled
    )
    
    db.add(advice_session)
    db.commit()
    db.refresh(advice_session)
    
    return advice_session


@router.get("/sessions/{action_id}", response_model=List[AIAdviceSessionResponse])
async def get_advice_sessions(
    action_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取指定行动项的所有AI建议会话"""
    
    # 验证行动项是否存在且属于当前用户
    action = db.query(Action).filter(
        Action.id == action_id,
        Action.user_id == current_user.id,
        Action.deleted_at.is_(None)
    ).first()
    
    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="行动项不存在"
        )
    
    # 获取会话列表
    sessions = db.query(AIAdviceSession).filter(
        AIAdviceSession.action_id == action_id,
        AIAdviceSession.user_id == current_user.id,
        AIAdviceSession.deleted_at.is_(None)
    ).order_by(desc(AIAdviceSession.created_at)).all()
    
    return sessions


@router.get("/sessions/{session_id}/messages", response_model=List[AIAdviceMessageResponse])
async def get_session_messages(
    session_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取会话的所有消息"""
    
    # 验证会话是否存在且属于当前用户
    session = db.query(AIAdviceSession).filter(
        AIAdviceSession.session_id == session_id,
        AIAdviceSession.user_id == current_user.id,
        AIAdviceSession.deleted_at.is_(None)
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在"
        )
    
    # 获取消息列表
    messages = db.query(AIAdviceMessage).filter(
        AIAdviceMessage.session_id == session.id,
        AIAdviceMessage.deleted_at.is_(None)
    ).order_by(AIAdviceMessage.created_at).all()
    
    return messages


@router.post("/sessions/{session_id}/chat", response_model=AIAdviceChatResponse)
async def chat_with_ai(
    session_id: str,
    chat_request: AIAdviceChatRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """与AI进行对话"""
    
    # 验证会话是否存在且属于当前用户
    session = db.query(AIAdviceSession).filter(
        AIAdviceSession.session_id == session_id,
        AIAdviceSession.user_id == current_user.id,
        AIAdviceSession.deleted_at.is_(None)
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在"
        )
    
    # 更新会话配置（如果提供）
    if chat_request.model_type:
        session.model_type = chat_request.model_type.value
    if chat_request.web_search_enabled is not None:
        session.web_search_enabled = chat_request.web_search_enabled
    
    # 保存用户消息
    user_message = AIAdviceMessage(
        session_id=session.id,
        role=MessageRole.USER.value,
        content=chat_request.message
    )
    
    db.add(user_message)
    db.commit()
    db.refresh(user_message)
    
    # 获取行动项和实践反馈信息
    action = db.query(Action).filter(Action.id == session.action_id).first()
    practice_logs = db.query(PracticeLog).filter(
        PracticeLog.action_id == session.action_id,
        PracticeLog.deleted_at.is_(None)
    ).order_by(desc(PracticeLog.created_at)).limit(5).all()
    
    # 构建上下文
    context = build_action_context(action, practice_logs)
    
    # 获取历史消息
    history_messages = db.query(AIAdviceMessage).filter(
        AIAdviceMessage.session_id == session.id,
        AIAdviceMessage.deleted_at.is_(None)
    ).order_by(AIAdviceMessage.created_at).limit(10).all()
    
    # 构建对话历史
    conversation_history = []
    for msg in history_messages:
        conversation_history.append({
            "role": msg.role,
            "content": msg.content
        })
    
    # 调用AI服务
    try:
        ai_response = await generate_ai_response(
            user_message=chat_request.message,
            context=context,
            conversation_history=conversation_history,
            model_type=session.model_type,
            web_search_enabled=session.web_search_enabled
        )
        
        # 保存AI回复
        ai_message = AIAdviceMessage(
            session_id=session.id,
            role=MessageRole.ASSISTANT.value,
            content=ai_response["content"],
            thinking_process=ai_response.get("thinking_process"),
            web_search_results=ai_response.get("web_search_results"),
            token_count=ai_response.get("token_count"),
            model_used=session.model_type
        )
        
        db.add(ai_message)
        
        # 更新会话的最后消息时间
        session.last_message_at = datetime.utcnow()
        
        db.commit()
        db.refresh(ai_message)
        
        return AIAdviceChatResponse(
            message=ai_message,
            thinking_process=ai_response.get("thinking_process"),
            web_search_results=ai_response.get("web_search_results")
        )
        
    except Exception as e:
        # 保存错误消息
        error_message = AIAdviceMessage(
            session_id=session.id,
            role=MessageRole.ASSISTANT.value,
            content=f"抱歉，我遇到了一些问题：{str(e)}"
        )
        
        db.add(error_message)
        db.commit()
        db.refresh(error_message)
        
        return AIAdviceChatResponse(message=error_message)


@router.post("/sessions/{session_id}/chat/stream")
async def chat_with_ai_stream(
    session_id: str,
    chat_request: AIAdviceChatRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """与AI进行流式对话（用于实时显示思考过程）"""
    
    # 验证会话是否存在且属于当前用户
    session = db.query(AIAdviceSession).filter(
        AIAdviceSession.session_id == session_id,
        AIAdviceSession.user_id == current_user.id,
        AIAdviceSession.deleted_at.is_(None)
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在"
        )
    
    # 保存用户消息
    user_message = AIAdviceMessage(
        session_id=session.id,
        role=MessageRole.USER.value,
        content=chat_request.message
    )
    
    db.add(user_message)
    db.commit()
    db.refresh(user_message)
    
    # 获取行动项和实践反馈信息
    action = db.query(Action).filter(Action.id == session.action_id).first()
    practice_logs = db.query(PracticeLog).filter(
        PracticeLog.action_id == session.action_id,
        PracticeLog.deleted_at.is_(None)
    ).order_by(desc(PracticeLog.created_at)).limit(5).all()
    
    # 构建上下文
    context = build_action_context(action, practice_logs)
    
    # 获取历史消息
    history_messages = db.query(AIAdviceMessage).filter(
        AIAdviceMessage.session_id == session.id,
        AIAdviceMessage.deleted_at.is_(None)
    ).order_by(AIAdviceMessage.created_at).limit(10).all()
    
    # 构建对话历史
    conversation_history = []
    for msg in history_messages:
        conversation_history.append({
            "role": msg.role,
            "content": msg.content
        })
    
    # 流式响应生成器
    async def generate_stream():
        try:
            async for chunk in generate_ai_response_stream(
                user_message=chat_request.message,
                context=context,
                conversation_history=conversation_history,
                model_type=session.model_type,
                web_search_enabled=session.web_search_enabled
            ):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            
            # 发送结束信号
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
            
        except Exception as e:
            error_chunk = {
                "type": "error",
                "content": f"抱歉，我遇到了一些问题：{str(e)}"
            }
            yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/plain",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


def build_action_context(action: Action, practice_logs: List[PracticeLog]) -> str:
    """构建行动项上下文"""
    context = f"""
行动项信息：
- 行动内容：{action.action_text}
- 行动类型：{'习惯养成型' if action.action_type == 'habit' else '情境触发型'}
- 频率：{action.frequency}
- 标签：{json.loads(action.tags) if action.tags else []}
- 来源：{action.book_title}
- 原文：{action.source_excerpt}
"""
    
    if practice_logs:
        context += "\n最近的实践反馈：\n"
        for log in practice_logs:
            context += f"- 日期：{log.date}，结果：{log.result}，评分：{log.rating}/5\n"
            if log.notes:
                context += f"  反馈：{log.notes}\n"
    
    return context


async def generate_ai_response(
    user_message: str,
    context: str,
    conversation_history: List[dict],
    model_type: str,
    web_search_enabled: bool
) -> dict:
    """生成AI响应"""
    
    # 构建系统提示
    system_prompt = f"""你是一个专业的行动建议助手。请基于用户的行动项和实践反馈，提供个性化的建议和指导。

{context}

请根据用户的提问，结合上述行动项信息和实践反馈，提供有针对性的建议。回答要：
1. 具体实用，可操作
2. 结合用户的实际情况
3. 鼓励和支持用户
4. 提供具体的改进建议

请用中文回答。"""
    
    # 构建消息列表
    messages = [{"role": "system", "content": system_prompt}]
    
    # 添加历史对话
    messages.extend(conversation_history)
    
    # 添加当前用户消息
    messages.append({"role": "user", "content": user_message})
    
    # 调用AI API
    response = await call_deepseek_api(
        messages=messages,
        task_type="default" if model_type == "deepseek-chat" else "analysis",
        temperature=0.7,
        max_tokens=2000,
        web_search_enabled=web_search_enabled
    )
    
    return {
        "content": response,
        "thinking_process": None,  # 暂时不实现思考过程
        "web_search_results": None,  # 暂时不实现搜索结果
        "token_count": len(response.split())  # 简单估算
    }


async def generate_ai_response_stream(
    user_message: str,
    context: str,
    conversation_history: List[dict],
    model_type: str,
    web_search_enabled: bool
):
    """生成AI流式响应"""
    
    # 构建系统提示
    system_prompt = f"""你是一个专业的行动建议助手。请基于用户的行动项和实践反馈，提供个性化的建议和指导。

{context}

请根据用户的提问，结合上述行动项信息和实践反馈，提供有针对性的建议。回答要：
1. 具体实用，可操作
2. 结合用户的实际情况
3. 鼓励和支持用户
4. 提供具体的改进建议

请用中文回答。"""
    
    # 构建消息列表
    messages = [{"role": "system", "content": system_prompt}]
    
    # 添加历史对话
    messages.extend(conversation_history)
    
    # 添加当前用户消息
    messages.append({"role": "user", "content": user_message})
    
    # 模拟流式响应（实际实现需要调用支持流式响应的API）
    response_text = await call_deepseek_api(
        messages=messages,
        task_type="default" if model_type == "deepseek-chat" else "analysis",
        temperature=0.7,
        max_tokens=2000,
        web_search_enabled=web_search_enabled
    )
    
    # 模拟逐字输出
    for i, char in enumerate(response_text):
        yield {
            "type": "content",
            "content": char,
            "position": i
        }
        await asyncio.sleep(0.02)  # 控制输出速度
