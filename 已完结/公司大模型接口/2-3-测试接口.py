#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多模型API接口测试脚本
支持：接口连通性测试 + 调用频率限制探测
"""

import requests
import json
import time
import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime


MODELS_CONFIG = [
    {
        "name": "ds-v3",
        "model": "ds-v3",
        "url": "http://ds.scc.com.cn/v1/chat/completions",
        "api_key": "0",
        "note": "DeepSeek 域名 - DeepSeek v3"
    },
]

# 频率限制测试参数
RATE_MAX_REQUESTS  = 300       # 最多发送多少个请求
RATE_INTERVAL      = 0.01      # 请求间隔（秒），0=不间隔连续发
RATE_TIMEOUT       = 30       # 单次请求超时（秒）


# ─────────────────────────────────────────────
# 主测试类
# ─────────────────────────────────────────────

class ModelAPITester:

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.results: List[Dict] = []

    def _post(self, config: Dict, messages: List[Dict],
              timeout: int = None, max_tokens: int = 16) -> Tuple[bool, str, float, int]:
        """
        发送请求，返回 (success, reply_or_error, elapsed, status_code)。
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['api_key']}"
        }
        payload = {
            "model": config["model"],
            "messages": messages,
            "max_tokens": max_tokens,
        }
        t0 = time.time()
        try:
            resp = requests.post(
                config["url"], headers=headers, json=payload,
                timeout=timeout or self.timeout
            )
            elapsed = round(time.time() - t0, 2)
            if resp.status_code == 200:
                data = resp.json()
                if "error" in data:
                    err = data["error"].get("message", str(data["error"]))[:200]
                    return False, f"API error: {err}", elapsed, resp.status_code
                reply = self._extract_reply(data)
                return True, reply, elapsed, resp.status_code
            else:
                return False, f"HTTP {resp.status_code}: {resp.text[:300]}", elapsed, resp.status_code
        except requests.exceptions.Timeout:
            return False, f"超时 (>{timeout or self.timeout}s)", round(time.time() - t0, 2), 0
        except Exception as e:
            return False, str(e), round(time.time() - t0, 2), 0

    def _extract_reply(self, data: Dict) -> str:
        try:
            if "choices" in data:
                return data["choices"][0]["message"]["content"]
            if "content" in data:
                return data["content"]
            if "result" in data:
                return str(data["result"])
            return json.dumps(data, ensure_ascii=False)[:300]
        except Exception:
            return json.dumps(data, ensure_ascii=False)[:300]

    # ── 接口连通性测试 ────────────────────────

    def test_model(self, config: Dict, test_message: str = "Hello, test.") -> Dict:
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
        print(f"[连通性] {config['name']}  {config['note']}")
        print(f"URL: {config['url']}")

        messages = [{"role": "user", "content": test_message}]
        success, reply, elapsed, _ = self._post(config, messages, max_tokens=64)

        result["response_time"] = elapsed
        if success:
            result["status"] = "成功"
            result["response"] = reply
            short = reply[:150] + ("..." if len(reply) > 150 else "")
            print(f"✓ 成功  {elapsed}s  回复: {short}")
        else:
            result["status"] = "失败"
            result["error"] = reply
            print(f"✗ 失败  {elapsed}s  {reply[:200]}")

        self.results.append(result)
        return result

    def test_all_models(self, test_message: str = "Hello, test."):
        print(f"\n开始连通性测试，共 {len(MODELS_CONFIG)} 个模型")
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        for config in MODELS_CONFIG:
            self.test_model(config, test_message)
            time.sleep(0.5)

    # ── 调用频率限制探测 ────────────────────────

    def test_rate_limit(self, config: Dict) -> Dict:
        """
        在短时间内连续发送请求，探测触发频率限制所需的请求数。
        记录每个请求的状态码、响应时间、是否被限流。
        """
        result = {
            "name":        config["name"],
            "model":       config["model"],
            "note":        config["note"],
            "test_type":   "rate_limit",
            "status":      "未完成",
            "total_sent":  0,
            "total_ok":    0,
            "total_429":   0,
            "total_other_error": 0,
            "first_429_at": None,   # 第几个请求首次触发 429
            "details":     [],
            "timestamp":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        print(f"\n{'='*60}")
        print(f"[频率限制] {config['name']}  {config['note']}")
        print(f"计划发送: 最多 {RATE_MAX_REQUESTS} 个请求, 间隔 {RATE_INTERVAL}s")

        messages = [{"role": "user", "content": "Hi"}]
        start_time = time.time()
        first_429 = None

        for i in range(1, RATE_MAX_REQUESTS + 1):
            success, reply, elapsed, status_code = self._post(
                config, messages, timeout=RATE_TIMEOUT, max_tokens=8
            )

            is_429 = status_code == 429 or (not success and "429" in reply)
            is_rate_limit = is_429 or ("rate" in reply.lower() if isinstance(reply, str) else False)

            if is_rate_limit:
                if first_429 is None:
                    first_429 = i
                result["total_429"] += 1
            elif success:
                result["total_ok"] += 1
            else:
                result["total_other_error"] += 1

            result["total_sent"] = i

            # 打印进度
            if is_rate_limit:
                icon = "⚠"
                print(f"  [{i:>3d}]  ⚠ 限流  {elapsed}s  {reply[:80]}")
            elif success:
                icon = "✓"
                print(f"  [{i:>3d}]  ✓ 成功  {elapsed}s")
            else:
                icon = "✗"
                print(f"  [{i:>3d}]  ✗ 错误  {elapsed}s  {reply[:80]}")

            detail = {
                "request_num": i,
                "success": success,
                "status_code": status_code,
                "elapsed": elapsed,
                "rate_limited": is_rate_limit,
                "info": reply[:150] if not success else "",
            }
            result["details"].append(detail)

            # 如果已经连续多个 429，可以提前停止
            if first_429 is not None and (i - first_429) >= 3:
                print(f"  ... 已连续 {(i - first_429)} 个 429，停止测试")
                break

            time.sleep(RATE_INTERVAL)

        elapsed_total = round(time.time() - start_time, 2)
        result["first_429_at"] = first_429
        result["elapsed_total"] = elapsed_total
        result["status"] = "完成"

        if first_429:
            print(f"\n  结论: 第 {first_429} 个请求首次触发限流 (429)")
            print(f"        共发送 {result['total_sent']} 个请求, 成功 {result['total_ok']} 个, "
                  f"限流 {result['total_429']} 个, 其他错误 {result['total_other_error']} 个")
            print(f"        总耗时: {elapsed_total}s")
        else:
            print(f"\n  结论: 发送 {result['total_sent']} 个请求均未触发限流")
            print(f"        成功 {result['total_ok']} 个, 其他错误 {result['total_other_error']} 个")
            print(f"        总耗时: {elapsed_total}s")

        self.results.append(result)
        return result

    def test_rate_limit_all_models(self):
        print(f"\n开始频率限制探测，共 {len(MODELS_CONFIG)} 个模型")
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        for config in MODELS_CONFIG:
            self.test_rate_limit(config)
            # 每个模型之间等待 5 秒，避免跨模型限流叠加
            time.sleep(5)

    # ── 汇总打印 ──────────────────────────────

    def print_summary(self):
        print(f"\n\n{'='*60}")
        print("测试摘要")
        print(f"{'='*60}\n")

        conn_results = [r for r in self.results if r.get("test_type") != "rate_limit"]
        rate_results = [r for r in self.results if r.get("test_type") == "rate_limit"]

        if conn_results:
            ok = sum(1 for r in conn_results if r["status"] == "成功")
            print(f"── 连通性测试  {ok}/{len(conn_results)} 成功\n")
            print(f"  {'模型名称':<20} {'状态':<15} {'响应时间':<10} {'说明'}")
            print(f"  {'-'*72}")
            for r in conn_results:
                icon = "✓" if r["status"] == "成功" else "✗"
                t = f"{r['response_time']}s" if r['response_time'] > 0 else "-"
                print(f"  {icon} {r['name']:<19} {r['status']:<15} {t:<10} {r['note'][:30]}")

        if rate_results:
            print(f"\n── 频率限制探测\n")
            print(f"  {'模型名称':<20} {'首次429':<15} {'成功/总数':<15} {'限流数':<10} {'总耗时'}")
            print(f"  {'-'*72}")
            for r in rate_results:
                first_429 = f"第{r['first_429_at']}个" if r['first_429_at'] else "未触发"
                ok_total = f"{r['total_ok']}/{r['total_sent']}"
                total_429 = str(r['total_429'])
                elapsed = f"{r.get('elapsed_total', 0)}s"
                print(f"  {r['name']:<20} {first_429:<15} {ok_total:<15} {total_429:<10} {elapsed}")

        print(f"\n{'='*60}\n")

    # ── 保存结果 ──────────────────────────────

    def save_results(self, filename: str = "test_results.json") -> str:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_file = os.path.join(script_dir, filename)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                "test_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total":   len(self.results),
                "results": self.results,
            }, f, ensure_ascii=False, indent=2)
        print(f"结果已保存: {output_file}")
        return output_file


# ─────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="模型API测试工具")
    parser.add_argument("--mode", choices=["conn", "rate", "all"], default="all",
                        help="测试模式: conn=仅连通性  rate=仅频率限制  all=两者都测 (默认: all)")
    parser.add_argument("--msg", default="Hello, test.", help="连通性测试消息")
    parser.add_argument("--max-requests", type=int, default=RATE_MAX_REQUESTS,
                        help=f"频率限制测试最大请求数 (默认: {RATE_MAX_REQUESTS})")
    parser.add_argument("--interval", type=float, default=RATE_INTERVAL,
                        help=f"请求间隔秒数 (默认: {RATE_INTERVAL})")
    args = parser.parse_args()

    # 应用命令行参数
    _g = globals()
    _g["RATE_MAX_REQUESTS"] = args.max_requests
    _g["RATE_INTERVAL"] = args.interval

    tester = ModelAPITester(timeout=30)

    if args.mode in ("conn", "all"):
        tester.test_all_models(args.msg)

    if args.mode in ("rate", "all"):
        tester.test_rate_limit_all_models()

    tester.print_summary()
    tester.save_results()


if __name__ == "__main__":
    main()
