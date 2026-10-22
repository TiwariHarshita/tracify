"""Run from backend: uv run python -m scripts.apply_phase2

Refactors only the existing /me handler and exposes Retry-After through the
existing CORS middleware. Other validated auth endpoints are preserved.
The supplied OAuth route file is copied separately by setup steps.
"""
import ast
from pathlib import Path

REPLACEMENT = '''@router.get("/me", response_model=UserResponse)
def current_user(user: User = Depends(get_current_user)):
    return user
'''


def refactor_current_user(source: str) -> str:
    tree = ast.parse(source)
    matches = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "current_user"
        and any(
            isinstance(decorator, ast.Call)
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
            and decorator.args[0].value == "/me"
            for decorator in node.decorator_list
        )
    ]
    if len(matches) != 1:
        raise SystemExit("Expected exactly one current_user /me route. No file changed.")
    node = matches[0]
    lines = source.splitlines(keepends=True)
    start = min([node.lineno] + [decorator.lineno for decorator in node.decorator_list]) - 1
    old = "".join(lines[start:node.end_lineno])
    if "Depends(get_current_user)" in old:
        return source
    updated = "".join(lines[:start]) + REPLACEMENT + "".join(lines[node.end_lineno:])
    import_line = "from app.api.dependencies import get_current_user\n"
    if import_line not in updated:
        future_end = max(
            [node.end_lineno for node in tree.body if isinstance(node, ast.ImportFrom) and node.module == "__future__"],
            default=0,
        )
        updated_lines = updated.splitlines(keepends=True)
        updated_lines.insert(future_end, import_line)
        updated = "".join(updated_lines)
    ast.parse(updated)
    return updated


def expose_retry_after(source: str) -> str:
    tree = ast.parse(source)
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_middleware"
        and node.args
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "CORSMiddleware"
    ]
    if len(calls) != 1:
        raise SystemExit("Expected exactly one CORSMiddleware registration. No files changed.")
    call = calls[0]
    keyword = next((item for item in call.keywords if item.arg == "expose_headers"), None)
    if keyword:
        if any(isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.lower() == "retry-after" for node in ast.walk(keyword.value)):
            return source
        node = keyword.value
        expression = ast.get_source_segment(source, node)
        replacement = f'[*({expression}), "Retry-After"]'
    else:
        node = call
        expression = ast.get_source_segment(source, call)
        prefix = expression[:-1].rstrip()
        if not prefix.endswith(","):
            prefix += ","
        indent = " " * call.col_offset
        replacement = prefix + '\n' + indent + '    expose_headers=["Retry-After"],\n' + indent + ')'
    lines = source.encode().splitlines(keepends=True)
    start = sum(map(len, lines[:node.lineno - 1])) + node.col_offset
    end = sum(map(len, lines[:node.end_lineno - 1])) + node.end_col_offset
    updated = (source.encode()[:start] + replacement.encode() + source.encode()[end:]).decode()
    ast.parse(updated)
    return updated


def main():
    root = Path(__file__).resolve().parents[1]
    target = root / "app/api/v1/routes/auth.py"
    source = target.read_text()
    updated = refactor_current_user(source)
    main_file = root / "app/main.py"
    main_source = main_file.read_text()
    updated_main = expose_retry_after(main_source)
    for path, original, result in [(target, source, updated), (main_file, main_source, updated_main)]:
        if result == original:
            continue
        backup = path.with_name(path.name + ".pre-phase2.bak")
        if not backup.exists():
            backup.write_text(original)
        path.write_text(result)
    print("Phase 2 applied: /me uses the session dependency and CORS exposes Retry-After. Other auth routes preserved.")


if __name__ == "__main__":
    main()
