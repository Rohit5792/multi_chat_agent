from fastmcp import FastMCP

mcp = FastMCP("Agent Registry", "A registry of agents and their capabilities.")

@mcp.tool()
async def EmployeeDeploymentQueryAgent(question: str, history: str = "[]") -> str:
    """
    EmployeeDeploymentQueryAgent: an agent which queries Employee Deployment Data from structured db. It receives Natural Language Questions and process them into SQL Queries. It can only generate SELECT queries, no INSERT/UPDATE/DELETE queries are allowed. The agent should be able to understand the context of the question and generate appropriate SQL queries to retrieve the required information from the database.

    Input: Natural Language Question

    Output: SQL Query (ONLY Select Queries, No Insert/Update/Delete)
    """
    from app.agents.EmployeeDeploymentQueryAgent.agent import run_agent
    return await run_agent(question, history)

@mcp.tool()
async def AskAboutZSAgent(question: str, history: str = "[]") -> str:
    """
    AskAboutZSAgent: an agent which answers questions about ZS. It receives Natural Language Questions and provides answers based on the knowledge it has about ZS. The agent should be able to understand the context of the question and provide accurate and relevant information about ZS.

    Input: Natural Language Question

    Output: Answer about ZS
    """
    from app.agents.AskAboutZSAgent.agent import run_agent
    return await run_agent(question, history)

@mcp.tool()
async def list_agents() -> list[dict]:
    from pathlib import Path
    import json
    """
    Returns the list of all available agents with their names,
    descriptions, capabilities, and I/O formats.
    """
    agents_path = Path(__file__).resolve().parent / "agents_list.json"

    if not agents_path.exists():
        return []
    return json.loads(agents_path.read_text())
