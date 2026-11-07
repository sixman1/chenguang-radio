#!/usr/bin/env python3
"""检查台本与发布目录，发现问题时以非零状态退出（发布前的闸门）。

python tools/check_episode.py episodes/2026-11-06-1900-ai-zh.json   # 写完台本后、提交前
python tools/check_episode.py --all                                 # 目录内全部台本（结构）
python tools/check_episode.py --all --audio                         # 配音后：字幕、章节、音频都要对得上
python tools/check_episode.py --site _site                          # 打包后：保留期内的节目音频一个都不能少
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ID = re.compile(r"^(\d{4}-\d{2}-\d{2})-(\d{2})(\d{2})-(ai|acg)$")
COLUMNS = {"ai": "AI 日报", "acg": "二次元／游戏"}
CHARS_PER_SECOND = 4.6   # Kokoro zf_001 普通话的大致语速（含停顿），用于在配音前估算时长


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def lines_of(ep):
    return [*ep.get("opening", []), *[l for n in ep.get("news", []) for l in n.get("lines", [])], *ep.get("closing", [])]


def check_script(path: Path, audio: bool, errors: list[str], warnings: list[str]) -> None:
    where = path.relative_to(ROOT).as_posix()
    err = lambda m: errors.append(f"{where}: {m}")
    warn = lambda m: warnings.append(f"{where}: {m}")
    try:
        ep = read(path)
    except json.JSONDecodeError as exc:
        err(f"不是合法 JSON：{exc}")
        return
    lang = ep.get("lang", "zh")
    for field in ("format", "date", "title", "opening", "news", "closing"):
        if field not in ep:
            err(f"缺少 {field}")
    if errors and errors[-1].startswith(where):
        return
    if not str(ep.get("title", "")).strip():
        err("title 不能为空")
    if ep.get("id"):
        m = ID.match(ep["id"])
        if not m:
            err("id 应为 YYYY-MM-DD-HHmm-ai 或 YYYY-MM-DD-HHmm-acg")
        else:
            if m.group(1) != ep["date"]: err("id 日期与 date 不一致")
            if ep.get("time") != f"{m.group(2)}:{m.group(3)}": err("time 应为 HH:mm 且与 id 一致")
            if ep.get("column") != m.group(4): err("column 应与 id 一致")
            if ep.get("timezone") != "Asia/Taipei": err("timezone 应为 Asia/Taipei")
        if path.stem != f"{ep.get('id')}-{lang}":
            err(f"文件名应为 {ep.get('id')}-{lang}.json")
        news = ep["news"]
        # 条数按内容：默认约 5，特别值得报可再多；硬上限避免失控
        if len(news) > 8:
            err("每期资讯过多（建议约 5 条，最多 8 条）")
        for j, n in enumerate(news):
            tag = f"news[{j}]"
            for field in ("label", "points", "lines", "url", "meta"):
                if not n.get(field):
                    err(f"{tag} 缺少 {field}")
            if not str(n.get("url", "")).startswith("https://"):
                err(f"{tag}.url 需要 https 原文链接")
            meta = n.get("meta") or {}
            for field in ("date", "region", "platform"):
                if not meta.get(field):
                    err(f"{tag}.meta.{field} 需要写明（日期／地区／平台）")
            if n.get("details") is not None and len(n["details"]) != len(n.get("points", [])):
                err(f"{tag}.details 应与 points 一样长")
            if not n.get("verified_at"):
                err(f"{tag} 缺少 verified_at（打开来源核实的时间）")
        chars = sum(len(l.get("say", "")) for l in lines_of(ep))
        estimate = chars / CHARS_PER_SECOND
        # 时长按内容，不再卡约 90 秒；过短或明显过长仅提醒
        if news and not 50 <= estimate <= 280:
            warn(f"按字数估算约 {estimate:.0f} 秒（按内容弹性，通常约 1–4 分钟）")
    for l in lines_of(ep):
        if not str(l.get("say", "")).strip():
            err("有空的 say")
    if audio:
        timed = ep.get("lines_timed") or []
        if len(timed) != len(lines_of(ep)):
            err(f"lines_timed {len(timed)} 句，台词 {len(lines_of(ep))} 句：需要重新配音")
        segs = ep.get("segments") or []
        if len(segs) != len(ep["news"]) + 2:
            err("segments 数量与开场＋话题＋结尾不符")
        if any(b["start"] < a["start"] for a, b in zip(timed, timed[1:])):
            err("lines_timed 时间没有递增")
        if timed and abs(timed[-1]["end"] - ep.get("seconds", 0)) > 2:
            err("seconds 与最后一句的结束时间不符")
        src = ep.get("audio") or f"audio/{path.stem}.mp3"
        if not src.startswith("http"):
            f = ROOT / src
            if not f.exists() or f.stat().st_size < 10_000:
                err(f"缺少音频或音频过小：{src}")
        if ep.get("id") and not 55 <= ep.get("seconds", 0) <= 135 and ep["news"]:
            warn(f"时长 {ep.get('seconds')} 秒，偏离约 90 秒的目标")


def check_catalog(errors: list[str]) -> list[Path]:
    catalog = read(ROOT / "episodes.json")
    keys, paths = set(), []
    for entry in catalog:
        key = entry.get("id") or entry["date"]
        if key in keys:
            errors.append(f"episodes.json: 编号重复 {key}")
        keys.add(key)
        for lang, value in entry.items():
            if isinstance(value, dict) and value.get("title"):
                p = ROOT / "episodes" / f"{key}-{lang}.json"
                if not p.exists():
                    errors.append(f"episodes.json: 缺少台本 {p.name}")
                else:
                    paths.append(p)
    return paths


def check_site(site: Path, errors: list[str]) -> None:
    station = read(site / "station.json")
    keep = station.get("audio", {}).get("keep_days", 30)
    zone = station.get("schedule", {}).get("timezone") or "Asia/Taipei"
    cutoff = datetime.now(ZoneInfo(zone)).date() - timedelta(days=keep)
    count = 0
    for entry in read(site / "episodes.json"):
        key = entry.get("id") or entry["date"]
        for lang, value in entry.items():
            if not (isinstance(value, dict) and value.get("title")):
                continue
            ep = read(site / "episodes" / f"{key}-{lang}.json")
            if date.fromisoformat(entry["date"]) < cutoff or str(ep.get("audio", "")).startswith("http"):
                continue
            a = site / (ep.get("audio") or f"audio/{key}-{lang}.mp3")
            if not a.exists() or a.stat().st_size < 10_000:
                errors.append(f"发布目录缺少保留期内的音频：{a.relative_to(site)}")
            count += 1
    for name in ("index.html", "station.json", "episodes.json", "LICENSE"):
        if not (site / name).exists():
            errors.append(f"发布目录缺少 {name}")
    print(f"发布目录：保留期（{cutoff} 起）内 {count} 份节目音频已检查")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("episode", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--audio", action="store_true")
    ap.add_argument("--site")
    a = ap.parse_args()
    errors, warnings = [], []
    paths = [Path(p).resolve() for p in a.episode]
    if a.all:
        paths += [p for p in check_catalog(errors) if p not in paths]
    for p in paths:
        check_script(p, a.audio, errors, warnings)
    if a.site:
        check_site(Path(a.site).resolve(), errors)
    for w in warnings:
        print("提醒：" + w)
    for e in errors:
        print("错误：" + e)
    print(f"检查完成：{len(paths)} 份台本，{len(errors)} 个错误，{len(warnings)} 个提醒")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
