#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
下载 Vosk 中文语音识别模型
"""
import os
import urllib.request
import zipfile
import shutil

def download_vosk_model():
    """下载 Vosk 中文模型"""
    model_name = "vosk-model-small-cn-0.22"
    model_url = "https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip"
    zip_file = f"{model_name}.zip"
    
    print("正在下载 Vosk 中文语音识别模型...")
    print(f"模型名称: {model_name}")
    print(f"下载地址: {model_url}")
    
    try:
        # 下载模型文件
        print("开始下载...")
        urllib.request.urlretrieve(model_url, zip_file)
        print(f"下载完成: {zip_file}")
        
        # 解压模型文件
        print("正在解压...")
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            zip_ref.extractall('.')
        print("解压完成")
        
        # 删除压缩文件
        os.remove(zip_file)
        print(f"已删除压缩文件: {zip_file}")
        
        # 检查模型文件
        if os.path.exists(model_name):
            print(f"✅ 模型安装成功: {model_name}")
            print("现在可以运行应用进行语音识别了")
        else:
            print("❌ 模型安装失败")
            
    except Exception as e:
        print(f"❌ 下载失败: {e}")
        print("请手动下载模型:")
        print("1. 访问 https://alphacephei.com/vosk/models")
        print("2. 下载 vosk-model-small-cn-0.22.zip")
        print("3. 解压到项目根目录")

if __name__ == "__main__":
    download_vosk_model()
