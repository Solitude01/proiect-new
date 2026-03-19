#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bb-browser CDP桥接模块
通过Chrome DevTools Protocol与bb-browser通信，获取当前页面信息
"""

import requests
import json
import re
import os
from typing import Dict, List, Optional, Tuple
from pathlib import Path


class BBBrowserBridge:
    """bb-browser CDP桥接器"""

    DEFAULT_CDP_PORT = 9222

    def __init__(self, cdp_port: Optional[int] = None):
        """
        初始化桥接器

        Args:
            cdp_port: CDP端口，None则自动发现（发现失败不报错，仍可使用browser_cookie3）
        """
        try:
            self.cdp_port = cdp_port or self._discover_cdp_port()
        except ConnectionError:
            self.cdp_port = self.DEFAULT_CDP_PORT
        self.base_url = f"http://localhost:{self.cdp_port}"

    def _discover_cdp_port(self) -> int:
        """自动发现bb-browser的CDP端口"""
        # 尝试从bb-browser配置文件中读取
        config_paths = [
            Path.home() / ".bb-browser" / "browser" / "cdp-port",
            Path.home() / ".config" / "bb-browser" / "cdp-port",
        ]

        for path in config_paths:
            if path.exists():
                try:
                    port = int(path.read_text().strip())
                    # 验证端口是否可用
                    if self._test_port(port):
                        return port
                except (ValueError, IOError):
                    pass

        # 默认端口
        if self._test_port(self.DEFAULT_CDP_PORT):
            return self.DEFAULT_CDP_PORT

        raise ConnectionError(
            f"无法发现bb-browser CDP端口。请确保bb-browser已启动。"
        )

    def _test_port(self, port: int) -> bool:
        """测试CDP端口是否可用"""
        try:
            response = requests.get(
                f"http://localhost:{port}/json/version",
                timeout=2
            )
            return response.status_code == 200
        except requests.exceptions.ConnectionError:
            return False

    def get_pages(self) -> List[Dict]:
        """获取所有页面列表"""
        try:
            response = requests.get(
                f"{self.base_url}/json/list",
                timeout=5
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"获取页面列表失败: {e}")
            return []

    def find_hikvision_page(self) -> Optional[Dict]:
        """
        查找海康AI平台的数据集页面

        Returns:
            页面信息字典，包含 id, url, title, webSocketDebuggerUrl 等
        """
        pages = self.get_pages()

        for page in pages:
            url = page.get("url", "")
            # 匹配海康AI平台的数据集页面
            # URL格式: .../overall/{dataset_id}/{version_id}/gallery
            if (
                "ai.hikvision.com" in url
                and "/overall/" in url
                and ("/gallery" in url or "/calibrate/" in url)
            ):
                return page

        return None

    def extract_ids_from_url(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        从URL提取dataset_id和version_id

        Args:
            url: 页面URL

        Returns:
            (dataset_id, version_id) 元组
        """
        # 匹配 /overall/{dataset_id}/{version_id}/ 模式
        pattern = r"/overall/(\d+)/(\d+)/"
        match = re.search(pattern, url)

        if match:
            return match.group(1), match.group(2)

        # 备选：匹配 /calibrate/online/{dataset_id}/{version_id} 模式
        pattern2 = r"/calibrate/online/(\d+)/(\d+)"
        match2 = re.search(pattern2, url)

        if match2:
            return match2.group(1), match2.group(2)

        return None, None

    def get_cookies_from_browser_cookie3(self) -> Dict[str, str]:
        """
        使用browser_cookie3从本地浏览器cookie数据库读取cookies

        Returns:
            cookie字典 {name: value}
        """
        try:
            import browser_cookie3

            # 从Chrome获取指定域名的cookies
            cj = browser_cookie3.chrome(domain_name="ai.hikvision.com")
            cookies = {cookie.name: cookie.value for cookie in cj}

            if cookies:
                print(f"  通过browser_cookie3获取到 {len(cookies)} 个cookies")

            return cookies

        except ImportError:
            print("  提示: 可安装 browser-cookie3 作为备选方案")
            print("  pip install browser-cookie3")
            return {}

        except Exception as e:
            print(f"  browser_cookie3获取失败: {e}")
            return {}

    def get_cookies(self, page_id: Optional[str] = None) -> Dict[str, str]:
        """
        获取指定页面的cookies

        优先使用browser_cookie3（不依赖WebSocket），失败时尝试WebSocket CDP

        Args:
            page_id: 页面ID，None则自动查找海康页面

        Returns:
            cookie字典 {name: value}
        """
        # 方法1：browser_cookie3（推荐，不需要WebSocket，兼容普通Chrome）
        cookies = self.get_cookies_from_browser_cookie3()
        if cookies and cookies.get("token"):
            print("  使用browser_cookie3获取cookies成功")
            return cookies

        # 方法2：WebSocket CDP（备选，需要--remote-allow-origins或bb-browser）
        print("  browser_cookie3未获取到token，尝试WebSocket CDP...")
        ws_url = self._get_ws_url(page_id)
        if ws_url:
            try:
                ws_cookies = self._get_cookies_from_websocket(ws_url)
                if ws_cookies:
                    return ws_cookies
            except Exception as e:
                print(f"  WebSocket获取cookies失败: {e}")

        # 返回browser_cookie3的结果（即使没有token）
        return cookies

    def _get_ws_url(self, page_id: Optional[str] = None) -> Optional[str]:
        """获取指定页面或海康页面的WebSocket调试URL"""
        pages = self.get_pages()

        if page_id:
            for page in pages:
                if page.get("id") == page_id:
                    return page.get("webSocketDebuggerUrl")
            return None

        # 查找海康页面
        for page in pages:
            url = page.get("url", "")
            if (
                "ai.hikvision.com" in url
                and "/overall/" in url
                and ("/gallery" in url or "/calibrate/" in url)
            ):
                return page.get("webSocketDebuggerUrl")

        return None

    def _get_cookies_from_websocket(self, ws_url: str) -> Dict[str, str]:
        """通过WebSocket CDP获取cookies"""
        import websocket

        ws = websocket.create_connection(ws_url, timeout=10)
        try:
            ws.send(json.dumps({"id": 1, "method": "Network.enable"}))
            ws.recv()

            ws.send(json.dumps({
                "id": 2,
                "method": "Network.getCookies",
                "params": {"urls": ["https://ai.hikvision.com"]}
            }))
            response = json.loads(ws.recv())

            cookies = {}
            for cookie in response.get("result", {}).get("cookies", []):
                cookies[cookie["name"]] = cookie["value"]

            if cookies:
                print(f"  WebSocket CDP获取到 {len(cookies)} 个cookies")
            return cookies
        finally:
            ws.close()

    def execute_js(self, expression: str, page_id: Optional[str] = None) -> any:
        """
        在指定页面执行JavaScript

        Args:
            expression: JavaScript表达式
            page_id: 页面ID，None则自动查找海康页面

        Returns:
            JavaScript执行结果
        """
        if page_id is None:
            page = self.find_hikvision_page()
            if not page:
                raise ValueError("未找到海康AI平台页面")
            page_id = page.get("id")

        pages = self.get_pages()
        ws_url = None

        for page in pages:
            if page.get("id") == page_id:
                ws_url = page.get("webSocketDebuggerUrl")
                break

        if not ws_url:
            raise ValueError(f"未找到页面 {page_id} 的WebSocket地址")

        try:
            import websocket

            ws = websocket.create_connection(ws_url, timeout=10)

            try:
                # 启用Runtime domain
                ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
                ws.recv()

                # 执行JavaScript
                ws.send(json.dumps({
                    "id": 2,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": expression,
                        "returnByValue": True,
                        "awaitPromise": True
                    }
                }))
                response = json.loads(ws.recv())

                result = response.get("result", {}).get("result", {})

                # 根据类型返回值
                result_type = result.get("type")
                if result_type == "number":
                    return result.get("value")
                elif result_type == "string":
                    return result.get("value")
                elif result_type == "boolean":
                    return result.get("value")
                elif result_type == "undefined":
                    return None
                elif result_type == "object":
                    value = result.get("value")
                    if value is None:
                        return None
                    try:
                        return json.loads(value) if isinstance(value, str) else value
                    except json.JSONDecodeError:
                        return value
                else:
                    return result.get("value")

            finally:
                ws.close()

        except ImportError:
            print("警告: websocket-client未安装")
            return None

    def get_labeled_count(self, page_id: Optional[str] = None) -> int:
        """
        从页面获取"已标注 (X)"的数量

        Args:
            page_id: 页面ID

        Returns:
            已标注图片数量
        """
        js_code = """
        (function() {
            // 尝试多种选择器找到已标注数量
            const selectors = [
                '.el-tabs__item.is-active',
                '[role="tab"].is-active',
                '.tab-item.active',
                '.el-tab-pane',
                '.dataset-statistics .labeled-count',
                '.gallery-header .count',
                '.stat-item'
            ];

            for (let selector of selectors) {
                const elements = document.querySelectorAll(selector);
                for (let el of elements) {
                    if (el && el.textContent) {
                        const match = el.textContent.match(/已标注[\\s\\(]*([\\d,]+)[\\)\\s]*$/);
                        if (match) {
                            return parseInt(match[1].replace(/,/g, ''));
                        }
                    }
                }
            }

            // 兜底：遍历所有元素
            const allElements = document.querySelectorAll('*');
            for (let el of allElements) {
                if (el.textContent) {
                    const match = el.textContent.match(/已标注[\\s\\(]*([\\d,]+)[\\)\\s]*$/);
                    if (match) {
                        return parseInt(match[1].replace(/,/g, ''));
                    }
                }
            }
            return 0;
        })()
        """
        result = self.execute_js(js_code, page_id)
        return result or 0

    def get_page_info(self) -> Dict:
        """
        获取当前海康页面的完整信息

        Returns:
            包含 dataset_id, version_id, labeled_count, url 的字典
        """
        print("=" * 60)
        print("从浏览器提取信息...")
        print("=" * 60)

        # 1. 找到海康页面
        page = self.find_hikvision_page()
        if not page:
            print("错误: 未找到海康AI平台页面")
            print("请确保已在浏览器中打开数据集页面")
            print("URL应包含 /overall/{dataset_id}/{version_id}/gallery")
            return {}

        url = page.get("url")
        page_id = page.get("id")
        title = page.get("title", "")

        print(f"\n找到页面: {title}")
        print(f"URL: {url[:80]}...")

        # 2. 提取ID
        dataset_id, version_id = self.extract_ids_from_url(url)
        if not dataset_id or not version_id:
            print("错误: 无法从URL提取dataset_id和version_id")
            return {}

        print(f"Dataset ID: {dataset_id}")
        print(f"Version ID: {version_id}")

        # 3. 获取cookies（优先browser_cookie3，不依赖WebSocket）
        try:
            cookies = self.get_cookies(page_id)
            print(f"获取到 {len(cookies)} 个cookies")
        except Exception as e:
            print(f"获取cookies失败: {e}")
            cookies = {}

        # 4. 尝试获取已标注数量（可选，失败不影响主流程）
        labeled_count = 0
        try:
            labeled_count = self.get_labeled_count(page_id)
            print(f"已标注图片: {labeled_count}")
        except Exception as e:
            print(f"  获取已标注数量失败（将从API获取）: {e}")

        return {
            "dataset_id": dataset_id,
            "version_id": version_id,
            "labeled_count": labeled_count,
            "url": url,
            "title": title,
            "page_id": page_id,
            "cookies": cookies
        }


def test_bridge():
    """测试桥接器"""
    bridge = BBBrowserBridge()
    print(f"CDP端口: {bridge.cdp_port}")
    print(f"连接状态: OK")

    pages = bridge.get_pages()
    print(f"\n浏览器页面数: {len(pages)}")

    for page in pages:
        print(f"  - {page.get('title', 'N/A')[:40]}... ({page.get('url', 'N/A')[:60]}...)")

    page_info = bridge.get_page_info()
    if page_info:
        print("\n提取成功!")
        print(f"Dataset: {page_info['dataset_id']}")
        print(f"Version: {page_info['version_id']}")
        print(f"已标注: {page_info['labeled_count']}")


if __name__ == "__main__":
    test_bridge()
