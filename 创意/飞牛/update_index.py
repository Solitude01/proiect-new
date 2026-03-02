import os
from datetime import datetime

# --- 配置 ---
TARGET_DIR = "."
OUTPUT_FILE = "index.html"
# 排除掉脚本本身和已经生成的 index.html
EXCLUDE_FILES = ["index.html", "update_index.py"]

# --- HTML 模板 ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI 项目演示门户</title>
    <style>
        :root {{ --primary: #2563eb; --bg: #f8fafc; --text: #1e293b; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
               background: var(--bg); color: var(--text); margin: 0; padding: 40px 20px; }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        header {{ margin-bottom: 40px; text-align: center; }}
        h1 {{ color: #0f172a; font-size: 2.5rem; margin-bottom: 10px; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; }}
        .card {{ background: white; padding: 24px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
                text-decoration: none; color: inherit; transition: all 0.3s ease; border: 1px solid #e2e8f0;
                display: flex; flex-direction: column; justify-content: space-between; }}
        .card:hover {{ transform: translateY(-5px); box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); border-color: var(--primary); }}
        .card-title {{ font-weight: 600; font-size: 1.1rem; margin-bottom: 8px; color: var(--primary); }}
        .card-footer {{ font-size: 0.85rem; color: #64748b; margin-top: 15px; border-top: 1px solid #f1f5f9; padding-top: 10px; }}
        .tag {{ background: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🚀 智能制造演示门户</h1>
            <p>自动化生成的项目索引页面</p>
        </header>
        <div class="grid">
            {content}
        </div>
        <footer style="margin-top: 50px; text-align: center; color: #94a3b8; font-size: 0.9rem;">
            最后更新于: {update_time}
        </footer>
    </div>
</body>
</html>
"""

def generate():
    # 获取目录下所有的 html 文件
    files = [f for f in os.listdir(TARGET_DIR) 
             if f.endswith('.html') and f not in EXCLUDE_FILES]
    
    # 按照文件名排序
    files.sort()

    cards_html = ""
    for file in files:
        # 获取文件修改时间作为展示
        mtime = os.path.getmtime(os.path.join(TARGET_DIR, file))
        date_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
        
        # 移除 .html 后缀作为标题
        title = file.replace('.html', '')
        
        cards_html += f"""
        <a href="{file}" class="card">
            <div>
                <div class="card-title">{title}</div>
                <span class="tag">HTML 演示</span>
            </div>
            <div class="card-footer">修改时间: {date_str}</div>
        </a>
        """

    # 填充模板
    final_html = HTML_TEMPLATE.format(
        content=cards_html, 
        update_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(final_html)
    
    print(f"成功! 已生成包含 {len(files)} 个页面的索引页。")

if __name__ == "__main__":
    generate()