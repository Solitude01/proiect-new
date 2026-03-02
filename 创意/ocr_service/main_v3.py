import gc
import os
import subprocess
import paddle
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

app = FastAPI(title="PaddleOCR-VL 4090 Native Service")

class OcrTask(BaseModel):
    file_path: str 

def release_gpu_memory():
    """使用 Paddle 原生接口彻底释放 4090 显存"""
    global pipeline
    if 'pipeline' in globals():
        del pipeline
    
    # 强制 Python 垃圾回收
    gc.collect()
    # 释放 Paddle 显存池
    paddle.device.cuda.empty_cache()
    print(">>> [GPU] 任务结束，4090 显存已释放。")

@app.post("/convert")
async def convert_ppt(task: OcrTask, background_tasks: BackgroundTasks):
    input_file = Path(task.file_path)
    if not input_file.exists():
        raise HTTPException(status_code=404, detail="PPT 文件路径不存在")

    # 1. 动态加载模型
    print(">>> [AI] 正在加载 PaddleOCR-VL...")
    from paddleocr import PaddleOCRVL
    global pipeline
    pipeline = PaddleOCRVL()

    try:
        # 2. PPT 转 PDF (借助已安装的 LibreOffice)
        pdf_path = input_file.with_suffix(".pdf")
        print(f">>> [Process] 正在转换 PDF: {input_file.name}")
        subprocess.run([
            'libreoffice', '--headless', '--convert-to', 'pdf',
            str(input_file), '--outdir', str(input_file.parent)
        ], check=True)

        # 3. OCR 推理与 Markdown 合并
        print(">>> [AI] 正在解析文档结构...")
        output = pipeline.predict(input=str(pdf_path))
        
        markdown_list = [res.markdown for res in output]
        # 官方接口合并各页内容
        final_markdown = pipeline.concatenate_markdown_pages(markdown_list)

        # 4. 清理 PDF
        if pdf_path.exists():
            os.remove(pdf_path)

        # 5. 注册后台释放任务
        background_tasks.add_task(release_gpu_memory)

        return {
            "status": "success",
            "markdown": final_markdown
        }

    except Exception as e:
        background_tasks.add_task(release_gpu_memory)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)