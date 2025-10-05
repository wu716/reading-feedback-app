#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 Self-talk 功能
"""
import requests
import json
import os

# API 基础配置
API_BASE = "http://localhost:8000"

def test_self_talk_api():
    """测试 Self-talk API"""
    print("🧪 开始测试 Self-talk API...")
    
    # 1. 测试语音识别服务状态
    print("\n1. 检查语音识别服务状态...")
    try:
        response = requests.get(f"{API_BASE}/api/self_talks/health/recognition")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 语音识别服务状态: {data}")
        else:
            print(f"❌ 语音识别服务检查失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 语音识别服务检查异常: {e}")
    
    # 2. 测试用户注册和登录
    print("\n2. 测试用户认证...")
    test_email = "test@example.com"
    test_password = "test123456"
    
    # 注册用户
    try:
        register_data = {
            "email": test_email,
            "password": test_password,
            "name": "测试用户"
        }
        response = requests.post(f"{API_BASE}/auth/register", json=register_data)
        if response.status_code == 200:
            print("✅ 用户注册成功")
        else:
            print(f"⚠️ 用户可能已存在: {response.status_code}")
    except Exception as e:
        print(f"❌ 用户注册失败: {e}")
    
    # 登录用户
    try:
        login_data = {
            "email": test_email,
            "password": test_password
        }
        response = requests.post(f"{API_BASE}/auth/login", json=login_data)
        if response.status_code == 200:
            token_data = response.json()
            token = token_data.get("access_token")
            print("✅ 用户登录成功")
        else:
            print(f"❌ 用户登录失败: {response.status_code}")
            return
    except Exception as e:
        print(f"❌ 用户登录异常: {e}")
        return
    
    # 3. 测试获取 Self-talk 列表
    print("\n3. 测试获取 Self-talk 列表...")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{API_BASE}/api/self_talks/", headers=headers)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 获取 Self-talk 列表成功: {len(data.get('self_talks', []))} 条记录")
        else:
            print(f"❌ 获取 Self-talk 列表失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 获取 Self-talk 列表异常: {e}")
    
    # 4. 测试上传音频文件（模拟）
    print("\n4. 测试上传音频文件...")
    try:
        # 创建一个模拟的音频文件
        test_audio_content = b"fake audio content for testing"
        files = {"file": ("test.wav", test_audio_content, "audio/wav")}
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.post(f"{API_BASE}/api/self_talks/", files=files, headers=headers)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 上传音频文件成功: ID={data.get('id')}")
            print(f"   音频路径: {data.get('audio_path')}")
            print(f"   转写结果: {data.get('transcript', '无')}")
        else:
            print(f"❌ 上传音频文件失败: {response.status_code}")
            print(f"   错误信息: {response.text}")
    except Exception as e:
        print(f"❌ 上传音频文件异常: {e}")
    
    print("\n🎉 Self-talk API 测试完成！")

if __name__ == "__main__":
    test_self_talk_api()
