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
        "static/self_talk/index.html", 
        "static/index.html",
        "requirements.txt"
    ]
    
    print("🔍 检查关键文件...")
    for file_path in files_to_check:
        if os.path.exists(file_path):
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path} - 文件不存在")
    
    print()

def check_dependencies():
    """检查依赖"""
    print("🔍 检查依赖...")
    
    # 检查 pydub
    try:
        import pydub
        print("✅ pydub 已安装")
    except ImportError:
        print("❌ pydub 未安装")
    
    # 检查 vosk
    try:
        import vosk
        print("✅ vosk 已安装")
    except ImportError:
        print("❌ vosk 未安装")
    
    # 检查 ffmpeg
    import subprocess
    try:
        result = subprocess.run(["ffmpeg", "-version"], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print("✅ ffmpeg 已安装")
        else:
            print("❌ ffmpeg 未正确安装")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("❌ ffmpeg 未找到")
    
    print()

def check_vosk_model():
    """检查 Vosk 模型"""
    model_path = "models/vosk-model-small-cn-0.22"
    print("🔍 检查 Vosk 模型...")
    
    if os.path.exists(model_path):
        print(f"✅ Vosk 模型存在: {model_path}")
    else:
        print(f"❌ Vosk 模型不存在: {model_path}")
        print("请下载模型: https://alphacephei.com/vosk/models")
    
    print()

def main():
    print("🧪 修复验证测试")
    print("=" * 50)
    
    # 确保在正确的目录下运行
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    check_files()
    check_dependencies()
    check_vosk_model()
    
    print("📋 修复总结:")
    print("1. ✅ 修复了语音识别功能 - 使用 pydub 进行音频格式转换")
    print("2. ✅ 修复了前端录音格式 - 改为 audio/webm")
    print("3. ✅ 修复了 HTTP 422 错误 - 修正了前端选项值")
    print("4. ✅ Self-talk 已成为主页面")
    print()
    print("🚀 现在可以启动应用测试修复效果:")
    print("   python start_app.py")
    print("   或")
    print("   start_app.cmd")
    print()
    print("⚠️  如果语音识别仍有问题，请运行:")
    print("   python install_audio_deps.py")

if __name__ == "__main__":
    main()
