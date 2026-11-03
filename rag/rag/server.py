"""本地知识库管理界面（无第三方依赖，只用标准库）。

启动：python rag/run.py serve
打开：http://127.0.0.1:8765

功能：上传新书（拖拽或选择 PDF）、查看书库、全文检索、按页看原文。
"""
import json
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config, store
from .ingest import ingest_path
from .search import Searcher

_MAX_UPLOAD = 400 * 1024 * 1024  # 400 MB

_lock = threading.Lock()
_cache = {'searcher': None}


def get_searcher():
    with _lock:
        if _cache['searcher'] is None:
            conn = store.connect()
            try:
                _cache['searcher'] = Searcher(conn)
            finally:
                conn.close()
        return _cache['searcher']


def invalidate():
    with _lock:
        _cache['searcher'] = None


PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>本地音乐知识库</title>
<style>
  :root { --ink:#1f201d; --muted:#6f6f6c; --line:#eaeaea; --surf:#f9f9f9; --accent:#b45309; }
  * { box-sizing: border-box; }
  body { margin:0; font: 14px/1.6 "Instrument Sans", -apple-system, "Segoe UI", system-ui, sans-serif;
         color:var(--ink); background:#fff; }
  .wrap { max-width: 900px; margin: 0 auto; padding: 40px 24px 80px; }
  h1 { font-size: 24px; font-weight: 600; margin: 0 0 6px; }
  .sub { color: var(--muted); font-size: 13px; margin-bottom: 32px; }
  h2 { font-size: 15px; font-weight: 600; margin: 36px 0 12px; padding-bottom: 8px; border-bottom: 1px solid var(--line); }
  .drop { border: 1.5px dashed #d9d9d6; border-radius: 14px; padding: 28px; text-align: center;
          color: var(--muted); background: var(--surf); cursor: pointer; transition: .15s; }
  .drop.on { border-color: var(--accent); background: #fffaf3; color: var(--accent); }
  .drop strong { color: var(--ink); }
  .fields { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 12px; }
  .fields input, .search input { width: 100%; padding: 9px 12px; border: 1px solid var(--line);
          border-radius: 8px; font: inherit; font-size: 13px; }
  .row-btn { display: flex; gap: 10px; margin-top: 12px; align-items: center; }
  button { padding: 9px 20px; border: none; border-radius: 999px; background: var(--ink); color: #fff;
           font: inherit; font-size: 13px; cursor: pointer; }
  button:disabled { background: #d9d9d6; cursor: default; }
  button.ghost { background: var(--surf); color: var(--ink); border: 1px solid var(--line); }
  .search { display: flex; gap: 10px; }
  .book { padding: 12px 0; border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; gap: 16px; }
  .book b { font-weight: 600; }
  .meta { color: var(--muted); font-size: 12px; }
  .hit { padding: 14px 0; border-bottom: 1px solid var(--line); }
  .hit .src { color: var(--accent); font-size: 12px; margin-bottom: 4px; }
  .hit p { margin: 0; font-size: 13px; color: #3d3d3a; }
  .status { margin-top: 12px; font-size: 13px; color: var(--muted); min-height: 20px; white-space: pre-wrap; }
  .status.err { color: #b42318; }
  code { background: var(--surf); padding: 1px 5px; border-radius: 4px; font-size: 12px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>本地音乐知识库</h1>
  <div class="sub">书库只存在这台电脑上。网站发布到 GitHub 时不会带上书籍原文。</div>

  <h2>添加新书</h2>
  <div class="drop" id="drop">
    把 PDF 拖到这里，或<strong>点击选择文件</strong>
  </div>
  <input type="file" id="file" accept="application/pdf" hidden>
  <div class="fields">
    <input id="title" placeholder="书名（留空则用文件名）">
    <input id="author" placeholder="作者">
  </div>
  <div class="fields">
    <input id="tags" placeholder="标签，如：乐理,教材">
    <input id="lang" placeholder="语言，如：zh / en">
  </div>
  <div class="row-btn">
    <button id="go" disabled>解析并入库</button>
    <span class="status" id="upStatus"></span>
  </div>

  <h2>书库</h2>
  <div id="books"><div class="meta">读取中…</div></div>

  <h2>全文检索</h2>
  <div class="search">
    <input id="q" placeholder="例如：五度相生律 / Notre Dame organum">
    <button id="searchBtn">检索</button>
  </div>
  <div id="hits"></div>
</div>
<script>
const $ = id => document.getElementById(id);
let picked = null;

const drop = $('drop'), fileInput = $('file'), go = $('go');
drop.addEventListener('click', () => fileInput.click());
drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('on'); });
drop.addEventListener('dragleave', () => drop.classList.remove('on'));
drop.addEventListener('drop', e => {
  e.preventDefault(); drop.classList.remove('on');
  if (e.dataTransfer.files.length) pick(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => { if (fileInput.files.length) pick(fileInput.files[0]); });

function pick(f) {
  picked = f;
  drop.innerHTML = '已选择：<strong>' + f.name + '</strong>（' + (f.size / 1048576).toFixed(1) + ' MB）';
  if (!$('title').value) $('title').value = f.name.replace(/\\.pdf$/i, '');
  go.disabled = false;
}

go.addEventListener('click', async () => {
  if (!picked) return;
  go.disabled = true;
  $('upStatus').className = 'status';
  $('upStatus').textContent = '正在上传…';
  const qs = new URLSearchParams({
    name: picked.name,
    title: $('title').value || '',
    author: $('author').value || '',
    tags: $('tags').value || '',
    lang: $('lang').value || '',
  });
  try {
    const res = await fetch('/api/upload?' + qs, { method: 'POST', body: picked });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
    $('upStatus').textContent = data.message;
    picked = null;
    fileInput.value = '';
    drop.innerHTML = '把 PDF 拖到这里，或<strong>点击选择文件</strong>';
    loadBooks();
  } catch (err) {
    $('upStatus').className = 'status err';
    $('upStatus').textContent = '失败：' + err.message;
  } finally {
    go.disabled = !picked;
  }
});

async function loadBooks() {
  const res = await fetch('/api/books');
  const data = await res.json();
  const el = $('books');
  if (!data.books.length) { el.innerHTML = '<div class="meta">书库还是空的，先添加一本书。</div>'; return; }
  el.innerHTML = data.books.map(b => `
    <div class="book">
      <div>
        <b>${b.title}</b>
        <div class="meta">${[b.author, b.year, b.tags].filter(Boolean).join(' · ') || '—'}</div>
      </div>
      <div class="meta">${b.pageCount} 页 · ${b.chunkCount} 段</div>
    </div>`).join('');
}

async function doSearch() {
  const q = $('q').value.trim();
  if (!q) return;
  const res = await fetch('/api/search?q=' + encodeURIComponent(q));
  const data = await res.json();
  const el = $('hits');
  if (!data.hits.length) { el.innerHTML = '<div class="meta" style="margin-top:12px">没有命中。</div>'; return; }
  el.innerHTML = data.hits.map(h => `
    <div class="hit">
      <div class="src">${h.book} · p.${h.pageStart}–${h.pageEnd} · ${h.score}</div>
      <p>${h.snippet.replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}</p>
    </div>`).join('');
}

$('searchBtn').addEventListener('click', doSearch);
$('q').addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });
loadBooks();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = 'MusicRAG/1.0'

    def log_message(self, fmt, *args):
        print(f'  {self.address_string()}  {fmt % args}')

    # ---------- 响应助手 ----------
    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        raw = body.encode('utf-8') if isinstance(body, str) else body
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(raw)

    def _json(self, payload, code=200):
        self._send(code, payload)

    def _query(self):
        parsed = urllib.parse.urlparse(self.path)
        return parsed.path, urllib.parse.parse_qs(parsed.query)

    # ---------- GET ----------
    def do_GET(self):
        path, qs = self._query()
        try:
            if path in ('/', '/index.html'):
                self._send(200, PAGE, 'text/html; charset=utf-8')
            elif path == '/api/books':
                conn = store.connect()
                try:
                    rows = store.list_books(conn)
                    books = [{
                        'id': r['id'], 'title': r['title'], 'author': r['author'],
                        'year': r['year'], 'tags': r['tags'],
                        'pageCount': r['page_count'], 'chunkCount': r['chunk_count'],
                    } for r in rows]
                finally:
                    conn.close()
                self._json({'books': books})
            elif path == '/api/search':
                q = (qs.get('q') or [''])[0].strip()
                book = (qs.get('book') or [None])[0]
                if not q:
                    return self._json({'hits': []})
                hits = get_searcher().search(q, top_k=8, book=book)
                for h in hits:
                    h.pop('text', None)
                self._json({'hits': hits})
            elif path == '/api/page':
                ident = (qs.get('book') or [''])[0]
                page_no = int((qs.get('page') or ['0'])[0] or 0)
                conn = store.connect()
                try:
                    b = store.get_book(conn, ident)
                    if not b:
                        return self._json({'error': 'book not found'}, 404)
                    text = store.page_text(conn, b['id'], page_no)
                finally:
                    conn.close()
                self._json({'title': b['title'], 'page': page_no, 'text': text})
            else:
                self._json({'error': 'not found'}, 404)
        except Exception as exc:
            self._json({'error': f'{type(exc).__name__}: {exc}'}, 500)

    # ---------- POST ----------
    def do_POST(self):
        path, qs = self._query()
        if path != '/api/upload':
            return self._json({'error': 'not found'}, 404)

        name = (qs.get('name') or ['upload.pdf'])[0]
        safe = os.path.basename(name).replace('\\', '_').replace('/', '_')
        if not safe.lower().endswith('.pdf'):
            safe += '.pdf'
        length = int(self.headers.get('Content-Length') or 0)
        if length <= 0:
            return self._json({'error': '没有收到文件内容'}, 400)
        if length > _MAX_UPLOAD:
            return self._json({'error': '文件超过 400 MB'}, 413)

        config.ensure_dirs()
        incoming = os.path.join(config.BOOKS_DIR, '_incoming')
        os.makedirs(incoming, exist_ok=True)
        tmp = os.path.join(incoming, safe)
        try:
            with open(tmp, 'wb') as f:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(1 << 20, remaining))
                    if not chunk:
                        break
                    f.write(chunk)
                    remaining -= len(chunk)
            logs = []
            book, created = ingest_path(
                tmp,
                title=(qs.get('title') or [''])[0] or None,
                author=(qs.get('author') or [''])[0],
                tags=(qs.get('tags') or [''])[0],
                lang=(qs.get('lang') or [''])[0],
                force=True,
                copy_into_library=False,
                log=lambda m: logs.append(str(m)),
            )
            invalidate()
            # ingest 里已经提交，这里再读一次拿到最新的页数/块数
            conn = store.connect()
            try:
                fresh = store.get_book(conn, book['id'])
            finally:
                conn.close()
            verb = '已入库' if created else '已更新'
            self._json({
                'ok': True,
                'book': {'id': fresh['id'], 'title': fresh['title']},
                'message': (f'{verb}：{fresh["title"]}'
                            f'（{fresh["page_count"]} 页 / {fresh["chunk_count"]} 段）\n'
                            + '\n'.join(logs)),
            })
        except Exception as exc:
            self._json({'error': f'{type(exc).__name__}: {exc}'}, 500)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass


def serve(host='127.0.0.1', port=8765):
    config.ensure_dirs()
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f'http://{host}:{port}'
    print(f'本地知识库已启动：{url}')
    print('按 Ctrl+C 停止。')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止。')
    finally:
        httpd.server_close()
