"""把 Open Music Theory（CC BY-SA 4.0，网页版教材）抓成本地知识库的一本书。

这本书没有印刷页码，因此「页」= 章节序号：检索结果显示的是章节名，不是 p.X。
用法：python tools/ingest_omt.py [--limit N]
"""
import argparse
import html
import os
import re
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'rag'))
sys.path.insert(0, os.path.join(ROOT, 'rag', '.pylibs'))

from rag import chunker, store  # noqa: E402

BASE = 'https://openmusictheory.github.io/'
UA = {'User-Agent': 'Mozilla/5.0 (music-everyday local study ingest)'}
SLUG = 'open-music-theory'


def fetch(url, tries=3, timeout=40):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception as exc:
            last = exc
            time.sleep(2 + i * 2)
    raise last


def html_to_text(raw):
    # 只取正文容器，避免把导航与页脚吃进来
    m = re.search(r'(?is)<article[^>]*>(.*?)</article>', raw)
    body = m.group(1) if m else raw
    s = re.sub(r'(?is)<(script|style|nav|footer|header|aside)[^>]*>.*?</\1>', ' ', body)
    # 标题保留层级
    s = re.sub(r'(?is)<h([1-4])[^>]*>(.*?)</h\1>', lambda m: '\n\n' + '#' * int(m.group(1)) + ' ' + re.sub(r'<[^>]+>', '', m.group(2)).strip() + '\n\n', s)
    s = re.sub(r'(?is)<li[^>]*>', '\n- ', s)
    s = re.sub(r'(?is)<(p|div|br|tr|section|article)[^>]*>', '\n', s)
    s = re.sub(r'(?s)<[^>]+>', ' ', s)
    s = html.unescape(s)
    s = re.sub(r'[ \t\u00a0]+', ' ', s)
    s = re.sub(r'\n\s*\n\s*\n+', '\n\n', s)
    # 去掉页尾的分享/面包屑碎片
    s = re.sub(r'(?m)^\s*-(\s*-)*\s*$', '', s)
    s = re.sub(r'(?m)^\s*Share\s*$', '', s)
    s = re.sub(r'《[^》]{1,80}》[^\n]{0,80}Open Music Theory[^\n]*', '', s)
    return s.strip()


def chapter_links(contents_html):
    """从目录页取出章节链接（同站 .html），保留顺序。"""
    out, seen = [], set()
    for m in re.finditer(r'href="([^"#:]+\.html)"[^>]*>(.*?)</a>', contents_html, re.I | re.S):
        href, label = m.group(1), re.sub(r'<[^>]+>', '', m.group(2))
        label = html.unescape(label).strip()
        if not label or href in seen or href.startswith('http'):
            continue
        if href in ('about.html', 'contents.html', 'index.html'):
            continue
        seen.add(href)
        out.append((href, label))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0, help='只抓前 N 章（调试用）')
    args = ap.parse_args()

    print('抓取目录…')
    contents = fetch(BASE + 'contents.html')
    links = chapter_links(contents)
    if args.limit:
        links = links[:args.limit]
    print(f'共 {len(links)} 章')

    pages = []
    for i, (href, label) in enumerate(links, 1):
        try:
            raw = fetch(BASE + href)
            text = html_to_text(raw)
            # 去掉每页重复的导航尾巴
            text = re.split(r'\nShare\n', text)[0]
            if len(text) < 300:
                print(f'  [{i:02d}] 跳过（内容过短）{label}')
                continue
            pages.append((len(pages) + 1, f'《{label}》\n\n{text}'))
            print(f'  [{len(pages):02d}] {label}  {len(text)} 字')
        except Exception as exc:
            print(f'  [!] {label} 失败：{exc}')
        time.sleep(0.3)

    if not pages:
        print('没有抓到任何章节，终止。')
        return 1

    conn = store.connect()
    try:
        book, created = store.add_book(
            conn, slug=SLUG, title='Open Music Theory', author='Kris Shaffer、Bryn Hughes、Brian Moseley 等',
            year='2022', lang='en', tags='乐理,和声,曲式,开放教材,无页码',
            source_path=BASE, stored_path='', sha='omt-web',
        )
        if not created:
            # 重新抓取时先清掉旧页与旧块，避免版本混杂
            conn.execute('DELETE FROM chunks WHERE book_id=?', (book['id'],))
            conn.execute('DELETE FROM pages WHERE book_id=?', (book['id'],))
            conn.execute(
                'UPDATE books SET author=?, year=?, tags=?, source_path=? WHERE id=?',
                ('Kris Shaffer、Bryn Hughes、Brian Moseley 等', '2022',
                 '乐理,和声,曲式,开放教材,无页码', BASE, book['id']),
            )
        store.save_pages(conn, book['id'], pages)
        chunks = chunker.chunk_pages(pages)
        store.save_chunks(conn, book['id'], chunks)
        store.finalize_book(conn, book['id'], len(pages), len(chunks))
        conn.commit()
        print(f'入库完成：id={book["id"]}  {len(pages)} 节  {len(chunks)} 块')
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
