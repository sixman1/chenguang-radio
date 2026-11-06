#!/usr/bin/env python3
"""把中文台本变成 MP3，并更新逐句字幕、章节时间和节目目录。

安装：python -m pip install -r tools/requirements-tts.txt
运行：python tools/make_episode.py episodes/2026-11-06-zh.json
另需把 ffmpeg 加入 PATH。合成需要联网，公开播音前请核对声音服务条款。
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RATE = 24000
BYTES_PER_SECOND = SAMPLE_RATE * 2  # mono, signed 16-bit PCM


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_ffmpeg(ffmpeg: str, arguments: list[str]) -> bytes:
    return subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", *arguments],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout


async def generate(args: argparse.Namespace) -> None:
    try:
        import edge_tts
    except ImportError as exc:
        raise SystemExit("请先运行：python -m pip install -r tools/requirements-tts.txt") from exc
    ffmpeg = shutil.which(args.ffmpeg)
    if not ffmpeg:
        raise SystemExit("找不到 ffmpeg。请安装 FFmpeg 并加入 PATH，或传入 --ffmpeg 路径。")
    source = Path(args.episode).resolve()
    episode = json.loads(source.read_text(encoding="utf-8-sig"))
    lang = episode.get("lang", "zh")
    date = episode["date"]
    groups = [("opening", None, episode["opening"])]
    groups += [("news", index, item["lines"]) for index, item in enumerate(episode["news"])]
    groups += [("closing", None, episode["closing"])]
    if any(not lines for _, _, lines in groups):
        raise SystemExit("开场、每个话题和结尾都需要至少一句台词。")
    if any(not isinstance(line.get("say"), str) or not line["say"].strip()
           for _, _, lines in groups for line in lines):
        raise SystemExit("每句台词的 say 都需要填写非空文字。")
    if args.gap < 0 or args.part_gap < 0:
        raise SystemExit("停顿时长不能小于零。")

    audio_dir = ROOT / "audio"
    audio_dir.mkdir(exist_ok=True)
    destination = audio_dir / f"{date}-{lang}.mp3"
    # 在音频目录中暂存，保证 Windows 跨磁盘解压后也能原子替换正式音频。
    # audio/ 受 Git 忽略，临时目录在成功或失败后都会清理。
    with tempfile.TemporaryDirectory(prefix="myradio-tts-", dir=audio_dir) as temporary:
        folder = Path(temporary)
        chunks = [b"\0" * int(0.4 * BYTES_PER_SECOND)]
        byte_count = len(chunks[0])
        timed, segments = [], []
        line_number = 0
        for part, (kind, index, lines) in enumerate(groups):
            segment_start = 0.0 if part == 0 else byte_count / BYTES_PER_SECOND
            for position, line in enumerate(lines):
                mp3 = folder / f"line-{line_number:03d}.mp3"
                line_number += 1
                print(f"合成第 {line_number} 句…", flush=True)
                speech = edge_tts.Communicate(line["say"], args.voice, rate=args.rate,
                                               connect_timeout=15, receive_timeout=45)
                await speech.save(str(mp3))
                pcm = run_ffmpeg(ffmpeg, ["-i", str(mp3), "-f", "s16le", "-ac", "1",
                                          "-ar", str(SAMPLE_RATE), "pipe:1"])
                if not pcm:
                    raise RuntimeError("语音服务没有返回声音。")
                start = byte_count / BYTES_PER_SECOND
                chunks.append(pcm)
                byte_count += len(pcm)
                timed.append({"start": round(start, 3), "end": round(byte_count / BYTES_PER_SECOND, 3),
                              "show": line.get("show") or line["say"], "part": part})
                gap = args.part_gap if position == len(lines) - 1 else args.gap
                silence = b"\0" * (int(gap * SAMPLE_RATE) * 2)
                chunks.append(silence)
                byte_count += len(silence)
            segments.append({"kind": kind, "index": index, "start": round(segment_start, 3),
                             "end": round(byte_count / BYTES_PER_SECOND, 3)})
        raw = folder / "episode.pcm"
        raw.write_bytes(b"".join(chunks))
        finished = folder / "episode.mp3"
        run_ffmpeg(ffmpeg, ["-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1", "-i", str(raw),
                           "-c:a", "libmp3lame", "-b:a", "96k", "-y", str(finished)])
        finished.replace(destination)

    duration = round(byte_count / BYTES_PER_SECOND, 3)
    episode.update({"seconds": duration, "audio": f"audio/{date}-{lang}.mp3",
                    "lines_timed": timed, "segments": segments,
                    "made_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "voice": {"provider": "edge-tts", "name": args.voice, "rate": args.rate}})
    write_json(source, episode)
    listing_path = ROOT / "episodes.json"
    listing = json.loads(listing_path.read_text(encoding="utf-8-sig")) if listing_path.exists() else []
    entry = next((item for item in listing if item["date"] == date), None)
    if entry is None:
        entry = {"date": date}
        listing.append(entry)
    entry[lang] = {"title": episode["title"], "seconds": duration}
    listing.sort(key=lambda item: item["date"], reverse=True)
    write_json(listing_path, listing)
    print(f"完成：{destination.name}，{duration:.1f} 秒；字幕、章节与节目目录已更新。")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("episode", help="台本 JSON 路径")
    parser.add_argument("--voice", default="zh-CN-XiaoxiaoNeural", help="声音，默认中文晓晓")
    parser.add_argument("--rate", default="+0%", help="语速，例如 +10%%；减速请用 --rate=-10%%")
    parser.add_argument("--gap", type=float, default=0.22, help="句间停顿秒数")
    parser.add_argument("--part-gap", type=float, default=0.7, help="章节之间停顿秒数")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg 程序名或路径")
    args = parser.parse_args()
    try:
        asyncio.run(generate(args))
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"生成失败：{exc}") from exc


if __name__ == "__main__":
    main()
