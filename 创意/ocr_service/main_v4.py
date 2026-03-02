import gc
import os
import subprocess
import paddle
import torch
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

# 显式设置环境变量防止 Paddle 报错
os.environ['FLAGS_allocator_strategy'] = 'auto_growth'

app = FastAPI(title="PaddleOCR-VL 4090 Final Service")

class OcrTask(BaseModel):
    file_path: str

# 全局变量：模型单例
pipeline = None

def get_pipeline():
    """单例模式加载模型，避免 PDX reinitialization 错误"""
    global pipeline
    if pipeline is None:
        print(">>> [AI] 正在初始化 PaddleOCR-VL 模型 (仅限一次)...")
        from paddleocr import PaddleOCRVL
        pipeline = PaddleOCRVL()
    return pipeline

def release_gpu_memory():
    """释放显存但保留模型对象在内存中（如果需要彻底关闭，请参考之前 del pipeline 的逻辑）"""
    # 注意：因为 PaddleX/PDX 不支持重复初始化，我们保留 pipeline 对象
    # 仅清理计算缓存
    paddle.device.cuda.empty_cache()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    gc.collect()
    print(">>> [GPU] 显存已清理。")

@app.post("/convert")
async def convert_ppt(task: OcrTask, background_tasks: BackgroundTasks):
    input_file = Path(task.file_path)
    if not input_file.exists():
        raise HTTPException(status_code=404, detail="PPT 文件未找到")

    try:
        # 1. 获取模型 (第一次调用会慢，后续会快)
        model = get_pipeline()

        # 2. PPT 转 PDF
        pdf_path = input_file.with_suffix(".pdf")
        print(f">>> [Process] 转换 PDF: {input_file.name}")
        subprocess.run([
            'libreoffice', '--headless', '--convert-to', 'pdf',
            str(input_file), '--outdir', str(input_file.parent)
        ], check=True)

        # 3. 推理
        print(">>> [AI] 正在解析文档...")
        output = model.predict(input=str(pdf_path))
        
        # 4. 提取 Markdown 内容
        markdown_list = [res.markdown for res in output]
        final_markdown = model.concatenate_markdown_pages(markdown_list)

        # 5. 清理 PDF
        if pdf_path.exists():
            os.remove(pdf_path)

        background_tasks.add_task(release_gpu_memory)

        return {
            "status": "success",
            "markdown": final_markdown
        }

    except Exception as e:
        print(f"!!! 运行时错误: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)