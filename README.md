# Agent Frameworks Bakeoff

The same two-agent refund desk built three times, in [CrewAI](https://github.com/crewAIInc/crewAI),
[AutoGen](https://github.com/microsoft/autogen) and [LangGraph](https://github.com/langchain-ai/langgraph), and
measured the same way: 24 graded cases, the same model, prompts and tools, every model call counted by one local
proxy, and every run traced in [Arize Phoenix](https://github.com/Arize-ai/phoenix).

**Status:** LangGraph has run all 24 cases and CrewAI 19. The rest is waiting on the free tier's daily token limit.

## The task

A customer emails a home goods shop asking for money back. Two agents handle it:

- **The investigator** has read-only tools (`find_customer`, `list_orders`, `get_order`). It finds the sender, picks
  the order and item the email means, and writes a brief. It decides nothing.
- **The reviewer** has the [refund policy](bakeoff/policy.md) in its instructions, `get_order` to check a fact, and
  three action tools: `issue_refund`, `deny_request` and `escalate`. It must call exactly one.

The policy has the edges where agents slip: a 30-day return window and a 60-day damage window (both inclusive), late
delivery refunds the shipping only when more than 5 days late, final-sale items can't be returned but can be refunded
when damaged, a lost order refunds everything plus shipping, anything above $300 goes to a human, and an agent may
only act on the sender's own orders.

The 24 [cases](bakeoff/cases.jsonl) cover each rule and its boundary: day 30 and day 60 exactly, 5 days late
exactly, a $299 item and a $354.90 lost order, an email naming somebody else's order, a sender who isn't a customer,
a customer with two orders of the same mug, and an email carrying a fake "system note" that orders a $500 refund.

## How it is graded

The grade is what the reviewer *did*, read from the tool call it made, not what it said. Each case's right answer
is computed by [plain code](bakeoff/reference.py) from the policy and the case's structured claim, and checked
against answers worked out by hand ([tests](tests/test_reference.py)). A case is right when the action, order id,
amount (to the cent) and reason code all match.

## Keeping it fair

- **One proxy for all three.** Every framework is pointed at a [local OpenAI-compatible proxy](bakeoff/proxy.py)
  instead of the provider. It counts each model call and its tokens, and sets the options no framework should
  differ on (temperature 0, reasoning effort low). It also handles the free tier's rate limits: it waits and retries
  itself, so no framework sees a 429, and the waiting is kept out of the latency numbers.
- **Same model, prompts and tools.** gpt-oss-120b on Groq's free tier. The [instructions](bakeoff/prompts.py) and
  [tools](bakeoff/desk.py) are shared code, and each framework turns the same Python functions into its tool schema.
- **Each framework written its own way**, not forced into one shape:
  - [CrewAI](bakeoff/frameworks/crewai_desk.py): two agents with a task each, run in sequence. The decision tools
    are marked `result_as_answer`, so recording a decision ends the crew.
  - [AutoGen](bakeoff/frameworks/autogen_desk.py): a round-robin group chat of two assistant agents. It ends on a
    `FunctionCallTermination` for any decision tool.
  - [LangGraph](bakeoff/frameworks/langgraph_desk.py): an explicit `StateGraph`. Each agent is a model node and a
    `ToolNode` in a loop, with its own message history, and a hand-off node passes the brief on.
- **A fresh desk for every case.** The data store, and the crew or team, are rebuilt for each case. Each framework
  runs in its own process, with its own Phoenix project.

## Results

LangGraph, all 24 cases: **22/24 right**, 5.1 model calls and about 3,700 tokens per case, 3.7 s median.
CrewAI, the first 19 cases: **18/19 right**, 5.2 model calls and about 4,200 tokens per case, 3.2 s median.

The misses so far:

| Case | Framework | What happened |
|---|---|---|
| unknown-sender | LangGraph | The investigator reported "no customer", but the email named order N1002. The reviewer looked it up and refunded it, to someone who doesn't own it. |
| which-mug | LangGraph | Picked the customer's older mug order instead of the one "that arrived last week". |
| lost-over-300 | CrewAI | Escalated the lost rug at $340.00, leaving out the $14.90 shipping. |

The unknown-sender miss is the one that matters. The policy was in the prompt and the investigator got it right, but
the reviewer still acted on an order the sender doesn't own. A check like that belongs in the action tool, which
can refuse, not in instructions the model can talk itself past. That's the next change worth making here, and it is
framework-independent.

## Run it

You'll need Python 3.12, [uv](https://docs.astral.sh/uv/) and a free [Groq](https://console.groq.com/keys) key.

```bash
cp .env.example .env    # GROQ_API_KEY
uv sync
uv run pytest           # the reference answers

# Phoenix, in its own environment (its aiosqlite pin conflicts with CrewAI's)
PHOENIX_WORKING_DIR=.phoenix uvx --python 3.12 --from "arize-phoenix>=21" phoenix serve

uv run python -m bakeoff.run --framework langgraph   # or crewai, autogen; --only <ids>, --resume
uv run python -m bakeoff.report                      # runs/report.md
```

Traces are at http://localhost:6006, one project per framework.

## Caveats

- **One run per case**, at temperature 0, with one model. A one-case difference between two frameworks is within
  noise. The point is how each one is built and traced, with numbers measured the same way, not a leaderboard.
- **The free tier's daily limit** is 200,000 tokens per model, so the whole bakeoff (about 320,000 tokens) takes
  more than a day. The proxy waits for the limit to refill rather than switch models.
- **AutoGen is in maintenance mode**, and [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)
  is its successor. AgentChat 0.7 is measured here because it's still the AutoGen most people know.
- **Versions:** crewai 1.15, autogen-agentchat 0.7.5, langgraph 1.2, arize-phoenix-otel 0.17.
