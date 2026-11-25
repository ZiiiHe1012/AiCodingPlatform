"""Validate author-provided hidden test manifests."""
import json
import re

def parse_private_tests(mapping):
    if set(mapping) != {"cases.json"}:
        raise ValueError("隐藏验收须仅含 tests/hidden/cases.json。")
    try:
        cases = json.loads(mapping["cases.json"])
    except (ValueError, TypeError) as exc:
        raise ValueError("cases.json 不是有效的 JSON。") from exc
    if not isinstance(cases, list) or not 2 <= len(cases) <= 24:
        raise ValueError("请配置 2 至 24 条隐藏验收。")
    result = []
    for case in cases:
        if not isinstance(case, dict) or case.get("dimension") not in ("D1", "D2"):
            raise ValueError("每条验收须指定 D1 或 D2。")
        if not re.fullmatch(r"[A-Za-z][\w]*(?:\.[A-Za-z][\w]*)*", str(case.get("module", "")), re.ASCII):
            raise ValueError("隐藏验收的 module 无效。")
        if not re.fullmatch(r"[A-Za-z][\w]*", str(case.get("function", "")), re.ASCII):
            raise ValueError("隐藏验收的 function 无效。")
        if not isinstance(case.get("args", []), list) or not isinstance(case.get("kwargs", {}), dict):
            raise ValueError("args 必须为数组，kwargs 必须为对象。")
        if "expected" not in case:
            raise ValueError("每条验收须指定 expected。")
        result.append((case["dimension"], {"action": "call", "module": case["module"],
                      "function": case["function"], "args": case.get("args", []),
                      "kwargs": case.get("kwargs", {})}, case["expected"]))
    if {d for d, _, _ in result} != {"D1", "D2"}:
        raise ValueError("D1 和 D2 各须至少一条验收。")
    return result
