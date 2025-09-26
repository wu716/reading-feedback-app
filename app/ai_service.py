import json
import asyncio
from typing import List, Dict, Any
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
import logging

from app.config import settings
from app.schemas import ActionItem, Frequency

logger = logging.getLogger(__name__)

# 初始化 DeepSeek 客户端
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


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10)
)
async def call_deepseek_api(prompt: str) -> str:
    """调用 DeepSeek API"""
    try:
        response = await client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[
                {
                    "role": "system",
                    "content": "你是一个专业的读书笔记行动项抽取助手，严格按照 JSON 格式输出结果。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,  # 降低随机性，提高一致性
            max_tokens=2000
        )
        
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        logger.error(f"DeepSeek API 调用失败: {e}")
        raise AIExtractionError(f"AI 服务调用失败: {str(e)}")


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
    try:
        test_prompt = "请回复：连接测试成功"
        response = await call_deepseek_api(test_prompt)
        return "成功" in response
    except Exception as e:
        logger.error(f"AI 连接测试失败: {e}")
        return False
