"""临时探针：NBS easyquery.htm 全量历史（用完即删）。"""
from __future__ import annotations

import json

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/151.0.0.0 Safari/537.36"}

# 老版接口
EASY = "https://data.stats.gov.cn/easyquery.htm"

# 核心CPI（不包括食品和能源）的 ek：6021702000021-6067101000036
# easyquery 指标编码一般是 zb 值，A 开头（月度库 hgyd）
# 试常见编码
CANDIDATES = ["A010101", "A010102", "A0101", "A010201"]


def try_query(zb: str) -> None:
    dfwds = json.dumps([
        {"wdcode": "zb", "valuecode": zb},
        {"wdcode": "sj", "valuecode": "2020-2026"},
    ])
    params = {
        "m": "QueryData",
        "dbcode": "hgyd",
        "rowcode": "zb",
        "colcode": "sj",
        "wds": "[]",
        "dfwds": dfwds,
        "k1": "1234",
    }
    try:
        r = requests.get(EASY, params=params, headers=UA, timeout=25)
        print(f"[zb={zb}] status={r.status_code} len={len(r.text)}")
        j = r.json()
        ret = j.get("returndata") or {}
        nodes = ret.get("datanodes") or []
        print(f"  datanodes={len(nodes)}")
        if nodes:
            # 展示前几个
            for n in nodes[:3]:
                print("   ", n.get("code"), n.get("data", {}).get("data"))
    except Exception as exc:  # noqa: BLE001
        print(f"[zb={zb}] 失败: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    for zb in CANDIDATES:
        try_query(zb)
