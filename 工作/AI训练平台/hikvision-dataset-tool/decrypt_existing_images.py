#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量解密已下载的加密图片

海康威视平台对图片使用 AES-ECB + Base64 加密。
此脚本从标注 JSON 中读取 file_id，通过 API 获取 key，然后解密图片。

用法：
    python decrypt_existing_images.py <数据集目录>

例如：
    python decrypt_existing_images.py ./output/dataset_100149930
"""

import base64
import json
import sys
from pathlib import Path


def decrypt_image(encrypted_b64: str, key: str) -> bytes:
    """解密海康威视加密图片（AES-ECB + Base64）"""
    try:
        from Crypto.Cipher import AES
    except ImportError:
        raise ImportError("缺少 pycryptodome，请运行: pip install pycryptodome")

    encrypted_data = base64.b64decode(encrypted_b64)
    cipher = AES.new(key.encode('utf-8'), AES.MODE_ECB)
    decrypted = cipher.decrypt(encrypted_data)

    pad_len = decrypted[-1]
    if 1 <= pad_len <= 16:
        decrypted = decrypted[:-pad_len]

    data_uri = decrypted.decode('utf-8')

    if 'base64,' in data_uri:
        img_b64 = data_uri.split('base64,')[1]
        return base64.b64decode(img_b64)

    raise ValueError("无效的 Data URI 格式")


def is_encrypted(file_path: Path) -> bool:
    """检查文件是否是加密的（非 JPEG/PNG 文件头）"""
    with open(file_path, 'rb') as f:
        header = f.read(4)
    # JPEG: FF D8 FF, PNG: 89 50 4E 47
    return not (header[:3] == b'\xff\xd8\xff' or header[:4] == b'\x89PNG')


def decrypt_with_key(image_path: Path, key: str) -> bool:
    """用给定 key 解密单张图片，覆盖原文件"""
    try:
        with open(image_path, 'r', encoding='utf-8') as f:
            encrypted_b64 = f.read().strip()
    except UnicodeDecodeError:
        # 可能已经是二进制 JPEG（Base64解码后有时是raw bytes）
        with open(image_path, 'rb') as f:
            raw = f.read()
        try:
            encrypted_b64 = raw.decode('utf-8').strip()
        except Exception:
            print(f"  无法读取文件内容: {image_path.name}")
            return False

    try:
        jpeg_data = decrypt_image(encrypted_b64, key)
        with open(image_path, 'wb') as f:
            f.write(jpeg_data)
        return True
    except Exception as e:
        print(f"  解密失败 {image_path.name}: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    dataset_dir = Path(sys.argv[1])
    images_dir = dataset_dir / "images"
    annotations_dir = dataset_dir / "annotations"

    if not images_dir.exists():
        print(f"错误: 找不到图片目录: {images_dir}")
        sys.exit(1)

    # 收集需要解密的图片
    image_files = list(images_dir.glob("*.jpg")) + list(images_dir.glob("*.jpeg"))
    encrypted_files = [f for f in image_files if is_encrypted(f)]

    if not encrypted_files:
        print("没有发现需要解密的图片（所有图片已是有效 JPEG）")
        return

    print(f"发现 {len(encrypted_files)}/{len(image_files)} 张加密图片")

    # 从标注 JSON 构建 filename -> key 映射
    # 注意：key 需要从 API 重新获取，因为标注 JSON 中可能没有存储 key
    # 如果你的标注 JSON 中有 key 字段，此处直接读取
    key_map = {}
    for anno_file in annotations_dir.glob("*.json"):
        try:
            with open(anno_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            key = data.get("key")
            file_name = data.get("file_name", "")
            if key and file_name:
                key_map[file_name] = key
        except Exception:
            pass

    if not key_map:
        print("\n标注 JSON 中没有 key 字段。")
        print("请先使用修改后的下载器重新下载图片（新版本会自动解密）。")
        print("\n或者，你可以手动指定 key（如果所有图片使用同一个 key）：")
        key = input("输入解密 key（直接回车跳过）: ").strip()
        if key:
            key_map = {f.name: key for f in encrypted_files}
        else:
            print("取消操作。")
            return

    # 解密
    success = 0
    failed = 0
    skipped = 0

    for img_path in encrypted_files:
        key = key_map.get(img_path.name)
        if not key:
            print(f"  跳过（无 key）: {img_path.name}")
            skipped += 1
            continue

        if decrypt_with_key(img_path, key):
            success += 1
            print(f"  ✓ {img_path.name}")
        else:
            failed += 1

    print(f"\n完成: 成功={success}, 失败={failed}, 跳过={skipped}")


if __name__ == "__main__":
    main()
