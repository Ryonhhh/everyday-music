"""PDF 文字提取与规范化。"""
import re
import sys

from . import config


def _ensure_pymupdf():
    if config.PYLIBS not in sys.path:
        sys.path.insert(0, config.PYLIBS)
    import pymupdf
    return pymupdf


# 连字符断行：word-\nword -> word
_HYPHEN_BREAK = re.compile(r'([A-Za-z])-\n([a-z])')
# 多余的空白
_SPACES = re.compile(r'[ \t\u00a0\u3000]+')


def normalize(text):
    if not text:
        return ''
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = _HYPHEN_BREAK.sub(r'\1\2', text)
    # 去页眉页脚式孤行：保留换行结构，但压缩行内空白
    lines = []
    for line in text.split('\n'):
        line = _SPACES.sub(' ', line).strip()
        lines.append(line)
    # 合并被 PDF 强制折断的中文行：上一行不以标点结尾且下一行是中文开头
    merged = []
    for line in lines:
        if not line:
            if merged and merged[-1] != '':
                merged.append('')
            continue
        if merged and merged[-1]:
            prev = merged[-1]
            if _should_join(prev, line):
                merged[-1] = prev + line
                continue
        merged.append(line)
    out = '\n'.join(merged)
    out = re.sub(r'\n{3,}', '\n\n', out)
    return out.strip()


def _should_join(prev, nxt):
    """中文段落内被硬折行的地方重新接上。"""
    if not prev or not nxt:
        return False
    last = prev[-1]
    first = nxt[0]
    # 上一行以句末标点结尾 -> 不接
    if last in '。！？；：”」』）.!?;:':
        return False
    prev_cjk = _is_cjk(last)
    next_cjk = _is_cjk(first)
    if prev_cjk and next_cjk:
        return len(prev) > 12
    return False


def _is_cjk(ch):
    return '\u4e00' <= ch <= '\u9fff'


def extract_pages(path, use_fontfix=True):
    """返回 [(page_no, text)]，page_no 为 1 基。

    某些中文 PDF 的内嵌子集字体没有 ToUnicode，数字与拉丁字母会被替换成
    符号（例如 `音分值为*))`）。若 fontfix 模块可用，会尝试还原，并只在
    「还原后字母数字更多」时采用还原结果，避免对正常 PDF 造成损伤。
    """
    pymupdf = _ensure_pymupdf()
    fixer = None
    if use_fontfix:
        try:
            from . import fontfix
            fixer = fontfix
        except Exception:
            fixer = None
    doc = pymupdf.open(path)
    pages = []
    try:
        for i in range(doc.page_count):
            page = doc[i]
            raw = page.get_text('text')
            if fixer is not None:
                try:
                    fixed = fixer.build_page_text(page)
                    if _alnum_score(fixed) > _alnum_score(raw):
                        raw = fixed
                except Exception:
                    pass
            pages.append((i + 1, normalize(raw)))
    finally:
        doc.close()
    return pages


def _alnum_score(text):
    return sum(1 for ch in text if ch.isascii() and ch.isalnum())


def book_title_guess(path):
    import os
    base = os.path.splitext(os.path.basename(path))[0]
    return base
