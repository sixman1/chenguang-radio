# 晨光电台 · 每日更新流程

时间一律按 **Asia/Taipei（GMT+8）**，与运行机器的时区无关。

| 时段 | 节目编号 | 栏目 |
| --- | --- | --- |
| 08:00 | `YYYY-MM-DD-0800-ai`、`YYYY-MM-DD-0800-acg` | AI 日报；二次元／游戏 |
| 16:00 | `YYYY-MM-DD-1600-ai`、`YYYY-MM-DD-1600-acg` | AI 日报；二次元／游戏 |

试播、补播用当时的台北时间作编号（例如 `2026-11-06-1800-ai`），不占用 0800／1600 正式时段。

## 文件与编号

- 台本：`episodes/<编号>-zh.json`；音频：`audio/<编号>-zh.mp3`（只在 gh-pages，不进 main）。
- 台本里保留标准字段：`id`、`date`、`time`（HH:mm）、`timezone`（`Asia/Taipei`）、`column`（`ai`／`acg`）、`column_name`。
- `episodes.json` 每期一条，按编号更新。同一编号重跑＝更新同一期，不会新增条目。
- 旧节目（没有 `id`，按日期命名，例如 `2026-11-06-zh`）和旧链接 `#2026-11-06/zh` 继续可用。
- 线上直达链接：`https://sixman1.github.io/chenguang-radio/#<编号>/zh`。

## 流程（搜集 → 台本 → 配音 → 字幕章节 → 校验 → 发布）

1. **准备**：`git pull`，然后
   `python3 tools/new_episode.py --slot 0800 --column ai`（或 `1600`、`acg`）。
   它给出编号、列出近 3 天同栏目已播的标题和链接，并生成台本骨架。
2. **搜集资料**：只报上一期之后的新消息。每条重要事实都要**打开来源核实**；传闻不报，旧闻不包装成新闻。
   - AI：不要自己另做一轮完整资讯搜集。使用 New Bot（AI 日报机器人）**同一时段**的最新简报。
     上午读 `/workspace/ai-briefings/YYYY-MM-DD-0800.md`（或 `latest-0800.md`），
     下午读 `/workspace/ai-briefings/YYYY-MM-DD-1600.md`（或 `latest-1600.md`）。
     从简报里挑选最多 3 条符合「模型、产品、开发工具、重要研究」的条目；跳过传闻和已经播过的内容。
     每条仍要打开原文核实，并写上链接、日期、地区、平台。
     若该时段简报还没写好，稍等再看；仍没有则只用尚未播过的最近一期简报，或少报、说明今天没有特别值得讲的。不要编造新闻。
   - 二次元／游戏：仍由本台自行搜集。优先官方公告、开发者博客、项目仓库、发行商消息。覆盖动画、游戏公布、更新、发售与活动。
3. **写台本**：默认 3 条，资讯不足就减少；没有重要消息时可以 0 条，只做简短更新说明（开场＋结尾）。
   约 90 秒 ≈ 全部 `say` 合计 420–460 个汉字。每条资讯必须有：
   `label`、`points`（与 `details` 等长）、`lines`、`url`（原文 https 链接）、
   `meta`（`date`／`region`／`platform`，写明日期、地区、平台）、`verified_at`（核实时间）。
   `say` 用汉字写数字和百分比（“百分之四十八点五”），避开多音字歧义（“重做”写成“全新制作”）；`show` 用常规写法。
4. **提交前检查**：`python3 tools/check_episode.py episodes/<编号>-zh.json`（有错误就改到通过）。
5. **配音并发布**：在 Grok Bot 云端机器上运行 `tools/daily_publish.sh <编号1> <编号2>`。它会提交台本、
   取回 gh-pages 上已有的音频、用 Kokoro 配音、写回字幕时间与章节、校验、打包（含保留期 30 天内的全部旧音频）、
   覆盖发布 gh-pages，最后打开线上网站核对音频、字幕、章节和来源链接（`tools/verify_site.py`）。
   发布前任一步失败都会停止，gh-pages 不变，线上继续保留上一版。音频只进 gh-pages，不进 main。
6. **可选：GitHub Actions**：`tools/ci/publish.yml` 是同一流程的 Actions 版本。复制到 `.github/workflows/` 并推送后，
   推送台本到 main 就会自动配音发布（推送工作流文件需要带 `workflow` 权限的 GitHub 凭据）。

## 准点说明

- 定时唤醒本身可能延迟几分钟；配音与打包约 1–3 分钟（Actions 版另有排队，约 3–8 分钟）；GitHub Pages 生效通常 1–10 分钟。
- 因此每期提前 30–40 分钟开始制作（07:20／15:20 左右），目标在整点前后上线，但不保证准点。

## 配音

- 模型：[Kokoro-82M-v1.1-zh](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh)，Apache-2.0；音色 `zf_001`。
  中文语音数据由 LongMaoData（龙猫数据）免费授权给模型作者；推理库 [kokoro](https://github.com/hexgrad/kokoro) 与 [misaki](https://github.com/hexgrad/misaki) 为 Apache-2.0。
- 合成在 GitHub Actions 上离线运行，不需要密钥，也不调用付费服务。
- 旧的 Microsoft Edge TTS（晓晓）只保留为 `--engine edge` 可选项，因公开传播授权未确认，默认不用。
