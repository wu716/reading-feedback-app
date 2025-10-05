#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安装音频处理依赖
"""
import subprocess
import sys
import os

def install_pydub():
    """安装 pydub"""
    print("📦 安装 pydub...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pydub==0.25.1"])
        print("✅ pydub 安装成功")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ pydub 安装失败: {e}")
        return False

def check_ffmpeg():
    """检查 ffmpeg 是否可用"""
    print("🔍 检查 ffmpeg...")
    try:
        result = subprocess.run(["ffmpeg", "-version"], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ ffmpeg 已安装")
            return True
        else:
            print("❌ ffmpeg 未正确安装")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("❌ ffmpeg 未找到")
        return False

def install_ffmpeg_windows():
    """Windows 下安装 ffmpeg 的指导"""
    print("📋 Windows 下安装 ffmpeg 的步骤:")
    print("1. 访问 https://ffmpeg.org/download.html")
    print("2. 下载 Windows 版本的 ffmpeg")
    print("3. 解压到 C:\\ffmpeg")
    print("4. 将 C:\\ffmpeg\\bin 添加到系统 PATH 环境变量")
    print("5. 重启命令行窗口")
    print()
    print("或者使用 Chocolatey:")
    print("choco install ffmpeg")
    print()
    print("或者使用 Scoop:")
    print("scoop install ffmpeg")

def test_pydub():
    """测试 pydub 是否工作"""
    print("🧪 测试 pydub...")
    try:
        from pydub import AudioSegment
        print("✅ pydub 导入成功")
        
        # 尝试创建一个简单的音频段
        audio = AudioSegment.silent(duration=1000)  # 1秒静音
        print("✅ pydub 基本功能正常")
        return True
    except ImportError:
        print("❌ pydub 导入失败")
        return False
    except Exception as e:
        print(f"❌ pydub 测试失败: {e}")
        return False

def main():
    print("🔧 音频处理依赖安装工具")
    print("=" * 50)
    
    # 安装 pydub
    pydub_ok = install_pydub()
    
    # 检查 ffmpeg
    ffmpeg_ok = check_ffmpeg()
    
    # 测试 pydub
    if pydub_ok:
        test_ok = test_pydub()
    else:
        test_ok = False
    
    print("\n📊 安装结果:")
    print(f"pydub: {'✅' if pydub_ok else '❌'}")
    print(f"ffmpeg: {'✅' if ffmpeg_ok else '❌'}")
    print(f"测试: {'✅' if test_ok else '❌'}")
    
    if not ffmpeg_ok:
        print("\n⚠️  ffmpeg 未安装，pydub 将无法处理音频文件")
        if os.name == 'nt':  # Windows
            install_ffmpeg_windows()
        else:
            print("请安装 ffmpeg: sudo apt install ffmpeg (Ubuntu/Debian)")
            print("或: brew install ffmpeg (macOS)")
    
    if pydub_ok and ffmpeg_ok and test_ok:
        print("\n🎉 所有依赖安装成功！现在可以正常使用语音识别功能了。")
    else:
        print("\n❌ 部分依赖安装失败，语音识别功能可能无法正常工作。")

if __name__ == "__main__":
    main()
