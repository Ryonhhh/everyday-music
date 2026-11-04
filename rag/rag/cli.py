"""本地音乐知识库：命令行入口。"""
import argparse
import json
import os
import shutil
import sys
import time

# 让 .pylibs 里的依赖可用
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from . import config  # noqa: E402
if config.PYLIBS not in sys.path:
    sys.path.insert(0, config.PYLIBS)

from . import chunker, pdftext, store  # noqa: E402
from .search import Searcher  # noqa: E402

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass


def cmd_add(args):
    path = args.pdf
    if not os.path.isfile(path):
        print(f'找不到文件：{path}')
        return 1
    config.ensure_dirs()
    title = args.title or pdftext.book_title_guess(path)
    slug = args.slug or store.slugify(title)
    sha = store.file_sha256(path)
    conn = store.connect()
    try:
        book, created = store.add_book(
            conn, slug=slug, title=title, author=args.author, year=args.year,
            lang=args.lang, tags=args.tags, source_path=os.path.abspath(path),
            stored_path='', sha=sha,
        )
        if not created:
            print(f'已存在，跳过：{book["title"]}（slug={book["slug"]}）')
            if args.force:
                print('  --force：重新解析覆盖')
                conn.execute('DELETE FROM chunks WHERE book_id=?', (book['id'],))
            else:
                return 0
        print(f'解析 PDF：{os.path.basename(path)}')
        t0 = time.time()
        pages = pdftext.extract_pages(path)
        total_chars = sum(len(t) for _, t in pages)
        print(f'  {len(pages)} 页，{total_chars:,} 字符，{time.time()-t0:.1f}s')
        store.save_pages(conn, book['id'], pages)
        chunks = chunker.chunk_pages(pages)
        print(f'  切分 {len(chunks)} 个检索块')
        store.save_chunks(conn, book['id'], chunks)
        store.finalize_book(conn, book['id'], len(pages), len(chunks))
        conn.commit()  # 先落库：后面的文件拷贝即使失败也不该丢数据

        # 书籍副本是可选的。沙箱环境不允许覆盖已存在文件，因此失败只警告。
        stored = os.path.join(config.BOOKS_DIR, f'{slug}.pdf')
        if os.path.abspath(path) != os.path.abspath(stored):
            try:
                if os.path.exists(stored):
                    os.remove(stored)
                shutil.copy2(path, stored)
                conn.execute('UPDATE books SET stored_path=? WHERE id=?', (stored, book['id']))
                conn.commit()
            except OSError as exc:
                print(f'  [warn] 未能复制书籍副本（{exc.__class__.__name__}），源文件仍在原处')
                conn.execute('UPDATE books SET stored_path=? WHERE id=?', (os.path.abspath(path), book['id']))
                conn.commit()
        print(f'完成：{title}  →  id={book["id"]}  slug={slug}')
        return 0
    finally:
        conn.close()


def cmd_list(args):
    conn = store.connect()
    try:
        books = store.list_books(conn)
        if not books:
            print('知识库还是空的。用 `add` 添加 PDF。')
            return 0
        for b in books:
            print(f'[{b["id"]}] {b["title"]}')
            meta = ' · '.join(x for x in (b['author'], b['year'], b['tags']) if x)
            print(f'    slug={b["slug"]}  页={b["page_count"]}  块={b["chunk_count"]}  {meta}')
        return 0
    finally:
        conn.close()


def cmd_search(args):
    conn = store.connect()
    try:
        s = Searcher(conn)
        hits = s.search(args.query, top_k=args.top, book=args.book)
        if not hits:
            print('没有命中。')
            return 0
        offsets = {}
        def offset_of(book_name):
            if book_name not in offsets:
                row = store.get_book(conn, book_name)
                offsets[book_name] = store.book_page_offset(conn, row['id']) if row else 0
            return offsets[book_name]

        for i, h in enumerate(hits, 1):
            # 库里存的是 PDF 物理页；显示时换算成书上的印刷页，避免引用页码错位
            off = offset_of(h['book'])
            a, b = h['pageStart'] - off, h['pageEnd'] - off
            print(f'--- {i}. [{h["book"]}] 印刷页 p.{a}-{b}（PDF 页 {h["pageStart"]}-{h["pageEnd"]}）  score={h["score"]}')
            if getattr(args, 'full', False):
                print(h['text'])
            else:
                print('   ' + h['snippet'])
        return 0
    finally:
        conn.close()


def cmd_show(args):
    conn = store.connect()
    try:
        book = store.get_book(conn, args.book)
        if not book:
            print('找不到这本书。')
            return 1
        if args.page:
            print(f'{book["title"]} 第 {args.page} 页')
            print(store.page_text(conn, book['id'], args.page))
        else:
            rows = conn.execute('SELECT page_no,text FROM pages WHERE book_id=? ORDER BY page_no',
                                (book['id'],)).fetchall()
            for r in rows:
                print(f'\n=== p.{r["page_no"]} ===')
                print(r['text'])
        return 0
    finally:
        conn.close()


def cmd_brief(args):
    """按课程规划为每个单元检索支撑材料，输出 JSON 供内容生成使用。"""
    conn = store.connect()
    try:
        with open(args.plan, encoding='utf-8') as f:
            plan = json.load(f)
        s = Searcher(conn)
        units = plan.get('units', {})
        out = {}
        for uid, u in units.items():
            track = u.get('track')
            book = None
            if args.bind:
                bind = json.loads(args.bind) if args.bind.strip().startswith('{') else None
                if bind:
                    book = bind.get(track)
            queries = []
            if u.get('title'):
                queries.append(u['title'])
            for sec in (u.get('sections') or [])[:4]:
                queries.append(sec)
            seen, passages = set(), []
            for q in queries:
                for h in s.search(q, top_k=3, book=book, window=700):
                    if h['chunkId'] in seen:
                        continue
                    seen.add(h['chunkId'])
                    passages.append({
                        'book': h['book'], 'pageStart': h['pageStart'],
                        'pageEnd': h['pageEnd'], 'score': h['score'],
                        'query': q, 'text': h['text'],
                    })
            out[uid] = {'unit': u, 'passages': passages[:6]}
            print(f'{uid}  {u.get("title","")}  → {len(out[uid]["passages"])} 段')
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f'\n写入 {args.out}')
        return 0
    finally:
        conn.close()


def cmd_serve(args):
    from .server import serve
    serve(host=args.host, port=args.port)


def build_parser():
    p = argparse.ArgumentParser(prog='rag', description='本地音乐知识库（BM25 检索）')
    sub = p.add_subparsers(dest='cmd', required=True)

    a = sub.add_parser('add', help='添加一本 PDF')
    a.add_argument('pdf')
    a.add_argument('--title')
    a.add_argument('--author', default='')
    a.add_argument('--year', default='')
    a.add_argument('--lang', default='')
    a.add_argument('--tags', default='')
    a.add_argument('--slug')
    a.add_argument('--force', action='store_true')
    a.set_defaults(func=cmd_add)

    l = sub.add_parser('list', help='列出已入库的书')
    l.set_defaults(func=cmd_list)

    s = sub.add_parser('search', help='检索')
    s.add_argument('query')
    s.add_argument('--book', default=None)
    s.add_argument('--top', type=int, default=5)
    s.add_argument('--full', action='store_true', help='输出整块原文而不是片段')
    s.set_defaults(func=cmd_search)

    w = sub.add_parser('show', help='查看书的原文')
    w.add_argument('book')
    w.add_argument('--page', type=int, default=None)
    w.set_defaults(func=cmd_show)

    b = sub.add_parser('brief', help='按课程规划检索支撑材料')
    b.add_argument('plan')
    b.add_argument('--out', default=os.path.join(config.DATA_DIR, '_brief.json'))
    b.add_argument('--bind', default=None,
                   help='JSON：单元 track -> 书名片段，如 {"theory":"乐理","history":"Grout"}')
    b.set_defaults(func=cmd_brief)

    v = sub.add_parser('serve', help='启动本地管理界面')
    v.add_argument('--host', default='127.0.0.1')
    v.add_argument('--port', type=int, default=8765)
    v.set_defaults(func=cmd_serve)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args) or 0


if __name__ == '__main__':
    sys.exit(main())
