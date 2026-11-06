# 晨光电台 · 中文试播版

基于 [myradio](https://github.com/monoradio102/myradio) 定制的一间中文虚拟主播电台。台名“晨光电台”是可以随时替换的初稿。

在线收听：**https://sixman1.github.io/chenguang-radio/**

源码仓库：https://github.com/sixman1/chenguang-radio

在线版由 GitHub Pages 托管，访问者不需要安装本机工具。本机预览方法见下文。

当前包含中文界面、一集约 66 秒的中文开台试播、晓晓普通话配音、同步字幕、角色口型和章节跳转。首集介绍电台玩法，未接入实时新闻或自动更新。

## 先听听看

1. 先完整解压项目，再双击文件夹里的 **启动电台.cmd**，保留打开的窗口。
2. 在浏览器打开 **http://127.0.0.1:8765/**，点击播放。
3. 修改文件并保存后，刷新浏览器查看效果。关闭命令窗口即可停止。

播放已有节目只需要 Node.js，不需要 Python 或账号。也可以在本文件夹运行：

```text
node tools/preview.mjs
```

启动失败时窗口会保留错误提示。如果提示缺少文件，请检查是否已完整解压，且 `启动电台.cmd` 与 `tools` 文件夹在同一层。启动文件已按 Windows 的 CRLF 换行保存。

不要直接双击 index.html：播放器需要通过本机网页服务读取台本和角色素材。

## 从哪里开始改

| 想改什么 | 文件 | 怎么改 |
| --- | --- | --- |
| 电台名字、标语、简介、配音署名 | `station.json` | 修改 `name`、`tagline`、`description`、`caster`、`credits` |
| 本期标题、开场、话题、结尾 | `episodes/2026-11-06-zh.json` | 修改 `title`、`opening`、`news`、`closing` |
| 电台标志 | `logo.svg` | 换成自己的 SVG；使用 PNG 时同时修改配置的 `logo` 路径 |
| 主播外观、嘴型与眨眼素材 | `character/` | 更换图片并调整 `character.json`，保留素材所需署名 |
| 界面颜色、布局、按钮文字 | `index.html` | CSS 开头的颜色变量和 JavaScript 中的 `UI.zh` |
| 节目列表 | `episodes.json` | 配音工具会更新；添加新一期后显示在这里 |

改名字后，还要检查开场和结尾中的台词，再重新生成声音。

### 改台本，再生成声音

每句台词有两个字段：`say` 是主播念出来的文字，`show` 是屏幕字幕。话题中的 `points` 是要点，`details` 是对应说明，`url` 是资料来源。

第一次需要 Python 3、FFmpeg（加入 PATH），并安装语音依赖：

```text
python -m pip install -r tools/requirements-tts.txt
```

保存台本后，在电台文件夹运行：

```text
python tools/make_episode.py episodes/2026-11-06-zh.json
```

工具会联网将 `say` 文本发送给 Microsoft Edge 语音服务，生成 `audio/2026-11-06-zh.mp3`，同时更新字幕、章节时间和节目目录。生成完成后刷新浏览器。只修改画面要点和补充说明时，不需要重新配音；修改台词时需要重新生成。

默认声音是晓晓。也可以改用云希：

```text
python tools/make_episode.py episodes/2026-11-06-zh.json --voice zh-CN-YunxiNeural
```

换声音后，同时更新 `station.json` 中的 `caster` 和 `credits`。自选语音和素材按相应提供方的条件使用。

### 添加新一期

复制本期 JSON 为 `episodes/日期-zh.json`，修改内部 `date`、`title` 和台词，再把新文件路径传给配音工具。日期采用 `YYYY-MM-DD`。工具按日期更新目录，新一期排在最上面。

完整台本和角色格式见 [docs/formats.md](docs/formats.md)；该文档沿用原项目的日文说明。

## 分享卡片（可选）

已附带试播版分享卡片。修改台名、标题或话题后，可重新生成：

```text
python -m pip install Pillow
python tools/share.py --url http://127.0.0.1:8765/ --all
```

工具自动尝试 Windows 微软雅黑或黑体，也可以用 `--font` 指定包含中文字形的字体。SVG 标志渲染依赖可选的 `resvg-py`，缺少时分享卡片跳过标志。正式发布时，把 `--url` 改为实际公开地址再重新生成卡片；不要把本机地址当成公开链接。

## 更新在线电台

自己的仓库是 `sixman1/chenguang-radio`。`main` 分支保留可编辑源文件，`gh-pages` 分支放实际发布文件和音频。`station.json` 已填写在线地址与仓库，原电台评论配置已移除。

以后修改的基本顺序：编辑配置或台本 → 需要时重新配音 → 本机预览 → 提交源码 → 发布站点。

1. 提交台本、配置和播放器代码到自己的 `main` 分支；`audio/` 保持忽略，不提交到 main。
2. 修改标题、台名或话题后，使用公开网址重新生成分享卡片：`python tools/share.py --url https://sixman1.github.io/chenguang-radio/ --all --front`。生成后也要提交这些修改。
3. 可用 `python tools/build_site.py --output 一个新的空文件夹路径` 在 Windows 上生成静态发布目录，包含网页、角色和最近 30 天音频。该命令只准备文件，不会联网发布。
4. 将发布目录更新到自己的 `gh-pages` 分支并推送，GitHub Pages 会更新网站。也可以在 Git Bash 中使用原项目的 `tools/publish.sh`；它从已提交的 HEAD 打包，发布前要先提交源码修改。

原 Bash 脚本会重建并覆盖自己仓库的 `gh-pages` 分支，默认只携带最近 30 天音频。发布工具不负责抓取新闻、编写台本或定时合成声音。想每天自动播报时，需要另外设计内容来源与更新流程。

本机工作文件夹保留了原项目的 Git 历史；交付压缩包不包含 `.git`。如果从压缩包解压后再发布，需要先初始化自己的 Git 仓库。

## 来源与署名

- 播放器和原工具：[monoradio102/myradio](https://github.com/monoradio102/myradio)，MIT，保留 [LICENSE](LICENSE)。
- 角色：沿用原项目允许复用的 AI 生成素材，具体说明见原项目 README。
- 台名及日出标志：本中文试播版的新设计，可继续替换。
- 本期声音：Microsoft Edge TTS，`zh-CN-XiaoxiaoNeural`；未使用原项目的日语或英语录音。

本版保留可编辑源文件，音频已经放在本地 `audio/`。Git 忽略音频只影响版本记录，不影响你在本机播放或备份文件夹。
