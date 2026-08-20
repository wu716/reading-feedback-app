import json
import asyncio
from typing import List, Dict, Any
from openai import AsyncOpenAI, APIStatusError, AuthenticationError, PermissionDeniedError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential, RetryError
import logging

from app.config import settings
from app.schemas import ActionItem, Frequency

logger = logging.getLogger(__name__)

# 初始化 DeepSeek 客户端
client = None
if settings.deepseek_api_key:
    client = AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url
    )


class AIExtractionError(Exception):
    """AI 抽取错误"""
    pass


class AIValidationError(Exception):
    """AI 输出验证错误"""
    pass


def create_extraction_prompt(notes: str, book_title: str = None) -> str:
    """创建 AI 抽取提示词"""
    book_context = f"来自《{book_title}》" if book_title else "来自读书笔记"
    
    prompt = f"""你是一个专业的读书笔记行动项抽取助手。

{book_context}的文本内容：
{notes}

请仔细分析上述文本，从中识别出可执行的行动项。要求：

1. **行动项必须是具体的、可操作的**，而不是抽象的概念
2. **每个行动项都应该有明确的执行步骤**
3. **保留原文引用**，便于用户回顾原始内容
4. **自动生成相关标签**，如：时间管理、学习方法、健康、工作、人际关系等
5. **评估执行频率**：daily（每日）、weekly（每周）、monthly（每月）

**重要：请直接返回 JSON 数组，不要包含任何其他文字、解释或 markdown 格式标记。**

输出格式（严格 JSON 数组）：
[
  {{
    "book": "书籍名称或笔记来源",
    "excerpt": "原文段落（50-200字）",
    "action": "具体的行动项描述",
    "tags": ["标签1", "标签2", "标签3"],
    "frequency": "daily"
  }}
]

注意：
- 如果文本中没有可执行的行动项，返回空数组 []
- 每个行动项都要有原文支撑
- 标签要准确反映行动项的性质
- 频率要根据行动项的特点合理设定
- **只返回 JSON，不要添加任何其他内容**
"""

    return prompt


def _should_retry_ai_call(exc: BaseException) -> bool:
    """余额不足、鉴权失败等不应重试，避免放大消耗。"""
    if isinstance(exc, (AuthenticationError, PermissionDeniedError, AIExtractionError)):
        return False
    if isinstance(exc, APIStatusError):
        if exc.status_code in (400, 401, 402, 403, 404, 422):
            return False
        text = str(exc).lower()
        if "insufficient" in text or "balance" in text or "quota" in text:
            return False
    return True


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception(_should_retry_ai_call),
    reraise=True,
)
async def call_deepseek_api(
    prompt: str = None,
    messages: List[Dict[str, str]] = None,
    task_type: str = "default",
    temperature: float = 0.7,
    max_tokens: int = 2000,
    web_search_enabled: bool = False
) -> str:
    """
    调用 DeepSeek API
    
    Args:
        prompt: 单个提示词字符串（向后兼容旧代码）
        messages: 消息列表（新方式，优先使用）
        task_type: 任务类型（"default" 或 "analysis"）
        temperature: 温度参数
        max_tokens: 最大token数
        web_search_enabled: 是否启用联网搜索
    
    Returns:
        str: AI响应内容
    """
    if not client:
        raise AIExtractionError("AI 服务未配置：缺少 DEEPSEEK_API_KEY")
    
    try:
        # 如果提供了 messages，直接使用；否则从 prompt 构建 messages
        if messages is not None:
            api_messages = messages
        elif prompt is not None:
            api_messages = [
                {
                    "role": "system",
                    "content": "你是一个专业的读书笔记行动项抽取助手，严格按照 JSON 格式输出结果。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        else:
            raise ValueError("必须提供 prompt 或 messages 参数")
        
        # 构建 API 请求参数
        api_params = {
            "model": settings.deepseek_model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        # 如果启用联网搜索，添加相应参数（DeepSeek API 可能需要额外参数）
        # 注意：实际的 DeepSeek API 可能不支持 web_search_enabled 参数
        # 这里先保留参数，但实际使用时可能需要根据 API 文档调整
        if web_search_enabled:
            # DeepSeek API 可能不支持此参数，暂时忽略
            logger.warning("web_search_enabled 参数当前未实现")
        
        # 如果是分析任务且使用 deepseek-reasoner 模型，可能需要特殊处理
        if task_type == "analysis" and "reasoner" in settings.deepseek_model:
            # 可能需要添加特殊参数，根据实际 API 文档调整
            pass
        
        response = await client.chat.completions.create(**api_params)
        
        return response.choices[0].message.content.strip()
    
    except RetryError as e:
        # 当所有重试都失败时，RetryError 包含最后一次尝试的异常
        # RetryError.last_attempt 是一个 Outcome 对象
        last_attempt = getattr(e, 'last_attempt', None)
        if last_attempt is not None:
            try:
                # 尝试获取原始异常
                original_error = last_attempt.exception()
                if original_error:
                    logger.error(f"DeepSeek API 调用失败（重试3次后）: {original_error}")
                    error_msg = str(original_error)
                else:
                    error_msg = str(e)
                    logger.error(f"DeepSeek API 调用失败（重试3次后）: {e}")
            except Exception:
                # 如果无法获取原始异常，使用 RetryError 本身
                error_msg = str(e)
                logger.error(f"DeepSeek API 调用失败（重试3次后）: {e}")
        else:
            error_msg = str(e)
            logger.error(f"DeepSeek API 调用失败（重试3次后）: {e}")
        
        # 检查是否是认证错误
        if "401" in error_msg or "unauthorized" in error_msg.lower() or ("api" in error_msg.lower() and "key" in error_msg.lower()):
            raise AIExtractionError("AI 服务认证失败：请检查 API Key 是否正确")
        # 检查是否是网络错误
        elif "connection" in error_msg.lower() or "timeout" in error_msg.lower():
            raise AIExtractionError("AI 服务连接失败：请检查网络连接")
        else:
            raise AIExtractionError(f"AI 服务调用失败: {error_msg}")

    except APIStatusError as e:
        logger.error("DeepSeek API 状态错误: %s %s", e.status_code, e)
        if e.status_code == 402 or "insufficient" in str(e).lower() or "balance" in str(e).lower():
            raise AIExtractionError("AI 服务余额不足，暂时无法调用")
        if e.status_code in (401, 403):
            raise AIExtractionError("AI 服务认证失败：请检查 API Key 是否正确")
        raise AIExtractionError(f"AI 服务调用失败: {e}")
    
    except Exception as e:
        logger.error(f"DeepSeek API 调用失败: {e}")
        # 记录更详细的错误信息
        import traceback
        logger.error(f"错误详情: {traceback.format_exc()}")
        error_msg = str(e)
        # 检查是否是认证错误
        if "401" in error_msg or "unauthorized" in error_msg.lower() or ("api" in error_msg.lower() and "key" in error_msg.lower()):
            raise AIExtractionError("AI 服务认证失败：请检查 API Key 是否正确")
        # 检查是否是网络错误
        elif "connection" in error_msg.lower() or "timeout" in error_msg.lower():
            raise AIExtractionError("AI 服务连接失败：请检查网络连接")
        else:
            raise AIExtractionError(f"AI 服务调用失败: {error_msg}")


def validate_ai_response(response: str) -> List[Dict[str, Any]]:
    """验证 AI 响应格式"""
    try:
        # 记录原始响应用于调试
        logger.info(f"AI 原始响应: {response[:200]}...")
        
        # 清理响应，移除可能的 markdown 代码块标记
        cleaned_response = response.strip()
        if cleaned_response.startswith("```json"):
            cleaned_response = cleaned_response[7:]
        if cleaned_response.startswith("```"):
            cleaned_response = cleaned_response[3:]
        if cleaned_response.endswith("```"):
            cleaned_response = cleaned_response[:-3]
        cleaned_response = cleaned_response.strip()
        
        logger.info(f"清理后的响应: {cleaned_response[:200]}...")
        
        # 尝试解析 JSON
        data = json.loads(cleaned_response)
        
        if not isinstance(data, list):
            raise AIValidationError("AI 响应必须是数组格式")
        
        validated_actions = []
        for item in data:
            if not isinstance(item, dict):
                continue
                
            # 验证必需字段
            required_fields = ["book", "excerpt", "action"]
            if not all(field in item for field in required_fields):
                continue
            
            # 验证字段类型和内容
            if not all(isinstance(item[field], str) and len(item[field].strip()) > 0 
                      for field in required_fields):
                continue
            
            # 设置默认值
            validated_item = {
                "book": item["book"].strip(),
                "excerpt": item["excerpt"].strip(),
                "action": item["action"].strip(),
                "tags": item.get("tags", []) if isinstance(item.get("tags"), list) else [],
                "frequency": item.get("frequency", "daily")
            }
            
            # 验证频率
            if validated_item["frequency"] not in ["daily", "weekly", "monthly"]:
                validated_item["frequency"] = "daily"
            
            # 验证标签
            if not isinstance(validated_item["tags"], list):
                validated_item["tags"] = []
            
            validated_actions.append(validated_item)
        
        return validated_actions
    
    except json.JSONDecodeError as e:
        logger.error(f"AI 响应 JSON 解析失败: {e}")
        raise AIValidationError(f"AI 响应格式错误: {str(e)}")
    
    except Exception as e:
        logger.error(f"AI 响应验证失败: {e}")
        raise AIValidationError(f"响应验证失败: {str(e)}")


async def extract_actions_from_notes(notes: str, book_title: str = None) -> List[ActionItem]:
    """从笔记中抽取行动项"""
    try:
        # 创建提示词
        prompt = create_extraction_prompt(notes, book_title)
        
        # 调用 AI API
        response = await call_deepseek_api(prompt)
        
        # 验证响应
        validated_data = validate_ai_response(response)
        
        # 转换为 ActionItem 对象
        actions = []
        for item in validated_data:
            action = ActionItem(
                book=item["book"],
                excerpt=item["excerpt"],
                action=item["action"],
                tags=item["tags"],
                frequency=Frequency(item["frequency"])
            )
            actions.append(action)
        
        logger.info(f"成功抽取 {len(actions)} 个行动项")
        return actions
    
    except (AIExtractionError, AIValidationError) as e:
        logger.error(f"行动项抽取失败: {e}")
        raise e
    
    except Exception as e:
        logger.error(f"未知错误: {e}")
        raise AIExtractionError(f"行动项抽取失败: {str(e)}")


async def test_ai_connection() -> bool:
    """测试 AI 连接"""
    if not client:
        logger.warning("AI 服务未配置：缺少 DEEPSEEK_API_KEY")
        return False
    
    try:
        test_prompt = "请回复：连接测试成功"
        response = await call_deepseek_api(test_prompt)
        
        # 更宽松的测试条件：只要 API 返回了响应就认为连接成功
        if response and len(response.strip()) > 0:
            logger.info(f"AI 连接测试成功，响应: {response[:100]}...")
            return True
        else:
            logger.warning(f"AI 连接测试失败，响应为空")
            return False
            
    except Exception as e:
        logger.error(f"AI 连接测试失败: {e}")
        return False


async def generate_action_advice(action_text: str, context: str = "") -> str:
    """
    为行动项生成AI建议
    
    Args:
        action_text: 行动项文本
        context: 上下文信息（可选）
    
    Returns:
        str: AI生成的建议
    """
    if not client:
        raise AIExtractionError("AI 服务未配置：缺少 DEEPSEEK_API_KEY")
    
    try:
        prompt = f"""你是一个专业的行为改变教练。请为以下行动项提供具体、可执行的建议：

行动项：{action_text}

{f'背景信息：{context}' if context else ''}

请提供以下方面的建议：
1. 具体执行步骤
2. 可能遇到的障碍和应对方法
3. 保持动力的技巧
4. 追踪进度的方法

请用简洁、实用的中文回答，并使用 Markdown 排版：关键步骤和注意事项用 **加粗**，分点用列表。"""
        
        response = await call_deepseek_api(prompt)
        return response
    
    except Exception as e:
        logger.error(f"生成行动建议失败: {e}")
        raise AIExtractionError(f"生成建议失败: {str(e)}")
