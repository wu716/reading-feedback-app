#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单的语音识别测试
"""
import os
import sys

def test_vosk_import():
    """测试 Vosk 库导入"""
    try:
        import vosk
        print("✅ Vosk 库导入成功")
        return True
    except ImportError:
        print("❌ Vosk 库未安装，请运行: pip install vosk")
        return False

def test_model_path():
    """测试模型路径"""
    model_path = "models/vosk-model-small-cn-0.22"
    if os.path.exists(model_path):
        print(f"✅ 模型路径存在: {model_path}")
        return True
    else:
        print(f"❌ 模型路径不存在: {model_path}")
        return False

def test_model_loading():
    """测试模型加载"""
    try:
        import vosk
        model_path = "models/vosk-model-small-cn-0.22"
        model = vosk.Model(model_path)
        print("✅ Vosk 模型加载成功")
        return True
    except Exception as e:
        print(f"❌ Vosk 模型加载失败: {e}")
        return False

def main():
    print("🧪 语音识别功能测试")
    print("=" * 40)
    
    # 确保在正确的目录下运行
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    tests = [
        ("Vosk 库导入", test_vosk_import),
        ("模型路径检查", test_model_path),
        ("模型加载测试", test_model_loading)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        if test_func():
            passed += 1
    
    print(f"\n📊 测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 语音识别功能正常！")
        return True
    else:
        print("❌ 语音识别功能存在问题")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
