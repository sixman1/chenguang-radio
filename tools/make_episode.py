#!/usr/bin/env python3
"""把中文台本变成 MP3，并更新逐句字幕、章节时间和节目目录。

默认配音：Kokoro-82M-v1.1-zh（Apache-2.0，开源权重，本机/CI 离线合成），音色 zf_001。
安装：python -m pip install -r tools/requirements-tts.txt   （另需 ffmpeg）
运行：
  python tools/make_episode.py episodes/2026-11-06-1900-ai-zh.json
  python tools/make_episode.py --pending          # 目录里缺音频、台词改过或仍是旧声音的节目都重做
  python tools/make_episode.py --pending --check  # 只列出需要重做的节目，不合成

节目编号：新节目在台本里写 "id": "YYYY-MM-DD-HHmm-<栏目>"（栏目 ai / acg），文件名为
episodes/<id>-<语言>.json，音频为 audio/<id>-<语言>.mp3。旧节目没有 id，仍按日期命名。
同一编号重跑时覆盖同一份节目（目录按编号更新，不新增条目）。
旧版 Microsoft Edge TTS 仍可用 --engine edge 显式选择，但其公开传播授权未确认，默认不再使用。
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RATE = 24000
BYTES_PER_SECOND = SAMPLE_RATE * 2  # mono, signed 16-bit PCM
KOKORO_REPO = "hexgrad/Kokoro-82M-v1.1-zh"
KOKORO_VOICE = "zf_001"
ID_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})-(\d{2})(\d{2})-([a-z0-9]+)$")


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def run_ffmpeg(ffmpeg: str, arguments: list[str], data: bytes | None = None) -> bytes:
    return subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", *arguments],
        check=True, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout


def episode_key(episode: dict) -> str:
    """节目编号：新节目用 id，旧节目用日期。"""
    key = episode.get("id") or episode["date"]
    m = ID_PATTERN.match(key) if episode.get("id") else None
    if episode.get("id"):
        if not m:
            raise SystemExit(f"id 格式应为 YYYY-MM-DD-HHmm-栏目：{key}")
        if m.group(1) != episode.get("date"):
            raise SystemExit(f"id 的日期与 date 不一致：{key} / {episode.get('date')}")
        if episode.get("time") and episode["time"] != f"{m.group(2)}:{m.group(3)}":
            raise SystemExit(f"id 的时间与 time 不一致：{key} / {episode.get('time')}")
        if episode.get("column") and episode["column"] != m.group(4):
            raise SystemExit(f"id 的栏目与 column 不一致：{key} / {episode.get('column')}")
    return key


def groups_of(episode: dict):
    groups = [("opening", None, episode["opening"])]
    groups += [("news", index, item["lines"]) for index, item in enumerate(episode["news"])]
    groups += [("closing", None, episode["closing"])]
    return groups


def speech_hash(episode: dict, voice: dict) -> str:
    says = [line["say"] for _, _, lines in groups_of(episode) for line in lines]
    blob = json.dumps({"voice": voice, "say": says}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


class Kokoro:
    def __init__(self, voice: str, speed: float):
        try:
            from kokoro import KModel, KPipeline
        except ImportError as exc:
            raise SystemExit("请先运行：python -m pip install -r tools/requirements-tts.txt") from exc
        import numpy as np
        self.np = np
        self.voice = voice
        self.base_speed = speed
        model = KModel(repo_id=KOKORO_REPO).eval()
        english = KPipeline(lang_code="a", repo_id=KOKORO_REPO, model=False)

        def en_callable(text: str) -> str:
            try:
                return next(english(text)).phonemes
            except Exception:  # noqa: BLE001 - 读不出的英文片段跳过，不让整期失败
                return ""
        self.pipeline = KPipeline(lang_code="z", repo_id=KOKORO_REPO, model=model, en_callable=en_callable)

    def speed(self, length: int) -> float:
        # 与官方 make_zh.py 相同：长句稍微放慢，避免赶字
        value = 0.8
        if length <= 83:
            value = 1.0
        elif length < 183:
            value = 1 - (length - 83) / 500
        return value * 1.1 * self.base_speed

    def pcm(self, text: str) -> bytes:
        parts = [result.audio.numpy() for result in self.pipeline(text, voice=self.voice, speed=self.speed)
                 if result.audio is not None]
        if not parts:
            return b""
        wave = self.np.clip(self.np.concatenate(parts), -1.0, 1.0)
        return (wave * 32767).astype("<i2").tobytes()


class Edge:
    def __init__(self, voice: str, rate: str, ffmpeg: str):
        try:
            import edge_tts
        except ImportError as exc:
            raise SystemExit("--engine edge 需要另外安装 edge-tts") from exc
        self.edge_tts, self.voice, self.rate, self.ffmpeg = edge_tts, voice, rate, ffmpeg

    def pcm(self, text: str) -> bytes:
        with tempfile.TemporaryDirectory() as folder:
            mp3 = Path(folder) / "line.mp3"
            speech = self.edge_tts.Communicate(text, self.voice, rate=self.rate, connect_timeout=15, receive_timeout=45)
            asyncio.run(speech.save(str(mp3)))
            return run_ffmpeg(self.ffmpeg, ["-i", str(mp3), "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "pipe:1"])


def voice_info(args: argparse.Namespace) -> dict:
    if args.engine == "kokoro":
        return {"provider": "kokoro", "model": KOKORO_REPO, "name": args.voice or KOKORO_VOICE,
                "speed": args.speed, "license": "Apache-2.0"}
    return {"provider": "edge-tts", "name": args.voice or "zh-CN-XiaoxiaoNeural", "rate": args.rate}


def validate(episode: dict, args: argparse.Namespace) -> None:
    groups = groups_of(episode)
    if any(not lines for _, _, lines in groups):
        raise SystemExit("开场、每个话题和结尾都需要至少一句台词。")
    if any(not isinstance(line.get("say"), str) or not line["say"].strip() for _, _, lines in groups for line in lines):
        raise SystemExit("每句台词的 say 都需要填写非空文字。")
    if args.gap < 0 or args.part_gap < 0:
        raise SystemExit("停顿时长不能小于零。")


def update_listing(episode: dict, key: str, lang: str, duration: float) -> None:
    listing_path = ROOT / "episodes.json"
    listing = read_json(listing_path) if listing_path.exists() else []
    entry = next((item for item in listing if (item.get("id") or item["date"]) == key), None)
    if entry is None:
        entry = {"date": episode["date"]}
        if episode.get("id"):
            entry["id"] = key
        listing.append(entry)
    for field in ("time", "timezone", "column", "column_name"):
        if episode.get(field):
            entry[field] = episode[field]
    entry[lang] = {"title": episode["title"], "seconds": duration}
    listing.sort(key=lambda item: (item["date"], item.get("time", ""), item.get("id", "")), reverse=True)
    write_json(listing_path, listing)


def generate(source: Path, args: argparse.Namespace, engine) -> None:
    ffmpeg = shutil.which(args.ffmpeg)
    if not ffmpeg:
        raise SystemExit("找不到 ffmpeg。请安装 FFmpeg 并加入 PATH，或传入 --ffmpeg 路径。")
    episode = read_json(source)
    validate(episode, args)
    lang = episode.get("lang", "zh")
    key = episode_key(episode)
    name = f"{key}-{lang}"
    if source.stem != name:
        raise SystemExit(f"台本文件名应为 episodes/{name}.json（现在是 {source.name}）")
    voice = voice_info(args)
    audio_dir = ROOT / "audio"
    audio_dir.mkdir(exist_ok=True)
    destination = audio_dir / f"{name}.mp3"
    with tempfile.TemporaryDirectory(prefix="myradio-tts-", dir=audio_dir) as temporary:
        folder = Path(temporary)
        chunks = [b"\0" * int(0.4 * BYTES_PER_SECOND)]
        byte_count = len(chunks[0])
        timed, segments = [], []
        line_number = 0
        for part, (kind, index, lines) in enumerate(groups_of(episode)):
            segment_start = 0.0 if part == 0 else byte_count / BYTES_PER_SECOND
            for position, line in enumerate(lines):
                line_number += 1
                print(f"[{name}] 合成第 {line_number} 句…", flush=True)
                pcm = engine.pcm(line["say"])
                if not pcm:
                    raise RuntimeError(f"第 {line_number} 句没有生成声音。")
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
        if finished.stat().st_size < 10_000:
            raise RuntimeError("生成的音频过小，可能合成失败。")
        finished.replace(destination)

    duration = round(byte_count / BYTES_PER_SECOND, 3)
    episode.update({"seconds": duration, "audio": f"audio/{name}.mp3",
                    "lines_timed": timed, "segments": segments,
                    "made_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "voice": voice, "speech_hash": speech_hash(episode, voice)})
    write_json(source, episode)
    update_listing(episode, key, lang, duration)
    print(f"完成：{destination.name}，{duration:.1f} 秒；字幕、章节与节目目录已更新。")


def pending(args: argparse.Namespace) -> list[Path]:
    """目录里需要（重新）配音的节目：缺音频、台词改了、声音不是当前方案。"""
    voice = voice_info(args)
    out = []
    for entry in read_json(ROOT / "episodes.json"):
        key = entry.get("id") or entry["date"]
        langs = [k for k, v in entry.items() if isinstance(v, dict) and v.get("title")]
        for lang in langs:
            path = ROOT / "episodes" / f"{key}-{lang}.json"
            if not path.exists():
                raise SystemExit(f"目录里有 {key}/{lang}，但缺少台本 {path.relative_to(ROOT)}")
            episode = read_json(path)
            audio = ROOT / (episode.get("audio") or f"audio/{key}-{lang}.mp3")
            if str(episode.get("audio", "")).startswith("http"):
                continue
            if (not audio.exists() or episode.get("speech_hash") != speech_hash(episode, voice)
                    or not episode.get("lines_timed")):
                out.append(path)
    # 新写好、还没进目录的台本
    listed = {p.resolve() for p in out}
    keys = {(e.get("id") or e["date"]) for e in read_json(ROOT / "episodes.json")}
    for path in sorted((ROOT / "episodes").glob("*.json")):
        try:
            episode = read_json(path)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"台本不是合法 JSON：{path.name}：{exc}") from exc
        if (episode.get("id") or episode.get("date")) not in keys and path.resolve() not in listed:
            out.append(path)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("episode", nargs="*", help="台本 JSON 路径")
    parser.add_argument("--pending", action="store_true", help="处理所有缺音频、台词改过或声音不同的节目")
    parser.add_argument("--check", action="store_true", help="与 --pending 一起用：只列出，不合成")
    parser.add_argument("--engine", choices=["kokoro", "edge"], default="kokoro", help="配音引擎，默认 kokoro")
    parser.add_argument("--voice", default=None, help="音色；kokoro 默认 zf_001")
    parser.add_argument("--speed", type=float, default=1.0, help="kokoro 语速倍率")
    parser.add_argument("--rate", default="+0%", help="edge 语速，例如 +10%%")
    parser.add_argument("--gap", type=float, default=0.22, help="句间停顿秒数")
    parser.add_argument("--part-gap", type=float, default=0.7, help="章节之间停顿秒数")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg 程序名或路径")
    args = parser.parse_args()
    targets = [Path(p).resolve() for p in args.episode]
    if args.pending:
        targets += [p for p in pending(args) if p not in targets]
    if args.check:
        for path in targets:
            print(path.relative_to(ROOT))
        return
    if not targets:
        print("没有需要配音的节目。")
        return
    try:
        engine = (Kokoro(args.voice or KOKORO_VOICE, args.speed) if args.engine == "kokoro"
                  else Edge(args.voice or "zh-CN-XiaoxiaoNeural", args.rate, args.ffmpeg))
        for path in targets:
            generate(path, args, engine)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"生成失败：{exc}") from exc


if __name__ == "__main__":
    sys.exit(main())
