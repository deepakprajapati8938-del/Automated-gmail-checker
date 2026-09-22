import ast
from pathlib import Path

def test_all_handlers_have_auth_check():
    handlers_file = Path("app/telegram/handlers.py")
    tree = ast.parse(handlers_file.read_text(encoding="utf-8"))

    handler_funcs = []
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef):
            if node.name.endswith("_cmd") or node.name.endswith("_handler"):
                handler_funcs.append(node)

    assert len(handler_funcs) > 0, "No handlers found?"

    for func in handler_funcs:
        # We look for an if statement checking `not is_authorized(...)` within the first few statements.
        auth_check_found = False
        for stmt in func.body[:3]:
            if isinstance(stmt, ast.If):
                test_expr = stmt.test
                if isinstance(test_expr, ast.UnaryOp) and isinstance(test_expr.op, ast.Not):
                    if isinstance(test_expr.operand, ast.Call) and getattr(test_expr.operand.func, "id", "") == "is_authorized":
                        auth_check_found = True
                        break
        assert auth_check_found, f"{func.name} missing 'is_authorized' check in its first few statements"
