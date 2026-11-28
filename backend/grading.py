"""Teacher-side oracles. Expected values, hidden fixtures and raw output stay on the worker."""
import json
import re
from . import model_client
from .core import digest, obj
RUBRIC_VERSION = "engineering-v2"
# Changing criteria or their weights requires a new rubric version.
CRITERIA = {
    "D3": {"clarity": ("命名清晰、关键意图可读", 50), "structure": ("职责清晰、易维护且避免重复逻辑", 50)},
    "D4": {"design": ("模块职责、接口和失败处理符合任务需要", 60), "efficiency": ("算法、数据访问及资源使用适当", 40)},
    "D5": {"coverage": ("测试覆盖正常、边界及失败情形", 60), "assertions": ("断言可发现缺陷并保护回归", 40)},
    "D6": {"rationale": ("解释需求、方案取舍与已知限制", 50), "verification": ("以证据核验实现及采纳的建议", 50)},
}


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


def builtin_cases(problem):
    if problem.get("version") != "v2.0":
        return []
    cases = []
    def add(dim, action, value, expected):
        cases.append((dim, {"action": action, "input": value}, expected))
    if problem["id"] == "E1002" and problem.get("repository") == "order-service":
        def paid(key, order="O-1", amount=9900):
            return {"id": key, "order_id": order, "amount": amount}
        ok = [False, 8, "paid", True]
        # A duplicate may be acknowledged or explicitly rejected. Only state changes are graded.
        add("D1", "payment", [paid("p-20"), paid("p-20")], [ok, [None, 8, "paid", True]])
        add("D1", "payment", [paid("p-21"), paid("p-22")], [ok, [None, 8, "paid", None]])
        add("D2", "payment", [paid("p-23", amount=9899)], [[True, 10, "pending", False]])
        add("D2", "payment", [paid("p-24", order="O-404")], [[True, 10, "pending", False]])
        add("D2", "payment", [{"stock": 1}, paid("p-25"), {"stock": 10}, paid("p-25")],
            [[True, 1, "pending", False], ok])
    elif problem["id"] == "E1007" and problem.get("repository") == "contact-importer":
        def person(n, email):
            return {"name": n, "email": email}
        a, b = person("A", "a@ex.cn"), person("B", "b@ex.cn")
        add("D1", "contacts", [person(" A ", " A@EX.CN "), b, a], [[a, b], [[3, True]], []])
        add("D1", "contacts", [b, a], [[b, a], [], []])
        add("D2", "contacts", [], [[], [], []])
        add("D2", "contacts", [person("", "x@ex.cn"), b, person("C", "bad"), b],
            [[b], [[4, True]], [[1, True], [3, True]]])
    elif problem["id"] == "E1008" and problem.get("repository") == "billing-core":
        for dimension, order_id, amount, member, coupon, due in [
                ("D1", "BK-7", 805, True, 100, 624), ("D1", "BK-8", 317, False, 53, 264),
                ("D2", "BK-9", 52, True, 70, 0), ("D2", "BK-10", 0, False, 0, 0)]:
            order = {"id": order_id, "amount": amount}
            user = {"id": "member-3", "member": member}
            add(dimension, "billing", [order, user, coupon], [[due, due], order, user, 2, True])
    elif problem["id"] == "E1005" and problem.get("repository") == "expense-workflow":
        manager = {"id": "mason", "role": "manager"}
        finance = {"id": "fay", "role": "finance"}
        def decision(actor, value="approve", reason=""):
            return {"actor": actor, "decision": value, "reason": reason}
        def approval(dim, amount, steps, expected):
            add(dim, "approval", {"amount": amount, "steps": steps}, expected)
        approval("D1", 5000, [decision(manager)], [["approved", 1]])
        approval("D1", 5001, [decision(manager), decision(finance)], [["finance_pending", 1], ["approved", 2]])
        approval("D2", 100, [decision(manager), decision(manager)], [["approved", 1], ["approved", 1]])
        approval("D2", 200, [decision(manager, "reject")], [["pending", 0]])
    elif problem["id"] == "E1001" and problem.get("repository") == "support-desk":
        ticket = {"id": "R-3", "title": "导出", "status": "open", "assignee": None, "resolution": ""}
        def ticket_case(dim, steps, result):
            add(dim, "ticket", {"ticket": ticket, "steps": steps}, result)
        ticket_case("D1", [{"assignee": "lin"}], ["ok", "open", "lin", True])
        ticket_case("D1", [{"assignee": "lin"}, {"status": "active"}, {"resolution": "已修复", "status": "resolved"}],
                    ["ok", "resolved", "lin", True])
        ticket_case("D2", [{"assignee": "chen"}], ["rejected", True])
        ticket_case("D2", [{"status": "active"}], ["rejected", True])
    elif problem["id"] == "E1003" and problem.get("repository") == "team-wiki":
        teammate = {"id": "fixture-member", "team": "B"}
        add("D1", "document", {"id": "D-1", "actor": teammate}, "D-1")
        add("D1", "document", {"id": "D-2", "actor": teammate}, "D-2")
        add("D2", "document", {"id": "missing-fixture", "actor": teammate}, "not_found")
        # Reuse the author-supplied permission contract from the immutable problem snapshot.
        add("D2", "published_checks", {"source": problem["files"]["tests/project.test.ts"]}, True)
    elif problem["id"] == "E1004" and problem.get("repository") == "notification-center":
        for dim, channel, outcomes, result in [
            ("D1", "email", ["temporary", "temporary", "ok"], [True, 3]),
            ("D1", "sms", ["ok"], [True, 1]),
            ("D2", "email", ["permanent"], [False, 1]),
            ("D2", "unsupported", ["ok"], [False, 0]),
        ]:
            add(dim, "notify", {"channel": channel, "message": "fixture", "outcomes": outcomes}, result)
    elif problem["id"] == "E1006" and problem.get("repository") == "customer-search":
        add("D1", "search", ["slow", "latest"], [["latest"], False, False])
        add("D1", "search", ["broken", "retry"], [["retry"], False, False])
        add("D2", "search", ["slow", ""], [[], False, False])
        add("D2", "search", ["broken"], [[], False, True])
    elif problem["id"] == "E1009" and problem.get("repository") == "event-booking":
        joined = [["join", "N"], ["join", "O"], ["join", "P"]]
        queue = [["N", "confirmed"], ["O", "waiting"], ["P", "waiting"]]
        def booking(dim, steps, result):
            add(dim, "booking", {"capacity": 1, "steps": steps}, result)
        booking("D1", joined, queue)
        booking("D1", joined + [["cancel", "N"]], [["O", "confirmed"], ["P", "waiting"]])
        booking("D2", joined + [["join", "N"], ["join", "P"]], queue)
        booking("D2", joined + [["cancel", "O"], ["cancel", "O"]], [["N", "confirmed"], ["P", "waiting"]])
    elif problem["id"] == "E1010" and problem.get("repository") == "api-client":
        for dim, method, responses, result in [
            ("D1", "GET", [503, 503, 200], [200, 3]),
            ("D1", "GET", ["network", 200], [200, 2]),
            ("D2", "POST", [503, 200], [None, 1]),
            ("D2", "GET", [404, 200], [None, 1]),
            ("D2", "GET", ["abort", 200], [None, 1]),
        ]:
            add(dim, "request", {"method": method, "responses": responses}, result)
    elif problem["id"] == "E1011" and problem.get("repository") == "release-console":
        current = {"id": "r5", "service": "api", "env": "prod", "time": 5, "status": "success"}
        def release(id_, timestamp, **updates):
            return {**current, "id": id_, "time": timestamp, **updates}
        a, b = release("first", 1), release("previous", 3)
        for dim, history, result in [
            ("D1", [b, a], "previous"), ("D1", [a, release("test", 4, env="test")], "first"),
            ("D2", [a, release("future", 6), release("failure", 4, status="failed")], "first"),
            ("D2", [release("other", 4, service="other")], None),
        ]:
            add(dim, "release", {"current": current, "history": history}, result)
    elif problem["id"] == "E1012" and problem.get("repository") == "sales-dashboard":
        orders = [{"id": "one", "month": "2026-02", "status": "paid", "amount": 123},
                  {"id": "two", "month": "2026-02", "status": "refunded", "amount": 400},
                  {"id": "three", "month": "2026-03", "status": "paid", "amount": 800}]
        feb, mar, empty = {"count": 1, "total": 123}, {"count": 1, "total": 800}, {"count": 0, "total": 0}
        for dim, rows, months, values in [
            ("D1", orders, ["2026-02"], [feb]), ("D1", orders, ["2026-03"], [mar]),
            ("D2", orders, ["2026-03", "2026-02", "2026-03"], [mar, feb, mar]),
            ("D2", [], ["2026-04"], [empty]),
        ]:
            add(dim, "metrics", {"orders": rows, "months": months}, [values, True])
    return cases


def test_version(problem, private):
    manifest = private if private else builtin_cases(problem)
    return digest(obj([problem["id"], problem["version"], manifest]))


def prompt_version():
    return digest(obj([model_client.RUBRIC_PROMPT, CRITERIA]))
