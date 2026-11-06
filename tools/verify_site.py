#!/usr/bin/env python3
"""发布后打开线上网站核对：节目目录、台本、音频、字幕、章节、来源链接与旧节目。

python tools/verify_site.py 2026-11-06-1800-ai 2026-11-06-1800-acg
python tools/verify_site.py --wait 600 2026-11-07-0800-ai 2026-11-07-0800-acg   # 等 Pages 生效（最多 600 秒）
不给编号时检查目录里的全部节目。任一项失败时以非零状态退出。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
UA = {"User-Agent": "Mozilla/5.0 (chenguang-radio verify)"}


def get(url: str, method: str = "GET", limit: int | None = None):
    req = urllib.request.Request(url, method=method, headers={**UA, **({"Range": f"bytes=0-{limit - 1}"} if limit else {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, dict(r.headers), r.read() if method == "GET" else b""


def fresh(url: str) -> str:
    return f"{url}{'&' if '?' in url else '?'}t={int(time.time())}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--base", default=None)
    ap.add_argument("--wait", type=int, default=0, help="等待新节目出现在线上目录的最长秒数")
    ap.add_argument("--skip-links", action="store_true", help="不检查来源链接")
    a = ap.parse_args()
    base = a.base or json.loads((ROOT / "station.json").read_text(encoding="utf-8"))["url"]
    base = base.rstrip("/") + "/"
    problems, notes = [], []
    deadline = time.time() + a.wait
    while True:
        catalog = json.loads(get(fresh(base + "episodes.json"))[2])
        keys = [e.get("id") or e["date"] for e in catalog]
        missing = [i for i in a.ids if i not in keys]
        if not missing or time.time() > deadline:
            break
        print(f"线上目录还没有 {missing}，等待 Pages 生效…", flush=True)
        time.sleep(20)
    for i in missing:
        problems.append(f"线上 episodes.json 没有 {i}")
    status, _, page = get(fresh(base))
    if status != 200 or b"<audio" not in page:
        problems.append("首页无法打开或缺少播放器")
    targets = a.ids or keys
    for entry in catalog:
        key = entry.get("id") or entry["date"]
        if key not in targets:
            continue
        for lang in [k for k, v in entry.items() if isinstance(v, dict) and v.get("title")]:
            name = f"{key}-{lang}"
            try:
                ep = json.loads(get(fresh(f"{base}episodes/{name}.json"))[2])
            except urllib.error.HTTPError as exc:
                problems.append(f"{name}: 台本 {exc.code}")
                continue
            audio = ep.get("audio") or f"audio/{name}.mp3"
            url = audio if audio.startswith("http") else base + audio
            try:
                st, headers, _ = get(url, "HEAD")
                size = int(headers.get("Content-Length", 0))
                ctype = headers.get("Content-Type", "")
                if size < 10_000 or "audio" not in ctype:
                    problems.append(f"{name}: 音频异常（{size} 字节，{ctype}）")
                head = get(url, limit=4)[2]
                if not (head.startswith(b"ID3") or head[:1] == b"\xff"):
                    problems.append(f"{name}: 音频不是 MP3")
            except urllib.error.HTTPError as exc:
                problems.append(f"{name}: 音频 {exc.code} {url}")
                continue
            lines = [*ep["opening"], *[l for n in ep["news"] for l in n["lines"]], *ep["closing"]]
            timed, segs = ep.get("lines_timed", []), ep.get("segments", [])
            if len(timed) != len(lines):
                problems.append(f"{name}: 字幕 {len(timed)} 句 / 台词 {len(lines)} 句")
            if len(segs) != len(ep["news"]) + 2 or any(s["end"] <= s["start"] for s in segs):
                problems.append(f"{name}: 章节不完整")
            if abs((timed[-1]["end"] if timed else 0) - ep.get("seconds", 0)) > 2:
                problems.append(f"{name}: 时长与字幕不符")
            links = []
            if not a.skip_links:
                for n in ep["news"]:
                    try:
                        code = get(n["url"], "GET", limit=2048)[0]
                    except urllib.error.HTTPError as exc:
                        code = exc.code
                    except Exception as exc:  # noqa: BLE001
                        code = type(exc).__name__
                    links.append(f"{code}")
                    if code not in (200, 206):
                        notes.append(f"{name}: 来源 {n['url']} 返回 {code}（可能是站点拒绝脚本访问，请人工确认）")
            share = f"{base}share/{name}.html"
            try:
                share_ok = get(share, "HEAD")[0] == 200
            except urllib.error.HTTPError:
                share_ok = False
            print(f"✓ {name}: {ep['title']} | {ep.get('seconds')} 秒 | 音频 {size} 字节 | 字幕 {len(timed)} 句 | "
                  f"章节 {len(segs)} 段 | 来源 {','.join(links) or '-'} | 分享页 {'有' if share_ok else '无'} | "
                  f"链接 {base}#{key}/{lang}")
    for n in notes:
        print("提醒：" + n)
    for p in problems:
        print("错误：" + p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
