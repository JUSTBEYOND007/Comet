"""LLM JSON 输出的健壮解析：剥离 markdown 代码块、截取首尾括号。

记忆萃取多处需要把 LLM 返回的文本解析成 dict / list，统一在此处理常见噪声。
"""
import json
from typing import Any


def _strip_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t[:4].lower() == "json":
            t = t[4:]
    return t.strip()


def parse_json_object(answer: str) -> dict[str, Any]:
    """从 LLM 文本中解析出 JSON 对象（取首个 { 到末个 }）。失败返回空 dict。"""
    text = _strip_fence(answer)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}
    try:
        data = json.loads(text[start : end + 1])
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


__all__ = ["parse_json_object"]
