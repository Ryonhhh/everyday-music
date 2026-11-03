"""取出指定单元的检索原文，供写课程正文用。

用法：
  python tools/unit_context.py T01 H01 --out .tmp/ctx.txt
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'rag'))
sys.path.insert(0, os.path.join(ROOT, 'rag', '.pylibs'))

from rag import store  # noqa: E402
from rag.search import Searcher  # noqa: E402

TRACK_BOOK = {'theory': '基本乐理通用教材', 'history': 'western-music-history'}
CJK_RUN = re.compile(r'[\u4e00-\u9fff：，、；！？“”‘’（）]+')
PAGES = re.compile(r'p\.\s*(\d+)\s*[-–]\s*(\d+)')


def clean_query(q, english_book):
    """章节标题常是中英混写；在英文书里检索要把中文部分去掉，否则打分被稀释。"""
    q = q or ''
    if english_book:
        q = re.sub(r'（[^）]*）|\([^)]*\)', ' ', q)
        q = CJK_RUN.sub(' ', q)
    else:
        q = re.sub(r'\([A-Za-z][^)]*\)', ' ', q)
    return re.sub(r'\s{2,}', ' ', q).strip()


def page_range_of(unit):
    m = PAGES.search(unit.get('chapter') or '')
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    return (a, b) if a <= b else (b, a)


def resolve_book_id(conn, track):
    """track -> books.id；找不到返回 None（此时不按书过滤）。"""
    needle = TRACK_BOOK.get(track)
    if not needle:
        return None
    row = store.get_book(conn, needle)
    return row['id'] if row else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('units', nargs='+')
    ap.add_argument('--plan', default=os.path.join(ROOT, 'curriculum', 'plan.json'))
    ap.add_argument('--out', default=os.path.join(ROOT, '.tmp', 'ctx.txt'))
    ap.add_argument('--per', type=int, default=3, help='每个查询取几段')
    ap.add_argument('--digest', action='store_true',
                    help='精简模式：每条截断到 900 字、每单元最多 6 段，便于快速写作')
    args = ap.parse_args()

    with open(args.plan, encoding='utf-8') as f:
        plan = json.load(f)
    units = plan['units']

    conn = store.connect()
    s = Searcher(conn)
    lines = []
    for uid in args.units:
        u = units.get(uid)
        if not u:
            lines.append(f'!! 未找到单元 {uid}')
            continue
        track = u.get('track')
        book = TRACK_BOOK.get(track)
        english = track == 'history'
        printed = page_range_of(u)
        book_id = resolve_book_id(conn, track)
        offset = store.book_page_offset(conn, book_id) if book_id else 0
        prange = (printed[0] + offset, printed[1] + offset) if printed else None
        lines.append('=' * 78)
        lines.append(f'单元 {uid}  [{track}]  {u.get("title", "")}')
        if u.get('lecture'):
            lines.append(f'讲次：{u["lecture"]}')
        if u.get('chapter'):
            lines.append(f'章节：{u["chapter"]}')
        if printed:
            lines.append(f'印刷页码 p.{printed[0]}-{printed[1]}'
                         f'（物理页偏移 +{offset} → 检索范围 p.{prange[0]}-{prange[1]}）')
        for sec in u.get('sections') or []:
            lines.append(f'  · {sec}')

        raw_queries = [u.get('title', '')] + list(u.get('sections') or [])
        queries = []
        for q in raw_queries:
            cq = clean_query(q, english)
            if cq and cq not in queries:
                queries.append(cq)

        seen = set()
        unit_passages = 0
        for q in queries:
            if args.digest and unit_passages >= 6:
                break
            hits = s.search(q, top_k=args.per, book=book, window=10000,
                            page_range=prange, expand=3)
            if not hits:
                # 页码范围太窄时退化为全书检索，避免空手而归
                hits = s.search(q, top_k=args.per, book=book, window=10000, expand=3)
            for h in hits:
                if h['chunkId'] in seen:
                    continue
                if args.digest and unit_passages >= 6:
                    break
                seen.add(h['chunkId'])
                unit_passages += 1
                tag = '（承接上文）' if h.get('follower') else ''
                lines.append('')
                pp = f'{h["pageStart"] - offset}-{h["pageEnd"] - offset}'
                lines.append(f'--- 检索「{q}」{tag} → {h["book"]} '
                             f'印刷页 p.{pp}（PDF 页 {h["pageStart"]}-{h["pageEnd"]}）'
                             f' (score {h["score"]})')
                body = h['text']
                if args.digest and len(body) > 900:
                    body = body[:900] + '……'
                lines.append(body)
    conn.close()

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'写入 {args.out}  ({len(lines)} 行)')


if __name__ == '__main__':
    main()
