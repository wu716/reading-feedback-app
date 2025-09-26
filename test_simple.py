# -*- coding: utf-8 -*-
"""
简单测试脚本 - 诊断编码问题
"""
import sys
import os

print("=== 测试脚本开始 ===")

# 测试1: 直接打印
print("测试1: 直接打印中文")

# 测试2: 设置编码
if sys.platform == "win32":
    print("测试2: Windows 平台")
    try:
        import codecs
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())
        print("测试2: 使用 codecs 设置编码")
    except Exception as e:
        print(f"测试2 错误: {e}")

# 测试3: 使用 io 模块
print("测试3: 使用 io 模块")
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    print("测试3: 使用 io.TextIOWrapper 设置编码")
except Exception as e:
    print(f"测试3 错误: {e}")

# 测试4: 环境变量
print(f"测试4: Python 版本: {sys.version}")
print(f"测试4: 文件系统编码: {sys.getfilesystemencoding()}")
print(f"测试4: 标准输出编码: {sys.stdout.encoding}")

print("=== 测试脚本结束 ===")
