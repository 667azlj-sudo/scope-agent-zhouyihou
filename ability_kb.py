# -*- coding: utf-8 -*-
"""
ability_kb.py —— 员工个人能力知识库（RAG）

员工可让 Agent 读取其电脑上的文档，RAG 成个人能力知识库，供任务适配度分析使用。
向量用本地 bge-m3（不可用时自动退化为纯 BM25），按用户分文件持久化。
"""
import json
import math
import os

import jieba
import numpy as np

EMBED_MODEL = "bge-m3"
_KB_DIR = "ability_kb"
STOPWORDS = {"是", "的", "了", "吗", "呢", "啊", "什么", "一个", "这个", "那个", "多少", "怎么"}


def _file(user_id):
    return os.path.join(_KB_DIR, f"kb_{user_id}.json")


def _embed(text):
    try:
        import ollama
        return np.array(ollama.embed(model=EMBED_MODEL, input=text).embeddings[0])
    except Exception:  # noqa: BLE001
        return None


def _tokenize(text):
    return [w for w in jieba.lcut(text) if w.strip() and w not in STOPWORDS]


def _prepare(records):
    tokenized = [_tokenize(t) for t, _ in records]
    df = {}
    for toks in tokenized:
        for w in set(toks):
            df[w] = df.get(w, 0) + 1
    avg_len = np.mean([len(t) for t in tokenized]) if tokenized else 1
    return tokenized, df, avg_len


def load_records(user_id):
    if not os.path.exists(_file(user_id)):
        return []
    with open(_file(user_id), encoding="utf-8") as f:
        data = json.load(f)
    return [(t, np.array(v) if v is not None else None) for t, v in data]


def build(user_id, texts):
    """重建该员工的能力知识库。"""
    records = []
    for t in texts:
        t = (t or "").strip()
        if not t:
            continue
        vec = _embed(t)
        records.append((t, vec.tolist() if vec is not None else None))
    os.makedirs(_KB_DIR, exist_ok=True)
    with open(_file(user_id), "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)
    return len(records)


def add(user_id, texts):
    """向该员工的能力知识库追加文本片段。"""
    existing_texts = [t for t, _ in load_records(user_id)]
    return build(user_id, existing_texts + list(texts))


def stats(user_id):
    return len(load_records(user_id))


def search(user_id, question, top_k=3):
    """检索该员工能力知识库，返回 [(text, score), ...]。"""
    records = load_records(user_id)
    if not records:
        return []
    tokenized, df, avg_len = _prepare(records)
    n = len(records)

    def idf(w):
        d = df.get(w, 0)
        return math.log((n - d + 0.5) / (d + 0.5) + 1)

    q = _tokenize(question)
    bm = []
    for toks in tokenized:
        tf = {}
        for w in toks:
            tf[w] = tf.get(w, 0) + 1
        s = 0.0
        for w in q:
            if w in tf:
                denom = tf[w] + 1.5 * (1 - 0.75 + 0.75 * len(toks) / avg_len)
                s += idf(w) * (tf[w] * 2.5) / denom
        bm.append(s)
    b_arr = np.array(bm)

    def norm(x):
        return (x - x.min()) / (x.max() - x.min() + 1e-10)

    fused = norm(b_arr)
    if all(v is not None for _, v in records):
        qv = _embed(question)
        if qv is not None:
            v_arr = np.array([(qv @ v) / (np.linalg.norm(qv) * np.linalg.norm(v) + 1e-10)
                              for _, v in records])
            fused = 0.5 * norm(v_arr) + 0.5 * norm(b_arr)

    top = np.argsort(fused)[::-1][:top_k]
    return [(records[i][0], float(fused[i])) for i in top]
