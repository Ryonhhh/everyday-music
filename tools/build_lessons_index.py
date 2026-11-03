"""扫描 data/lessons/*.md，生成站点用的 data/lessons/index.json。

每篇正文的标题取自课程规划，字数用于估算阅读时间。
运行：python tools/build_lessons_index.py
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LESSON_DIR = os.path.join(ROOT, 'data', 'lessons')
CURRICULUM = os.path.join(ROOT, 'data', 'curriculum.json')
OUT = os.path.join(LESSON_DIR, 'index.json')

CHARS_PER_MINUTE = 320
DAY_FILE = re.compile(r'day-(\d{2})\.md$')


def first_sentence(md):
    """取正文里第一段非标题、非引用的文字，截成一句摘要。"""
    for raw in md.split('\n'):
        line = raw.strip()
        if not line or line.startswith('#') or line.startswith('>'):
            continue
        if line.startswith('-') or line.startswith('*') or line.startswith('|'):
            continue
        line = re.sub(r'[*`_]', '', line)
        line = re.split(r'[。！？]', line)[0]
        return line[:52]
    return ''


def main():
    if not os.path.exists(CURRICULUM):
        print('缺少 data/curriculum.json，请先运行 tools/build_curriculum.py')
        return 1
    with open(CURRICULUM, encoding='utf-8') as f:
        curriculum = json.load(f)
    days = {d['day']: d for d in curriculum['days']}

    lessons = []
    for name in sorted(os.listdir(LESSON_DIR)):
        m = DAY_FILE.search(name)
        if not m:
            continue
        day = int(m.group(1))
        path = os.path.join(LESSON_DIR, name)
        with open(path, encoding='utf-8') as f:
            md = f.read()
        chars = len(re.sub(r'\s', '', md))
        info = days.get(day)
        unit_titles = [u['title'] for u in info['units']] if info else []
        lessons.append({
            'day': day,
            'title': ' × '.join(unit_titles) or f'第 {day} 天',
            'summary': first_sentence(md),
            'minutes': max(5, round(chars / CHARS_PER_MINUTE)),
            'chars': chars,
        })

    lessons.sort(key=lambda x: x['day'])
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump({'lessons': lessons}, f, ensure_ascii=False, indent=2)

    missing = [d for d in sorted(days) if d not in {l['day'] for l in lessons}]
    print(f'写入 {OUT}')
    print(f'  已生成 {len(lessons)} 篇；未生成 {len(missing)} 天：{missing[:12]}{" …" if len(missing) > 12 else ""}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
