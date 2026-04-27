from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from pathlib import Path

from app.state import AgentState
from app.nodes.prompt import CLASSIFIER_PROMPT
from app.config import LLM_MODEL, OPENAI_BASE_URL, OPENAI_API_KEY
from app.logger import get_logger

logger = get_logger(__name__)

_agents_path = (Path(__file__).parent.parent / "agents")

KNOWN_AGENTS = {item.name for item in _agents_path.iterdir() if item.is_dir() and not item.name.startswith("__")}

_llm = ChatOpenAI(
    model=LLM_MODEL,
    openai_api_key=OPENAI_API_KEY,
    openai_api_base=OPENAI_BASE_URL,
    max_tokens=20,
)


async def classifier_node(state: AgentState) -> dict:
    question = state["messages"][-1].content
    logger.info("Classifying question: %s", question)
    response = await _llm.ainvoke([
        SystemMessage(content=CLASSIFIER_PROMPT),
        HumanMessage(content=question),
    ])
    agent_name = response.content.strip()
    if agent_name not in KNOWN_AGENTS:
        logger.warning("Unknown agent %r — falling back to None", agent_name)
        agent_name = "None"
    logger.info("Classified as agent: %s", agent_name)
    return {"agent_name": agent_name}
