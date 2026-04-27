import json
from fastmcp import Client
from langchain_core.messages import AIMessage, HumanMessage
from app.state import AgentState
from app.agents.registry import mcp
from app.logger import get_logger

logger = get_logger(__name__)


async def _call_agent(agent_name: str, question: str, history: str) -> str:
    async with Client(mcp) as client:
        result = await client.call_tool(agent_name, {"question": question, "history": history})
    return result.content[0].text


def _agent_history(messages: list, agent_name: str) -> str:
    """
    Return only the (human, AI) turn pairs where the AI response was produced
    by agent_name, serialised as a JSON string for the agent to consume.
    """
    filtered = []
    prior = messages[:-1]  # exclude the current (unanswered) question
    i = 0
    while i < len(prior):
        msg = prior[i]
        if isinstance(msg, HumanMessage) and i + 1 < len(prior):
            reply = prior[i + 1]
            if (
                isinstance(reply, AIMessage)
                and reply.additional_kwargs.get("agent") == agent_name
            ):
                filtered.append({"role": "user",      "content": msg.content})
                filtered.append({"role": "assistant",  "content": reply.content})
            i += 2
        else:
            i += 1
    return json.dumps(filtered)


async def router_node(state: AgentState) -> dict:
    agent_name = state["agent_name"]
    messages   = state["messages"]
    question   = messages[-1].content
    history    = _agent_history(messages, agent_name)
    prior_count = len(json.loads(history)) // 2
    logger.info("Routing to agent: %s with %d prior turn(s)", agent_name, prior_count)
    try:
        answer = await _call_agent(agent_name, question, history)
        logger.info("Agent %s responded successfully", agent_name)
        return {"messages": [AIMessage(content=answer, additional_kwargs={"agent": agent_name})]}
    except Exception as exc:
        logger.error("Agent %s failed: %s", agent_name, exc, exc_info=True)
        return {"error": str(exc)}