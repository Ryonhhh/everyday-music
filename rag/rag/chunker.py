"""把页面文本切成语义块（chunk）。"""
from . import config


def chunk_pages(pages, chunk_chars=None, overlap=None):
    """pages: [(page_no, text)] -> [(ord, page_start, page_end, text)]

    以段落为单位累积到目标字数，跨页时记录起止页；块间保留少量重叠
    以便检索命中后仍有上下文。
    """
    chunk_chars = chunk_chars or config.CHUNK_CHARS
    overlap = overlap or config.CHUNK_OVERLAP

    # 先展开为 (page_no, paragraph) 列表
    paras = []
    for page_no, text in pages:
        if not text:
            continue
        for block in text.split('\n\n'):
            block = block.strip()
            if not block:
                continue
            paras.append((page_no, block))

    chunks = []
    buf, buf_pages, buf_len = [], [], 0

    def flush():
        nonlocal buf, buf_pages, buf_len
        if not buf:
            return
        body = '\n\n'.join(buf).strip()
        if len(body) >= config.MIN_CHUNK_CHARS:
            chunks.append((
                len(chunks),
                buf_pages[0],
                buf_pages[-1],
                body,
            ))
        # 重叠：保留尾部若干段
        tail, tail_len = [], 0
        for piece in reversed(buf):
            if tail_len >= overlap:
                break
            tail.insert(0, piece)
            tail_len += len(piece)
        buf = tail[:]
        buf_len = sum(len(p) for p in buf)
        buf_pages = buf_pages[-1:] if buf_pages else []

    for page_no, block in paras:
        if len(block) > chunk_chars * 2:
            # 超长段落（如整章无空行）按句切分
            for frag in _split_sentences(block, chunk_chars):
                if buf_len + len(frag) > chunk_chars and buf:
                    flush()
                if not buf_pages or buf_pages[-1] != page_no:
                    buf_pages.append(page_no)
                buf.append(frag)
                buf_len += len(frag)
            continue
        if buf_len + len(block) > chunk_chars and buf:
            flush()
        if not buf_pages or buf_pages[-1] != page_no:
            buf_pages.append(page_no)
        buf.append(block)
        buf_len += len(block)

    flush()
    return chunks


def _split_sentences(text, limit):
    ends = '。！？.!?'
    out, cur = [], ''
    for ch in text:
        cur += ch
        if ch in ends and len(cur) >= limit * 0.6:
            out.append(cur.strip())
            cur = ''
    if cur.strip():
        out.append(cur.strip())
    if not out:
        return [text]
    # 再按长度硬切
    fixed = []
    for piece in out:
        while len(piece) > limit:
            fixed.append(piece[:limit])
            piece = piece[limit:]
        if piece:
            fixed.append(piece)
    return fixed
