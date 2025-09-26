#!/usr/bin/env python3
"""
简化的 API Key 设置脚本
"""
import os
import base64
from cryptography.fernet import Fernet

def setup_api_key():
    print("🔐 设置 DeepSeek API Key")
    print("=" * 30)
    
    # 获取 API Key
    api_key = input("请输入您的 DeepSeek API Key: ").strip()
    
    if not api_key:
        print("❌ API Key 不能为空")
        return False
    
    if api_key == "your-deepseek-api-key-here":
        print("❌ 请使用真实的 API Key，不是示例值")
        return False
    
    # 生成或获取加密密钥
    key_file = "encryption.key"
    if os.path.exists(key_file):
        with open(key_file, 'rb') as f:
            key = f.read()
    else:
        key = Fernet.generate_key()
        with open(key_file, 'wb') as f:
            f.write(key)
        print(f"✅ 已生成新的加密密钥: {key_file}")
    
    # 加密 API Key
    f = Fernet(key)
    encrypted = f.encrypt(api_key.encode())
    encrypted_b64 = base64.b64encode(encrypted).decode()
    
    # 保存加密的 API Key
    with open("encrypted_api_key.txt", 'w') as f:
        f.write(encrypted_b64)
    
    print("✅ API Key 已安全加密并存储")
    print("📁 加密文件: encrypted_api_key.txt")
    print("🔑 密钥文件: encryption.key")
    print()
    print("🚀 现在可以启动应用了：")
    print("python start_with_env.py")
    
    return True

if __name__ == "__main__":
    setup_api_key()
