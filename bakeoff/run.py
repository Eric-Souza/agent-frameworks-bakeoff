"""Runs the cases through one framework and writes runs/<framework>.jsonl.

    python -m bakeoff.run --framework langgraph [--only return-in-window,which-mug] [--limit 3] [--resume]

One process per framework, so their instrumentation and global state don't meet. Traces go to Phoenix
(http://localhost:6006), one project per framework.
"""

import argparse
import importlib
import json
import time
import traceback
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

from bakeoff import desk
from bakeoff.cases import CASES
from bakeoff.proxy import Proxy, calls_as_dicts
from bakeoff.reference import grade

FRAMEWORKS = {
    "crewai": ("bakeoff.frameworks.crewai_desk", "openinference.instrumentation.crewai", "CrewAIInstrumentor"),
    "autogen": (
        "bakeoff.frameworks.autogen_desk",
        "openinference.instrumentation.autogen_agentchat",
        "AutogenAgentChatInstrumentor",
    ),
    "langgraph": (
        "bakeoff.frameworks.langgraph_desk",
        "openinference.instrumentation.langchain",
        "LangChainInstrumentor",
    ),
}
RUNS = Path(__file__).parent.parent / "runs"


def trace(framework: str):
    """Phoenix, with the framework's own instrumentor and the OpenAI one, so every framework has the same model spans"""
    from openinference.instrumentation.openai import OpenAIInstrumentor
    from phoenix.otel import register

    provider = register(project_name=f"bakeoff-{framework}", endpoint="http://localhost:6006/v1/traces", batch=True)
    _, module, name = FRAMEWORKS[framework]
    getattr(importlib.import_module(module), name)().instrument(tracer_provider=provider)
    OpenAIInstrumentor().instrument(tracer_provider=provider)
    return provider


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework", choices=FRAMEWORKS, required=True)
    parser.add_argument("--upstream", default="groq")
    parser.add_argument("--model", default="openai/gpt-oss-120b")
    parser.add_argument("--effort", default="low", help="reasoning effort, the same for every framework")
    parser.add_argument("--only", help="comma-separated case ids")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true", help="skip the cases already in runs/<framework>.jsonl")
    parser.add_argument("--no-trace", action="store_true")
    args = parser.parse_args()

    cases = [c for c in CASES if not args.only or c.id in args.only.split(",")][: args.limit]
    out = RUNS / f"{args.framework}.jsonl"
    rows = {json.loads(line)["id"]: line for line in out.read_text().splitlines()} if out.exists() else {}
    if args.resume:
        cases = [c for c in cases if c.id not in rows]
    overrides = {"temperature": 0}
    if args.effort:
        overrides["reasoning_effort"] = args.effort
    proxy = Proxy(args.upstream, overrides)
    base_url = proxy.start()
    provider = None if args.no_trace else trace(args.framework)
    solve = importlib.import_module(FRAMEWORKS[args.framework][0]).build(base_url, args.model)

    RUNS.mkdir(exist_ok=True)
    right = 0
    for case in cases:
        store = desk.reset()
        proxy.meter.case = case.id
        started, error = time.monotonic(), None
        try:
            solve(case.email)
        except Exception as e:  # noqa: BLE001 - a crash is a wrong answer, and its traceback is kept to read
            error = "".join(traceback.format_exception_only(e)).strip()
            traceback.print_exc()
        wall = time.monotonic() - started
        if proxy.exhausted:
            print(f"The daily quota ran out during {case.id}; it was not recorded. Run again later to go on.")
            break
        got = store.decisions[0] if store.decisions else None
        result = grade(got, case.expected)
        calls = proxy.meter.for_case(case.id)
        waited = sum(c.waited for c in calls)
        row = {
            "id": case.id,
            "framework": args.framework,
            "model": args.model,
            "correct": result["correct"],
            "grade": result,
            "expected": asdict(case.expected),
            "got": asdict(got) if got else None,
            "decisions": len(store.decisions),
            "tool_calls": store.tool_calls,
            "llm_calls": len(calls),
            "prompt_tokens": sum(c.prompt_tokens for c in calls),
            "completion_tokens": sum(c.completion_tokens for c in calls),
            "seconds": round(wall - waited, 2),  # wall clock without the rate-limit waits
            "waited": round(waited, 2),
            "calls": calls_as_dicts(calls),
            "error": error,
        }
        rows[case.id] = json.dumps(row)
        out.write_text("\n".join(rows.values()) + "\n")
        right += result["correct"]
        mark = "ok " if result["correct"] else "BAD"
        print(
            f"{mark} {case.id:28} {len(calls):2} calls {row['prompt_tokens'] + row['completion_tokens']:6} tokens "
            f"{row['seconds']:6.1f}s  got {got and (got.action, got.order_id, got.amount, got.reason)}",
            flush=True,
        )
    print(f"{right}/{len(cases)} right")
    if provider:
        provider.force_flush()


if __name__ == "__main__":
    main()
