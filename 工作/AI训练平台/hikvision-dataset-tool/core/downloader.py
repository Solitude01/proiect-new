#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
下载模块 - 异步下载图片和标注数据
"""

import base64
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Callable, Tuple
from dataclasses import dataclass
from .auth import AuthManager
from .api_client import ImageFile, Annotation, HikvisionAPIClient


def decrypt_image(encrypted_b64: str, key: str) -> bytes:
    """解密海康威视加密图片（AES-ECB + Base64）"""
    try:
        from Crypto.Cipher import AES
    except ImportError:
        raise ImportError("缺少 pycryptodome，请运行: pip install pycryptodome")

    # 1. Base64 解码
    encrypted_data = base64.b64decode(encrypted_b64)

    # 2. AES-ECB 解密
    cipher = AES.new(key.encode('utf-8'), AES.MODE_ECB)
    decrypted = cipher.decrypt(encrypted_data)

    # 3. 去除 PKCS7 填充
    pad_len = decrypted[-1]
    if 1 <= pad_len <= 16:
        decrypted = decrypted[:-pad_len]

    # 4. 解码为 Data URI 字符串
    data_uri = decrypted.decode('utf-8')

    # 5. 提取 Base64 部分
    if 'base64,' in data_uri:
        img_b64 = data_uri.split('base64,')[1]
        return base64.b64decode(img_b64)

    raise ValueError("无效的 Data URI 格式")


@dataclass
class DownloadResult:
    """下载结果"""
    success: int
    failed: int
    total: int
    failed_files: List[str]


class DatasetDownloader:
    """数据集下载器"""

    def __init__(
        self,
        auth_manager: AuthManager,
        dataset_id: str,
        version_id: str,
        output_dir: Path,
        max_concurrent: int = 5,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ):
        """
        初始化下载器

        Args:
            auth_manager: 认证管理器
            dataset_id: 数据集ID
            version_id: 版本ID
            output_dir: 输出目录
            max_concurrent: 最大并发数
            progress_callback: 进度回调(current, total, filename)
        """
        self.auth = auth_manager
        self.dataset_id = dataset_id
        self.version_id = version_id
        self.output_dir = Path(output_dir)
        self.max_concurrent = max_concurrent
        self.progress_callback = progress_callback

        # API客户端
        self.api = HikvisionAPIClient(auth_manager, dataset_id, version_id)

        # 创建目录结构
        self.images_dir = self.output_dir / "images"
        self.annotations_dir = self.output_dir / "annotations"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.annotations_dir.mkdir(parents=True, exist_ok=True)

        # 统计
        self.downloaded = 0
        self.failed = []

    def download_image_sync(
        self,
        image: ImageFile,
        annotations: List[Annotation]
    ) -> bool:
        """
        同步下载单张图片和对应标注（使用requests，更好地处理OSS）

        Args:
            image: 图片信息
            annotations: 标注列表

        Returns:
            是否成功
        """
        import requests

        file_id = image.id
        file_name = image.file_name or f"{file_id}.jpg"

        # 确保文件名有效（移除非法字符）
        safe_name = self._sanitize_filename(file_name)
        name_without_ext = Path(safe_name).stem

        image_path = self.images_dir / safe_name
        anno_path = self.annotations_dir / f"{name_without_ext}.json"

        # 检查是否已存在（避免重复下载）
        if image_path.exists() and anno_path.exists():
            print(f"  跳过已存在: {safe_name}")
            return True

        # 下载图片
        if image.file_url:
            try:
                # 确保URL有https://前缀
                url = image.file_url
                if not url.startswith('http'):
                    url = 'https://' + url

                headers = {
                    "Referer": "https://ai.hikvision.com/",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "image/*,image/jpeg,image/png,image/jpg,application/octet-stream,*/*"
                }

                response = requests.get(
                    url,
                    headers=headers,
                    timeout=60,
                    stream=True
                )

                if response.status_code == 200:
                    raw_data = response.content

                    # 如果有解密密钥，解密数据
                    if image.key:
                        try:
                            raw_data = decrypt_image(raw_data.decode('utf-8'), image.key)
                        except Exception as e:
                            print(f"  解密失败 {safe_name}: {e}")
                            return False

                    with open(image_path, 'wb') as f:
                        f.write(raw_data)

                    # 验证文件大小
                    if image_path.stat().st_size < 100:
                        print(f"  文件过小，可能损坏: {safe_name}")
                        image_path.unlink()  # 删除损坏文件
                        return False
                else:
                    print(f"  下载失败 {safe_name}: HTTP {response.status_code}")
                    return False

            except Exception as e:
                print(f"  下载错误 {safe_name}: {e}")
                return False
        else:
            print(f"  无下载URL: {safe_name}")
            return False

        # 保存标注
        try:
            anno_data = {
                "file_id": file_id,
                "file_name": file_name,
                "width": image.width,
                "height": image.height,
                "tag_user": image.tag_user_name,
                "create_time": image.create_time,
                "annotations": [
                    {
                        "id": ann.id,
                        "label_id": ann.label_id,
                        "label_name": ann.label_name,
                        "label_item_name": ann.label_item_name,
                        "label_set_name": ann.label_set_name,
                        "bbox": ann.bbox,
                        "property": ann.property,
                        "order_num": ann.order_num
                    }
                    for ann in annotations
                ]
            }

            with open(anno_path, 'w', encoding='utf-8') as f:
                json.dump(anno_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"  保存标注失败 {safe_name}: {e}")
            return False

        return True

    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名中的非法字符"""
        # Windows非法字符: < > : " / \ | ? *
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename.strip()

    def download_all(
        self,
        labeled_only: bool = True
    ) -> DownloadResult:
        """
        下载所有图片和标注（同步版本，使用线程池）

        Args:
            labeled_only: 只下载已标注图片

        Returns:
            下载结果统计
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        print("=" * 60)
        print("开始批量下载")
        print("=" * 60)

        # 1. 获取所有图片
        print("\n[1/3] 获取图片列表...")
        is_tagged = 1 if labeled_only else -1
        images = list(self.api.get_all_images(is_tagged=is_tagged))
        print(f"找到 {len(images)} 张图片")

        if not images:
            return DownloadResult(0, 0, 0, [])

        # 2. 获取所有标注
        print("\n[2/3] 获取标注数据...")
        file_ids = [img.id for img in images]
        annotations_map = {}

        batch_size = 50
        for i in range(0, len(file_ids), batch_size):
            batch_ids = file_ids[i:i + batch_size]
            batch_annotations = self.api.get_annotations(batch_ids)
            annotations_map.update(batch_annotations)
            print(f"  获取标注 {i+1}-{min(i+batch_size, len(file_ids))}/{len(file_ids)}")

        # 3. 并发下载
        print(f"\n[3/3] 下载图片和标注 (并发数: {self.max_concurrent})...")

        completed = 0
        total = len(images)
        success_count = 0
        failed_files = []

        with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
            # 提交所有任务
            future_to_image = {
                executor.submit(
                    self.download_image_sync,
                    img,
                    annotations_map.get(img.id, [])
                ): img
                for img in images
            }

            # 处理完成的任务
            for future in as_completed(future_to_image):
                image = future_to_image[future]
                completed += 1

                try:
                    success = future.result()
                    if success:
                        success_count += 1
                    else:
                        failed_files.append(image.file_name)
                except Exception as e:
                    print(f"  错误 {image.file_name}: {e}")
                    failed_files.append(image.file_name)

                # 进度回调
                if self.progress_callback:
                    self.progress_callback(completed, total, image.file_name)

                # 显示进度
                pct = (completed / total) * 100 if total > 0 else 0
                bar_length = 30
                filled = int(bar_length * pct / 100)
                bar = "█" * filled + "░" * (bar_length - filled)
                print(f"\r[{bar}] {pct:.1f}% ({completed}/{total})", end="", flush=True)

        print()  # 换行

        # 输出统计
        print("\n" + "=" * 60)
        print("下载完成")
        print(f"成功: {success_count}/{total}")
        print(f"失败: {len(failed_files)}")
        print(f"保存位置: {self.output_dir}")
        print("=" * 60)

        return DownloadResult(
            success=success_count,
            failed=len(failed_files),
            total=total,
            failed_files=failed_files
        )

    def run(self, labeled_only: bool = True) -> DownloadResult:
        """
        运行下载

        Args:
            labeled_only: 只下载已标注图片

        Returns:
            下载结果
        """
        return self.download_all(labeled_only)


def test_downloader():
    """测试下载器"""
    from .auth import AuthManager

    auth = AuthManager()
    if not auth.authenticate_from_browser():
        print("认证失败")
        return

    output_dir = Path.home() / "Downloads" / "hikvision_test"

    downloader = DatasetDownloader(
        auth_manager=auth,
        dataset_id="100149930",
        version_id="100240402",
        output_dir=output_dir,
        max_concurrent=3
    )

    result = downloader.run(labeled_only=True)
    print(f"\n结果: {result}")


if __name__ == "__main__":
    test_downloader()
