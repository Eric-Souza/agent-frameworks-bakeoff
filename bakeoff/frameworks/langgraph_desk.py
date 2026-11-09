"""LangGraph: the desk as an explicit graph. Each agent is a model node and a tool node in a loop, with its own
message history, and a handoff node between them passes on the investigator's brief."""

from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from bakeoff import prompts
from bakeoff.desk import ACTION_NAMES, INVESTIGATOR_TOOLS, REVIEWER_TOOLS


class Desk(TypedDict):
    email: str
    investigator: Annotated[list, add_messages]
    reviewer: Annotated[list, add_messages]


def build(base_url: str, model: str):
    llm = ChatOpenAI(model=model, base_url=base_url, api_key="proxy", max_retries=0)
    investigator = llm.bind_tools(INVESTIGATOR_TOOLS)
    reviewer = llm.bind_tools(REVIEWER_TOOLS)

    def investigate(state: Desk):
        return {"investigator": [investigator.invoke([SystemMessage(prompts.INVESTIGATOR), *state["investigator"]])]}

    def hand_off(state: Desk):
        brief = state["investigator"][-1].content
        return {"reviewer": [HumanMessage(prompts.reviewer_task(state["email"], brief))]}

    def review(state: Desk):
        return {"reviewer": [reviewer.invoke([SystemMessage(prompts.REVIEWER), *state["reviewer"]])]}

    def after_investigator(state: Desk):
        return "investigator_tools" if state["investigator"][-1].tool_calls else "hand_off"

    def after_reviewer(state: Desk):
        return "reviewer_tools" if state["reviewer"][-1].tool_calls else END

    def after_reviewer_tools(state: Desk):
        # Recording the decision ends the run; there is nothing to say after it
        asked = next(m for m in reversed(state["reviewer"]) if isinstance(m, AIMessage))
        return END if any(c["name"] in ACTION_NAMES for c in asked.tool_calls) else "review"

    graph = StateGraph(Desk)
    graph.add_node("investigate", investigate)
    graph.add_node("investigator_tools", ToolNode(INVESTIGATOR_TOOLS, messages_key="investigator"))
    graph.add_node("hand_off", hand_off)
    graph.add_node("review", review)
    graph.add_node("reviewer_tools", ToolNode(REVIEWER_TOOLS, messages_key="reviewer"))
    graph.add_edge(START, "investigate")
    graph.add_conditional_edges("investigate", after_investigator)
    graph.add_edge("investigator_tools", "investigate")
    graph.add_edge("hand_off", "review")
    graph.add_conditional_edges("review", after_reviewer)
    graph.add_conditional_edges("reviewer_tools", after_reviewer_tools)
    app = graph.compile()

    def solve(email: str) -> None:
        # About ten model calls per agent at most, as in the other two
        app.invoke({"email": email, "investigator": [HumanMessage(email)], "reviewer": []}, {"recursion_limit": 44})

    return solve
