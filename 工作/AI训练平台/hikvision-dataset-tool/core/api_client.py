#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API客户端 - 封装海康威视AI开放平台的所有API调用
"""

import requests
import urllib.parse
from typing import Dict, List, Optional, Generator, Any
from dataclasses import dataclass
from .auth import AuthManager


BASE_URL = "https://ai.hikvision.com/api/saas/ai-training/algorithms"


@dataclass
class ImageFile:
    """图片文件数据类"""
    id: str
    file_name: str
    file_url: str
    thumb_url: str
    width: int
    height: int
    label_status: int  # 0=未标注, 1=已标注
    tag_user_name: Optional[str]
    tag_user_id: Optional[str]
    create_time: Optional[str]
    key: Optional[str] = None  # AES-ECB解密密钥


@dataclass
class Annotation:
    """标注数据类"""
    id: str
    file_id: str
    label_id: str
    label_name: str
    label_item_name: Optional[str]
    label_set_name: Optional[str]
    bbox: Dict[str, Any]  # {xmin, ymin, xmax, ymax} 或 {x, y, w, h}
    property: Optional[Dict]
    order_num: Optional[str]


class APIError(Exception):
    """API错误"""
    pass


class HikvisionAPIClient:
    """海康威视API客户端"""

    def __init__(self, auth_manager: AuthManager, dataset_id: str, version_id: str):
        """
        初始化API客户端

        Args:
            auth_manager: 认证管理器
            dataset_id: 数据集ID
            version_id: 版本ID
        """
        self.auth = auth_manager
        self.dataset_id = dataset_id
        self.version_id = version_id
        self.session = requests.Session()

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        timeout: int = 30
    ) -> Dict:
        """
        发送HTTP请求

        Args:
            method: HTTP方法 (GET/POST)
            endpoint: API端点路径
            data: 请求数据
            timeout: 超时时间

        Returns:
            API响应JSON
        """
        url = f"{BASE_URL}{endpoint}"
        headers = self.auth.get_headers()
        cookies = self.auth.get_cookies()

        try:
            if method.upper() == "GET":
                response = self.session.get(
                    url,
                    headers=headers,
                    cookies=cookies,
                    timeout=timeout
                )
            else:
                encoded_data = urllib.parse.urlencode(data) if data else None
                response = self.session.post(
                    url,
                    headers=headers,
                    data=encoded_data,
                    cookies=cookies,
                    timeout=timeout
                )

            response.raise_for_status()
            result = response.json()

            # 检查API返回码
            if result.get("code") != "200":
                raise APIError(f"API错误: {result.get('msg', 'Unknown error')} (code: {result.get('code')})")

            return result

        except requests.exceptions.RequestException as e:
            raise APIError(f"请求失败: {e}")

    def get_labels(self) -> List[Dict]:
        """
        获取数据集的标签列表

        Returns:
            标签列表
        """
        result = self._make_request(
            "POST",
            "/datasets/label/list",
            {"dataSetVersionId": self.version_id}
        )

        data = result.get("data", {})
        if isinstance(data, dict):
            return data.get("labelList", [])
        return data if isinstance(data, list) else []

    def get_image_list(
        self,
        offset: int = 0,
        page_size: int = 100,
        is_tagged: int = 1,
        file_name: str = ""
    ) -> Dict:
        """
        获取图片列表（分页）

        Args:
            offset: 偏移量
            page_size: 每页数量
            is_tagged: 1=只获取已标注, 0=未标注, -1=全部
            file_name: 文件名搜索关键词

        Returns:
            API原始响应
        """
        data = {
            "dataSetId": self.dataset_id,
            "dataSetVersionId": self.version_id,
            "offset": offset,
            "pageSize": page_size,
            "isTag": is_tagged,
            "labelIds": "[]",
            "sortType": 1,  # 上传时间降序
            "fileName": file_name,
            "tagUserInfos": "[{}]",
            "labelProperty": ""
        }

        return self._make_request("POST", "/datasets/file/offset-list/query", data)

    def get_all_images(
        self,
        is_tagged: int = 1,
        progress_callback: Optional[callable] = None
    ) -> Generator[ImageFile, None, None]:
        """
        获取所有图片（生成器，自动处理分页）

        Args:
            is_tagged: 1=只获取已标注
            progress_callback: 进度回调函数(current, total)

        Yields:
            ImageFile对象
        """
        offset = 0
        page_size = 100
        total = None
        current = 0

        while True:
            result = self.get_image_list(offset, page_size, is_tagged)

            # 解析数据
            data = result.get("data", [])
            if isinstance(data, dict):
                items = data.get("dataList", [])
                if total is None:
                    page_info = data.get("page", {})
                    total = page_info.get("total", 0)
            else:
                items = data

            if not items:
                break

            for item in items:
                yield ImageFile(
                    id=str(item.get("id", "")),
                    file_name=item.get("fileName", ""),
                    file_url=item.get("cloudUrl", ""),
                    thumb_url=item.get("thumbnailCloudUrl", ""),
                    width=item.get("frameWidth", 0),
                    height=item.get("frameHeight", 0),
                    label_status=item.get("labelStatus", 0),
                    tag_user_name=item.get("tagUserName"),
                    tag_user_id=item.get("tagUserId"),
                    create_time=item.get("createTime"),
                    key=item.get("key")
                )
                current += 1

                if progress_callback and total:
                    progress_callback(current, total)

            # 检查是否还有更多数据
            if len(items) < page_size:
                break

            offset += page_size

    def get_annotations(self, file_ids: List[str]) -> Dict[str, List[Annotation]]:
        """
        批量获取标注数据

        Args:
            file_ids: 文件ID列表

        Returns:
            {file_id: [Annotation, ...]}
        """
        if not file_ids:
            return {}

        data = {"dataSetVersionId": self.version_id}
        for i, fid in enumerate(file_ids):
            data[f"fileIds[{i}]"] = fid

        result = self._make_request("POST", "/datasets/files/targets/query", data)

        annotations_map = {}
        response_data = result.get("data", {})

        # 处理数组格式: [{"fileId": "...", "formData": [...]}, ...]
        if isinstance(response_data, list):
            for item in response_data:
                file_id = item.get("fileId")
                anns = item.get("formData", [])
                annotations_map[file_id] = []

                for ann in anns:
                    # 解析边界框
                    bbox = ann.get("bndBox", {})
                    if not bbox:
                        # 尝试从tagCoord解析（格式: "x1 y1 x2 y2"）
                        tag_coord = ann.get("tagCoord", "")
                        if tag_coord:
                            coords = tag_coord.split()
                            if len(coords) == 4:
                                bbox = {
                                    "xmin": float(coords[0]),
                                    "ymin": float(coords[1]),
                                    "xmax": float(coords[2]),
                                    "ymax": float(coords[3])
                                }

                    annotations_map[file_id].append(Annotation(
                        id=str(ann.get("id", "")),
                        file_id=file_id,
                        label_id=str(ann.get("labelId", "")),
                        label_name=ann.get("labelName", ""),
                        label_item_name=ann.get("labelItemName"),
                        label_set_name=ann.get("labelSetName"),
                        bbox=bbox,
                        property=ann.get("property"),
                        order_num=ann.get("orderNum")
                    ))

        # 也处理字典格式（以防万一）
        elif isinstance(response_data, dict):
            for file_id, anns in response_data.items():
                annotations_map[file_id] = []

                if not isinstance(anns, list):
                    continue

                for ann in anns:
                    bbox = ann.get("bndBox", {})
                    if not bbox:
                        tag_coord = ann.get("tagCoord", "")
                        if tag_coord:
                            coords = tag_coord.split()
                            if len(coords) == 4:
                                bbox = {
                                    "xmin": float(coords[0]),
                                    "ymin": float(coords[1]),
                                    "xmax": float(coords[2]),
                                    "ymax": float(coords[3])
                                }

                    annotations_map[file_id].append(Annotation(
                        id=str(ann.get("id", "")),
                        file_id=file_id,
                        label_id=str(ann.get("labelId", "")),
                        label_name=ann.get("labelName", ""),
                        label_item_name=ann.get("labelItemName"),
                        label_set_name=ann.get("labelSetName"),
                        bbox=bbox,
                        property=ann.get("property"),
                        order_num=ann.get("orderNum")
                    ))

        return annotations_map

    def get_all_annotations(
        self,
        file_ids: List[str],
        batch_size: int = 50,
        progress_callback: Optional[callable] = None
    ) -> Generator[Tuple[str, List[Annotation]], None, None]:
        """
        分批获取所有标注

        Args:
            file_ids: 所有文件ID
            batch_size: 每批数量
            progress_callback: 进度回调

        Yields:
            (file_id, annotations_list) 元组
        """
        total_batches = (len(file_ids) + batch_size - 1) // batch_size

        for i in range(0, len(file_ids), batch_size):
            batch = file_ids[i:i + batch_size]
            batch_annotations = self.get_annotations(batch)

            for file_id, anns in batch_annotations.items():
                yield file_id, anns

            if progress_callback:
                progress_callback(min(i + batch_size, len(file_ids)), len(file_ids))


def test_api_client():
    """测试API客户端"""
    from .auth import AuthManager

    auth = AuthManager()
    if not auth.authenticate_from_browser():
        print("认证失败")
        return

    # 需要替换为实际的ID
    dataset_id = "100149930"
    version_id = "100240402"

    client = HikvisionAPIClient(auth, dataset_id, version_id)

    print("获取标签列表...")
    labels = client.get_labels()
    print(f"找到 {len(labels)} 个标签")
    for label in labels[:5]:
        print(f"  - {label.get('name')} ({label.get('num', 0)}张)")

    print("\n获取图片列表...")
    images = list(client.get_all_images(is_tagged=1))
    print(f"找到 {len(images)} 张已标注图片")

    if images:
        print("\n获取标注数据...")
        file_ids = [img.id for img in images[:5]]
        annotations = client.get_annotations(file_ids)
        for fid, anns in annotations.items():
            print(f"  {fid}: {len(anns)} 个标注")


if __name__ == "__main__":
    test_api_client()
