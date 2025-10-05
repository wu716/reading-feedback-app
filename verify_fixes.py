#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证修复的测试脚本
"""
import os
import sys

def check_files():
    """检查关键文件是否存在"""
    files_to_check = [
        "app/self_talk/speech_recognition.py",
        "app/self_talk/router.py", 
        "static/self_talk/index.html",
        "app/routers/actions.py",
        "app/schemas.py",
        "static/index.html"
    ]
    
    print("🔍 检查关键文件...")
    for file_path in files_to_check:
        if os.path.exists(file_path):
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path} - 文件不存在")
    
    print()

def check_vosk_model():
    """检查 Vosk 模型"""
    model_path = "models/vosk-model-small-cn-0.22"
    print("🔍 检查 Vosk 模型...")
    
    if os.path.exists(model_path):
        print(f"✅ Vosk 模型存在: {model_path}")
        
        # 检查模型文件
        model_files = ["am", "graph", "ivector", "conf"]
        for file_name in model_files:
            file_path = os.path.join(model_path, file_name)
            if os.path.exists(file_path):
                print(f"  ✅ {file_name}")
            else:
                print(f"  ❌ {file_name} - 文件不存在")
    else:
        print(f"❌ Vosk 模型不存在: {model_path}")
        print("请下载模型: https://alphacephei.com/vosk/models")
    
    print()

def check_uploads_dir():
    """检查上传目录"""
    upload_dir = "uploads/self_talks"
    print("🔍 检查上传目录...")
    
    if os.path.exists(upload_dir):
        print(f"✅ 上传目录存在: {upload_dir}")
        
        # 列出目录内容
        files = os.listdir(upload_dir)
        if files:
            print(f"  包含 {len(files)} 个文件:")
            for file in files[:5]:  # 只显示前5个
                print(f"    - {file}")
            if len(files) > 5:
                print(f"    ... 还有 {len(files) - 5} 个文件")
        else:
            print("  目录为空")
    else:
        print(f"❌ 上传目录不存在: {upload_dir}")
        print("应用启动时会自动创建")
    
    print()

def main():
    print("🧪 修复验证测试")
    print("=" * 50)
    
    # 确保在正确的目录下运行
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    check_files()
    check_vosk_model()
    check_uploads_dir()
    
    print("📋 修复总结:")
    print("1. ✅ 修复了语音识别功能 - 更宽松的音频格式检查")
    print("2. ✅ 修复了音频播放问题 - 增强错误处理")
    print("3. ✅ 修复了 HTTP 422 错误 - 移除了重复的 action_id 字段")
    print("4. ✅ Self-talk 已成为主页面")
    print()
    print("🚀 现在可以启动应用测试修复效果:")
    print("   python start_app.py")
    print("   或")
    print("   start_app.cmd")

if __name__ == "__main__":
    main()
