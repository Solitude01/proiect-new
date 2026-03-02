import os
import shutil
from pathlib import Path

def add_jpg_suffix_and_copy(source_dirs):
    """
    为指定目录下的所有文件添加.jpg后缀,并复制到新的副本文件夹
    
    Args:
        source_dirs: 源目录列表
    """
    for source_dir in source_dirs:
        source_path = Path(source_dir)
        
        # 检查源目录是否存在
        if not source_path.exists():
            print(f"警告: 目录不存在 - {source_dir}")
            continue
        
        # 创建副本文件夹名称(在原目录同级)
        copy_dir = source_path.parent / f"{source_path.name}_副本"
        
        # 创建副本文件夹
        copy_dir.mkdir(exist_ok=True)
        print(f"处理目录: {source_dir}")
        print(f"副本目录: {copy_dir}")
        
        # 遍历源目录中的所有文件
        file_count = 0
        for file_path in source_path.iterdir():
            if file_path.is_file():
                # 生成新文件名(原文件名 + .jpg)
                new_filename = file_path.name + ".jpg"
                new_file_path = copy_dir / new_filename
                
                # 复制文件到副本目录并重命名
                try:
                    shutil.copy2(file_path, new_file_path)
                    file_count += 1
                    print(f"  已处理: {file_path.name} -> {new_filename}")
                except Exception as e:
                    print(f"  错误: 无法处理文件 {file_path.name} - {e}")
        
        print(f"完成! 共处理 {file_count} 个文件\n")

def main():
    # 定义要处理的目录
    directories = [
        r"D:\本地素材\12-11-百度SOP测试\翻版",
        r"D:\本地素材\12-11-百度SOP测试\送板"
    ]
    
    print("=" * 60)
    print("批量添加.jpg后缀工具")
    print("=" * 60)
    print()
    
    add_jpg_suffix_and_copy(directories)
    
    print("=" * 60)
    print("所有操作完成!")
    print("=" * 60)

if __name__ == "__main__":
    main()