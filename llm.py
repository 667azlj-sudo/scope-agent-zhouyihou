# -*- coding: utf-8 -*-
"""
llm.py —— LLM 调用封装
支持本地 Ollama 与云端 LLM 双模式，按配置切换。
"""
import ollama
from openai import OpenAI

# 云端 LLM 客户端（配置 API key 时启用）
_cloud_client = None


def set_cloud_key(api_key):
    """用户提交 DeepSeek API key 后调用，切换到云端模式"""
    global _cloud_client
    _cloud_client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")


def is_cloud():
    """当前是否用云端 DeepSeek"""
    return _cloud_client is not None


def chat(messages, tools=None):
    """统一的 LLM 调用（可带工具），返回 message 对象

    返回的 message 有 .content 和 .tool_calls。
    注意：DeepSeek 的 tool_calls 里 arguments 是 JSON 字符串，
          ollama 的是 dict —— 调用方要兼容两种。
    """
    if _cloud_client:
        resp = _cloud_client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=tools,
        )
        return resp.choices[0].message
    else:
        resp = ollama.chat(
            model="gemma4:26b",
            messages=messages,
            tools=tools,
        )
        return resp.message
