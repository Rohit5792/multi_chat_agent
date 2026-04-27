import json
from fastmcp import Client
from langchain_core.messages import AIMessage, HumanMessage
from app.state import AgentState
from app.registry import mcp
from app.logger import get_logger

logger = get_logger(__name__)


async def _call_agent(agent_name: str, question: str, history: str) -> str:
    async with Client(mcp) as client:
        result = await client.call_tool(agent_name, {"question": question, "history": history})
    return result.content[0].text


async def router_node(state: AgentState) -> dict:
    agent_name = state["agent_name"]
    messages = state["messages"]
    question = messages[-1].content
    history = json.dumps([
        {"role": "user" if isinstance(m, HumanMessage) else "assistant", "content": m.content}
        for m in messages[:-1]
    ])
    logger.info("Routing to agent: %s with %d prior message(s)", agent_name, len(messages) - 1)
    try:
        answer = await _call_agent(agent_name, question, history)
        logger.info("Agent %s responded successfully", agent_name)
        return {"messages": [AIMessage(content=answer)]}
    except Exception as exc:
        logger.error("Agent %s failed: %s", agent_name, exc, exc_info=True)
        return {"error": str(exc)}