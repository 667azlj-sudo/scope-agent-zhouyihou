# -*- coding: utf-8 -*-
"""
config.py —— 集中读取环境变量与数据目录配置。

所有持久化路径都以 DATA_DIR 为根（默认当前目录，保持原有行为）；
生产环境通过 DATA_DIR 指向挂载卷，实现数据与代码分离、可持久化、可备份。
"""
import os

DATA_DIR = (os.environ.get("DATA_DIR", "") or "").strip() or os.getcwd()

DB_PATH = os.path.join(DATA_DIR, "scope_agent.db")

# 数据库连接串（可选）。设置后走 PostgreSQL，否则回退 SQLite（开发/测试）。
# 例：postgresql://user:pass@host:5432/scope_agent
DATABASE_URL = (os.environ.get("DATABASE_URL", "") or "").strip()
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
KB_DIR = os.path.join(DATA_DIR, "ability_kb")
KNOWLEDGE_FILE = os.path.join(DATA_DIR, "knowledge_store.json")
LLM_KEY_FILE = os.path.join(DATA_DIR, "llm_key.txt")


def ensure_dirs():
    """确保数据目录存在（应用启动时调用）。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(KB_DIR, exist_ok=True)
