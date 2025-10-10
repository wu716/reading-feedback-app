#!/usr/bin/env python3
"""
生成安全的文件加密密钥
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

if __name__ == "__main__":
    key = generate_secure_key()
    print("生成的FILE_ENCRYPTION_KEY:")
    print(key)
    print()
    print("这是一个32字节的随机密钥，安全性足够高。")
    print("请将此密钥设置到代码中的FILE_ENCRYPTION_KEY变量中。")