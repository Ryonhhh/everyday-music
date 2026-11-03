"""把旧的专辑 HTML 页面转成站点用的 Markdown。

用法：python tools/html2md.py albums/soul-mining.html data/albums/soul-mining.md
"""
import html
import os
import re
import sys

BLOCK_RE = re.compile(
    r'<(h1|h2|h3|h4|p|li|blockquote|dt|dd|figcaption|td|th)\b[^>]*>(.*?)</\1>',
    re.S | re.I,
)


def strip_tags(s):
    s = re.sub(r'(?s)<[^>]+>', '', s)
    return html.unescape(s).strip()


def convert(raw):
    # 丢掉 head / script / style / svg / nav
    for tag in ('script', 'style', 'svg', 'nav', 'head'):
        raw = re.sub(rf'(?s)<{tag}\b.*?</{tag}>', ' ', raw, flags=re.I)

    # 先取出列表项，保留其父列表语义的做法太复杂，这里逐块线性输出
    out = []
    for m in BLOCK_RE.finditer(raw):
        tag = m.group(1).lower()
        text = strip_tags(m.group(2))
        if not text:
            continue
        # 压缩块内的多余换行
        text = re.sub(r'\s+', ' ', text)
        if tag == 'h1' or tag == 'h2':
            out.append(f'## {text}')
        elif tag == 'h3':
            out.append(f'### {text}')
        elif tag == 'h4':
            out.append(f'#### {text}')
        elif tag == 'li':
            out.append(f'- {text}')
        elif tag == 'blockquote':
            out.append(f'> {text}')
        elif tag in ('dt', 'dd'):
            continue  # 元数据另存 index.json
        elif tag in ('td', 'th'):
            continue
        else:
            out.append(text)

    # 合并连续重复标题（旧页面常有 eyebrow + h1 重复）
    cleaned = []
    for line in out:
        if cleaned and line == cleaned[-1]:
            continue
        cleaned.append(line)
    return '\n\n'.join(cleaned) + '\n'


def main():
    src, dst = sys.argv[1], sys.argv[2]
    raw = open(src, encoding='utf-8', errors='replace').read()
    md = convert(raw)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    open(dst, 'w', encoding='utf-8').write(md)
    print(f'{src} -> {dst}  ({len(md)} 字符)')


if __name__ == '__main__':
    main()
