# -*- coding: utf-8 -*-
import subprocess
import os
import shutil
import sys # Keep sys for potential future use, like exiting on critical ffmpeg check failure
from typing import Tuple, Optional # For type hinting the return value

# --- 检查 FFmpeg ---
def check_ffmpeg():
    """检查 ffmpeg 是否安装并在 PATH 中"""
    if shutil.which("ffmpeg") is None:
         # 在 Web 应用中，打印到控制台可能不直接可见，但对调试有用
         print("="*60)
         print("错误: 未找到 'ffmpeg' 可执行程序！")
         print("请确保 FFmpeg 已经安装，并且添加到了系统环境变量 PATH 中。")
         print("可以从 https://ffmpeg.org/download.html 下载。")
         print("="*60)
         # 在 Web 后端，通常不使用 input()
         # input("按回车键(Enter)退出...") 
         return False
    # print("✅ FFmpeg 已找到。") # 移除不必要的成功打印
    return True

# --- 配置 (从原脚本保留，可能在 main.py 中使用) ---
SUPPORTED_EXTENSIONS = ['.mp4', '.mov', '.mkv', '.avi', '.webm', '.flv', '.wmv']
DEFAULT_FPS = 15 
# --- 配置结束 ---

def convert_video_to_apng(input_file: str, output_file: str, fps: int) -> Tuple[bool, Optional[str]]:
    """
     使用 ffmpeg 将单个视频文件转换为 APNG (核心函数)
     返回: (bool, Optional[str]) -> (成功状态, 错误信息或None)
    """
    # 构建 ffmpeg 命令
    command = [
        'ffmpeg',
        '-hide_banner',
        '-loglevel', 'error', # 只显示错误
        '-y',  # 自动覆盖
        '-i', input_file,
         # 使用 scale 滤镜确保色彩空间和像素格式对APNG友好，并设置fps
         # sws_flags=lanczos 或 bicubic 可以提高缩放/采样质量，这里主要用于fps
        '-vf', f'fps={fps},scale=-1:-1:flags=lanczos', 
        '-plays', '0',  # 0 = 无限循环
        # 可以尝试添加参数控制优化，但默认通常最好。例如禁用预测: -pred none
        '-f', 'apng', # 强制输出APNG格式
        output_file
    ]

    try:
        process = subprocess.run(
            command, 
            check=True, 
            capture_output=True, 
            text=True,
            encoding='utf-8',
            errors='replace' # handle potential encoding errors in stderr
            )
        # print(f"    ✅ 成功: {os.path.basename(input_file)} -> {os.path.basename(output_file)}") # 移除 print
        return True, None # 成功时返回 True 和 None 错误信息
    except subprocess.CalledProcessError as e:
        error_message = f"FFmpeg 转换失败 (返回码: {e.returncode}):\n{e.stderr.strip()}"
        # print(f"    ❌ 失败: 转换 {os.path.basename(input_file)} 时 FFmpeg 发生错误!") # 移除 print
        # print(f"       命令: {' '.join(e.cmd)}") # 移除 print
        # print(f"       返回码: {e.returncode}") # 移除 print
        # print(f"       错误信息:\n{e.stderr.strip()}") # 移除 print
        return False, error_message # 失败时返回 False 和错误信息
    except Exception as e:
        error_message = f"运行 FFmpeg 时发生未知错误: {type(e).__name__} - {e}"
        # print(f"    ❌ 失败: 运行 FFmpeg 时发生未知错误: {type(e).__name__} - {e}") # 移除 print
        return False, error_message # 失败时返回 False 和错误信息

# 移除了原脚本的 process_path 和 main 函数，这些逻辑将在 FastAPI 中处理
