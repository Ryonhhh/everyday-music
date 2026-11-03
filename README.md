# 每日音乐学习

一个 36 天的音乐自学课程站。底本是两本书：

- 李重光《基本乐理通用教材》（26 个乐理单元）
- Donald Jay Grout & Claude V. Palisca, *A History of Western Music*, 4th ed.（36 个音乐史单元）

网站是**纯静态**的：没有服务器、没有数据库、没有登录。课程正文提前写好，随仓库一起发布。
书籍全文检索在**本地**运行，书籍原文不会上传到 GitHub。

---

## 为什么以前跑不起来

旧版本的前端把所有数据请求都发往 `/functions/v1/app/api/...`，那是 Qoder 平台**运行时注入**的后端，
依赖一个磁盘上并不存在的 `functions/_qoder/backend.mjs`，还依赖 Qoder 的登录态和云数据库。
GitHub Pages 是纯静态托管，没有任何后端，所以这套代码在那里**永远**跑不起来——不是样式问题。

现在这些已全部移到 `_archive/`（不入库），前端只读 `data/*.json` 与 `data/**/*.md`。

---

## 目录结构

```
index.html              首页（今日学习 / 课程目录 / 专辑解析 / 资料库）
detail.html             课程与专辑详情页
assets/
  core.js               工具：转义、日期、Markdown 渲染、乐谱进度图、本地进度
  app.js                页面逻辑（读 data/，无任何后端调用）
  app.css / site.css    设计系统
  site-extra.css        补齐列表行等缺失样式
data/
  curriculum.json       36 天课程表（由 tools/build_curriculum.py 生成）
  lessons/index.json    已生成课文的清单
  lessons/day-01.md …   课程正文（Markdown）
  albums/index.json     专辑清单
  albums/*.md           专辑解析
curriculum/plan.json    课程规划（唯一人工维护的课程结构来源）
rag/                    本地知识库（不入库）
  run.py                命令行入口
  rag/                  Python 包：解析、切块、BM25 检索、字体修复、本地服务
  db/rag.db             SQLite 知识库（不入库）
tools/                  构建与辅助脚本
_archive/               已废弃的 Qoder 后端（不入库）
```

---

## 本地预览

必须用 HTTP 服务器打开，不能用 `file://` 直接双击（浏览器不允许读取本地 JSON）。

```powershell
python -m http.server 8777 --directory "G:\music everyday"
```

然后访问 <http://127.0.0.1:8777/>。

---

## 本地知识库（RAG）

### 给新书入库

两种方式，效果相同。

**方式一：命令行**

```powershell
python rag/run.py add "新书.pdf" --title "书名" --author "作者" --tags "乐理,教材" --lang zh
```

**方式二：网页上传（拖拽即可）**

```powershell
python rag/run.py serve
```

打开 <http://127.0.0.1:8765>，把 PDF 拖进虚线框，填书名/作者后点「解析并入库」。

入库会做四件事：解析 PDF → 按语义切块 → 建立 BM25 索引 → 写入 `rag/db/rag.db`。
以后再添加新书，重复这一步即可，网页不需要改。

### 检索

```powershell
python rag/run.py list                      # 书库
python rag/run.py search "五度相生律"        # 检索，返回片段与页码
python rag/run.py search "Notre Dame organum" --book Grout
python rag/run.py show 基本乐理 --page 20    # 看某一页原文
```

检索是中文友好的：汉字取单字 + 相邻二元组，英文取整词，BM25 打分。
不依赖 jieba 之类的分词器，术语（「五度相生律」）能被精确命中。

---

## 写一篇新课程

1. 取出该天对应单元的原文材料：

```powershell
python tools/unit_context.py T02 H02 --out ".tmp\ctx-day02.txt" --per 2
```

   英文教材的章节标题是中英混写，脚本会自动只保留英文部分检索，并按
   `plan.json` 里的页码区间（如 `p.1-41`）限定范围。

2. 照着 `data/lessons/day-01.md` 的结构写 `data/lessons/day-02.md`
   （乐理 + 音乐史 + 今日练习 + 今日思考 + 今日小结 + 参考出处）。

3. 重建清单：

```powershell
python tools/build_lessons_index.py
```

4. 提交发布。

---

## 发布到 GitHub Pages

1. 新建一个 GitHub 仓库（public 即可）。
2. 推送本仓库：

```powershell
git init
git add .
git commit -m "静态站 + 本地 RAG 知识库"
git branch -M main
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

3. 仓库 → Settings → Pages → Source 选 **Deploy from a branch**，分支 `main`，目录 `/ (root)`，保存。
4. 一两分钟后访问 `https://<你的用户名>.github.io/<仓库名>/`。

仓库根目录已有 `.nojekyll`，首页、详情页与 `data/` 都是相对路径，因此放在项目子路径下（`/仓库名/`）也能正常工作。

**注意**：`.gitignore` 已排除 `*.pdf`、`rag/books/`、`rag/db/`，书籍原文不会进入仓库。
课程正文里对原文的引用以「书名 + 页码」标注，不复制大段原文。

---

## 已知限制

- **乐理书的字体问题**：该 PDF 内嵌了 656 个逐页生成的 Type1 子集字体，数字与拉丁字母被故意打乱
  （`音分值为*))` 其实是 `音分值为700`）。`rag/rag/fontfix.py` 通过字形识别重建了 550 条映射，
  字母数字已 100% 还原，汉字零损伤。
  余下的音乐符号（谱号、♯♭♮、圈号、音符等，约占字形出现次数的 11%）仍未映射。
- **进度只存在本机**：学习进度保存在浏览器 `localStorage`，换设备或清缓存会重置。
- **没有运行时 AI 生成**：课程正文是提前写好的静态文件。要加新内容，按上面「写一篇新课程」的流程走。
