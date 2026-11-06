#!/usr/bin/env python3
"""打包可发布的静态电台，不联网、不提交，也不推送代码。

python tools/build_site.py --output ../../work/chenguang-site
目标目录必须为空；输出包含播放器、台本、角色、分享卡和保留期内的音频。
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
import os
from pathlib import Path
import shutil
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
ASSET_TYPES = {".json", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".svg", ".mp4", ".webm"}
AUDIO_TYPES = {".mp3", ".wav", ".ogg", ".m4a", ".opus"}


def source_path(relative: str) -> Path:
    url = urlsplit(relative)
    if url.scheme or url.netloc or "\\" in relative:
        raise ValueError(f"需要仓库内的相对路径：{relative}")
    path = Path(os.path.normpath(str(ROOT / unquote(url.path)))).resolve()
    if not path.is_relative_to(ROOT) or path == ROOT:
        raise ValueError(f"路径超出电台目录：{relative}")
    if not path.is_file():
        raise ValueError(f"缺少发布素材：{relative}")
    return path


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def collect(today: date) -> tuple[set[Path], int, date]:
    station = read_json(ROOT / "station.json")
    keep = station.get("audio", {}).get("keep_days", 30)
    if not isinstance(keep, int) or keep < 0:
        raise ValueError("station.json 的 audio.keep_days 必须是非负整数。")
    cutoff = today - timedelta(days=keep)
    paths = {source_path(name) for name in ("index.html", "station.json", "LICENSE")}
    for field in (station.get("logo"), station.get("character", {}).get("thumbnail")):
        if field:
            paths.add(source_path(field))
    catalog_path = source_path(station.get("episodes", "episodes.json"))
    paths.add(catalog_path)
    catalog = read_json(catalog_path)
    if not isinstance(catalog, list):
        raise ValueError("节目目录必须是 JSON 数组。")

    character_pack = source_path(station["character"]["pack"])
    paths.add(character_pack)
    character = read_json(character_pack)
    references = [character.get("base"), character.get("depth"), character.get("idle")]
    references.extend(character.get("talk", []))
    references.extend(part.get("src") for part in character.get("parts", {}).values())
    for reference in filter(None, references):
        path = source_path((character_pack.parent / reference).relative_to(ROOT).as_posix())
        if path.suffix.lower() not in ASSET_TYPES:
            raise ValueError(f"不支持的角色素材类型：{path.name}")
        paths.add(path)

    for entry in catalog:
        episode_date = date.fromisoformat(entry["date"])
        languages = [lang for lang, value in entry.items()
                     if lang != "date" and isinstance(value, dict) and value.get("title")]
        names = [f"{entry['date']}-{language}" for language in languages] or [entry["date"]]
        for name in names:
            episode_path = source_path(f"episodes/{name}.json")
            paths.add(episode_path)
            episode = read_json(episode_path)
            if episode_date < cutoff:
                continue
            audio = episode.get("audio") or f"{station.get('audio', {}).get('dir', 'audio')}/{name}.mp3"
            url = urlsplit(audio)
            if url.scheme in {"http", "https"}:
                continue  # 外部音频保持原始链接，不下载或重新分发。
            if url.scheme or url.netloc:
                raise ValueError(f"不支持的音频地址：{audio}")
            audio_path = source_path(audio)
            if audio_path.suffix.lower() not in AUDIO_TYPES:
                raise ValueError(f"不支持的音频类型：{audio_path.name}")
            paths.add(audio_path)

    share = ROOT / "share"
    if share.is_dir():
        for file in share.rglob("*"):
            if file.is_file() and file.suffix.lower() in {".html", ".jpg", ".jpeg", ".png", ".webp", ".svg"}:
                paths.add(source_path(file.relative_to(ROOT).as_posix()))
    audio_count = sum(path.suffix.lower() in AUDIO_TYPES for path in paths)
    return paths, audio_count, cutoff


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", required=True, help="新的空输出目录")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today(), help="音频保留期基准，YYYY-MM-DD")
    args = parser.parse_args()
    output = Path(os.path.normpath(str(Path.cwd() / args.output))).resolve()
    try:
        if output == ROOT or output in ROOT.parents or output.is_relative_to(ROOT):
            raise ValueError("输出目录必须放在源码目录以外，避免混入源文件。")
        if output.exists() and (not output.is_dir() or any(output.iterdir())):
            raise ValueError("输出目录必须不存在或为空；本工具不会清空已有文件。")
        paths, audio_count, cutoff = collect(args.today)
        output.mkdir(parents=True, exist_ok=True)
        for source in sorted(paths):
            destination = output / source.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        (output / ".nojekyll").touch()
        print(f"静态站点已打包：{output}")
        print(f"共 {len(paths) + 1} 个文件，{audio_count} 个音频；保留 {cutoff.isoformat()} 起的节目音频。")
        print("此命令只生成文件；请把输出目录作为 GitHub Pages 的 gh-pages 分支内容发布。")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"打包失败：{exc}") from exc


if __name__ == "__main__":
    main()
