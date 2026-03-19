#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
海康威视AI开放平台数据集导出工具
主程序入口
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

# 添加项目目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.auth import AuthManager
from core.downloader import DatasetDownloader
from browser.bb_browser_bridge import BBBrowserBridge


def generate_output_dir(base_dir: Path, dataset_id: str) -> Path:
    """
    生成带时间戳的输出目录

    Args:
        base_dir: 基础目录
        dataset_id: 数据集ID

    Returns:
        带时间戳的唯一目录路径
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = base_dir / f"dataset_{dataset_id}_{timestamp}"

    # 避免覆盖：如果目录已存在，添加序号后缀
    counter = 1
    original_output_dir = output_dir
    while output_dir.exists():
        output_dir = base_dir / f"dataset_{dataset_id}_{timestamp}_{counter}"
        counter += 1

    return output_dir


def run_auto_mode(output_dir: Path = None):
    """
    自动模式：从当前浏览器页面自动提取信息并下载
    """
    print("=" * 60)
    print("海康威视AI平台数据集导出工具 - 自动模式")
    print("=" * 60)

    # 1. 从浏览器获取页面信息
    print("\n[步骤1] 连接bb-browser获取当前页面信息...")
    try:
        bridge = BBBrowserBridge()
        page_info = bridge.get_page_info()

        if not page_info:
            print("\n错误: 无法从浏览器获取页面信息")
            print("请确保:")
            print("1. bb-browser已启动 (运行: bb-browser)")
            print("2. 已在浏览器中打开海康AI平台的数据集页面")
            print("   URL格式: https://ai.hikvision.com/.../overall/{dataset_id}/{version_id}/gallery")
            return False

    except Exception as e:
        print(f"\n连接bb-browser失败: {e}")
        print("请确保bb-browser已启动")
        return False

    dataset_id = page_info["dataset_id"]
    version_id = page_info["version_id"]
    labeled_count = page_info["labeled_count"]

    print(f"\n✓ 找到数据集:")
    print(f"  - Dataset ID: {dataset_id}")
    print(f"  - Version ID: {version_id}")
    print(f"  - 已标注图片: {labeled_count}")

    # 2. 获取认证信息
    print("\n[步骤2] 获取认证信息...")
    auth = AuthManager()

    # 尝试从页面获取cookies
    cookies = page_info.get("cookies", {})
    token = cookies.get("token")

    if token:
        auth.authenticate_manual(
            token=token,
            account_name=cookies.get("accountName", ""),
            sub_account_name=cookies.get("subAccountName", ""),
            project_id=cookies.get("projectId", "")
        )
        print("✓ 已从浏览器获取认证信息")
    else:
        print("✗ 无法从浏览器获取token")
        return False

    # 3. 设置输出目录（使用时间戳子文件夹）
    if output_dir is None:
        base_dir = Path.home() / "Downloads"
        output_dir = generate_output_dir(base_dir, dataset_id)
    else:
        output_dir = generate_output_dir(Path(output_dir), dataset_id)

    print(f"\n[步骤3] 输出目录: {output_dir}")

    # 4. 开始下载
    print("\n[步骤4] 开始下载...")
    print("-" * 60)

    def progress_callback(current, total, filename):
        pct = (current / total) * 100 if total > 0 else 0
        bar_length = 30
        filled = int(bar_length * pct / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        print(f"\r[{bar}] {pct:.1f}% ({current}/{total}) {filename[:30]}...", end="", flush=True)

    try:
        downloader = DatasetDownloader(
            auth_manager=auth,
            dataset_id=dataset_id,
            version_id=version_id,
            output_dir=output_dir,
            max_concurrent=5,
            progress_callback=progress_callback
        )

        result = downloader.run(labeled_only=True)

        print("\n" + "-" * 60)
        print(f"\n下载完成!")
        print(f"成功: {result.success}/{result.total}")
        if result.failed > 0:
            print(f"失败: {result.failed}")
            print(f"失败文件:")
            for f in result.failed_files[:5]:
                print(f"  - {f}")

        print(f"\n文件保存在: {output_dir}")
        print(f"  - 图片: {output_dir / 'images'}")
        print(f"  - 标注: {output_dir / 'annotations'}")

        return True

    except Exception as e:
        print(f"\n下载失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_manual_mode(dataset_id: str, version_id: str, token: str, output_dir: Path):
    """
    手动模式：指定参数下载
    """
    print("=" * 60)
    print("海康威视AI平台数据集导出工具 - 手动模式")
    print("=" * 60)

    # 认证
    auth = AuthManager()
    if not auth.authenticate_manual(token=token):
        print("认证失败")
        return False

    # 下载
    downloader = DatasetDownloader(
        auth_manager=auth,
        dataset_id=dataset_id,
        version_id=version_id,
        output_dir=output_dir,
        max_concurrent=5
    )

    result = downloader.run(labeled_only=True)

    print(f"\n完成: {result.success}/{result.total} 成功")
    return result.failed == 0


def run_gui_mode():
    """
    GUI模式：启动图形界面
    """
    from gui import run_gui
    run_gui()
    return True


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="海康威视AI开放平台数据集导出工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # GUI模式（推荐）
  python main.py --gui

  # 自动模式（命令行，从当前浏览器页面提取信息）
  python main.py --auto

  # 指定输出目录
  python main.py --auto --output ./my_dataset

  # 手动模式（指定数据集ID和token）
  python main.py --dataset 100149930 --version 100240402 --token "your_token_here"
        """
    )

    parser.add_argument(
        "--gui", "-g",
        action="store_true",
        help="GUI模式：启动图形界面（推荐）"
    )

    parser.add_argument(
        "--auto", "-a",
        action="store_true",
        help="自动模式：从当前浏览器页面自动提取dataset_id和version_id"
    )

    parser.add_argument(
        "--dataset", "-d",
        type=str,
        help="数据集ID（手动模式）"
    )

    parser.add_argument(
        "--version", "-v",
        type=str,
        help="版本ID（手动模式）"
    )

    parser.add_argument(
        "--token", "-t",
        type=str,
        help="认证token（手动模式）"
    )

    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="输出目录（默认: ~/Downloads/hikvision_dataset_{id}）"
    )

    args = parser.parse_args()

    # 根据参数选择模式
    if args.gui:
        # GUI模式
        success = run_gui_mode()
    elif args.auto or (not args.dataset and not args.version):
        # 自动模式
        output_dir = Path(args.output) if args.output else None
        success = run_auto_mode(output_dir)
    elif args.dataset and args.version and args.token:
        # 手动模式
        base_dir = Path(args.output) if args.output else Path.home() / "Downloads"
        output_dir = generate_output_dir(base_dir, args.dataset)
        success = run_manual_mode(
            dataset_id=args.dataset,
            version_id=args.version,
            token=args.token,
            output_dir=output_dir
        )
    else:
        parser.print_help()
        print("\n错误: 手动模式需要同时指定 --dataset, --version 和 --token")
        return 1

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
