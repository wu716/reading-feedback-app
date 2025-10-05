# -*- coding: utf-8 -*-
"""
检查 Vosk 模型安装状态
"""
import os
import sys

def check_vosk_model():
    print("🎤 检查 Vosk 中文语音识别模型")
    print("=" * 50)
    
    model_dir = "models"
    model_name = "vosk-model-small-cn-0.22"
    model_path = os.path.join(model_dir, model_name)
    
    print(f"📁 检查路径: {model_path}")
    print()
    
    # 检查目录是否存在
    if not os.path.exists(model_dir):
        print("❌ models 目录不存在")
        return False
    
    if not os.path.exists(model_path):
        print("❌ 模型目录不存在")
        print(f"   期望路径: {model_path}")
        return False
    
    # 检查必要的子目录
    required_dirs = ['am', 'graph', 'ivector', 'conf']
    missing_dirs = []
    
    for dir_name in required_dirs:
        dir_path = os.path.join(model_path, dir_name)
        if not os.path.exists(dir_path):
            missing_dirs.append(dir_name)
    
    if missing_dirs:
        print("❌ 模型目录不完整")
        print(f"   缺少目录: {', '.join(missing_dirs)}")
        return False
    
    # 检查 vosk 库
    try:
        import vosk
        print("✅ Vosk 库已安装")
    except ImportError:
        print("❌ Vosk 库未安装")
        print("   请运行: pip install vosk")
        return False
    
    # 尝试加载模型
    try:
        model = vosk.Model(model_path)
        print("✅ 模型加载成功")
        print("🎉 语音识别功能已就绪！")
        return True
    except Exception as e:
        print(f"❌ 模型加载失败: {e}")
        return False

if __name__ == "__main__":
    success = check_vosk_model()
    if success:
        print("\n🚀 现在可以重新启动应用，语音识别功能将正常工作！")
    else:
        print("\n📋 请按照以下步骤完成安装：")
        print("1. 访问: https://alphacephei.com/vosk/models")
        print("2. 下载: vosk-model-small-cn-0.22")
        print("3. 解压到: models/vosk-model-small-cn-0.22/")
        print("4. 重新运行此脚本检查")
    
    sys.exit(0 if success else 1)
