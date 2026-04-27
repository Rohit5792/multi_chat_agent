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