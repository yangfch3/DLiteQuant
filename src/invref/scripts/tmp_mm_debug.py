"""临时诊断：macromicro 在 CI 环境失败原因（用完即删）。

打印：环境版本、代理、出口 IP、实际发出的请求头、多组请求变体的响应形态。
"""
from __future__ import annotations

import os
import re
import sys

import requests


def section(t: str) -> None:
    print("\n" + "=" * 60)
    print("== " + t)
    print("=" * 60)


section("环境")
print("python:", sys.version.replace("\n", " "))
print("requests:", requests.__version__)
import urllib3

print("urllib3:", urllib3.__version__)
for mod in ["brotli", "brotlicffi", "zstandard"]:
    try:
        __import__(mod)
        print(f"{mod}: installed")
    except ImportError:
        print(f"{mod}: NOT installed")

section("代理环境变量")
for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "NO_PROXY", "no_proxy", "ALL_PROXY", "all_proxy"]:
    print(f"{k} = {os.environ.get(k)!r}")

section("出口 IP")
for url in ["https://api.ipify.org", "https://ifconfig.me/ip", "https://ipinfo.io/ip"]:
    try:
        r = requests.get(url, timeout=15)
        print(url, "->", r.text.strip()[:120])
        break
    except Exception as e:  # noqa: BLE001
        print(url, "fail:", type(e).__name__, str(e)[:120])

BASE = "https://www.macromicro.me/charts/225/cn-cpi"

FULL_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Sec-Ch-Ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def probe(label: str, headers: dict) -> None:
    section(f"请求变体: {label}")
    s = requests.Session()
    s.headers.update(headers)
    try:
        r = s.get(BASE, timeout=30)
    except Exception as e:  # noqa: BLE001
        print("请求失败:", type(e).__name__, str(e)[:200])
        return
    print("status:", r.status_code)
    print("Content-Encoding:", r.headers.get("Content-Encoding"))
    print("Content-Type:", r.headers.get("Content-Type"))
    print("Server:", r.headers.get("Server"))
    print("Set-Cookie:", str(r.headers.get("Set-Cookie"))[:200])
    print("len(text):", len(r.text), "len(content):", len(r.content))
    text = r.text
    for kw in ["challenge-platform", "turnstile", "Just a moment", "attention required", "__cf_chl", "cf-clearance", "验证码", "cf-error"]:
        if kw in text:
            print(f"  含 Cloudflare 特征: {kw}")
    m = re.search(r'stk\s*[:=]\s*["\']([^"\']+)["\']', text)
    print("stk found:", bool(m))
    print("text 开头 150:", repr(text[:150]))
    print("content 前 40 字节 hex:", r.content[:40].hex())


section("项目默认请求头（实际发出）")
s = requests.Session()
prep = requests.Request("GET", BASE, headers=dict(s.headers)).prepare()
for k, v in prep.headers.items():
    print(f"  {k}: {v}")

probe("默认(无显式AE)", {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
probe("显式 gzip,deflate", {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept-Encoding": "gzip, deflate"})
probe("完整浏览器头", FULL_BROWSER)
probe("完整浏览器头+gzip", {**FULL_BROWSER, "Accept-Encoding": "gzip, deflate"})
