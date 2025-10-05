#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
应用功能测试脚本
"""
import os
import sys
import asyncio
import requests
import json

# 设置环境变量
os.environ["DEEPSEEK_API_KEY"] = os.getenv("DEEPSEEK_API_KEY", "your-api-key-here")
os.environ["SECRET_KEY"] = os.getenv("SECRET_KEY", "K7mN2pQ9rS8tU3vW5xY1zA4bC6dE0fG")
os.environ["ENVIRONMENT"] = os.getenv("ENVIRONMENT", "development")
os.environ["DATABASE_URL"] = os.getenv("DATABASE_URL", "sqlite:///./app.db")

def test_basic_functionality():
    """测试基本功能"""
    print("🧪 测试应用基本功能")
    print("=" * 50)
    
    # 测试健康检查
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
            print("✅ 健康检查通过")
        else:
            print(f"❌ 健康检查失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 健康检查失败: {e}")
        return False
    
    # 测试 API 文档
    try:
        response = requests.get("http://localhost:8000/docs", timeout=5)
        if response.status_code == 200:
            print("✅ API 文档可访问")
        else:
            print(f"❌ API 文档不可访问: {response.status_code}")
    except Exception as e:
        print(f"❌ API 文档测试失败: {e}")
    
    # 测试静态文件
    try:
        response = requests.get("http://localhost:8000/static/index.html", timeout=5)
        if response.status_code == 200:
            print("✅ 主页面可访问")
        else:
            print(f"❌ 主页面不可访问: {response.status_code}")
    except Exception as e:
        print(f"❌ 主页面测试失败: {e}")
    
    # 测试 Self-talk 页面
    try:
        response = requests.get("http://localhost:8000/static/self_talk/index.html", timeout=5)
        if response.status_code == 200:
            print("✅ Self-talk 页面可访问")
        else:
            print(f"❌ Self-talk 页面不可访问: {response.status_code}")
    except Exception as e:
        print(f"❌ Self-talk 页面测试失败: {e}")
    
    return True

async def test_ai_service():
    """测试 AI 服务"""
    print("\n🤖 测试 AI 服务")
    print("=" * 50)
    
    try:
        from app.ai_service import test_ai_connection
        result = await test_ai_connection()
        if result:
            print("✅ AI 服务连接成功")
        else:
            print("❌ AI 服务连接失败")
        return result
    except Exception as e:
        print(f"❌ AI 服务测试失败: {e}")
        return False

def test_vosk_model():
    """测试 Vosk 模型"""
    print("\n🎤 测试语音识别")
    print("=" * 50)
    
    try:
        from app.self_talk.speech_recognition import is_speech_recognition_available
        result = is_speech_recognition_available()
        if result:
            print("✅ Vosk 语音识别可用")
        else:
            print("❌ Vosk 语音识别不可用")
        return result
    except Exception as e:
        print(f"❌ 语音识别测试失败: {e}")
        return False

def test_database():
    """测试数据库"""
    print("\n🗄️ 测试数据库")
    print("=" * 50)
    
    try:
        from app.database import create_tables
        create_tables()
        print("✅ 数据库连接正常")
        return True
    except Exception as e:
        print(f"❌ 数据库测试失败: {e}")
        return False

def main():
    print("🚀 读书反馈应用功能测试")
    print("=" * 50)
    print("请确保应用已启动 (http://localhost:8000)")
    print("=" * 50)
    
    # 测试数据库
    db_ok = test_database()
    
    # 测试 AI 服务
    ai_ok = asyncio.run(test_ai_service())
    
    # 测试语音识别
    vosk_ok = test_vosk_model()
    
    # 测试基本功能
    basic_ok = test_basic_functionality()
    
    print("\n📊 测试结果汇总")
    print("=" * 50)
    print(f"数据库: {'✅' if db_ok else '❌'}")
    print(f"AI 服务: {'✅' if ai_ok else '❌'}")
    print(f"语音识别: {'✅' if vosk_ok else '❌'}")
    print(f"基本功能: {'✅' if basic_ok else '❌'}")
    
    if all([db_ok, basic_ok]):
        print("\n🎉 应用基本功能正常！")
        if ai_ok:
            print("✅ AI 服务正常")
        else:
            print("⚠️ AI 服务异常，但不影响基本功能")
        
        if vosk_ok:
            print("✅ 语音识别正常")
        else:
            print("⚠️ 语音识别异常，但不影响基本功能")
    else:
        print("\n❌ 应用存在问题，请检查配置")

if __name__ == "__main__":
    main()
