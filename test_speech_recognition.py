#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试语音识别功能
"""
import os
import sys
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_speech_recognition():
    """测试语音识别功能"""
    print("🧪 测试语音识别功能")
    print("=" * 50)
    
    # 检查 Vosk 模型
    from app.self_talk.speech_recognition import is_speech_recognition_available, transcribe_audio_file
    
    print("1. 检查语音识别服务状态...")
    is_available = is_speech_recognition_available()
    print(f"   语音识别服务: {'✅ 可用' if is_available else '❌ 不可用'}")
    
    if not is_available:
        print("❌ 语音识别服务不可用，请检查：")
        print("   - Vosk 库是否已安装: pip install vosk")
        print("   - 模型文件是否存在: models/vosk-model-small-cn-0.22")
        return False
    
    print("2. 检查模型文件...")
    model_path = "models/vosk-model-small-cn-0.22"
    if os.path.exists(model_path):
        print(f"   ✅ 模型文件存在: {model_path}")
        
        # 检查模型目录内容
        model_files = os.listdir(model_path)
        print(f"   模型文件数量: {len(model_files)}")
        for file in model_files[:5]:  # 只显示前5个文件
            print(f"   - {file}")
        if len(model_files) > 5:
            print(f"   ... 还有 {len(model_files) - 5} 个文件")
    else:
        print(f"   ❌ 模型文件不存在: {model_path}")
        return False
    
    print("3. 检查上传目录...")
    upload_dir = "uploads/self_talks"
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
        print(f"   ✅ 创建上传目录: {upload_dir}")
    else:
        print(f"   ✅ 上传目录存在: {upload_dir}")
    
    print("4. 测试音频文件处理...")
    # 创建一个测试音频文件（静音）
    test_audio_path = os.path.join(upload_dir, "test_audio.wav")
    
    try:
        import wave
        import struct
        
        # 创建1秒的静音WAV文件
        sample_rate = 16000
        duration = 1  # 1秒
        samples = [0] * (sample_rate * duration)
        
        with wave.open(test_audio_path, 'w') as wav_file:
            wav_file.setnchannels(1)  # 单声道
            wav_file.setsampwidth(2)  # 16位
            wav_file.setframerate(sample_rate)  # 16kHz
            
            for sample in samples:
                wav_file.writeframes(struct.pack('<h', sample))
        
        print(f"   ✅ 创建测试音频文件: {test_audio_path}")
        
        # 测试语音识别
        print("5. 测试语音识别...")
        transcript = transcribe_audio_file(test_audio_path)
        
        if transcript is not None:
            print(f"   ✅ 语音识别成功: '{transcript}'")
        else:
            print("   ⚠️ 语音识别返回空结果（静音文件正常）")
        
        # 清理测试文件
        os.remove(test_audio_path)
        print("   ✅ 清理测试文件")
        
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        return False
    
    print("\n🎉 语音识别功能测试完成！")
    print("=" * 50)
    return True

if __name__ == "__main__":
    # 确保在正确的目录下运行
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    success = test_speech_recognition()
    sys.exit(0 if success else 1)
