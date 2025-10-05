#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试删除功能修复
"""
import requests
import json
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_auth_and_delete():
    """测试认证和删除功能"""
    base_url = "http://127.0.0.1:8000"
    
    print("=== 测试删除功能修复 ===")
    
    # 1. 测试登录
    print("\n1. 测试用户登录...")
    login_data = {
        "username": "admin@example.com",  # 请替换为您的测试用户
        "password": "admin123"  # 请替换为您的测试密码
    }
    
    try:
        login_response = requests.post(
            f"{base_url}/auth/login",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        if login_response.status_code == 200:
            token_data = login_response.json()
            access_token = token_data.get("access_token")
            print(f"✅ 登录成功，获得令牌: {access_token[:20]}...")
        else:
            print(f"❌ 登录失败: {login_response.status_code}")
            print(f"错误信息: {login_response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到服务器，请确保应用正在运行")
        return False
    except Exception as e:
        print(f"❌ 登录异常: {e}")
        return False
    
    # 2. 获取Self-talk列表
    print("\n2. 获取Self-talk列表...")
    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        list_response = requests.get(f"{base_url}/api/self_talks/", headers=headers)
        
        if list_response.status_code == 200:
            data = list_response.json()
            self_talks = data.get("self_talks", [])
            print(f"✅ 获取列表成功，共 {len(self_talks)} 条记录")
            
            if not self_talks:
                print("⚠️  没有Self-talk记录，无法测试删除功能")
                return True
                
            # 显示记录
            for talk in self_talks[:3]:  # 只显示前3条
                print(f"   - ID: {talk['id']}, 创建时间: {talk['created_at']}")
        else:
            print(f"❌ 获取列表失败: {list_response.status_code}")
            print(f"错误信息: {list_response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 获取列表异常: {e}")
        return False
    
    # 3. 测试删除功能
    print("\n3. 测试删除功能...")
    if self_talks:
        test_id = self_talks[0]["id"]  # 使用第一条记录进行测试
        
        print(f"尝试删除记录 ID: {test_id}")
        
        try:
            delete_response = requests.delete(
                f"{base_url}/api/self_talks/{test_id}",
                headers=headers
            )
            
            if delete_response.status_code == 200:
                print("✅ 删除成功")
                result = delete_response.json()
                print(f"删除结果: {result}")
            elif delete_response.status_code == 401:
                print("❌ 删除失败: 认证错误")
                print(f"错误信息: {delete_response.text}")
                return False
            else:
                print(f"❌ 删除失败: {delete_response.status_code}")
                print(f"错误信息: {delete_response.text}")
                return False
                
        except Exception as e:
            print(f"❌ 删除异常: {e}")
            return False
    else:
        print("⚠️  没有记录可删除")
    
    # 4. 验证删除结果
    print("\n4. 验证删除结果...")
    try:
        verify_response = requests.get(f"{base_url}/api/self_talks/", headers=headers)
        
        if verify_response.status_code == 200:
            verify_data = verify_response.json()
            verify_talks = verify_data.get("self_talks", [])
            print(f"✅ 验证成功，剩余 {len(verify_talks)} 条记录")
        else:
            print(f"❌ 验证失败: {verify_response.status_code}")
            
    except Exception as e:
        print(f"❌ 验证异常: {e}")
    
    print("\n=== 测试完成 ===")
    return True

def test_invalid_token():
    """测试无效令牌的处理"""
    base_url = "http://127.0.0.1:8000"
    
    print("\n=== 测试无效令牌处理 ===")
    
    # 使用无效令牌
    invalid_headers = {"Authorization": "Bearer invalid_token_123"}
    
    try:
        response = requests.get(f"{base_url}/api/self_talks/", headers=invalid_headers)
        
        if response.status_code == 401:
            print("✅ 无效令牌正确返回401错误")
            return True
        else:
            print(f"❌ 无效令牌返回了错误的状态码: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 测试无效令牌异常: {e}")
        return False

def main():
    """主函数"""
    print("删除功能修复测试")
    print("=" * 50)
    
    # 测试正常流程
    success1 = test_auth_and_delete()
    
    # 测试无效令牌
    success2 = test_invalid_token()
    
    print("\n" + "=" * 50)
    if success1 and success2:
        print("🎉 所有测试通过！删除功能修复成功")
    else:
        print("❌ 部分测试失败，请检查修复")
    
    print("\n使用说明:")
    print("1. 确保应用正在运行 (python main.py)")
    print("2. 确保有测试用户和数据")
    print("3. 修改脚本中的用户名和密码")

if __name__ == "__main__":
    main()
