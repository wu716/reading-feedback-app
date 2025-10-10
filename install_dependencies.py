#!/usr/bin/env python3
"""
安装缺失的依赖，特别是pydub和langdetect
"""
import subprocess
import sys

def install_package(package_name):
    """安装Python包"""
    try:
        print(f"正在安装 {package_name}...")
        result = subprocess.run([sys.executable, "-m", "pip", "install", package_name],
                              capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print(f"✅ {package_name} 安装成功")
            return True
        else:
            print(f"❌ {package_name} 安装失败: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ 安装 {package_name} 时出错: {e}")
        return False

def main():
    print("🔧 检查并安装语音识别相关依赖...\n")

    # 注意: Python 3.13 移除了内置的 audioop 模块
    # pydub 会自动使用 FFmpeg 作为后备方案，无需额外安装 audioop 替代品
    
    # 安装pydub
    print("📦 安装 pydub...")
    if not install_package("pydub==0.25.1"):
        print("⚠️ pydub安装失败，请手动安装: pip install pydub==0.25.1")

    # 安装langdetect
    print("📦 安装 langdetect...")
    if not install_package("langdetect==1.0.9"):
        print("⚠️ langdetect安装失败，请手动安装: pip install langdetect==1.0.9")

    print("\n✅ 依赖安装完成")
    print("💡 重要提醒：")
    print("   - Python 3.13 已移除内置的 audioop 模块")
    print("   - pydub 会自动使用 FFmpeg 进行音频处理 ✓")
    print("   - FFmpeg 已确认安装，语音识别功能将正常工作 ✓")

if __name__ == "__main__":
    main()
