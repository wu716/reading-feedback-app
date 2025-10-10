#!/usr/bin/env python3
"""
生成安全的文件加密密钥脚本
运行此脚本将生成一个新的加密密钥，并更新config/encryption_key.py文件
"""
import base64
import secrets

def generate_secure_key():
    """生成32字节的随机密钥并返回base64编码"""
    # 生成32字节的随机密钥
    key = secrets.token_bytes(32)

    # base64编码
    encoded_key = base64.urlsafe_b64encode(key).decode()

    return encoded_key

def update_config_file(key):
    """更新配置文件"""
    config_content = f'''# -*- coding: utf-8 -*-
"""
文件加密密钥配置
此文件包含用于加密/解密文件的密钥。
重要：此文件不应被提交到Git仓库，请确保在.gitignore中添加此文件。
"""

# 文件加密密钥 - Fernet加密使用的32字节密钥（base64编码）
FILE_ENCRYPTION_KEY = "{key}"

print(f"当前的FILE_ENCRYPTION_KEY: {{FILE_ENCRYPTION_KEY}}")
print("警告：这是生产环境使用的密钥，请妥善保管！")'''

    with open('config/encryption_key.py', 'w', encoding='utf-8') as f:
        f.write(config_content)

    print(f"✅ 已生成新的加密密钥并更新配置文件")
    print(f"🔑 密钥: {key}")
    print("⚠️  重要提醒："    print("   1. 此密钥用于加密用户上传的文件"    print("   2. 如果更换密钥，旧的加密文件将无法解密"    print("   3. 请妥善备份此密钥"    print("   4. 确保config/encryption_key.py文件在.gitignore中被忽略"

if __name__ == "__main__":
    print("🔐 生成安全的文件加密密钥...")
    key = generate_secure_key()
    update_config_file(key)
    print("\n🎉 密钥生成完成！")
