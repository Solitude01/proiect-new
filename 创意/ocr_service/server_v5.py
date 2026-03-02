import os
import subprocess
import paddle
import gc
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from paddleocr import PaddleOCRVL

# 屏蔽导致段错误的特定优化
os.environ['FLAGS_allocator_strategy'] = 'auto_growth'
os.environ['DISABLE_PADDLE_TENSORRT'] = '1' 

app = FastAPI(title="PaddleOCR-VL Official v2.3 API")

class OcrTask(BaseModel):
    file_path: str

# 1. 按照指南初始化模型
print(">>> [AI] 正在初始化 PaddleOCR-VL 模型...")
pipeline = PaddleOCRVL()

def release_mem():
    paddle.device.cuda.empty_cache()
    gc.collect()

@app.post("/convert")
async def process_ppt(task: OcrTask, background_tasks: BackgroundTasks):
    input_file = Path(task.file_path)
    if not input_file.exists():
        raise HTTPException(status_code=404, detail="文件未找到")

    try:
        # 2. PPT -> PDF (容器内需要安装 libreoffice)
        pdf_path = input_file.with_suffix(".pdf")
        print(f">>> [Process] 转换 PDF: {input_file.name}")
        subprocess.run(['libreoffice', '--headless', '--convert-to', 'pdf', 
                        str(input_file), '--outdir', str(input_file.parent)], check=True)

        # 3. 按照官方 2.3 逻辑进行 PDF 解析
        print(">>> [AI] 执行多页文档解析...")
        output = pipeline.predict(input=str(pdf_path))
        
        markdown_list = []
        for res in output:
            markdown_list.append(res.markdown)

        # 4. 合并所有页面内容
        final_markdown = pipeline.concatenate_markdown_pages(markdown_list)

        # 5. 清理并释放
        if pdf_path.exists(): os.remove(pdf_path)
        background_tasks.add_task(release_mem)

        return {"status": "success", "markdown": final_markdown}

    except Exception as e:
        background_tasks.add_task(release_mem)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)