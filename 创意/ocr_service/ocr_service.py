import gc
import os
import subprocess
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import paddle

# 尝试导入 torch 用于清空显存 (如果是 NVIDIA 环境常用技巧)
try:
    import torch
except ImportError:
    torch = None

app = FastAPI(title="PaddleOCR-VL Dynamic Service")

class OcrTask(BaseModel):
    file_path: str

def release_mem():
    """彻底释放显存的逻辑"""
    global pipeline
    if 'pipeline' in globals():
        del pipeline
    
    # 强制进行垃圾回收
    gc.collect()
    
    # 释放 PaddlePaddle 内部显存池
    paddle.device.cuda.empty_cache()
    
    # 如果环境中有 torch，也一并清理防止占用
    if torch and torch.cuda.is_available():
        torch.cuda.empty_cache()
    print("--- GPU Memory Released ---")

@app.post("/convert")
async def convert_ppt(task: OcrTask, background_tasks: BackgroundTasks):
    input_file = Path(task.file_path)
    if not input_file.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # 1. 动态加载模型 (即开)
    print("--- Loading PaddleOCR-VL (GPU) ---")
    from paddleocr import PaddleOCRVL
    global pipeline
    pipeline = PaddleOCRVL()

    try:
        # 2. PPT 转 PDF
        pdf_path = input_file.with_suffix(".pdf")
        subprocess.run([
            'libreoffice', '--headless', '--convert-to', 'pdf',
            str(input_file), '--outdir', str(input_file.parent)
        ], check=True)

        # 3. 推理 (参考官方 PDF 文档解析逻辑)
        output = pipeline.predict(input=str(pdf_path))
        
        markdown_list = []
        for res in output:
            markdown_list.append(res.markdown)
        
        # 4. 合并并获取最终文本
        final_markdown = pipeline.concatenate_markdown_pages(markdown_list)

        # 5. 清理临时文件
        if pdf_path.exists():
            os.remove(pdf_path)

        # 6. 注册后台任务：在响应发送后立即释放显存 (即关)
        background_tasks.add_task(release_mem)

        return {
            "status": "success",
            "markdown": final_markdown
        }

    except Exception as e:
        # 报错也要尝试释放，防止显存卡死
        background_tasks.add_task(release_mem)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)