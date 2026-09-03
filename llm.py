# -*- coding: utf-8 -*-
"""
llm.py —— 统一 LLM 调用封装

网页端优先走云端 API（DeepSeek），本地 Ollama 只在「未配置密钥」时作为开发回退。

配置方式（按优先级）：
  1. 环境变量 DEEPSEEK_API_KEY（部署时设置，启动即云端）
  2. 运行时调用 set_cloud_key(key)（对应 /api/config/llm 接口）

所有业务代码统一通过 chat() 调用，不要再各自直连 Ollama。
"""
import os

import ollama
from openai import OpenAI

_cloud_client = None

DEEPSEEK_BASE = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
LOCAL_MODEL = "gemma4:26b"
_KEY_FILE = "llm_key.txt"   # 运行时保存的 key（已 gitignore，勿提交）


def set_cloud_key(api_key):
    """设置 DeepSeek API key 并切到云端；传空则回退本地。"""
    global _cloud_client
    key = (api_key or "").strip()
    _cloud_client = OpenAI(api_key=key, base_url=DEEPSEEK_BASE) if key else None
    return is_cloud()


def persist_cloud_key(api_key):
    """设置云端 key 并写到本地文件，重启后仍生效。"""
    set_cloud_key(api_key)
    key = (api_key or "").strip()
    if key:
        with open(_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(key)
    elif os.path.exists(_KEY_FILE):
        os.remove(_KEY_FILE)
    return is_cloud()


def load_cloud_from_env():
    """启动时加载云端 key：优先环境变量 DEEPSEEK_API_KEY，其次本地文件。"""
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_KEY") or ""
    if not key and os.path.exists(_KEY_FILE):
        try:
            with open(_KEY_FILE, encoding="utf-8") as f:
                key = f.read().strip()
        except Exception:  # noqa: BLE001
            key = ""
    if key:
        set_cloud_key(key)
    return is_cloud()


def is_cloud():
    """当前是否用云端 DeepSeek"""
    return _cloud_client is not None


def chat(messages, tools=None):
    """统一 LLM 调用（可带工具），返回 message 对象（有 .content / .tool_calls）。

    云端 DeepSeek 的 tool_calls.arguments 是 JSON 字符串，本地 ollama 是 dict，
    调用方需兼容两者（已按此约定编写）。
    """
    if _cloud_client:
        resp = _cloud_client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=messages,
            tools=tools,
        )
        return resp.choices[0].message
    # 本地回退：仅未配置云端 key 时使用
    resp = ollama.chat(
        model=LOCAL_MODEL,
        messages=messages,
        tools=tools,
    )
    return resp.message
