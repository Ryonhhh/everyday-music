"""中文友好的 BM25 检索。

分词策略：中日韩字符取「单字 + 相邻二元组」，ASCII 取小写单词。
这样无需 jieba 等外部分词器，"五度相生律" 这类术语能被二元组精确命中。
"""
import math
import re

_WORD = re.compile(r'[a-zA-Z][a-zA-Z\'\-]*')
_CJK = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf]')

def tokenize(text):
    if not text:
        return []
    tokens = []
    lower = text.lower()
    for m in _WORD.finditer(lower):
        w = m.group(0)
        if len(w) >= 2:
            tokens.append(w)
    for m in _CJK.finditer(text):
        tokens.append(m.group(0))
    # 二元组
    runs = re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]+', text)
    for run in runs:
        for i in range(len(run) - 1):
            tokens.append(run[i:i + 2])
    return tokens


class BM25:
    def __init__(self, docs, k1=1.2, b=0.75):
        """docs: [{'id':.., 'text':..}]"""
        self.k1 = k1
        self.b = b
        self.doc_ids = []
        self.doc_tf = []
        self.doc_len = []
        df = {}
        for d in docs:
            toks = tokenize(d.get('text', ''))
            tf = {}
            for t in toks:
                tf[t] = tf.get(t, 0) + 1
            self.doc_ids.append(d['id'])
            self.doc_tf.append(tf)
            self.doc_len.append(len(toks))
            for t in tf:
                df[t] = df.get(t, 0) + 1
        self.N = len(self.doc_ids)
        self.avgdl = (sum(self.doc_len) / self.N) if self.N else 1.0
        self.df = df

    def search(self, query, top_k=8):
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        scores = {}
        for t in set(q_tokens):
            df = self.df.get(t)
            if not df:
                continue
            idf = math.log(1 + (self.N - df + 0.5) / (df + 0.5))
            for i, tf in enumerate(self.doc_tf):
                f = tf.get(t)
                if not f:
                    continue
                dl = self.doc_len[i] or 1
                denom = f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                scores[i] = scores.get(i, 0.0) + idf * f * (self.k1 + 1) / denom
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        return [(self.doc_ids[i], s) for i, s in ranked]
