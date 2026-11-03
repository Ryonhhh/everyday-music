"""把 curriculum/plan.json 编译成静态站可直接读取的 data/curriculum.json。

运行：python tools/build_curriculum.py
"""
import json
import os
import sqlite3
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAN = os.path.join(ROOT, 'curriculum', 'plan.json')
DB = os.path.join(ROOT, 'rag', 'db', 'rag.db')
OUT = os.path.join(ROOT, 'data', 'curriculum.json')

# plan.json 的 book id -> 书本展示信息
BOOK_META = {
    'theory': {
        'slug': '基本乐理通用教材',
        'subtitle': 'Basic Music Theory',
        'note': '中文教材，按「讲」组织，共 16 讲',
        'label': '李重光《基本乐理通用教材》',
    },
    'history': {
        'slug': 'western-music-history',
        'subtitle': 'A History of Western Music',
        'note': '英文教材，4th Edition，20 章',
        'label': 'Grout & Palisca《西方音乐史》',
    },
}


def book_stats():
    """从 RAG 库里读每本书的页数/块数，读不到就留空。"""
    stats = {}
    if not os.path.exists(DB):
        return stats
    try:
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        for row in conn.execute('SELECT * FROM books'):
            for key, meta in BOOK_META.items():
                if row['slug'] == meta['slug']:
                    stats[key] = {
                        'pages': row['page_count'],
                        'chunks': row['chunk_count'],
                    }
        conn.close()
    except Exception as exc:  # 库还没建好时不应阻塞构建
        print(f'[warn] 读取 RAG 库失败：{exc}', file=sys.stderr)
    return stats


def main():
    with open(PLAN, encoding='utf-8') as f:
        plan = json.load(f)

    units = plan.get('units', {})
    days_raw = plan.get('days', [])
    stats = book_stats()

    books = []
    for b in plan.get('books', []):
        bid = b['id']
        meta = BOOK_META.get(bid, {})
        entry = {
            'id': bid,
            'title': b['title'],
            'author': b['author'],
            'publisher': b.get('publisher', ''),
            'totalUnits': b.get('totalUnits', 0),
            'structure': b.get('structure', ''),
            'subtitle': meta.get('subtitle', ''),
            'note': meta.get('note', ''),
            'label': meta.get('label', b['title']),
        }
        entry.update(stats.get(bid, {}))
        books.append(entry)

    day_map = {}
    for d in days_raw:
        unit_ids = []
        for track in ('theory', 'history'):
            uid = d.get(track)
            if uid:
                unit_ids.append(uid)
        day_map[d['day']] = unit_ids

    days = []
    for day_no in sorted(day_map):
        resolved = []
        for uid in day_map[day_no]:
            u = units.get(uid)
            if not u:
                continue
            track = u.get('track', 'theory')
            book = next((b for b in books if b['id'] == track), None)
            resolved.append({
                'id': uid,
                'track': track,
                'title': u.get('title', ''),
                'book': book['title'] if book else '',
                'source': {
                    'lecture': u.get('lecture', ''),
                    'chapter': u.get('chapter', ''),
                    'sections': u.get('sections', []),
                },
            })
        days.append({'day': day_no, 'units': resolved})

    counts = {'theory': 0, 'history': 0}
    for u in units.values():
        t = u.get('track')
        if t in counts:
            counts[t] += 1

    payload = {
        'title': '每日音乐学习',
        'generatedAt': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'totalDays': len(days),
        'tracks': counts,
        'scheduleNote': plan.get('scheduleNote', ''),
        'books': books,
        'days': days,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f'写入 {OUT}')
    print(f'  天数 {len(days)}  乐理单元 {counts["theory"]}  音乐史单元 {counts["history"]}')
    for b in books:
        extra = f'  页={b.get("pages")} 块={b.get("chunks")}' if b.get('pages') else '  （尚未入库）'
        print(f'  · {b["title"]} — {b["author"]}{extra}')


if __name__ == '__main__':
    main()
