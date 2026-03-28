#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多模型API接口测试脚本 - 修复版
支持 Windows 和 Linux，使用正确的 API 配置
"""

import requests
import json
import time
import os
from typing import Dict, List, Optional
from datetime import datetime


# 模型配置 - 根据你的实际工作代码更新
MODELS_CONFIG = [
    # 可用的 DeepSeek 域名接口
    {
        "name": "qwen3-8b",
        "model": "qwen3-8b",
        "url": "http://ds.scc.com.cn/v1/chat/completions",
        "api_key": "0",
        "note": "DeepSeek 域名 - Qwen3 8B"
    },
    {
        "name": "ds-v3",
        "model": "ds-v3",
        "url": "http://ds.scc.com.cn/v1/chat/completions",
        "api_key": "0",
        "note": "DeepSeek 域名 - DeepSeek v3"
    },
    {
        "name": "glm",
        "model": "glm",
        "url": "http://ds.scc.com.cn/v1/chat/completions",
        "api_key": "0",
        "note": "DeepSeek 域名 - GLM 4.7 Flash"
    },
]


class ModelAPITester:
    """模型API测试器"""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.results = []
    
    def test_model(self, config: Dict, test_message: str = "你好，请介绍一下你自己") -> Dict:
        """
        测试单个模型接口
        
        Args:
            config: 模型配置
            test_message: 测试消息
            
        Returns:
            测试结果字典
        """
        result = {
            "name": config["name"],
            "model": config["model"],
            "note": config["note"],
            "url": config["url"],
            "status": "未测试",
            "response_time": 0,
            "error": None,
            "response": None,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        print(f"\n{'='*60}")
        print(f"测试模型: {config['name']} ({config['note']})")
        print(f"URL: {config['url']}")
        print(f"测试消息: {test_message}")
        print(f"{'='*60}")
        
        # 准备请求数据 - 使用你的工作代码的格式
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['api_key']}"
        }
        
        # 使用 system 消息，和你的代码保持一致
        payload = {
            "model": config["model"],
            "messages": [
                {
                    "role": "system",
                    "content": test_message
                }
            ]
        }
        
        try:
            start_time = time.time()
            
            response = requests.post(
                config["url"],
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            
            end_time = time.time()
            response_time = round(end_time - start_time, 2)
            
            result["response_time"] = response_time
            
            # 检查响应状态
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    result["status"] = "成功"
                    result["response"] = response_data
                    
                    # 尝试提取回复内容
                    reply_content = self._extract_reply(response_data)
                    
                    print(f"✓ 状态: 成功")
                    print(f"✓ 响应时间: {response_time}秒")
                    print(f"✓ 回复内容: {reply_content[:200]}..." if len(reply_content) > 200 else f"✓ 回复内容: {reply_content}")
                    
                except json.JSONDecodeError as e:
                    result["status"] = "JSON解析失败"
                    result["error"] = str(e)
                    result["response"] = response.text[:500]
                    print(f"✗ JSON解析失败: {e}")
                    
            else:
                result["status"] = f"HTTP错误 {response.status_code}"
                result["error"] = response.text[:500]
                print(f"✗ HTTP错误: {response.status_code}")
                print(f"✗ 错误信息: {response.text[:200]}")
                
        except requests.exceptions.Timeout:
            result["status"] = "超时"
            result["error"] = f"请求超时 (>{self.timeout}秒)"
            print(f"✗ 请求超时 (>{self.timeout}秒)")
            
        except requests.exceptions.ConnectionError as e:
            result["status"] = "连接错误"
            result["error"] = str(e)
            print(f"✗ 连接错误: {e}")
            
        except Exception as e:
            result["status"] = "未知错误"
            result["error"] = str(e)
            print(f"✗ 未知错误: {e}")
        
        self.results.append(result)
        return result
    
    def _extract_reply(self, response_data: Dict) -> str:
        """从响应数据中提取回复内容"""
        try:
            # OpenAI格式
            if "choices" in response_data:
                return response_data["choices"][0]["message"]["content"]
            
            # 直接content字段
            if "content" in response_data:
                return response_data["content"]
            
            # result字段
            if "result" in response_data:
                return str(response_data["result"])
            
            # 返回整个响应的字符串形式
            return json.dumps(response_data, ensure_ascii=False, indent=2)[:500]
            
        except (KeyError, IndexError, TypeError):
            return json.dumps(response_data, ensure_ascii=False, indent=2)[:500]
    
    def test_all_models(self, test_message: str = "你好，请介绍一下你自己"):
        """测试所有模型"""
        print(f"\n开始测试 {len(MODELS_CONFIG)} 个模型接口...")
        print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        for config in MODELS_CONFIG:
            self.test_model(config, test_message)
            time.sleep(0.5)  # 避免请求过快
    
    def print_summary(self):
        """打印测试摘要"""
        print(f"\n\n{'='*60}")
        print("测试摘要")
        print(f"{'='*60}\n")
        
        success_count = sum(1 for r in self.results if r["status"] == "成功")
        total_count = len(self.results)
        
        print(f"总计: {total_count} 个接口")
        print(f"成功: {success_count} 个")
        print(f"失败: {total_count - success_count} 个")
        print(f"\n详细结果:\n")
        
        # 表格形式显示结果
        print(f"{'模型名称':<20} {'状态':<15} {'响应时间':<10} {'说明'}")
        print(f"{'-'*80}")
        
        for result in self.results:
            status_icon = "✓" if result["status"] == "成功" else "✗"
            response_time = f"{result['response_time']}s" if result['response_time'] > 0 else "-"
            print(f"{status_icon} {result['name']:<18} {result['status']:<15} {response_time:<10} {result['note'][:30]}")
        
        print(f"\n{'='*60}\n")
    
    def save_results(self, filename: str = "test_results.json"):
        """保存测试结果到JSON文件 - 支持 Windows 和 Linux"""
        # 获取当前脚本所在目录
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_file = os.path.join(script_dir, filename)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                "test_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total": len(self.results),
                "success": sum(1 for r in self.results if r["status"] == "成功"),
                "results": self.results
            }, f, ensure_ascii=False, indent=2)
        
        print(f"测试结果已保存到: {output_file}")
        return output_file


def main():
    """主函数"""
    # 创建测试器
    tester = ModelAPITester(timeout=30)
    
    # 默认测试消息 - 使用你代码中的格式
    test_message = "Hello, test."
    
    # 执行测试
    tester.test_all_models(test_message)
    
    # 打印摘要
    tester.print_summary()
    
    # 保存结果
    result_file = tester.save_results()
    
    return result_file


if __name__ == "__main__":
    result_file = main()