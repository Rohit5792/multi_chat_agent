import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from app.agents.EmployeeDeploymentQueryAgent.tools import get_schema, execute_sql, format_table
from app.agents.EmployeeDeploymentQueryAgent.prompt import EMPLOYEE_DEPLOYMENT_QUERY_AGENT_PROMPT as _SYSTEM
from app.config import LLM_MODEL, OPENAI_BASE_URL, OPENAI_API_KEY
from app.logger import get_logger

logger = get_logger(__name__)

llm = ChatOpenAI(
    model=LLM_MODEL,
    openai_api_key=OPENAI_API_KEY,
    openai_api_base=OPENAI_BASE_URL,
    max_tokens=600,
)


async def run_agent(question: str, history: str = "[]") -> str:
    logger.info("Question received: %s", question)
    schema = get_schema()

    prior: list = []
    for msg in json.loads(history):
        if msg["role"] == "user":
            prior.append(HumanMessage(content=msg["content"]))
        else:
            # Wrap table results with explicit context so the LLM understands
            # these are result sets from its previous queries, not SQL statements.
            prior.append(AIMessage(content=f"[Result table from my previous SQL query]\n{msg['content']}"))

    messages = [
        SystemMessage(content=_SYSTEM.format(schema=schema)),
        *prior,
        HumanMessage(content=question),
    ]

    response = await _llm.ainvoke(messages)
    sql = response.content.strip()
    logger.debug("Generated SQL: %s", sql)
    columns, rows = execute_sql(sql)
    logger.info("Query returned %d row(s)", len(rows))
    return format_table(columns, rows)