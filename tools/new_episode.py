#!/usr/bin/env python3
"""为一个时段准备新节目：算出编号、列出近期已播资讯（避免重复），并生成待填写的台本骨架。

python tools/new_episode.py --slot 0800 --column ai        # 今天（台北时间）08:00 的 AI 日报
python tools/new_episode.py --slot 1600 --column acg       # 今天 16:00 的二次元／游戏日报
python tools/new_episode.py --slot now --column ai         # 用当前台北时间（试播、补播）
python tools/new_episode.py --slot 0800 --column ai --date 2026-11-07
加 --recent-only 只看近期已播内容，不写文件。时间固定按 Asia/Taipei 计算，与运行机器的时区无关。
已存在同编号的台本时不会覆盖：直接编辑那份文件即可（重跑会更新同一期，不新增）。
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Taipei")
COLUMNS = {
    "ai": {"name": "AI 日报", "focus": "模型、产品、开发工具和重要研究"},
    "acg": {"name": "二次元／游戏", "focus": "动画、游戏公布、更新、发售与活动"},
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slot", required=True, help="0800、1600 或 now")
    ap.add_argument("--column", required=True, choices=sorted(COLUMNS))
    ap.add_argument("--date", help="YYYY-MM-DD，默认台北时间今天")
    ap.add_argument("--recent-only", action="store_true")
    ap.add_argument("--days", type=int, default=3, help="列出最近几天的已播资讯")
    a = ap.parse_args()
    now = datetime.now(TZ)
    day = a.date or now.strftime("%Y-%m-%d")
    hhmm = now.strftime("%H%M") if a.slot == "now" else a.slot
    if len(hhmm) != 4 or not hhmm.isdigit():
        raise SystemExit("--slot 应为 0800、1600 或 now")
    key = f"{day}-{hhmm}-{a.column}"
    path = ROOT / "episodes" / f"{key}-zh.json"
    col = COLUMNS[a.column]

    catalog = json.loads((ROOT / "episodes.json").read_text(encoding="utf-8"))
    print(f"节目编号：{key}（台北时间 {day} {hhmm[:2]}:{hhmm[2:]}，栏目：{col['name']}）")
    print(f"台本文件：{path.relative_to(ROOT)}")
    print(f"当前台北时间：{now.isoformat(timespec='minutes')}")
    previous = None
    print(f"\n近 {a.days} 天同栏目已播（优先报道这些之后的新消息，不要重复）：")
    for entry in catalog:
        if entry.get("column") != a.column or entry.get("id") == key:
            continue
        if (datetime.fromisoformat(day) - datetime.fromisoformat(entry["date"])).days > a.days:
            continue
        ep = json.loads((ROOT / "episodes" / f"{entry['id']}-zh.json").read_text(encoding="utf-8"))
        previous = previous or ep
        print(f"- {entry['id']}《{ep['title']}》 made_at={ep.get('made_at')}")
        for n in ep["news"]:
            print(f"    · {n['label']}  {n['url']}")
    if previous:
        print(f"\n上一期同栏目：{previous['id']}，制作于 {previous.get('made_at')}（UTC）。")
    if a.recent_only:
        return
    if path.exists():
        print("\n台本已存在：直接编辑并重新提交即可（同编号会更新同一期）。")
        return
    skeleton = {
        "format": "monoradio/news-1",
        "id": key,
        "date": day,
        "time": f"{hhmm[:2]}:{hhmm[2:]}",
        "timezone": "Asia/Taipei",
        "column": a.column,
        "column_name": col["name"],
        "lang": "zh",
        "title": "",
        "opening": [],
        "news": [],
        "closing": [],
        "highlight": 0,
    }
    path.write_text(json.dumps(skeleton, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n已生成骨架：{path.relative_to(ROOT)}。按 docs/daily.md 填写后运行 tools/check_episode.py。")


if __name__ == "__main__":
    main()
