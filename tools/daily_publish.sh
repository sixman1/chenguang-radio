#!/bin/bash
# 晨光电台：配音 → 对齐字幕和章节 → 校验 → 发布（在 Grok Bot 的云端机器上运行，不依赖个人电脑）。
#
# 用法（在仓库根目录）：
#   tools/daily_publish.sh [要在线上核对的节目编号 ...]
#   例：tools/daily_publish.sh 2026-11-07-0800-ai 2026-11-07-0800-acg
#
# 做的事：
#   1. 提交 episodes/ 下尚未提交的台本，并与 origin/main 同步
#   2. 取回 gh-pages 上已发布的音频（保留期内的旧节目一个都不漏）
#   3. 用 Kokoro-82M-v1.1-zh 为缺音频、台词改过或声音不同的节目配音，写回字幕时间与章节
#   4. 校验台本、字幕、章节、音频；把字幕时间推回 main（音频不进 main）
#   5. 打包站点（最近 keep_days 天音频）＋分享卡片，再校验发布目录
#   6. 以单个提交覆盖 gh-pages（与原 publish.sh 相同），然后打开线上网站核对
# 第 1–5 步任一步失败都会停止，gh-pages 不变，线上保留上一版可用网站。
# Python 环境：RADIO_PYTHON（默认 /workspace/.venv-kokoro/bin/python；不存在时用 uv 自动创建）。
# GitHub 凭据：使用本机 gh CLI 的登录（不写入仓库）。
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
export TZ=Asia/Taipei
exec 9>"${TMPDIR:-/tmp}/chenguang-radio-publish.lock"
flock -w 1800 9 || { echo "另一轮发布仍在进行，放弃本次"; exit 1; }

GIT=(git -c credential.helper= -c "credential.helper=!gh auth git-credential")
PY=${RADIO_PYTHON:-/workspace/.venv-kokoro/bin/python}
if [ ! -x "$PY" ]; then
  echo "创建配音环境：$(dirname "$(dirname "$PY")")"
  uv venv -q -p 3.12 "$(dirname "$(dirname "$PY")")"
  uv pip install -q -p "$PY" --index-strategy unsafe-best-match \
    --extra-index-url https://download.pytorch.org/whl/cpu -r tools/requirements-tts.txt
fi
command -v ffmpeg >/dev/null || { echo "缺少 ffmpeg"; exit 1; }
FONT=${SHARE_FONT:-/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc}

echo "== 1. 同步 main"
git add episodes/*.json 2>/dev/null || true
if ! git diff --cached --quiet; then
  git commit -q -m "台本：$(git diff --cached --name-only | sed -n 's#episodes/\(.*\)-zh.json#\1#p' | tr '\n' ' ')"
fi
"${GIT[@]}" pull -q --rebase origin main
"$PY" tools/check_episode.py --all

echo "== 2. 取回已发布音频"
mkdir -p audio
if "${GIT[@]}" fetch -q origin gh-pages 2>/dev/null; then
  git archive origin/gh-pages audio 2>/dev/null | tar -x || echo "gh-pages 上暂无音频"
fi

echo "== 3. 配音"
PYTHONWARNINGS=ignore "$PY" tools/make_episode.py --pending
"$PY" tools/make_episode.py --pending --check | (! grep .) || { echo "仍有节目没配好音"; exit 1; }

echo "== 4. 校验并提交字幕时间"
"$PY" tools/check_episode.py --all --audio
git add episodes episodes.json
if ! git diff --cached --quiet; then
  git commit -q -m "配音：更新字幕与章节时间（Kokoro zf_001）"
fi
"${GIT[@]}" push -q origin HEAD:main

echo "== 5. 打包"
SITE=$(mktemp -d); trap 'rm -rf "$SITE"' EXIT
rmdir "$SITE"
"$PY" tools/build_site.py --output "$SITE"
SHARE_FONT="$FONT" "$PY" tools/share.py "$SITE" --all --front
"$PY" tools/check_episode.py --site "$SITE"

echo "== 6. 发布 gh-pages"
REMOTE=$(git remote get-url origin)
SRC=$(git rev-parse --short HEAD)
(
  cd "$SITE"
  git init -q -b gh-pages
  git add -A -f
  git -c user.name="$(git -C "$OLDPWD" config user.name || echo chenguang-radio)" \
      -c user.email="$(git -C "$OLDPWD" config user.email || echo chenguang-radio@users.noreply.github.com)" \
      commit -q -m "publish $(date '+%F %H:%M') Asia/Taipei from $SRC"
  "${GIT[@]}" push -q -f "$REMOTE" gh-pages
  echo "已发布：$(git ls-files | wc -l | tr -d ' ') 个文件，$(git ls-files audio | wc -l | tr -d ' ') 个音频（源码 $SRC）"
)

echo "== 7. 线上核对（等待 GitHub Pages 生效）"
"$PY" tools/verify_site.py --wait 900 "$@"
