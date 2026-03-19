#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取海康威视AI开放平台的标注数据
"""

import requests
import json
import urllib.parse

# 基础配置
BASE_URL = "https://ai.hikvision.com/api/saas/ai-training/algorithms"
DATASET_ID = "100149930"
VERSION_ID = "100240402"

COOKIES = {
    "subLoginList": '[{"accountName":"ntscc2021","subAccountName":"ZXY6699"}]',
    "accountName": "ntscc2021",
    "subAccountName": "ZXY6699",
    "visitor": "false",
    "token": "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJBdXRoIiwicGF5bG9hZCI6IntcImFjY291bnRUeXBlXCI6MSxcImF1dGhvcml6ZUFjY291bnRJZFwiOlwiNjcxNzJjODE0MTZhNGZlN2IzZmRiMDI2NTRlMmQ3NWNcIixcImF1dGhvcml6ZUFjY291bnROYW1lXCI6XCJudHNjYzIwMjFcIixcImNsaWVudFR5cGVcIjowLFwiZGVwYXJ0bWVudElkXCI6XCIxXCIsXCJleHBpcmVkXCI6MTgwMCxcInN0YXJ0VGltZVwiOjE3NzM4ODc5NTA0MjUsXCJ0ZW5hbnRJZFwiOlwiaGlreXVuZm9yYWlvcGVucGxhdGZvcm1wcm9kXCIsXCJ1c2VySWRcIjpcIjIxODM2MDQ5MjM3MTI3NDRcIixcInVzZXJOYW1lXCI6XCJaWFk2Njk5XCJ9In0.toni1TXwLwzCq0rs10wM5QmlsBFhH9iPMmeGnJ-P5Ci8zwLtVfNuqLwQ1k4EFzUKcT0_VJoxbL47fRIx87lGtg",
    "projectId": "9a323db2bce24cd69ce018e41eff6e68"
}

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "content-type": "application/x-www-form-urlencoded",
    "origin": "https://ai.hikvision.com",
    "referer": "https://ai.hikvision.com/intellisense/ai-training/console/data/",
    "token": COOKIES.get("token", ""),
    "projectid": "9a323db2bce24cd69ce018e41eff6e68",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def get_file_list():
    url = f"{BASE_URL}/datasets/file/offset-list/query"
    data = {
        "dataSetId": DATASET_ID,
        "dataSetVersionId": VERSION_ID,
        "offset": 0,
        "pageSize": 24,
        "isTag": 1,
        "labelIds": "[]",
        "sortType": 1,
        "fileName": "",
        "tagUserInfos": "[{}]",
        "labelProperty": ""
    }
    response = requests.post(url, headers=HEADERS, data=urllib.parse.urlencode(data), cookies=COOKIES)
    return response.json()

def get_targets(file_ids):
    url = f"{BASE_URL}/datasets/files/targets/query"
    data = {"dataSetVersionId": VERSION_ID}
    for i, fid in enumerate(file_ids):
        data[f"fileIds[{i}]"] = fid
    response = requests.post(url, headers=HEADERS, data=urllib.parse.urlencode(data), cookies=COOKIES)
    return response.json()

def get_labels():
    url = f"{BASE_URL}/datasets/label/list"
    data = {"dataSetVersionId": VERSION_ID}
    response = requests.post(url, headers=HEADERS, data=urllib.parse.urlencode(data), cookies=COOKIES)
    return response.json()

def safe_get(data, *keys, default=None):
    """安全获取嵌套字典值"""
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key, default)
        else:
            return default
    return data

def main():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    print("="*60)
    print("海康威视AI开放平台 - 标注数据抓取")
    print("="*60)

    # 1. 获取标签列表
    print("\n[1/3] 获取标签列表...")
    labels = []
    try:
        labels_data = get_labels()
        print(f"  API响应: {labels_data.get('msg', 'Unknown')}")
        if labels_data.get("code") == "200":
            data = labels_data.get("data", {})
            if isinstance(data, dict):
                labels = data.get("labelList", [])
            elif isinstance(data, list):
                labels = data
            print(f"  找到 {len(labels)} 个标签")
            for label in labels[:5]:
                print(f"    - {label.get('name')} (ID: {label.get('id')})")
    except Exception as e:
        print(f"  错误: {e}")

    # 2. 获取图片列表
    print("\n[2/3] 获取图片列表...")
    files = []
    try:
        files_data = get_file_list()
        print(f"  API响应: {files_data.get('msg', 'Unknown')}")
        if files_data.get("code") == "200":
            data = files_data.get("data", [])
            if isinstance(data, list):
                files = data
            elif isinstance(data, dict):
                files = data.get("dataList", [])
            print(f"  找到 {len(files)} 张图片")

            for f in files[:3]:
                print(f"\n  图片: {f.get('fileName', 'Unknown')}")
                print(f"    - ID: {f.get('id')}")
                print(f"    - 尺寸: {f.get('frameWidth')}x{f.get('frameHeight')}")
                print(f"    - 标注人: {f.get('tagUserName', 'N/A')}")
    except Exception as e:
        print(f"  错误: {e}")

    # 3. 获取标注目标数据
    file_ids = [f.get("id") for f in files if f.get("id")]
    if file_ids:
        print("\n[3/3] 获取标注目标数据...")
        try:
            targets_data = get_targets(file_ids)
            print(f"  API响应: {targets_data.get('msg', 'Unknown')}")

            if targets_data.get("code") == "200":
                # 保存完整数据
                output_file = "C:\\Users\\Lane\\annotation_data.json"
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(targets_data, f, ensure_ascii=False, indent=2)
                print(f"  数据已保存到: {output_file}")

                # 解析标注数据
                data = targets_data.get("data", {})
                if isinstance(data, dict):
                    for file_id, annotations in data.items():
                        print(f"\n  文件 {file_id[:8]}...:")
                        if isinstance(annotations, list):
                            print(f"    共 {len(annotations)} 个标注目标")
                            for ann in annotations[:3]:
                                print(f"    - 标签: {ann.get('labelName')}")
                                print(f"      边界框: {ann.get('bndBox')}")
                                if ann.get('property'):
                                    print(f"      属性: {ann.get('property')}")
            else:
                print(f"  错误: {targets_data}")
        except Exception as e:
            print(f"  错误: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*60)
    print("完成！")
    print("="*60)

if __name__ == "__main__":
    main()
