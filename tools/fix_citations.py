"""把课程正文里的引注页码统一为「印刷页码」。

李重光那本的引注当初取的是 PDF 物理页（偏移 7），Grout 的已经是印刷页，不动。
只改「出处」行与「参考出处」列表行，正文其它数字一概不碰。

用法：
  python tools/fix_citations.py            # 干跑，只打印将要修改的行
  python tools/fix_citations.py --apply    # 实际写入
"""
import argparse
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LESSONS = os.path.join(ROOT, 'data', 'lessons')

THEORY_OFFSET = 7        # 李重光：印刷页 = PDF 页 - 7
THEORY_MARKERS = ('李重光', '基本乐理')
WEST_MARKERS = ('Grout', 'History of Western Music')
PAGE = re.compile(r'p\.\s*(\d{1,4})(?:\s*[–—\-]\s*(\d{1,4}))?')


def shift_line(line, delta):
    def repl(m):
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else None
        na = a + delta
        if b is None:
            return f'p.{na}'
        return f'p.{na}–{b + delta}'

    return PAGE.sub(repl, line)


def process(path, apply_changes):
    with open(path, encoding='utf-8') as f:
        lines = f.read().split('\n')
    current = None
    changes = []
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        is_cite = ('出处' in line) or stripped.startswith('- ')
        if not is_cite:
            continue
        if any(m in line for m in THEORY_MARKERS):
            current = 'theory'
        elif any(m in line for m in WEST_MARKERS):
            current = 'west'
        if current != 'theory':
            continue
        if not PAGE.search(line):
            continue
        new = shift_line(line, -THEORY_OFFSET)
        if new != line:
            changes.append((i + 1, line, new))
            lines[i] = new
    if changes and apply_changes:
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    return changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    total = 0
    for name in sorted(os.listdir(LESSONS)):
        if not re.fullmatch(r'day-\d{2}\.md', name):
            continue
        path = os.path.join(LESSONS, name)
        changes = process(path, args.apply)
        if not changes:
            continue
        print(f'--- {name}  （{len(changes)} 行）')
        for lineno, old, new in changes:
            print(f'  L{lineno}')
            print(f'    - {old.strip()}')
            print(f'    + {new.strip()}')
        total += len(changes)
    print(f'\n共 {total} 行' + ('，已写入' if args.apply else '（干跑，未写入）'))


if __name__ == '__main__':
    main()
