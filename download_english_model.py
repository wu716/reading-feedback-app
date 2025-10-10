#!/usr/bin/env python3
"""
下载英文Vosk模型脚本
"""
import os
import urllib.request
import zipfile

def download_and_extract_model():
    """下载并解压英文Vosk模型"""
    model_url = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
    zip_path = "models/vosk-model-small-en-us-0.15.zip"
    extract_path = "models/vosk-model-small-en-us-0.15"

    # 创建models目录（如果不存在）
    os.makedirs("models", exist_ok=True)

    # 检查是否已存在
    if os.path.exists(extract_path):
        print(f"英文模型已存在: {extract_path}")
        return True

    try:
        print(f"正在下载英文模型: {model_url}")
        print("这可能需要几分钟，请耐心等待...")

        # 显示下载进度
        def progress(block_num, block_size, total_size):
            downloaded = block_num * block_size
            percent = min(100, downloaded * 100 / total_size)
            print(f"\r下载进度: {percent:.1f}% ({downloaded/1024/1024:.1f}MB/{total_size/1024/1024:.1f}MB)", end='', flush=True)

        urllib.request.urlretrieve(model_url, zip_path, progress)
        print("\n下载完成，正在解压...")

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall("models")

        # 删除zip文件
        os.remove(zip_path)

        print(f"英文模型下载并解压完成: {extract_path}")
        print("模型大小约40MB，现在可以识别英文音频了！")
        return True

    except Exception as e:
        print(f"下载失败: {e}")
        if os.path.exists(zip_path):
            os.remove(zip_path)
        return False

if __name__ == "__main__":
    success = download_and_extract_model()
    if success:
        print("\n✅ 英文Vosk模型准备完成!")
        print("现在您可以使用英文语音识别了。")
    else:
        print("\n❌ 英文Vosk模型下载失败!")
        print("请手动下载: https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip")
        print("然后解压到 models/ 目录下")
