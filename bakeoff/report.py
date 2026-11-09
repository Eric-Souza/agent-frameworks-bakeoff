"""Reads runs/*.jsonl and prints the comparison as markdown (and writes it to runs/report.md).

python -m bakeoff.report
"""

import ast
import io
import json
import statistics
import sys
import tokenize
from pathlib import Path

from bakeoff.cases import CASES
from bakeoff.run import FRAMEWORKS, RUNS

ROOT = Path(__file__).parent


def code_lines(path: Path) -> int:
    """Lines of code: not blank, not a comment, not a docstring"""
    source = path.read_text(encoding="utf-8")
    docstrings = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and ast.get_docstring(
            node
        ):
            first = node.body[0]
            docstrings.update(range(first.lineno, first.end_lineno + 1))
    code = set()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
            code.update(range(token.start[0], token.end[0] + 1))
    return len(code - docstrings)


def load(framework: str) -> dict[str, dict]:
    path = RUNS / f"{framework}.jsonl"
    if not path.exists():
        return {}
    return {row["id"]: row for row in map(json.loads, path.read_text().splitlines())}


def main() -> None:
    runs = {f: load(f) for f in FRAMEWORKS}
    runs = {f: rows for f, rows in runs.items() if rows}
    out = []

    out.append("| | " + " | ".join(runs) + " |")
    out.append("|---|" + "---|" * len(runs))

    def line(label, fn):
        out.append(f"| {label} | " + " | ".join(fn(list(rows.values())) for rows in runs.values()) + " |")

    def mean(key):
        return lambda rows: f"{statistics.mean(r[key] for r in rows):.1f}"

    line("Right", lambda rows: f"**{sum(r['correct'] for r in rows)}/{len(rows)}**")
    for part in ("action", "order_id", "amount", "reason"):
        line(f"&nbsp;&nbsp;right {part.replace('_', ' ')}", lambda rows, p=part: f"{sum(r['grade'][p] for r in rows)}")
    line("No decision recorded", lambda rows: str(sum(r["got"] is None for r in rows)))
    line("Crashed", lambda rows: str(sum(bool(r["error"]) for r in rows)))
    line("Model calls per case", mean("llm_calls"))
    line("Tool calls per case", lambda rows: f"{statistics.mean(len(r['tool_calls']) for r in rows):.1f}")
    line("Prompt tokens per case", lambda rows: f"{statistics.mean(r['prompt_tokens'] for r in rows):,.0f}")
    line("Completion tokens per case", lambda rows: f"{statistics.mean(r['completion_tokens'] for r in rows):,.0f}")
    line("Seconds per case (median)", lambda rows: f"{statistics.median(r['seconds'] for r in rows):.1f}")
    line(
        "Framework code (lines)", lambda rows: str(code_lines(ROOT / "frameworks" / f"{rows[0]['framework']}_desk.py"))
    )

    out.append("")
    out.append("| Case | Expected | " + " | ".join(runs) + " |")
    out.append("|---|---|" + "---|" * len(runs))
    for case in CASES:
        e = case.expected
        want = (
            f"{e.action} {e.order_id} {e.amount:.2f} {e.reason}"
            if e.action != "deny"
            else f"deny {e.order_id} {e.reason}"
        )
        cells = []
        for rows in runs.values():
            row = rows.get(case.id)
            if row is None:
                cells.append("")
            elif row["correct"]:
                cells.append("✓")
            elif row["got"] is None:
                cells.append("✗ none")
            else:
                g = row["got"]
                cells.append(f"✗ {g['action']} {g['order_id']} {g['amount']:.2f} {g['reason']}")
        out.append(f"| {case.id} | {want} | " + " | ".join(cells) + " |")

    text = "\n".join(out) + "\n"
    (RUNS / "report.md").write_text(text, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
