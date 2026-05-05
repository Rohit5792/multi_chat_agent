import json

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from app.agents.AskAboutZSAgent.prompt import ASK_ABOUT_ZS_AGENT_PROMPT as _SYSTEM
from app.agents.AskAboutZSAgent.tools import retrieve
from app.config import LLM_MODEL, OPENAI_BASE_URL, OPENAI_API_KEY
from app.logger import get_logger

logger = get_logger(__name__)

_llm = ChatOpenAI(
    model=LLM_MODEL,
    openai_api_key=OPENAI_API_KEY,
    openai_api_base=OPENAI_BASE_URL,
    max_tokens=1000,
)


async def run_agent(question: str, history: str = "[]") -> str:
    logger.info("Question received: %s", question)

    chunks = retrieve(question, n=10)
    context = "\n\n".join(chunks)
    # print(context)
    logger.debug("Context built from %d chunk(s)", len(chunks))

    prior: list = []
    for msg in json.loads(history):
        if msg["role"] == "user":
            prior.append(HumanMessage(content=msg["content"]))
        else:
            prior.append(AIMessage(content=f"[My previous response]\n{msg['content']}"))

    messages = [
        SystemMessage(content=_SYSTEM),
        *prior,
        HumanMessage(content=f"Retrieved Context:\n\n{context}\n\nUser Question: {question}"),
    ]

    response = await _llm.ainvoke(messages)
    logger.info("Response generated")
    return response.content.strip()
