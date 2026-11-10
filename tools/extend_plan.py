"""在既有 36 天之后追加 12 天「进阶乐理」，教材换成 Open Music Theory。

用法：python tools/extend_plan.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAN = os.path.join(ROOT, 'curriculum', 'plan.json')

# (天, 单元标题, 章节来源说明, 小节)
NEW = [
    (37, '和声功能：从「三个和弦」到语法', 'Harmonic functions / Harmonic syntax',
     ['功能（T/S/D）如何构成语法', '乐句的和声框架', '延长（prolongation）与装饰']),
    (38, '终止式：乐句如何结束', 'Classical cadence types',
     ['正格终止与变格终止', '半终止与阻碍终止', '终止式在乐句中的位置']),
    (39, '副属和弦：把 V 借给任何人', 'Applied chords',
     ['副属和弦的构成与标记', '链条式副属进行', '副属和弦与转调的界线']),
    (40, '调式交替：借用同名调的色彩', 'Modal mixture',
     ['同名大小调互借', '下属功能的变化和弦', '那不勒斯和弦与增六和弦']),
    (41, '转调：枢纽和弦与共同音', 'Modulation',
     ['枢纽和弦法', '共同音与等音转调', '转调还是离调：判据']),
    (42, '乐句结构（一）：sentence', 'The sentence',
     ['基本型与延续型', '4+4 结构如何铺开', '在古典作品中的实例']),
    (43, '乐句结构（二）：period 与混合型', 'The period / Hybrid themes',
     ['前句与后句', '混合型主题', '复合乐段与复合乐句']),
    (44, '小型曲式：二部与三部', 'The small binary / The small ternary',
     ['小型二部', '小型三部与再现', '与李重光「一段体/两段体」的对照']),
    (45, '奏鸣曲式（一）：呈示部', 'Sonata form: exposition types',
     ['主题群与调性布局', '连接部的功能', '呈示部的类型']),
    (46, '奏鸣曲式（二）：发展部与再现部', 'Sonata form: development / recapitulation',
     ['发展部的展开手法', '再现部的调性解决', '尾声的独立意义']),
    (47, '流行音乐和声：循环进行', 'Harmony in pop/rock music',
     ['doo-wop 进行', '四五一与卡农进行', '循环和声与形式的关系']),
    (48, '后调性入门：音级集合与十二音', 'Post-tonal: set theory / twelve-tone',
     ['音级与音程级', '标准序与原型', '音列与四种基本操作']),
]


def main():
    with open(PLAN, encoding='utf-8') as f:
        plan = json.load(f)

    units, days = plan['units'], plan['days']
    added = 0
    for day, title, chapter, sections in NEW:
        uid = f'T{day}'
        if uid in units:
            continue
        units[uid] = {
            'track': 'theory',
            'book': 'open-music-theory',
            'chapter': 'Open Music Theory · ' + chapter,
            'title': title,
            'sections': sections,
        }
        # 已有同一天则补 theory 字段，否则新建一天
        existing = next((d for d in days if d['day'] == day), None)
        if existing:
            existing['theory'] = uid
        else:
            days.append({'day': day, 'theory': uid, 'history': None})
        added += 1

    days.sort(key=lambda d: d['day'])
    with open(PLAN, 'w', encoding='utf-8') as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print(f'新增 {added} 个单元；总天数 {len(days)}，总单元 {len(units)}')


if __name__ == '__main__':
    main()
