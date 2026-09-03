from __future__ import annotations

import json
import urllib.request

cases = [
    ("bangumi API + cheese ep 1122054", "https://api.bilibili.com/pgc/view/web/season?ep_id=1122054"),
    ("bangumi API + cheese ep 6902", "https://api.bilibili.com/pgc/view/web/season?ep_id=6902"),
    ("cheese API + bangumi ep 100367", "https://api.bilibili.com/pugv/view/web/season?ep_id=100367"),
    ("cheese API + bangumi ep 779775", "https://api.bilibili.com/pugv/view/web/season?ep_id=779775"),
    ("bangumi API + bangumi ep 100367 (happy)", "https://api.bilibili.com/pgc/view/web/season?ep_id=100367"),
    ("cheese API + cheese ep 1122054 (happy)", "https://api.bilibili.com/pugv/view/web/season?ep_id=1122054"),
]

for label, url in cases:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.load(resp)
    code = data.get("code")
    message = data.get("message")
    has_result = "result" in data
    has_data = "data" in data
    print(f"{label}: code={code}, message={message!r}, has_result={has_result}, has_data={has_data}")
