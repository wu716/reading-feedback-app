#!/usr/bin/env python3
"""
简单的行动类型分析测试
"""

import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.ai_service import analyze_action_type

async def simple_test():
    """简单测试行动类型分析功能"""
    
    print("🧪 测试行动类型分析功能...")
    print("=" * 50)
    
    # 测试您提到的例子
    test_case = {
        "action_text": "在三餐时进行一次自我对话，强化积极信念",
        "frequency": "daily",
        "tags": ["自我对话", "心理建设"]
    }
    
    print(f"测试案例:")
    print(f"  行动描述: {test_case['action_text']}")
    print(f"  频率: {test_case['frequency']}")
    print(f"  标签: {test_case['tags']}")
    print(f"  期望结果: habit")
    
    try:
        result = await analyze_action_type(
            test_case['action_text'],
            test_case['frequency'],
            test_case['tags']
        )
        
        is_correct = result == "habit"
        status = "✅ 正确" if is_correct else "❌ 错误"
        
        print(f"  实际结果: {result}")
        print(f"  状态: {status}")
        
        if is_correct:
            print("\n🎉 改进成功！现在AI能正确识别这个行动为'习惯型'了")
        else:
            print(f"\n⚠️ 仍然有问题，需要进一步调试")
        
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")

if __name__ == "__main__":
    asyncio.run(simple_test())
