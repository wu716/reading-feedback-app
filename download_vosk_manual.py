# -*- coding: utf-8 -*-
"""
手动下载 Vosk 中文模型的说明脚本
"""
import os
import sys

def main():
    print("🎤 Vosk 中文语音识别模型下载指南")
    print("=" * 50)
    
    model_dir = "models"
    model_name = "vosk-model-small-cn-0.22"
    model_path = os.path.join(model_dir, model_name)
    
    print(f"📁 模型目录: {model_path}")
    print()
    
    if os.path.exists(model_path):
        print("✅ 模型已存在！")
        print(f"📂 路径: {model_path}")
        return True
    
    print("❌ 模型不存在，需要手动下载")
    print()
    print("📋 下载步骤：")
    print("1. 打开浏览器")
    print("2. 访问: https://alphacephei.com/vosk/models")
    print("3. 找到 'vosk-model-small-cn-0.22'")
    print("4. 点击下载（约 50MB）")
    print("5. 解压到项目目录:")
    print(f"   {model_path}")
    print()
    print("📂 目录结构应该是:")
    print(f"   {model_path}/")
    print("   ├── am/")
    print("   ├── graph/")
    print("   ├── ivector/")
    print("   └── conf/")
    print()
    print("🔄 下载完成后，重新运行此脚本检查")
    
    return False

if __name__ == "__main__":
    main()
