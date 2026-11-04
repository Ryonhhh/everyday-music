# 维护说明

面向要改这个项目的人。读者向的介绍在 [README](../README.md)。

## 课程生产流程

```
plan.json  ──build_curriculum.py──▶  data/curriculum.json  ──▶  站点
                │
书籍 PDF ──rag add──▶ 知识库 ──unit_context.py──▶ 原文材料 ──▶ 写 day-NN.md
                                                        │
                                          build_lessons_index.py ──▶ data/lessons/index.json
```

写一篇新课：

```powershell
$env:PYTHONIOENCODING='utf-8'

# 1. 取该天对应单元的原文（第 N 天 = T{N} + H{N}；第 27 天起只有 H）
python tools/unit_context.py T07 H07 --out ".tmp\ctx-day07.txt" --per 2

# 2. 照 data/lessons/day-01.md 的结构写 day-07.md

# 3. 重建清单
python tools/build_lessons_index.py
```

正文结构固定为：`>` 引言 → `## 乐理 · …` → `## 音乐史 · …` → `### 今日练习` → `### 今日思考`
→ `## 今日小结` → `## 参考出处`，每节末尾带 `> 出处：…，p.X–Y`。

## 页码体系（重要）

存在两套页码，别混：

- **印刷页码**：书上印的，`curriculum/plan.json` 里写的就是这个，课程正文引注也该用这个。
- **PDF 物理页序号**：`chunks` / `pages` 表里存的 `page_start` / `page_end` 是这个。

两者差一个固定偏移（Grout 这本 +20，李重光 +7）。`rag/rag/store.py` 的 `book_page_offset()`
从页眉页脚的页码投票算出偏移，`tools/unit_context.py` 在检索前自动换算，输出里同时打印
「印刷页」和「PDF 页」。

历史正文如果引注用的是 PDF 页，用 `tools/fix_citations.py` 批量校正（只动「出处」行与
「参考出处」列表行，不碰正文其它数字）。先不带参数干跑看要改哪些行，确认后再 `--apply`。

## 检索实现

`rag/rag/` 下：

| 文件 | 作用 |
| --- | --- |
| `pdftext.py` | PDF → 带页码的文本，合并中文硬折行，可选调用字体修复 |
| `chunker.py` | 按段落累积到约 1100 字切块，块间留 160 字重叠 |
| `bm25.py` | BM25；汉字取单字 + 相邻二元组，ASCII 取整词 |
| `search.py` | 检索 + 去重 + 按书过滤 + 页码范围过滤 + 相邻段落扩展 |
| `store.py` | SQLite 持久层，含页码偏移检测 |
| `ingest.py` | 入库流程（命令行与网页上传共用） |
| `server.py` | 本地管理界面，标准库 HTTP 服务，无第三方依赖 |
| `fontfix.py` | 见下节 |

两个容易踩的点：

1. **限定页码范围时要先放大候选池**。BM25 先全局排序再过滤的话，范围内的好段落会被全局
   排名挤掉。`search()` 在 `page_range` 存在时把候选池放大到 400。
2. **小节标题常常独占一页，正文在下一页且不重复标题词**，单靠标题检索抓不到。所以命中后
   默认顺延取后续 2–3 块（`expand` 参数），且承接块不占 `top_k` 配额。

## PDF 字体重建（fontfix）

李重光那本 PDF 内嵌了 **656 个逐页生成的 Type1 子集字体**，数字与拉丁字母被故意打乱：

```
原文应为：以 C、D、E、F、G、A、B 七个字母命名的音
提取出来：以 ! " # $ % & ' ( 个字母命名的音
```

字体 `/Encoding` 是标准 ASCII 名（code 33 叫 `/exclam`），解密 eexec 后 CharStrings 名同样是假名，
所以任何 PDF 库都读不出来，只能靠字形形状识别。

`fontfix.py` 的做法：把每个子集字体重新插入空白页、60pt 隔离渲染 → 位图哈希归并成 170 个字形
形状 → 字形对照图人工辨认 + Base14 模板匹配双通道互证 → 建成 550 条按字体的映射表。

- 字母数字与标点：**100% 还原**
- 汉字：零损伤
- 未覆盖：音乐符号（谱号、♯♭♮、圈号、音符等），约占字形出现次数的 11%

`pdftext.extract_pages()` 会自动尝试 fontfix，并且只在「还原后字母数字更多」时采用还原结果，
对正常 PDF 无害。换一本同版本 PDF 后字体名会变，需要重跑建表流程重生成映射。

## 已知限制

- 学习进度存在浏览器 `localStorage`，换设备或清缓存会重置。
- 没有运行时 AI 生成：课程正文是静态 Markdown，要加内容走上面的生产流程。
- 引注已统一为印刷页码；若日后发现残留 PDF 页码，跑一次 `fix_citations.py` 校正。

## 关于 `_archive/`

早期版本前端请求 `/functions/v1/app/api/...`，那是 Qoder 平台运行时注入的后端，依赖一个
磁盘上并不存在的 `functions/_qoder/backend.mjs` 以及 Qoder 登录态与云数据库。GitHub Pages
是纯静态托管，没有后端，所以那套代码在仓库里永远跑不起来。

相关文件已移入 `_archive/` 并在 `.gitignore` 中排除，仅作留档，不再参与构建。

## 静态资源缓存

改了 CSS / JS 之后，把 index.html 与 detail.html 里 ssets/*.css?v=、ssets/*.js?v= 的版本号改掉（例如 ?v=20261104），否则浏览器会用旧缓存。

