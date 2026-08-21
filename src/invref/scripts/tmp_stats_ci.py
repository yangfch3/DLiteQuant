"""临时：CI 验证 NBS 接口可达性（用完即删）。"""
from __future__ import annotations

import json

import requests

BASE = "https://data.stats.gov.cn/dg/website/publicrelease/web/external"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://data.stats.gov.cn",
    "Referer": "https://data.stats.gov.cn/dg/website/page.html",
}

BODY = {
    "cid": "809d2522b0fe4be89142650341b19083",
    "indicatorIds": ["c2050e97c49a4763a6d0f0f38bf0b4ed"],
    "daCatalogId": "",
    "das": [{"text": "全国", "value": "000000000000"}],
    "showType": "1",
    "dts": "",
    "rootId": "fc982599aa684be7969d7b90b1bd0e84",
}

# 指标树（确认可达）
r = requests.get(
    f"{BASE}/new/queryIndicatorsByCid",
    params={"cid": "809d2522b0fe4be89142650341b19083", "dt": "2025-2026", "name": ""},
    headers=HEADERS, timeout=25,
)
print("queryIndicatorsByCid:", r.status_code, "len:", len(r.text))

# esData
r = requests.post(f"{BASE}/stream/esData", data=json.dumps(BODY), headers=HEADERS, timeout=30)
print("esData:", r.status_code, "len:", len(r.text))
try:
    j = r.json()
    data = j.get("data") or []
    print("月份数:", len(data))
    if data:
        for m in data[:3]:
            for item in m.get("values") or []:
                print("  ", m["code"], item.get("i_showname"), item.get("value"))
except Exception as exc:  # noqa: BLE001
    print("解析失败:", type(exc).__name__, r.text[:200])
