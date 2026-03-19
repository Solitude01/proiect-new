#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认证模块 - 管理海康威视AI平台的认证信息
支持从bb-browser自动获取或手动输入
"""

from typing import Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class AuthInfo:
    """认证信息数据类"""
    token: str
    cookies: Dict[str, str]
    account_name: Optional[str] = None
    sub_account_name: Optional[str] = None
    project_id: Optional[str] = None


class AuthManager:
    """认证管理器"""

    def __init__(self):
        self.auth_info: Optional[AuthInfo] = None

    def authenticate_from_browser(self) -> bool:
        """
        从bb-browser自动获取认证信息

        Returns:
            是否成功获取认证
        """
        try:
            from ..browser.bb_browser_bridge import BBBrowserBridge

            bridge = BBBrowserBridge()
            page_info = bridge.get_page_info()

            if not page_info:
                return False

            cookies = page_info.get("cookies", {})
            token = cookies.get("token")

            if not token:
                print("错误: 无法从浏览器获取token")
                print("请确保已登录海康AI平台")
                return False

            self.auth_info = AuthInfo(
                token=token,
                cookies=cookies,
                account_name=cookies.get("accountName"),
                sub_account_name=cookies.get("subAccountName"),
                project_id=cookies.get("projectId")
            )

            return True

        except Exception as e:
            print(f"从浏览器获取认证失败: {e}")
            return False

    def authenticate_manual(
        self,
        token: str,
        account_name: str = "",
        sub_account_name: str = "",
        project_id: str = ""
    ) -> bool:
        """
        手动设置认证信息

        Args:
            token: 认证token
            account_name: 账户名
            sub_account_name: 子账户名
            project_id: 项目ID

        Returns:
            是否成功设置
        """
        if not token:
            print("错误: token不能为空")
            return False

        cookies = {
            "token": token,
            "accountName": account_name,
            "subAccountName": sub_account_name,
            "projectId": project_id or "9a323db2bce24cd69ce018e41eff6e68",
            "visitor": "false"
        }

        # 清理空值
        cookies = {k: v for k, v in cookies.items() if v}

        self.auth_info = AuthInfo(
            token=token,
            cookies=cookies,
            account_name=account_name,
            sub_account_name=sub_account_name,
            project_id=project_id
        )

        return True

    def is_authenticated(self) -> bool:
        """检查是否已认证"""
        return self.auth_info is not None and self.auth_info.token

    def get_token(self) -> Optional[str]:
        """获取token"""
        if self.auth_info:
            return self.auth_info.token
        return None

    def get_cookies(self) -> Dict[str, str]:
        """获取完整cookies"""
        if self.auth_info:
            return self.auth_info.cookies
        return {}

    def get_headers(self) -> Dict[str, str]:
        """
        获取API请求头

        Returns:
            包含认证信息的HTTP请求头
        """
        if not self.auth_info:
            raise ValueError("未设置认证信息")

        return {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://ai.hikvision.com",
            "referer": "https://ai.hikvision.com/intellisense/ai-training/console/data/",
            "token": self.auth_info.token,
            "projectid": self.auth_info.project_id or "9a323db2bce24cd69ce018e41eff6e68",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def get_auth_summary(self) -> str:
        """获取认证信息摘要"""
        if not self.auth_info:
            return "未认证"

        token_preview = self.auth_info.token[:20] + "..." if len(self.auth_info.token) > 20 else self.auth_info.token
        return f"Token: {token_preview}, Cookies: {len(self.auth_info.cookies)}个"


def test_auth():
    """测试认证模块"""
    auth = AuthManager()

    # 尝试从浏览器获取
    print("尝试从浏览器获取认证...")
    if auth.authenticate_from_browser():
        print(f"认证成功!")
        print(f"Token: {auth.get_token()[:30]}...")
        print(f"Cookies: {list(auth.get_cookies().keys())}")
    else:
        print("从浏览器获取失败")


if __name__ == "__main__":
    test_auth()
