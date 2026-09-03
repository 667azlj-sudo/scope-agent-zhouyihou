# -*- coding: utf-8 -*-
"""
personal_rag.py —— 用户本地个人知识库 + DeepSeek RAG

设计：
- 本地存储：用户「信息与习惯」画像 + 文本片段（工作记录 / 聊天 / 文档），按用户分文件持久化。
- 检索：本地 BM25（jieba 分词，不可用时退化为正则分词），无需 Ollama / bge-m3。
- 生成：走 llm.chat（配置 DEEPSEEK_API_KEY 即用 DeepSeek），让模型读取用户信息/习惯与检索片段后个性化作答。

数据目录：{DATA_DIR}/personal_kb/
  profile_{uid}.json   用户信息与习惯画像
  chunks_{uid}.json    知识库文本片段
"""
import json
import math
import os
import re
import time

from config import DATA_DIR

_KB_DIR = os.path.join(DATA_DIR, "personal_kb")

STOPWORDS = {
    "的", "了", "是", "我", "你", "他", "她", "它", "们", "和", "与", "及", "或", "在",
    "有", "就", "都", "而", "等", "这", "那", "什么", "一个", "这个", "那个", "怎么",
    "多少", "吗", "呢", "啊", "吧", "很", "也", "还", "把", "被", "让", "给",
}


def _profile_file(uid):
    return os.path.join(_KB_DIR, f"profile_{uid}.json")


def _chunks_file(uid):
    return os.path.join(_KB_DIR, f"chunks_{uid}.json")


def _tokenize(text):
    """中文/英文分词；jieba 不可用时退化为正则切分。"""
    try:
        import jieba
        return [w for w in jieba.lcut(text or "") if w.strip() and w not in STOPWORDS]
    except Exception:  # noqa: BLE001
        return [w for w in re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+", text or "")
                if w.strip() and w not in STOPWORDS]


def _read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def _write_json(path, data):
    os.makedirs(_KB_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 画像：用户信息与习惯
# ---------------------------------------------------------------------------
def upsert_profile(user_id, info="", habits=""):
    """保存/更新用户的基本信息与习惯（本地持久化）。"""
    profile = {
        "info": (info or "").strip(),
        "habits": (habits or "").strip(),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _write_json(_profile_file(user_id), profile)
    return {"ok": True, "profile": profile}


def get_profile(user_id):
    """读取用户画像；无则返回空画像。"""
    return _read_json(_profile_file(user_id), {"info": "", "habits": "", "updated_at": ""})


# ---------------------------------------------------------------------------
# 知识库片段
# ---------------------------------------------------------------------------
def add_chunks(user_id, texts, source="manual"):
    """向用户本地知识库追加文本片段。texts: [str]。"""
    chunks = _read_json(_chunks_file(user_id), [])
    for t in texts:
        t = (t or "").strip()
        if t:
            chunks.append({"text": t, "source": source,
                           "ts": time.strftime("%Y-%m-%d %H:%M:%S")})
    _write_json(_chunks_file(user_id), chunks)
    return {"ok": True, "count": len(chunks)}


def load_chunks(user_id):
    return _read_json(_chunks_file(user_id), [])


def clear_chunks(user_id):
    _write_json(_chunks_file(user_id), [])
    return {"ok": True}


# ---------------------------------------------------------------------------
# 检索：本地 BM25
# ---------------------------------------------------------------------------
def _bm25(chunks, query, top_k=5):
    if not chunks:
        return []
    corpus = [c["text"] for c in chunks]
    tokenized = [_tokenize(t) for t in corpus]
    df = {}
    for toks in tokenized:
        for w in set(toks):
            df[w] = df.get(w, 0) + 1
    n = len(corpus)
    avg_len = (sum(len(t) for t in tokenized) / n) if n else 1

    def idf(w):
        d = df.get(w, 0)
        return math.log((n - d + 0.5) / (d + 0.5) + 1)

    q = _tokenize(query)
    scores = []
    for toks in tokenized:
        tf = {}
        for w in toks:
            tf[w] = tf.get(w, 0) + 1
        s = 0.0
        for w in q:
            if w in tf:
                denom = tf[w] + 1.5 * (1 - 0.75 + 0.75 * len(toks) / avg_len)
                s += idf(w) * (tf[w] * 2.5) / denom
        scores.append(s)

    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    out = []
    for i in order:
        if scores[i] <= 0:
            break
        out.append({"text": chunks[i]["text"], "source": chunks[i].get("source", ""),
                    "score": round(float(scores[i]), 4)})
        if len(out) >= top_k:
            break
    return out


def search(user_id, query, top_k=5):
    """检索用户本地知识库，返回 top_k 片段。"""
    return _bm25(load_chunks(user_id), query, top_k)


# ---------------------------------------------------------------------------
# 从现有用户数据自动建库
# ---------------------------------------------------------------------------
def index_user_sources(user_id):
    """把画像 + 工作记录 + 聊天记录 + 能力库文本统一索引为可检索片段。"""
    texts = []
    profile = get_profile(user_id)
    if profile.get("info"):
        texts.append(profile["info"])
    if profile.get("habits"):
        texts.append(profile["habits"])
    try:
        import agent_framework as af
        for r in af.get_work_records(user_id):
            texts.append(r["content"])
    except Exception:  # noqa: BLE001
        pass
    try:
        from chat import get_user_sent_messages
        for m in get_user_sent_messages(user_id, limit=50):
            texts.append(m["content"])
    except Exception:  # noqa: BLE001
        pass
    try:
        import ability_kb
        for t in ability_kb.texts(user_id):
            texts.append(t)
    except Exception:  # noqa: BLE001
        pass

    seen, uniq = set(), []
    for t in texts:
        t = (t or "").strip()
        if t and t not in seen:
            seen.add(t)
            uniq.append(t)
    _write_json(_chunks_file(user_id), [
        {"text": t, "source": "auto", "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
        for t in uniq
    ])
    return {"ok": True, "count": len(uniq)}


# ---------------------------------------------------------------------------
# 生成：DeepSeek 读取用户信息与习惯
# ---------------------------------------------------------------------------
_MAX_READ_ALL = 40  # 个人知识库片段不超过该值时，整库交给 DeepSeek 阅读


def _select_chunks(user_id, question, top_k):
    """选取交给模型的片段：小知识库整库交给模型阅读；大知识库用 BM25 收窄。"""
    chunks = load_chunks(user_id)
    if len(chunks) <= _MAX_READ_ALL:
        return [{"text": c["text"], "source": c.get("source", ""), "score": None}
                for c in chunks]
    return _bm25(chunks, question, top_k)


def ask(user_id, question, top_k=5):
    """RAG 问答：把画像（信息+习惯）与知识库片段交给 DeepSeek 阅读后个性化作答。"""
    import llm

    profile = get_profile(user_id)
    selected = _select_chunks(user_id, question, top_k)

    info = profile.get("info") or "（未填写）"
    habits = profile.get("habits") or "（未填写）"
    hits_text = "\n\n".join(f"[{i + 1}] {h['text']}" for i, h in enumerate(selected)) or "（无）"

    system = (
        "你是该用户的专属 AI 助手。请始终参考下面的「用户信息与习惯」，用符合用户习惯的方式作答；"
        "再阅读「本地知识库片段」回答具体问题。若片段与问题无关，据实说明，并基于用户画像给出建议。"
    )
    user_prompt = (
        f"【用户信息】\n{info}\n\n"
        f"【用户习惯】\n{habits}\n\n"
        f"【本地知识库片段】\n{hits_text}\n\n"
        f"【用户问题】\n{question}"
    )
    try:
        resp = llm.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ])
        answer = (getattr(resp, "content", None) or "").strip()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "msg": f"模型调用失败：{e}"}
    return {
        "ok": True,
        "answer": answer,
        "profile": {"info": info, "habits": habits},
        "sources": selected,
        "profile_used": bool(profile.get("info") or profile.get("habits")),
    }
