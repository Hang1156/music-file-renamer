#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
music_file_renamer.py - 音乐文件轨道号重命名工具

解决音乐文件拷贝到 MP3 播放器或车机后顺序混乱的问题。
通过读取音频文件的元数据（轨道号），将文件重命名为统一格式，
确保在按文件名排序的设备上也能正确显示播放顺序。

作者：AI Assistant
"""

import os
import sys
import argparse
import re
from pathlib import Path

try:
    from mutagen import File as MutagenFile
    from mutagen.id3 import ID3
    from mutagen.flac import FLAC
    from mutagen.mp4 import MP4
    from mutagen.wave import WAVE
except ImportError:
    print("错误：未找到 mutagen 库，请先安装：pip install mutagen")
    sys.exit(1)


# 支持的音频文件扩展名
SUPPORTED_EXTENSIONS = {'.mp3', '.flac', '.wav', '.m4a'}

# 用于检测文件名是否已符合格式的正则表达式
# 匹配格式：数字（可带前导零） + " - " + 任意内容
ALREADY_RENAMED_PATTERN = re.compile(r'^\d+\s*-\s*.+')


def extract_track_number(audio_file):
    """
    从音频文件中提取轨道号（Track Number）
    
    参数:
        audio_file: mutagen 音频文件对象
    
    返回:
        int 或 None: 轨道号，如果无法提取则返回 None
    """
    try:
        # 不同格式的文件，元数据存储位置不同
        if audio_file.tags is None:
            return None
        
        track_number = None
        
        # MP3 文件 (ID3 标签)
        if isinstance(audio_file.tags, ID3):
            # TRCK 帧存储轨道号，格式可能是 "1" 或 "1/10"
            trck_frame = audio_file.tags.get('TRCK')
            if trck_frame:
                track_str = str(trck_frame)
                # 处理 "1/10" 格式，只取分子部分
                track_str = track_str.split('/')[0]
                try:
                    track_number = int(track_str)
                except ValueError:
                    pass
        
        # FLAC 文件
        elif isinstance(audio_file, FLAC):
            track_str = audio_file.get('tracknumber', [None])[0]
            if track_str:
                track_str = str(track_str).split('/')[0]
                try:
                    track_number = int(track_str)
                except ValueError:
                    pass
        
        # M4A 文件 (MP4/AAC)
        elif hasattr(audio_file, 'tags') and audio_file.tags is not None:
            # MP4 使用 trkn 字段，是一个元组 (track, total)
            if hasattr(audio_file.tags, 'trkn') and audio_file.tags.trkn:
                track_number = audio_file.tags.trkn[0][0]
        
        # WAV 文件
        elif isinstance(audio_file, WAVE):
            # WAV 文件的标签支持有限，尝试通用方法
            if hasattr(audio_file.tags, 'get'):
                track_str = audio_file.tags.get('TRCK')
                if track_str:
                    track_str = str(track_str).split('/')[0]
                    try:
                        track_number = int(track_str)
                    except ValueError:
                        pass
        
        # 通用回退方法：尝试从 tags 字典中获取
        if track_number is None and hasattr(audio_file.tags, '__getitem__'):
            for key in ['tracknumber', 'TRACKNUMBER', 'TRCK', 'track']:
                try:
                    value = audio_file.tags[key]
                    if isinstance(value, list) and len(value) > 0:
                        value = value[0]
                    if isinstance(value, tuple) and len(value) > 0:
                        value = value[0]
                    track_str = str(value).split('/')[0]
                    track_number = int(track_str)
                    break
                except (KeyError, ValueError, TypeError, IndexError):
                    continue
        
        return track_number
        
    except Exception as e:
        print(f"  警告：提取轨道号时出错：{e}")
        return None


def extract_title(audio_file):
    """
    从音频文件中提取标题（Title）
    
    参数:
        audio_file: mutagen 音频文件对象
    
    返回:
        str 或 None: 标题，如果无法提取则返回 None
    """
    try:
        if audio_file.tags is None:
            return None
        
        title = None
        
        # MP3 文件 (ID3 标签)
        if isinstance(audio_file.tags, ID3):
            title_frame = audio_file.tags.get('TIT2')
            if title_frame:
                title = str(title_frame)
        
        # FLAC 文件
        elif isinstance(audio_file, FLAC):
            title_list = audio_file.get('title')
            if title_list and len(title_list) > 0:
                title = title_list[0]
        
        # M4A 文件
        elif hasattr(audio_file, 'tags') and audio_file.tags is not None:
            if hasattr(audio_file.tags, '\xa9nam') and audio_file.tags['\xa9nam']:
                title = audio_file.tags['\xa9nam'][0]
        
        # WAV 文件
        elif isinstance(audio_file, WAVE):
            if hasattr(audio_file.tags, 'get'):
                title_value = audio_file.tags.get('TIT2')
                if title_value:
                    title = str(title_value)
        
        # 通用回退方法
        if title is None and hasattr(audio_file.tags, '__getitem__'):
            for key in ['title', 'TITLE', 'TIT2']:
                try:
                    value = audio_file.tags[key]
                    if isinstance(value, list) and len(value) > 0:
                        value = value[0]
                    title = str(value)
                    break
                except (KeyError, TypeError, IndexError):
                    continue
        
        return title
        
    except Exception as e:
        print(f"  警告：提取标题时出错：{e}")
        return None


def is_already_renamed(filename):
    """
    检查文件名是否已经符合 [数字] - [标题] 的格式
    
    参数:
        filename: 文件名（不含路径）
    
    返回:
        bool: 如果已符合格式返回 True，否则返回 False
    """
    # 去掉扩展名进行检查
    name_without_ext = os.path.splitext(filename)[0]
    return bool(ALREADY_RENAMED_PATTERN.match(name_without_ext))


def format_track_number(track_number):
    """
    格式化轨道号，确保两位数（补零）
    
    参数:
        track_number: 整数轨道号
    
    返回:
        str: 格式化后的轨道号字符串（如 "01", "10"）
    """
    return f"{track_number:02d}"


def generate_new_filename(original_filename, track_number, title):
    """
    生成新的文件名
    
    参数:
        original_filename: 原始文件名
        track_number: 轨道号（整数）
        title: 标题
    
    返回:
        str: 新文件名
    """
    # 获取原文件扩展名
    _, ext = os.path.splitext(original_filename)
    
    # 格式化轨道号
    formatted_track = format_track_number(track_number)
    
    # 清理标题中的非法文件名字符
    # Windows 和大多数文件系统不允许：\ / : * ? " < > |
    safe_title = title
    for char in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']:
        safe_title = safe_title.replace(char, '_')
    
    # 去除首尾空格
    safe_title = safe_title.strip()
    
    # 生成新文件名
    new_filename = f"{formatted_track} - {safe_title}{ext}"
    
    return new_filename


def process_audio_file(filepath, execute=False):
    """
    处理单个音频文件
    
    参数:
        filepath: 文件完整路径
        execute: 是否实际执行重命名（False 为预览模式）
    
    返回:
        tuple: (success, message) success 为布尔值，message 为描述信息
    """
    filename = os.path.basename(filepath)
    
    # 检查是否已符合命名格式
    if is_already_renamed(filename):
        return (True, f"跳过：文件名已符合格式 -> {filename}")
    
    # 尝试读取音频文件元数据
    try:
        audio_file = MutagenFile(filepath)
    except Exception as e:
        return (False, f"错误：无法读取文件元数据 - {e}")
    
    if audio_file is None:
        return (False, f"错误：不支持的文件格式或文件损坏")
    
    # 提取轨道号
    track_number = extract_track_number(audio_file)
    if track_number is None:
        return (False, f"跳过：未找到轨道号信息")
    
    # 提取标题
    title = extract_title(audio_file)
    if title is None:
        # 如果没有标题，使用轨道号作为备选
        title = f"Track {track_number}"
        print(f"  提示：未找到标题，使用默认标题 '{title}'")
    
    # 生成新文件名
    new_filename = generate_new_filename(filename, track_number, title)
    
    # 检查新旧文件名是否相同
    if new_filename == filename:
        return (True, f"跳过：文件名无需更改 -> {filename}")
    
    # 输出结果
    if execute:
        # 实际执行重命名
        new_filepath = os.path.join(os.path.dirname(filepath), new_filename)
        
        # 检查目标文件是否已存在
        if os.path.exists(new_filepath):
            return (False, f"错误：目标文件已存在 -> {new_filename}")
        
        try:
            os.rename(filepath, new_filepath)
            return (True, f"重命名：{filename} -> {new_filename}")
        except PermissionError:
            return (False, f"错误：无权限修改文件")
        except OSError as e:
            return (False, f"错误：重命名失败 - {e}")
    else:
        # 预览模式
        return (True, f"预览：{filename} -> {new_filename}")


def scan_directory(directory_path, execute=False):
    """
    扫描目录并处理所有音频文件
    
    参数:
        directory_path: 目录路径
        execute: 是否实际执行重命名
    
    返回:
        tuple: (success_count, skip_count, fail_count)
    """
    directory = Path(directory_path)
    
    if not directory.exists():
        print(f"错误：目录不存在 -> {directory_path}")
        return (0, 0, 0)
    
    if not directory.is_dir():
        print(f"错误：路径不是目录 -> {directory_path}")
        return (0, 0, 0)
    
    print(f"\n{'='*60}")
    if execute:
        print(f"执行模式：将实际重命名文件")
    else:
        print(f"预览模式：仅显示将要进行的操作（添加 -e 参数执行）")
    print(f"扫描目录：{directory.absolute()}")
    print(f"{'='*60}\n")
    
    success_count = 0
    skip_count = 0
    fail_count = 0
    
    # 收集所有支持的音频文件
    audio_files = []
    for ext in SUPPORTED_EXTENSIONS:
        audio_files.extend(directory.glob(f"*{ext}"))
        audio_files.extend(directory.glob(f"*{ext.upper()}"))
    
    if not audio_files:
        print(f"未找到支持的音频文件（支持：{', '.join(SUPPORTED_EXTENSIONS)}）")
        return (0, 0, 0)
    
    print(f"找到 {len(audio_files)} 个音频文件\n")
    
    # 按原文件名排序，保证输出顺序一致
    audio_files.sort(key=lambda x: x.name)
    
    # 处理每个文件
    for filepath in audio_files:
        success, message = process_audio_file(str(filepath), execute)
        print(message)
        
        if success:
            if "跳过" in message or "预览" in message:
                skip_count += 1
            else:
                success_count += 1
        else:
            fail_count += 1
    
    # 打印统计信息
    print(f"\n{'='*60}")
    print(f"处理完成！")
    print(f"  成功重命名：{success_count} 个文件")
    print(f"  跳过/无需更改：{skip_count} 个文件")
    print(f"  失败：{fail_count} 个文件")
    print(f"{'='*60}\n")
    
    return (success_count, skip_count, fail_count)


def main():
    """
    主函数：解析命令行参数并执行程序
    """
    # 创建参数解析器
    parser = argparse.ArgumentParser(
        description='音乐文件轨道号重命名工具 - 解决播放器顺序混乱问题',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  %(prog)s ./my_album                 # 预览模式，显示将要进行的操作
  %(prog)s ./my_album -e              # 执行模式，实际重命名文件
  %(prog)s /path/to/music --execute   # 使用绝对路径执行
  %(prog)s .                          # 处理当前目录

输出格式:
  文件将被重命名为：[轨道号] - [标题].[扩展名]
  例如：01 - 晴天.mp3

注意事项:
  - 默认使用预览模式，不会实际修改文件
  - 已符合格式的文件会被自动跳过
  - 缺少轨道号信息的文件会被跳过并提示
        """
    )
    
    # 定义命令行参数
    parser.add_argument(
        'directory',
        type=str,
        help='包含音乐文件的目录路径'
    )
    
    parser.add_argument(
        '-e', '--execute',
        action='store_true',
        help='执行实际的重命名操作（默认为预览模式）'
    )
    
    parser.add_argument(
        '-v', '--version',
        action='version',
        version='%(prog)s 1.0.0'
    )
    
    # 解析参数
    args = parser.parse_args()
    
    # 验证目录路径
    if not os.path.exists(args.directory):
        print(f"错误：目录不存在 -> {args.directory}")
        sys.exit(1)
    
    # 执行扫描和处理
    success, skip, fail = scan_directory(args.directory, args.execute)
    
    # 根据结果设置退出码
    if fail > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
