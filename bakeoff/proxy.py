"""A local OpenAI-compatible proxy every framework is pointed at, which is how they are measured the same way.

- It counts: every model call, its tokens and its upstream latency, tagged with the case that made it.
- It paces: the free tier allows 8,000 tokens a minute, so it waits for the window to reset and retries 429s itself.
  No framework sees a rate limit, so none is helped or hurt by its own retry logic, and waiting is kept out of the
  latency numbers.
- It sets the request options no framework should differ on, like the reasoning effort.
"""

import asyncio
import json
import os
import re
import socket
import ssl
import threading
import time
from dataclasses import asdict, dataclass

import httpx
import truststore
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

UPSTREAMS = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
}
# The OS certificate store, so it works behind a TLS-inspecting corporate proxy too
TLS = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


@dataclass
class Call:
    case: str
    status: int
    prompt_tokens: int
    completion_tokens: int
    seconds: float  # upstream time of the call that succeeded
    waited: float  # time spent pacing and retrying rate limits
    retries: int
    tools_offered: int
    tool_calls: int


class Meter:
    def __init__(self) -> None:
        self.case = ""
        self.calls: list[Call] = []

    def for_case(self, case: str) -> list[Call]:
        return [c for c in self.calls if c.case == case]


def _seconds(value: str | None) -> float:
    """Groq's reset headers look like '7.66s', '1m26.4s' or '577ms'"""
    if not value:
        return 0.0
    total = 0.0
    for number, unit in re.findall(r"([\d.]+)(ms|s|m|h)", value):
        total += float(number) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
    return total


class Proxy:
    def __init__(self, upstream: str, overrides: dict | None = None) -> None:
        self.base, key_name = UPSTREAMS[upstream]
        self.key = os.environ[key_name]
        self.overrides = overrides or {}
        self.meter = Meter()
        self.lock = asyncio.Lock()
        self.remaining_tokens: int | None = None
        self.reset_at = 0.0
        self.port = 0
        self.exhausted = False  # set when the daily quota runs out

    async def handle(self, request: Request) -> Response:
        body = json.loads(await request.body())
        if body.get("stream"):
            return JSONResponse({"error": "the bakeoff proxy does not stream"}, status_code=400)
        body.update(self.overrides)
        # A rough count of what this request will spend, to decide whether to wait for the window first
        estimate = len(json.dumps(body)) // 3 + body.get("max_completion_tokens", body.get("max_tokens", 0) or 1000)

        async with self.lock, httpx.AsyncClient(timeout=180, verify=TLS) as client:
            waited, retries = 0.0, 0
            while True:
                if self.remaining_tokens is not None and estimate > self.remaining_tokens:
                    pause = max(0.0, self.reset_at - time.monotonic()) + 0.5
                    await asyncio.sleep(pause)
                    waited += pause
                    self.remaining_tokens = None
                started = time.monotonic()
                upstream = await client.post(
                    f"{self.base}/{request.path_params['path']}",
                    json=body,
                    headers={"Authorization": f"Bearer {self.key}"},
                )
                seconds = time.monotonic() - started
                headers = upstream.headers
                if "x-ratelimit-remaining-tokens" in headers:
                    self.remaining_tokens = int(headers["x-ratelimit-remaining-tokens"])
                    self.reset_at = time.monotonic() + _seconds(headers.get("x-ratelimit-reset-tokens"))
                if upstream.status_code not in (429, 503) or retries >= 200:
                    break
                pause = float(headers.get("retry-after") or 0) or _seconds(headers.get("x-ratelimit-reset-tokens")) or 5
                # The daily token limit refills a little every minute, so its waits are minutes long too. A wait of
                # more than a quarter hour means the quota is gone for the day: give up rather than hang
                if pause > 900:
                    self.exhausted = True
                    break
                await asyncio.sleep(pause + 0.5)
                waited += pause + 0.5
                retries += 1

        data = upstream.json() if upstream.headers.get("content-type", "").startswith("application/json") else {}
        usage = data.get("usage") or {}
        message = (data.get("choices") or [{}])[0].get("message") or {}
        self.meter.calls.append(
            Call(
                case=self.meter.case,
                status=upstream.status_code,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                seconds=round(seconds, 3),
                waited=round(waited, 3),
                retries=retries,
                tools_offered=len(body.get("tools") or []),
                tool_calls=len(message.get("tool_calls") or []),
            )
        )
        return Response(upstream.content, status_code=upstream.status_code, media_type="application/json")

    def start(self) -> str:
        """Serves on a free local port in a background thread, and returns the base URL to give the frameworks"""
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        app = Starlette(routes=[Route("/v1/{path:path}", self.handle, methods=["POST"])])
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning"))
        threading.Thread(target=server.run, daemon=True).start()
        while not server.started:
            time.sleep(0.05)
        return f"http://127.0.0.1:{self.port}/v1"


def calls_as_dicts(calls: list[Call]) -> list[dict]:
    return [asdict(c) for c in calls]
