#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 pydub 安装和功能
"""
import sys
import os

def test_pydub():
    print("=== 测试 pydub 安装 ===")
    
    try:
        import pydub
        print(f"✅ pydub 导入成功，版本: {pydub.__version__}")
    except ImportError as e:
        print(f"❌ pydub 导入失败: {e}")
        return False
    
    try:
        from pydub import AudioSegment
        print("✅ AudioSegment 导入成功")
    except ImportError as e:
        print(f"❌ AudioSegment 导入失败: {e}")
        return False
    
    try:
        # 测试创建空音频段
        audio = AudioSegment.silent(duration=1000)
        print(f"✅ 创建音频段成功: {len(audio)}ms")
    except Exception as e:
        print(f"❌ 创建音频段失败: {e}")
        return False
    
    print("✅ pydub 功能测试通过")
    return True

def test_ffmpeg():
    print("\n=== 测试 ffmpeg ===")
    
    try:
        import subprocess
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print("✅ ffmpeg 可用")
            # 显示版本信息的第一行
            version_line = result.stdout.split('\n')[0]
            print(f"   版本: {version_line}")
            return True
        else:
            print("❌ ffmpeg 不可用")
            return False
    except FileNotFoundError:
        print("❌ ffmpeg 未找到，请确保已安装并添加到 PATH")
        return False
    except Exception as e:
        print(f"❌ 测试 ffmpeg 时出错: {e}")
        return False

def test_audio_conversion():
    print("\n=== 测试音频转换 ===")
    
    try:
        from pydub import AudioSegment
        
        # 创建一个简单的音频段
        audio = AudioSegment.silent(duration=1000)  # 1秒静音
        print("✅ 创建测试音频成功")
        
        # 测试转换为 WAV 格式
        wav_data = audio.export(format="wav")
        print("✅ 音频转换为 WAV 成功")
        
        # 关闭缓冲区
        wav_data.close()
        print("✅ 音频转换测试通过")
        return True
        
    except Exception as e:
        print(f"❌ 音频转换测试失败: {e}")
        return False

if __name__ == "__main__":
    print(f"Python 版本: {sys.version}")
    print(f"当前工作目录: {os.getcwd()}")
    
    pydub_ok = test_pydub()
    ffmpeg_ok = test_ffmpeg()
    
    if pydub_ok and ffmpeg_ok:
        audio_ok = test_audio_conversion()
        if audio_ok:
            print("\n🎉 所有测试通过！pydub 和 ffmpeg 工作正常")
        else:
            print("\n⚠️ 音频转换测试失败")
    else:
        print("\n❌ 基础组件测试失败")
        
    print("\n建议:")
    if not pydub_ok:
        print("- 安装 pydub: pip install pydub")
    if not ffmpeg_ok:
        print("- 安装 ffmpeg: https://ffmpeg.org/download.html")
        print("- 或使用 winget: winget install ffmpeg")
