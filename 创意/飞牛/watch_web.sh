#!/bin/bash
MONITOR_DIR="/vol1/1000/webdemo"
SCRIPT_PATH="/vol1/1000/webdemo/update_index.py"

# 监控 增加、删除、移动 文件事件
inotifywait -m -e create -e delete -e moved_to -e moved_from "$MONITOR_DIR" --format '%f' | while read FILE
do
    # 排除 index.html 自身的变动，防止死循环
    if [ "$FILE" != "index.html" ]; then
        echo "检测到文件 $FILE 变动，正在更新索引..."
        python3 "$SCRIPT_PATH"
    fi
done