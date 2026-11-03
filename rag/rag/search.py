"""检索层：把 chunks 装进 BM25，并提供带上下文的片段。"""
import re

from .bm25 import BM25, tokenize
from . import store


class Searcher:
    def __init__(self, conn):
        self.conn = conn
        rows = store.all_chunks(conn)
        self.rows = rows
        self.by_id = {r['id']: r for r in rows}
        self.by_ord = {(r['book_id'], r['ord']): r for r in rows}
        docs = [{'id': r['id'], 'text': r['text']} for r in rows]
        self.bm25 = BM25(docs)

    def _neighbors(self, row, n):
        """命中块之后的 n 块。

        小节标题常常单独一页，正文在下一页，且不会重复标题词，
        单靠标题检索抓不到；顺延取相邻块能补上。
        """
        out = []
        for step in range(1, n + 1):
            nb = self.by_ord.get((row['book_id'], row['ord'] + step))
            if nb is not None:
                out.append(nb)
        return out

    def search(self, query, top_k=8, book=None, window=320, page_range=None, expand=0):
        # 限定页码时必须先放宽候选，否则范围内的好段落会被全局排序挤掉
        pool = max(top_k * 40, 400) if page_range else max(top_k * 6, 24)
        hits = self.bm25.search(query, top_k=pool)
        out = []
        q_terms = [t for t in tokenize(query) if len(t) >= 2]
        taken_pages = []
        seen_ids = set()
        scored = 0  # 只统计真正命中的块；承接块不占 top_k 配额
        pmin = pmax = None
        if page_range:
            pmin, pmax = page_range
        for cid, score in hits:
            row = self.by_id.get(cid)
            if row is None:
                continue
            if pmin is not None and not (row['page_start'] <= pmax and row['page_end'] >= pmin):
                continue
            if book and not _book_matches(self.conn, row, book):
                continue
            # 跳过与已选中结果页码重叠的块（分块有重叠，否则同一段会被重复列出）
            span = (row['book_slug'], row['page_start'], row['page_end'])
            if any(_overlaps(span, t) for t in taken_pages):
                continue
            taken_pages.append(span)
            seen_ids.add(row['id'])
            scored += 1
            out.append({
                'chunkId': row['id'],
                'book': row['book_title'],
                'bookSlug': row['book_slug'],
                'pageStart': row['page_start'],
                'pageEnd': row['page_end'],
                'score': round(score, 3),
                'snippet': make_snippet(row['text'], q_terms, window),
                'text': row['text'],
            })
            if expand:
                for nb in self._neighbors(row, expand):
                    if nb['id'] in seen_ids:
                        continue
                    # 承接块若与已选块页码重叠，说明那几页已经在上下文里了，
                    # 再加一份只会让材料变长、拖慢阅读，跳过
                    nb_span = (nb['book_slug'], nb['page_start'], nb['page_end'])
                    if any(_overlaps(nb_span, t) for t in taken_pages):
                        continue
                    seen_ids.add(nb['id'])
                    taken_pages.append(nb_span)
                    out.append({
                        'chunkId': nb['id'],
                        'book': nb['book_title'],
                        'bookSlug': nb['book_slug'],
                        'pageStart': nb['page_start'],
                        'pageEnd': nb['page_end'],
                        'score': 0.0,
                        'snippet': make_snippet(nb['text'], q_terms, window),
                        'text': nb['text'],
                        'follower': True,
                    })
            if scored >= top_k:
                break
        return out

    def chunk_at(self, book_id, page_no):
        row = self.conn.execute(
            'SELECT * FROM chunks WHERE book_id=? AND page_start<=? AND page_end>=?'
            ' ORDER BY ord LIMIT 1', (book_id, page_no, page_no)).fetchone()
        return row


def _book_matches(conn, row, book):
    """书名过滤：slug / 标题 / 作者 任一命中即可（不区分大小写）。"""
    needle = book.lower()
    if needle in (row['book_slug'] or '').lower():
        return True
    if needle in (row['book_title'] or '').lower():
        return True
    meta = conn.execute('SELECT author FROM books WHERE id=?', (row['book_id'],)).fetchone()
    if meta and needle in (meta['author'] or '').lower():
        return True
    return False


def _overlaps(a, b):
    """两个 (slug, page_start, page_end) 是否来自同一本书且页码重叠。"""
    if a[0] != b[0]:
        return False
    return not (a[2] < b[1] or b[2] < a[1])


def make_snippet(text, terms, window=320):
    """在 text 里找命中词最密集的窗口。"""
    if not text:
        return ''
    if not terms:
        return text[:window].replace('\n', ' ')
    flat = re.sub(r'\s+', ' ', text)
    best_pos, best_hits = 0, -1
    step = max(window // 4, 1)
    for start in range(0, max(len(flat) - window, 0) + 1, step):
        seg = flat[start:start + window].lower()
        hits = sum(seg.count(t.lower()) for t in terms)
        if hits > best_hits:
            best_hits, best_pos = hits, start
    seg = flat[best_pos:best_pos + window]
    prefix = '…' if best_pos > 0 else ''
    suffix = '…' if best_pos + window < len(flat) else ''
    return prefix + seg.strip() + suffix
