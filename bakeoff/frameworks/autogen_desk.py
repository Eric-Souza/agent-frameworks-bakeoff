"""AutoGen (AgentChat): the desk as a round-robin group chat of two assistant agents. The investigator's reply is
broadcast to the reviewer, and the chat ends when a decision tool is called.

AutoGen is in maintenance mode; Microsoft Agent Framework is its successor. AgentChat is still the AutoGen most
people know, so that is what is measured here."""

import asyncio

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import FunctionCallTermination, MaxMessageTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient

from bakeoff import prompts
from bakeoff.desk import ACTION_NAMES, INVESTIGATOR_TOOLS, REVIEWER_TOOLS


def build(base_url: str, model: str):
    def solve(email: str) -> None:
        asyncio.run(_solve(base_url, model, email))

    return solve


async def _solve(base_url: str, model: str, email: str) -> None:
    # A model AutoGen doesn't know needs its capabilities spelled out
    client = OpenAIChatCompletionClient(
        model=model,
        base_url=base_url,
        api_key="proxy",
        max_retries=0,
        model_info={
            "vision": False,
            "function_calling": True,
            "json_output": True,
            "structured_output": True,
            "family": "unknown",
        },
    )
    # A new team for each case, so nothing carries over from the last one. Each agent keeps calling tools until it
    # answers in text, up to ten rounds, as in the other two
    investigator = AssistantAgent(
        "investigator",
        client,
        tools=INVESTIGATOR_TOOLS,
        system_message=prompts.INVESTIGATOR,
        max_tool_iterations=10,
    )
    reviewer = AssistantAgent(
        "reviewer",
        client,
        tools=REVIEWER_TOOLS,
        system_message=prompts.REVIEWER,
        max_tool_iterations=10,
    )
    decided = FunctionCallTermination(ACTION_NAMES[0])
    for name in ACTION_NAMES[1:]:
        decided |= FunctionCallTermination(name)
    team = RoundRobinGroupChat([investigator, reviewer], termination_condition=decided | MaxMessageTermination(8))
    try:
        await team.run(task=email)
    finally:
        await client.close()
