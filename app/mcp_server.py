"""
app/mcp_server.py

Standalone FastMCP server with two tools:
  1. list_agents  — returns all agents from agents_list.json
  2. ask          — classifies, filters history internally, dispatches to agent

History is managed internally per session_id — callers never pass history.
The server tracks full conversation history and filters per agent exactly
like the main app does in router.py.

Run:
    uv run python app/mcp_server.py

Test in inspector:
    uv run fastmcp dev inspector app/mcp_server.py -e .
"""

import json
from pathlib import Path
from collections import defaultdict
import os
from fastmcp import FastMCP, Client
from langchain_core.messages import HumanMessage, AIMessage

from app.node_graph.classifier import classifier_node, KNOWN_AGENTS
from app.node_graph.router import _agent_history
from app.agents.registry import mcp as agent_registry
from app.logger import get_logger

logger = get_logger(__name__)
API_KEY = os.environ.get("API_KEY", "test123")
# After
import importlib.resources
_AGENTS_JSON= json.loads(
    importlib.resources.files("app.agents").joinpath("agents_list.json").read_text()
)

mcp = FastMCP(
    "Multi-Agent MCP Server",
    "Exposes the full multi-agent pipeline as MCP tools.",
)

# In-memory history store: session_id -> list of LangChain messages
# Each session maintains its own full conversation history
_sessions: dict[str, list] = defaultdict(list)


# ---------------------------------------------------------------------------
# Tool 1 — list_agents
# ---------------------------------------------------------------------------
@mcp.tool()
async def list_agents() -> list[dict]:
    """
    Returns the list of all available agents with their names,
    descriptions, capabilities, and I/O formats.

    Input:  none
    Output: list of agent metadata dicts from agents_list.json
    """
    return json.loads(_AGENTS_JSON.read_text())


# ---------------------------------------------------------------------------
# Tool 2 — ask
# ---------------------------------------------------------------------------
@mcp.tool()
async def ask(question: str, session_id: str = "default") -> dict:
    """
    Routes a natural language question through the existing classifier,
    manages conversation history internally per session,
    and returns the answer.

    History is never exposed to or required from the caller.
    Each session_id maintains its own independent conversation history.

    Args:
        question:   The user's natural language question.
        session_id: Optional session identifier to maintain separate
                    conversation histories (default: "default").

    Returns:
        {
          "agent":      "AgentName",
          "answer":     "...",
          "session_id": "..."
        }
    """
    # Step 1 — append current question to session history
    history = _sessions[session_id]
    history.append(HumanMessage(content=question))

    # Step 2 — classify using existing classifier_node
    state = {
        "messages": history,
        "agent_name": None,
        "error": None,
    }
    result = await classifier_node(state)
    agent_name = result["agent_name"]

    if agent_name == "None" or agent_name not in KNOWN_AGENTS:
        # Remove the question we just appended since we can't answer it
        history.pop()
        return {
            "agent":      "None",
            "answer":     "No suitable agent found for this question.",
            "session_id": session_id,
        }

    logger.info("[ask] session=%s classified → %s", session_id, agent_name)

    # Step 3 — filter history to only this agent's turns (same as router.py)
    filtered_history = _agent_history(history, agent_name)

    logger.info(
        "[ask] Passing %d prior turn(s) to %s",
        len(json.loads(filtered_history)) // 2,
        agent_name,
    )

    # Step 4 — dispatch to agent via existing registry
    try:
        async with Client(agent_registry) as client:
            tool_result = await client.call_tool(
                agent_name,
                {"question": question, "history": filtered_history},
            )
        answer = tool_result.content[0].text

        # Step 5 — store agent's reply in session history (tagged with agent name)
        history.append(
            AIMessage(
                content=answer,
                additional_kwargs={"agent": agent_name},
            )
        )
        logger.info("[ask] session=%s agent=%s replied OK", session_id, agent_name)

        return {
            "agent":      agent_name,
            "answer":     answer,
            "session_id": session_id,
        }

    except Exception as exc:
        # Remove the unanswered question from history on failure
        history.pop()
        logger.error("[ask] Agent %s failed: %s", agent_name, exc, exc_info=True)
        return {
            "agent":      agent_name,
            "answer":     f"Error: {exc}",
            "session_id": session_id,
        }


# ---------------------------------------------------------------------------
# Tool 3 — clear_history  (optional utility)
# ---------------------------------------------------------------------------
@mcp.tool()
async def clear_history(session_id: str = "default") -> dict:
    """
    Clears the conversation history for a given session.

    Args:
        session_id: The session whose history should be cleared.

    Returns:
        {"cleared": true, "session_id": "..."}
    """
    _sessions[session_id] = []
    logger.info("[clear_history] session=%s cleared", session_id)
    return {"cleared": True, "session_id": session_id}


if __name__ == "__main__":
    import os

    mcp.run(transport="http",host="0.0.0.0",port=8000)