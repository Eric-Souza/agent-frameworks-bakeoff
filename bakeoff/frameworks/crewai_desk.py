"""CrewAI: the desk as a crew of two agents with a task each, run in sequence. CrewAI hands the investigator's
output to the reviewer's task as context, and an action tool marked result_as_answer ends the reviewer's task."""

import os

os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")

from crewai import LLM, Agent, Crew, Process, Task
from crewai.tools import tool

from bakeoff import prompts
from bakeoff.desk import ACTION_TOOLS, INVESTIGATOR_TOOLS, get_order


def build(base_url: str, model: str):
    # provider="openai" keeps the model id as it is; with an "openai/" prefix CrewAI would strip it
    llm = LLM(model=model, provider="openai", base_url=base_url, api_key="proxy", max_retries=0)

    def solve(email: str) -> None:
        crew(llm).kickoff(inputs={"email": email})

    return solve


def crew(llm: LLM) -> Crew:
    """A new crew for each case, so nothing carries over from the last one"""
    investigator = Agent(
        role="Investigator",
        goal="Gather the facts of one refund request and write a brief",
        backstory=prompts.INVESTIGATOR,
        tools=[tool(fn) for fn in INVESTIGATOR_TOOLS],
        llm=llm,
        max_iter=10,
        allow_delegation=False,
    )
    reviewer = Agent(
        role="Reviewer",
        goal="Decide one refund request by the policy and record the decision",
        backstory=prompts.REVIEWER,
        tools=[tool(get_order), *(tool(result_as_answer=True)(fn) for fn in ACTION_TOOLS)],
        llm=llm,
        max_iter=10,
        allow_delegation=False,
    )
    investigate = Task(
        description="{email}",
        expected_output="The brief, in the format your instructions give",
        agent=investigator,
    )
    review = Task(
        description="Customer email:\n\n{email}\n\nThe investigator's brief is in the context below.",
        expected_output="The decision, recorded by calling issue_refund, deny_request or escalate once",
        agent=reviewer,
        context=[investigate],
    )
    return Crew(agents=[investigator, reviewer], tasks=[investigate, review], process=Process.sequential)
