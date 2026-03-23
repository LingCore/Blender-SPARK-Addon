#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Blender 插件打包脚本

功能：
- 将 bofu_enhanced 文件夹打包成 zip 文件
- 自动从 __init__.py 读取版本号
- 排除 __pycache__、.pyc 等不需要的文件
- 生成带版本号的 zip 文件名

使用方法：
- 双击运行 pack_addon.bat
- 或者命令行运行: python pack_addon.py
"""

import os
import sys
import zipfile
import re
import io
from datetime import datetime

# 修复 Windows 控制台编码问题
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ==================== 配置 ====================

ADDON_FOLDER = "bofu_enhanced"
OUTPUT_PREFIX = "blender_spark_addon"

# 要排除的文件/文件夹模式
EXCLUDE_PATTERNS = [
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".git",
    ".gitignore",
    ".DS_Store",
    "Thumbs.db",
    "*.blend1",
    "*.blend2",
]

# ==================== 函数 ====================

def get_version_from_init(addon_path):
    """从 __init__.py 读取版本号"""
    init_file = os.path.join(addon_path, "__init__.py")
    
    if not os.path.exists(init_file):
        return None
    
    try:
        with open(init_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 匹配 "version": (x, y, z) 格式
        match = re.search(r'"version"\s*:\s*\((\d+),\s*(\d+),\s*(\d+)\)', content)
        if match:
            return f"{match.group(1)}.{match.group(2)}.{match.group(3)}"
    except Exception as e:
        print(f"[!] 读取版本号失败: {e}")
    
    return None


def should_exclude(name):
    """检查文件/文件夹是否应该被排除"""
    import fnmatch
    
    for pattern in EXCLUDE_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            return True
        if name == pattern:
            return True
    
    return False


def pack_addon(script_dir):
    """打包插件"""
    addon_path = os.path.join(script_dir, ADDON_FOLDER)
    
    # 检查插件文件夹是否存在
    if not os.path.exists(addon_path):
        print(f"[X] 错误: 找不到插件文件夹 '{ADDON_FOLDER}'")
        print(f"    请确保脚本位于插件文件夹的同级目录")
        return False
    
    # 获取版本号
    version = get_version_from_init(addon_path)
    if version:
        print(f"[*] 检测到版本: v{version}")
    else:
        version = datetime.now().strftime("%Y%m%d")
        print(f"[!] 未能读取版本号，使用日期: {version}")
    
    # 生成输出文件名
    output_filename = f"{OUTPUT_PREFIX}_v{version}.zip"
    output_path = os.path.join(script_dir, output_filename)
    
    if os.path.exists(output_path):
        print(f"[*] 覆盖已有文件: {output_filename}")
    
    print(f"[*] 源文件夹: {addon_path}")
    print(f"[*] 输出文件: {output_filename}")
    print()
    
    # 开始打包
    file_count = 0
    
    try:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(addon_path):
                # 排除不需要的目录
                dirs[:] = [d for d in dirs if not should_exclude(d)]
                
                for file in files:
                    # 排除不需要的文件
                    if should_exclude(file):
                        continue
                    
                    file_path = os.path.join(root, file)
                    # 计算在 zip 中的相对路径（保持 bofu_enhanced 作为顶级目录）
                    arcname = os.path.relpath(file_path, script_dir)
                    
                    zipf.write(file_path, arcname)
                    file_count += 1
                    print(f"  + {arcname}")
        
        print()
        print(f"[OK] 打包完成!")
        print(f"     文件数量: {file_count}")
        print(f"     输出路径: {output_path}")
        
        # 显示文件大小
        size_bytes = os.path.getsize(output_path)
        if size_bytes < 1024:
            size_str = f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            size_str = f"{size_bytes / 1024:.1f} KB"
        else:
            size_str = f"{size_bytes / (1024 * 1024):.2f} MB"
        print(f"     文件大小: {size_str}")
        
        return True
        
    except Exception as e:
        print(f"[X] 打包失败: {e}")
        return False


def main():
    """主函数"""
    print("=" * 50)
    print("  Blender Enhanced Toolkit 打包工具")
    print("=" * 50)
    print()
    
    # 获取脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    success = pack_addon(script_dir)
    
    print()
    print("=" * 50)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
