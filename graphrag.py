# -*- coding: utf-8 -*-
"""
graphrag.py —— GraphRAG 图检索（可选启用）
用 LLM 从知识库抽实体关系建图，多跳检索；带开关（客户可选启用）
"""
import llm

# 图结构：实体 -> [(关系, 邻居实体), ...]（邻接表）
_graph = {}
_enabled = False          # GraphRAG 开关，默认关（客户可在设置里开）


def set_enabled(flag):
    global _enabled
    _enabled = bool(flag)


def is_enabled():
    return _enabled


def _extract_triplets(text):
    """用 LLM 从一段文本抽三元组（实体|关系|实体）"""
    prompt = (
        "从下面文本抽取实体关系三元组，每行一个，格式：实体1|关系|实体2\n"
        f"文本：{text}\n只输出三元组，不要其他文字："
    )
    msg = llm.chat([{"role": "user", "content": prompt}])
    triplets = []
    for line in msg.content.strip().split("\n"):
        parts = [p.strip() for p in line.split("|")]
        if len(parts) == 3:
            triplets.append(tuple(parts))
    return triplets


def build_graph(knowledge_texts):
    """从知识库文本抽实体关系，建图，返回三元组数量"""
    global _graph
    _graph = {}
    n = 0
    for text in knowledge_texts:
        for e1, rel, e2 in _extract_triplets(text):
            _graph.setdefault(e1, []).append((rel, e2))
            n += 1
    return n


def _find_start(question):
    """找问题里出现的实体作为起点"""
    for entity in _graph:
        if entity and entity in question:
            return entity
    return None


def search(question, max_hop=2):
    """多跳检索：从起点实体 BFS，返回路径（可能有多条）"""
    if not _graph or not _enabled:
        return []
    start = _find_start(question)
    if not start:
        return []
    visited = set()
    queue = [(start, [])]
    paths = []
    while queue and len(paths) < 10:
        entity, path = queue.pop(0)
        if entity in visited:
            continue
        visited.add(entity)
        for rel, neigh in _graph.get(entity, []):
            new_path = path + [(entity, rel, neigh)]
            if len(new_path) > max_hop:
                continue
            paths.append(new_path)
            queue.append((neigh, new_path))
    return paths


if __name__ == "__main__":
    # 测试：建图 + 开关 + 多跳检索
    set_enabled(True)
    texts = [
        "张三负责公司官网项目。",
        "张三毕业于清华大学。",
        "官网项目预算10万，工期一个月。",
    ]
    n = build_graph(texts)
    print(f"建图完成，三元组 {n} 条")
    print("图结构：", {k: v for k, v in list(_graph.items())[:3]})
    print("\n问「清华大学」多跳检索：")
    for path in search("张三毕业于哪里"):
        print(f"  路径：{path}")
