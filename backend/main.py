import os
import shutil
import uuid
import zipfile
import logging
import asyncio # 导入 asyncio
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from contextlib import asynccontextmanager # 导入 asynccontextmanager

from fastapi import FastAPI, File, UploadFile, BackgroundTasks, HTTPException, Request # Keep BackgroundTasks (plural) for adding tasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask # Import BackgroundTask (singular) for FileResponse
from pydantic import BaseModel, Field
import aiofiles

# 假设 converter.py 在同一目录下
from converter import check_ffmpeg, convert_video_to_apng

# --- 配置 ---
# 使用绝对路径以避免相对路径问题
BASE_DIR = Path(__file__).resolve().parent.parent
TEMP_BASE_DIR = BASE_DIR / "temp_files"
TEMP_UPLOADS_DIR = TEMP_BASE_DIR / "uploads"
TEMP_RESULTS_DIR = TEMP_BASE_DIR / "results"
FRONTEND_DIR = BASE_DIR / "frontend"
DEFAULT_FPS = 15 # 定义默认FPS

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 任务状态存储 ---
tasks: Dict[str, Dict[str, Any]] = {}

# --- Pydantic 模型 ---
class ConvertRequest(BaseModel):
    task_id: str
    fps: Optional[int] = Field(None, gt=0, description="目标帧率，必须大于0 (可选, 默认使用 DEFAULT_FPS)")

class FailedFileDetail(BaseModel):
    file_name: str
    message: str

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str # e.g., "uploaded", "queued", "processing", "complete", "failed"
    progress: float = 0.0 # 0.0 to 1.0
    total_files: int = 0
    processed_files: int = 0
    fps: Optional[int] = None # 实际使用的FPS
    successful_files: List[str] = []
    failed_files: List[FailedFileDetail] = []

# --- Lifespan 事件处理器 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 应用启动时执行的代码 (替代 @app.on_event("startup"))
    logger.info("应用启动...")
    if not check_ffmpeg():
        logger.error("FFmpeg 未找到或无法执行。请确保已安装并添加到系统 PATH。")
        # Consider raising an error or handling it appropriately
    try:
        TEMP_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        TEMP_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"临时上传目录已确认/创建: {TEMP_UPLOADS_DIR}")
        logger.info(f"临时结果目录已确认/创建: {TEMP_RESULTS_DIR}")
    except OSError as e:
        logger.error(f"创建临时目录失败: {e}")
        raise RuntimeError(f"无法创建临时目录: {e}")

    yield # 应用运行时执行

    # 应用关闭时执行的代码 (替代 @app.on_event("shutdown"))
    logger.info("应用关闭...")
    # 可选：在此处添加清理逻辑，例如删除 temp_files 目录
    # try:
    #     if TEMP_BASE_DIR.exists():
    #         shutil.rmtree(TEMP_BASE_DIR)
    #         logger.info(f"已清理临时文件目录: {TEMP_BASE_DIR}")
    # except OSError as e:
    #     logger.error(f"清理临时文件目录失败: {e}")


# --- FastAPI 应用 ---
# 将 lifespan 函数传递给 FastAPI 实例
app = FastAPI(title="Video to APNG Converter API", lifespan=lifespan)

# 移除旧的 @app.on_event("startup") 装饰器

# --- 后台转换任务 ---
async def run_conversion_task(task_id: str, fps_to_use: int):
    """后台执行视频转换"""
    if task_id not in tasks:
        logger.error(f"任务 {task_id} 在开始处理时未找到。")
        return

    task = tasks[task_id]
    task["status"] = "processing"
    task["fps"] = fps_to_use # 记录实际使用的FPS
    task["processed_files"] = 0
    task["successful_files"] = []
    task["failed_files"] = []
    logger.info(f"任务 {task_id}: 开始处理，使用 FPS: {fps_to_use}")

    upload_dir = TEMP_UPLOADS_DIR / task_id
    result_dir = TEMP_RESULTS_DIR / task_id
    result_dir.mkdir(parents=True, exist_ok=True)

    input_files = task.get("input_files", [])
    task["total_files"] = len(input_files)

    for i, file_info in enumerate(input_files):
        original_filename = file_info["original_filename"]
        saved_path = Path(file_info["saved_path"])
        output_filename = saved_path.stem + ".png" # APNG 使用 .png 扩展名
        output_path = result_dir / output_filename

        logger.info(f"任务 {task_id}: 正在转换文件 {i+1}/{task['total_files']}: {original_filename} (FPS: {fps_to_use})")
        try:
            # 使用 asyncio.to_thread 在单独线程中运行同步的转换函数
            success, message = await asyncio.to_thread(
                convert_video_to_apng, str(saved_path), str(output_path), fps_to_use
            )
            if success:
                task["successful_files"].append(output_filename)
                logger.info(f"任务 {task_id}: 文件 {original_filename} 转换成功 -> {output_filename}")
            else:
                task["failed_files"].append({"file_name": original_filename, "message": message})
                logger.error(f"任务 {task_id}: 文件 {original_filename} 转换失败: {message}")
        except Exception as e:
            error_msg = f"转换过程中发生意外错误: {e}"
            task["failed_files"].append({"file_name": original_filename, "message": error_msg})
            logger.exception(f"任务 {task_id}: 文件 {original_filename} 转换时发生异常")

        task["processed_files"] = i + 1
        task["progress"] = task["processed_files"] / task["total_files"] if task["total_files"] > 0 else 1.0

    # 清理上传的临时文件
    try:
        shutil.rmtree(upload_dir)
        logger.info(f"任务 {task_id}: 已清理上传目录 {upload_dir}")
    except OSError as e:
        logger.error(f"任务 {task_id}: 清理上传目录 {upload_dir} 失败: {e}")


    if not task["failed_files"]:
        task["status"] = "complete"
        logger.info(f"任务 {task_id}: 处理完成，所有文件成功。")
    else:
        task["status"] = "failed" # 标记为 failed 即使有部分成功
        logger.warning(f"任务 {task_id}: 处理完成，有 {len(task['failed_files'])} 个文件失败。")


# --- API 端点 ---
@app.post("/upload")
async def upload_videos(files: List[UploadFile] = File(...)):
    """接收上传的视频文件"""
    task_id = str(uuid.uuid4())
    task_upload_dir = TEMP_UPLOADS_DIR / task_id
    task_upload_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"创建任务 {task_id} 的上传目录: {task_upload_dir}")

    input_files_info = []
    for file in files:
        if not file.filename:
            logger.warning(f"任务 {task_id}: 收到一个没有文件名的文件，已跳过。")
            continue
        safe_filename = file.filename
        file_path = task_upload_dir / safe_filename
        try:
            async with aiofiles.open(file_path, 'wb') as out_file:
                content = await file.read()
                await out_file.write(content)
            input_files_info.append({
                "original_filename": file.filename,
                "saved_path": str(file_path)
            })
            logger.info(f"任务 {task_id}: 文件 '{file.filename}' 已保存到 {file_path}")
        except Exception as e:
            logger.error(f"任务 {task_id}: 保存文件 '{file.filename}' 失败: {e}")

    if not input_files_info:
         raise HTTPException(status_code=400, detail="没有成功上传的文件。")

    tasks[task_id] = {
        "task_id": task_id,
        "status": "uploaded",
        "progress": 0.0,
        "total_files": len(input_files_info),
        "processed_files": 0,
        "fps": None,
        "input_files": input_files_info,
        "successful_files": [],
        "failed_files": []
    }
    logger.info(f"任务 {task_id}: 创建成功，包含 {len(input_files_info)} 个文件。")
    return {"task_id": task_id}


@app.post("/convert")
async def convert_videos(request: ConvertRequest, background_tasks: BackgroundTasks):
    """根据 task_id 和可选的 fps 启动转换任务"""
    task_id = request.task_id
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务 ID 未找到")

    task = tasks[task_id]
    if task["status"] not in ["uploaded", "complete", "failed"]:
        raise HTTPException(status_code=400, detail=f"任务当前状态为 '{task['status']}'，无法启动转换")

    fps_to_use = request.fps if request.fps is not None else DEFAULT_FPS
    logger.info(f"任务 {task_id}: 请求转换，将使用 FPS: {fps_to_use}")

    task["status"] = "queued"
    task["progress"] = 0.0
    task["processed_files"] = 0
    task["successful_files"] = []
    task["failed_files"] = []
    task["fps"] = fps_to_use

    result_dir = TEMP_RESULTS_DIR / task_id
    if result_dir.exists():
        try:
            shutil.rmtree(result_dir)
            logger.info(f"任务 {task_id}: 已清理旧的结果目录 {result_dir}")
        except OSError as e:
             logger.error(f"任务 {task_id}: 清理旧的结果目录 {result_dir} 失败: {e}")

    background_tasks.add_task(run_conversion_task, task_id, fps_to_use)
    logger.info(f"任务 {task_id}: 已添加到后台队列。")

    return {"message": "转换任务已加入队列"}


@app.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """获取指定任务的状态"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务 ID 未找到")
    task = tasks[task_id]
    return TaskStatusResponse(**task)


@app.get("/download/{task_id}")
async def download_results(task_id: str):
    """下载指定任务的结果（打包为 ZIP）"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务 ID 未找到")

    task = tasks[task_id]
    if task["status"] not in ["complete", "failed"]:
        raise HTTPException(status_code=400, detail="任务尚未完成或失败，无法下载")

    if not task["successful_files"]:
         raise HTTPException(status_code=404, detail="没有成功转换的文件可供下载")

    result_dir = TEMP_RESULTS_DIR / task_id
    zip_filename = f"apng_results_{task_id}.zip"
    zip_filepath = TEMP_RESULTS_DIR / zip_filename

    try:
        with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for filename in task["successful_files"]:
                file_to_add = result_dir / filename
                if file_to_add.is_file():
                    zipf.write(file_to_add, arcname=filename)
                else:
                     logger.warning(f"任务 {task_id}: 结果文件 {filename} 未找到，跳过打包。")

        if not os.path.exists(zip_filepath) or os.path.getsize(zip_filepath) == 0:
             logger.error(f"任务 {task_id}: ZIP 文件创建失败或为空。")
             raise HTTPException(status_code=500, detail="无法创建包含结果的 ZIP 文件。")

        logger.info(f"任务 {task_id}: 结果已打包到 {zip_filepath}")
        return FileResponse(
            path=zip_filepath,
            filename=zip_filename,
            media_type='application/zip',
            background=BackgroundTask(lambda: os.remove(zip_filepath) if os.path.exists(zip_filepath) else None)
        )

    except Exception as e:
        logger.exception(f"任务 {task_id}: 创建或发送 ZIP 文件时出错")
        raise HTTPException(status_code=500, detail=f"打包或下载结果时出错: {e}")


# --- 静态文件服务 ---
try:
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
    logger.info(f"静态文件目录已挂载: {FRONTEND_DIR}")
except RuntimeError as e:
     logger.error(f"挂载静态文件目录失败: {e}. 请确保 frontend 目录存在于 {BASE_DIR}。")


if __name__ == "__main__":
    import uvicorn
    # Lifespan 会自动处理启动检查和目录创建
    uvicorn.run(app, host="0.0.0.0", port=8000)
