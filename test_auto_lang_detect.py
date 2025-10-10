#!/usr/bin/env python3
"""
测试自动语言检测功能
"""
import os
import sys
sys.path.append('.')

from app.self_talk.speech_recognition import (
    is_any_speech_recognition_available,
    detect_text_language,
    quick_sample_transcription,
    transcribe_audio_file
)

def test_basic_functions():
    """测试基本功能"""
    print("=== 测试基本功能 ===")

    # 测试语言检测服务可用性
    print(f"语音识别服务可用: {is_any_speech_recognition_available()}")

    # 测试文本语言检测
    test_texts = [
        "Hello world, how are you today?",
        "你好世界，今天怎么样？",
        "",
        "Bonjour le monde"
    ]

    for text in test_texts:
        lang = detect_text_language(text)
        print(f"'{text[:30]}...' -> 检测语言: {lang}")

    print("基本功能测试完成\n")

def test_sample_audio():
    """测试采样音频转录（如果有测试音频）"""
    print("=== 测试采样转录 ===")

    # 检查是否有测试音频文件
    test_audio = "uploads/self_talks/2_70b60b2e6fb44d8ca5d03d7660dd54e5.webm"
    if os.path.exists(test_audio):
        print(f"找到测试音频: {test_audio}")
        sample_result = quick_sample_transcription(test_audio)
        if sample_result:
            print(f"采样结果: '{sample_result}'")
            lang = detect_text_language(sample_result)
            print(f"检测语言: {lang}")
        else:
            print("采样失败或无结果")
    else:
        print("未找到测试音频文件")

    print("采样转录测试完成\n")

if __name__ == "__main__":
    try:
        test_basic_functions()
        test_sample_audio()
        print("所有测试完成!")
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
