# -*- coding: utf-8 -*-
"""
knowledge.py —— 本地 RAG 知识库（bge-m3 向量 + BM25 混合检索，持久化）
知识库重建覆盖旧数据；混合检索 = 向量 + BM25
仅本地环境可用（需要 Ollama + bge-m3 + jieba）
"""
import json
import math
import os

import jieba
import numpy as np
import ollama

EMBED_MODEL = "bge-m3"
_KNOWLEDGE_FILE = "knowledge_store.json"

# 简单停用词（BM25 分词时过滤，减少噪声）
STOPWORDS = {"是", "的", "了", "吗", "呢", "啊", "什么", "一个", "这个", "那个", "多少", "怎么"}

_knowledge = []       # [(文本, 向量), ...]
_tokenized = []       # 每个片段的词列表（BM25 用）
_df = {}              # 词 -> 出现几篇（IDF 用）
_avg_len = 1          # 平均长度


def _prepare_bm25():
    global _tokenized, _df, _avg_len
    _tokenized = []
    for text, _ in _knowledge:
        _tokenized.append([w for w in jieba.lcut(text) if w.strip() and w not in STOPWORDS])
    _df = {}
    for tokens in _tokenized:
        for w in set(tokens):
            _df[w] = _df.get(w, 0) + 1
    _avg_len = np.mean([len(t) for t in _tokenized]) if _tokenized else 1


def _idf(word):
    n = len(_knowledge)
    d = _df.get(word, 0)
    return math.log((n - d + 0.5) / (d + 0.5) + 1)


def _bm25_scores(query):
    """对每个片段算 BM25 分"""
    q_tokens = [w for w in jieba.lcut(query) if w.strip() and w not in STOPWORDS]
    scores = []
    for tokens in _tokenized:
        tf = {}
        for w in tokens:
            tf[w] = tf.get(w, 0) + 1
        s = 0.0
        for w in q_tokens:
            if w in tf:
                denom = tf[w] + 1.5 * (1 - 0.75 + 0.75 * len(tokens) / _avg_len)
                s += _idf(w) * (tf[w] * 2.5) / denom
        scores.append(s)
    return scores


def build_knowledge(texts):
    """重建知识库：向量化 + 准备 BM25 索引，并写文件"""
    global _knowledge
    _knowledge = []
    for text in texts:
        vec = ollama.embed(model=EMBED_MODEL, input=text).embeddings[0]
        _knowledge.append((text, vec))
    _prepare_bm25()
    with open(_KNOWLEDGE_FILE, "w", encoding="utf-8") as f:
        json.dump([(t, v) for t, v in _knowledge], f)
    return len(_knowledge)


def load_knowledge():
    """启动时从文件加载上次的知识库，返回条数"""
    if os.path.exists(_KNOWLEDGE_FILE):
        with open(_KNOWLEDGE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        global _knowledge
        _knowledge = [(t, np.array(v)) for t, v in data]
        _prepare_bm25()
        return len(_knowledge)
    return 0


def search(question, top_k=3):
    """混合检索：向量分 + BM25 分，各自归一化后融合"""
    if not _knowledge:
        return []

    # 向量分
    qv = ollama.embed(model=EMBED_MODEL, input=question).embeddings[0]
    Q = np.array(qv)
    v_arr = np.array([(Q @ np.array(v)) / (np.linalg.norm(Q) * np.linalg.norm(v) + 1e-10)
                      for _, v in _knowledge])
    # BM25 分
    b_arr = np.array(_bm25_scores(question))

    # 归一化 + 融合
    def norm(x):
        return (x - x.min()) / (x.max() - x.min() + 1e-10)
    fused = 0.5 * norm(v_arr) + 0.5 * norm(b_arr)

    top = np.argsort(fused)[::-1][:top_k]
    return [(_knowledge[i][0], float(fused[i])) for i in top]


if __name__ == "__main__":
    texts = [
        "公司今年预算 10 万，工期一个月，做一个企业官网。",
        "官网包含首页、产品展示、新闻、联系我们模块。",
        "客户是制造业公司，希望突出品牌形象。",
    ]
    print(f"建库 {build_knowledge(texts)} 条（向量+BM25 混合）")
    print("问「官网预算」，检索：")
    for text, sim in search("官网预算", top_k=2):
        print(f"  [{sim:.3f}] {text}")
