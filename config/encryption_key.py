# -*- coding: utf-8 -*-
"""
文件加密密钥配置
此文件包含用于加密/解密文件的密钥。
重要：此文件不应被提交到Git仓库，请确保在.gitignore中添加此文件。
"""

# 文件加密密钥 - Fernet加密使用的32字节密钥（base64编码）
FILE_ENCRYPTION_KEY = "aBcDeFgHiJkLmNoPqRsTuVwXyZaBcDeFgHiJkLmNoPqRsTuVwXyZaBcDeFgHiJkL="

print(f"当前的FILE_ENCRYPTION_KEY: {FILE_ENCRYPTION_KEY}")
print("⚠️  重要提醒：")
print("   1. 此密钥用于加密用户上传的文件")
print("   2. 如果更换密钥，已有的加密文件将无法解密")
print("   3. 请妥善备份此密钥")
print("   4. 确保此文件不会被提交到Git仓库")