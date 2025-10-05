# -*- coding: utf-8 -*-
"""
修复 Vosk 模型目录结构
解决双重嵌套问题
"""
import os
import shutil
import sys

def fix_vosk_model_structure():
    print("🔧 修复 Vosk 模型目录结构")
    print("=" * 50)
    
    model_dir = "models"
    model_name = "vosk-model-small-cn-0.22"
    model_path = os.path.join(model_dir, model_name)
    nested_path = os.path.join(model_path, model_name)  # 双重嵌套路径
    
    print(f"📁 检查路径: {model_path}")
    print(f"📁 嵌套路径: {nested_path}")
    print()
    
    # 检查是否存在双重嵌套
    if os.path.exists(nested_path):
        print("❌ 发现双重嵌套问题！")
        print(f"   嵌套目录: {nested_path}")
        
        # 检查嵌套目录中是否有正确的文件
        required_dirs = ['am', 'graph', 'ivector', 'conf']
        nested_has_files = all(os.path.exists(os.path.join(nested_path, d)) for d in required_dirs)
        
        if nested_has_files:
            print("✅ 嵌套目录中包含正确的模型文件")
            print("🔄 开始修复目录结构...")
            
            try:
                # 创建临时目录
                temp_dir = os.path.join(model_dir, f"{model_name}_temp")
                
                # 移动嵌套目录中的内容到临时目录
                print(f"   移动文件到临时目录: {temp_dir}")
                shutil.move(nested_path, temp_dir)
                
                # 删除空的嵌套目录
                if os.path.exists(model_path):
                    os.rmdir(model_path)
                
                # 将临时目录重命名为正确的模型目录
                print(f"   重命名临时目录为: {model_path}")
                shutil.move(temp_dir, model_path)
                
                print("✅ 目录结构修复完成！")
                
                # 验证修复结果
                if all(os.path.exists(os.path.join(model_path, d)) for d in required_dirs):
                    print("🎉 修复成功！模型目录结构正确")
                    return True
                else:
                    print("❌ 修复后验证失败")
                    return False
                    
            except Exception as e:
                print(f"❌ 修复过程中出错: {e}")
                return False
        else:
            print("❌ 嵌套目录中缺少必要的模型文件")
            return False
    else:
        print("✅ 目录结构正常，无需修复")
        return True

if __name__ == "__main__":
    success = fix_vosk_model_structure()
    if success:
        print("\n🚀 现在可以重新运行检查脚本验证修复结果！")
    else:
        print("\n❌ 修复失败，请手动调整目录结构")
    
    sys.exit(0 if success else 1)
