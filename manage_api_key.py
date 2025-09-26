#!/usr/bin/env python3
"""
API Key 管理工具 - 安全地存储和管理 DeepSeek API Key
"""
import os
import base64
from cryptography.fernet import Fernet
from getpass import getpass

class APIKeyManager:
    def __init__(self):
        self.encryption_key_file = "encryption.key"
        self.encrypted_api_key_file = "encrypted_api_key.txt"
    
    def get_or_create_encryption_key(self):
        """获取或创建加密密钥"""
        if os.path.exists(self.encryption_key_file):
            with open(self.encryption_key_file, 'rb') as f:
                return f.read()
        else:
            # 生成新的加密密钥
            key = Fernet.generate_key()
            with open(self.encryption_key_file, 'wb') as f:
                f.write(key)
            print(f"✅ 已生成新的加密密钥: {self.encryption_key_file}")
            return key
    
    def encrypt_api_key(self, api_key: str):
        """加密并存储 API Key"""
        key = self.get_or_create_encryption_key()
        f = Fernet(key)
        
        # 加密 API Key
        encrypted = f.encrypt(api_key.encode())
        encrypted_b64 = base64.b64encode(encrypted).decode()
        
        # 保存到文件
        with open(self.encrypted_api_key_file, 'w') as f:
            f.write(encrypted_b64)
        
        print("✅ API Key 已安全加密并存储")
        print(f"📁 加密文件: {self.encrypted_api_key_file}")
        print(f"🔑 密钥文件: {self.encryption_key_file}")
    
    def decrypt_api_key(self):
        """解密 API Key"""
        if not os.path.exists(self.encrypted_api_key_file):
            print("❌ 未找到加密的 API Key 文件")
            return None
        
        key = self.get_or_create_encryption_key()
        f = Fernet(key)
        
        try:
            with open(self.encrypted_api_key_file, 'r') as f:
                encrypted_b64 = f.read().strip()
            
            encrypted = base64.b64decode(encrypted_b64.encode())
            decrypted = f.decrypt(encrypted)
            return decrypted.decode()
        except Exception as e:
            print(f"❌ 解密失败: {e}")
            return None
    
    def set_api_key_interactive(self):
        """交互式设置 API Key"""
        print("🔐 DeepSeek API Key 安全设置")
        print("=" * 40)
        
        # 获取 API Key
        api_key = getpass("请输入你的 DeepSeek API Key: ")
        
        if not api_key:
            print("❌ API Key 不能为空")
            return False
        
        # 验证 API Key 格式
        if not api_key.startswith('sk-'):
            print("⚠️  警告: API Key 通常以 'sk-' 开头")
            confirm = input("是否继续？(y/N): ")
            if confirm.lower() != 'y':
                return False
        
        # 加密并存储
        self.encrypt_api_key(api_key)
        
        print("\n✅ 设置完成！")
        print("📝 安全提示：")
        print("- 加密文件已添加到 .gitignore")
        print("- 不要将加密文件提交到代码库")
        print("- 定期备份加密文件")
        
        return True

def main():
    manager = APIKeyManager()
    
    print("🔐 DeepSeek API Key 管理器")
    print("=" * 30)
    print("1. 设置新的 API Key")
    print("2. 查看当前 API Key")
    print("3. 退出")
    
    while True:
        choice = input("\n请选择操作 (1-3): ").strip()
        
        if choice == '1':
            manager.set_api_key_interactive()
        elif choice == '2':
            api_key = manager.decrypt_api_key()
            if api_key:
                # 只显示前几位和后几位
                masked = api_key[:8] + "..." + api_key[-4:]
                print(f"当前 API Key: {masked}")
            else:
                print("❌ 无法获取 API Key")
        elif choice == '3':
            print("👋 再见！")
            break
        else:
            print("❌ 无效选择，请重新输入")

if __name__ == "__main__":
    main()

