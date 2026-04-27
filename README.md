# Multi-Agent Chat

An extensible multi-agent chat application built with LangGraph, FastMCP, and FastAPI. Users ask questions in natural language via a streaming web UI; an LLM classifier routes each question to the correct specialist agent, which answers and streams the response back token by token.

---

## Table of Contents

- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Configuration](#configuration)
- [Running the App](#running-the-app)
- [Data Ingestion](#data-ingestion)
- [Adding a New Agent](#adding-a-new-agent)
- [Existing Agents](#existing-agents)

---

## Architecture

```
Browser (WebSocket)
       │
       ▼
FastAPI  (/ws)
       │  streams JSON tokens
       ▼
LangGraph State Graph
  ┌────────────┐     ┌──────────────┐
  │ Classifier │────>│    Router    │────> END
  └────────────┘     └──────────────┘
   LLM picks             FastMCP
   agent name        dispatches to
   from registry     chosen agent
                          │
             ┌────────────┴────────────┐
             ▼                         ▼
  EmployeeDeploymentQueryAgent     (future agents)
    NL → SQL → execute → table
```

**Message flow:**

1. User sends a message over WebSocket.
2. The app maintains full conversation history per connection.
3. LangGraph runs the **classifier node** — an LLM call that reads `agents_list.json` and picks the best agent (or `"None"` if no agent matches).
4. The **router node** filters the history to only the turns the chosen agent handled, then dispatches via **FastMCP** in-process.
5. The agent generates a response, which is streamed line-by-line back to the browser.
6. The browser renders the response as markdown with an agent-name badge.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) |
| Agent registry & dispatch | [FastMCP](https://github.com/jlowin/fastmcp) |
| LLM client | [LangChain OpenAI](https://github.com/langchain-ai/langchain) via OpenRouter |
| Embeddings | Google Generative AI (`langchain-google-genai`) |
| Vector store | [ChromaDB](https://www.trychroma.com/) |
| Structured DB | SQLite via [SQLAlchemy](https://www.sqlalchemy.org/) |
| PDF parsing | [Docling](https://github.com/DS4SD/docling) |
| Web framework | [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) |
| Frontend | Vanilla JS + WebSocket + [marked.js](https://marked.js.org/) |
| Package manager | [uv](https://docs.astral.sh/uv/) |

---

## Project Structure

```
multi_agent_chat/
├── app/
│   ├── agents/
│   │   ├── agents_list.json                  # Agent registry (read by classifier)
│   │   ├── registry.py                       # FastMCP tool definitions
│   │   └── EmployeeDeploymentQueryAgent/
│   │       ├── agent.py                      # run_agent() entry point
│   │       ├── prompt.py                     # System prompt
│   │       └── tools.py                      # get_schema, execute_sql, format_table
│   ├── data_ingest_scripts/
│   │   ├── ingest_db.py                      # Excel → SQLite ingest
│   │   └── ingest_pdf.py                     # PDF → ChromaDB ingest
│   ├── node_graph/
│   │   ├── classifier.py                     # Classifier LangGraph node
│   │   ├── router.py                         # Router LangGraph node
│   │   ├── graph.py                          # LangGraph compilation
│   │   └── prompt.py                         # Classifier system prompt
│   ├── config.py                             # Env var loading
│   ├── logger.py                             # Rotating file + console logger
│   ├── main.py                               # FastAPI app + WebSocket endpoint
│   └── state.py                              # AgentState TypedDict
├── data/                                     # Drop Excel / PDF files here
├── db/
│   ├── sql/                                  # SQLite database (auto-created)
│   └── chroma/                               # ChromaDB store (auto-created)
├── static/
│   └── index.html                            # Chat UI
├── logs/                                     # Rotating log files (auto-created)
├── docs/
│   └── employee_snapshot_schema.html         # DB schema diagram
├── .env                                      # Secret config (never commit)
├── .env.example                              # Config template
└── pyproject.toml
```

---

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (`pip install uv`)
- An [OpenRouter](https://openrouter.ai/) account (or any OpenAI-spec LLM provider)
- A [Google AI Studio](https://aistudio.google.com/) API key (for PDF embeddings)

---

## Setup

```bash
# 1. Clone the repo
git clone <repo-url>
cd multi_agent_chat

# 2. Install dependencies
uv sync

# 3. Copy and fill in the config
cp .env.example .env
# Edit .env — see Configuration section below
```

---

## Configuration

All configuration is loaded from `.env`. Copy `.env.example` and set the following:

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_BASE_URL` | Yes | — | Base URL of your OpenAI-spec LLM provider (e.g. `https://openrouter.ai/api/v1`) |
| `OPENAI_API_KEY` | Yes | — | API key for the LLM provider |
| `LLM_MODEL` | Yes | — | Model name (e.g. `openai/gpt-4o`, `openai/gpt-oss-120b:free`) |
| `DB_URL` | Yes | — | SQLAlchemy DB URL (e.g. `sqlite:///db/sql/employees.db`) |
| `GEMINI_API_KEY` | PDF only | — | Google AI Studio key — required for `uv run ingest_pdf` |
| `GOOGLE_EMBED_MODEL` | PDF only | — | Google embedding model (e.g. `models/text-embedding-004`, `gemini-embedding-2`) |
| `CHROMA_DIR` | No | `./chroma_db` | Directory where ChromaDB persists its data |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## Running the App

```bash
uv run app
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## Data Ingestion

### Structured data — Excel → SQLite

Place a single `.xlsx` or `.xls` file in the `data/` folder, then run:

```bash
uv run ingest_db
```

This reads every sheet (one employee per sheet), parses the key-value block layout, creates the `employees` and `employee_snapshots` tables if they don't exist, and upserts all rows. Safe to re-run — existing rows are replaced.

### Documents — PDF → ChromaDB

Place one or more `.pdf` files in the `data/` folder, then run:

```bash
uv run ingest_pdf
```

Docling parses each PDF preserving structure and tables, chunks the content semantically, generates Google embeddings, and upserts them into the persistent `documents` ChromaDB collection. Safe to re-run — existing chunks are replaced by ID.

> **First run:** Docling downloads its layout and OCR models (~1 GB) to a local cache. This can take a few minutes but only happens once.

---

## Adding a New Agent

Every agent is a self-contained Python package. Adding one requires changes to **four places only** — no changes to the core graph, router, or WebSocket code are needed.

### Step 1 — Create the agent package

Create the following directory structure. The folder name becomes the agent's identifier everywhere in the system.

```
app/agents/<YourAgentName>/
├── __init__.py       ← empty file
├── agent.py          ← required: run_agent() function
├── prompt.py         ← required: system prompt string
└── tools.py          ← optional: helper functions (DB, APIs, etc.)
```

### Step 2 — Implement `agent.py`

Every agent must expose an **async `run_agent` function** with this exact signature:

```python
# app/agents/YourAgentName/agent.py
import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from app.agents.YourAgentName.prompt import YOUR_AGENT_PROMPT
from app.config import LLM_MODEL, OPENAI_BASE_URL, OPENAI_API_KEY
from app.logger import get_logger

logger = get_logger(__name__)

_llm = ChatOpenAI(
    model=LLM_MODEL,
    openai_api_key=OPENAI_API_KEY,
    openai_api_base=OPENAI_BASE_URL,
    max_tokens=600,
)


async def run_agent(question: str, history: str = "[]") -> str:
    """
    question : the current user question
    history  : JSON string — list of {"role": "user"|"assistant", "content": "..."}
               containing only the previous turns this agent handled
    returns  : response as a plain string (markdown is rendered automatically)
    """
    logger.info("Question received: %s", question)

    # Deserialise agent-specific conversation history
    prior = []
    for msg in json.loads(history):
        if msg["role"] == "user":
            prior.append(HumanMessage(content=msg["content"]))
        else:
            prior.append(AIMessage(content=f"[Result from my previous response]\n{msg['content']}"))

    messages = [
        SystemMessage(content=YOUR_AGENT_PROMPT),
        *prior,
        HumanMessage(content=question),
    ]

    response = await _llm.ainvoke(messages)
    logger.info("Response generated")
    return response.content.strip()
```

Key rules:
- The function **must be `async`**.
- `history` arrives pre-filtered — it only contains turns this specific agent previously handled. No extra filtering needed.
- Return a **plain string**. Markdown is rendered by the UI automatically.

### Step 3 — Write the system prompt

```python
# app/agents/YourAgentName/prompt.py

YOUR_AGENT_PROMPT = """You are a specialist agent that <describe purpose>.

<Add rules, output format requirements, constraints, and examples here.>

Conversation History (if prior turns are provided):
- Previous user messages are earlier questions in this conversation.
- Previous assistant messages show your own prior responses.
- Use history to resolve pronouns and build on previous answers.
"""
```

### Step 4 — Register the tool in `registry.py`

Open `app/agents/registry.py` and add one `@mcp.tool()` function. The **function name must exactly match the agent directory name**.

```python
# app/agents/registry.py

@mcp.tool()
async def YourAgentName(question: str, history: str = "[]") -> str:
    """
    Short description of what this agent does.

    Input: Natural Language Question
    Output: <describe the response format>
    """
    from app.agents.YourAgentName.agent import run_agent
    return await run_agent(question, history)
```

### Step 5 — Describe the agent in `agents_list.json`

The classifier LLM reads this file to decide which agent to route each question to. Write the `description` and `capabilities` clearly — they are injected verbatim into the classifier's system prompt.

```jsonc
// app/agents/agents_list.json
[
  // ... existing agents ...
  {
    "name": "YourAgentName",
    "description": "A clear one-sentence description of what this agent does and the kinds of questions it handles.",
    "capabilities": [
      "specific thing it can do",
      "another thing it can do",
      "the type of data or domain it covers"
    ],
    "input": "Natural Language Question",
    "output": "Description of response format (e.g. plain text, markdown table)"
  }
]
```

### Checklist

- [ ] `app/agents/YourAgentName/__init__.py` created (empty)
- [ ] `app/agents/YourAgentName/agent.py` — `async run_agent(question, history)` implemented
- [ ] `app/agents/YourAgentName/prompt.py` — system prompt written
- [ ] `app/agents/registry.py` — `@mcp.tool()` function added with matching name
- [ ] `app/agents/agents_list.json` — agent entry added with clear description

> **No restart needed for the agent name to be discovered.** The classifier reads `agents_list.json` on each request and `KNOWN_AGENTS` is auto-populated from the `app/agents/` directory at startup. Simply restart the server after adding the new files.

---

## Existing Agents

### EmployeeDeploymentQueryAgent

Converts natural language questions into SQL `SELECT` queries against the employee deployment database and returns the results as a markdown table.

**Activates for:** Questions about employee deployments, project assignments, NPS scores, tech stacks, skills, and any other data in the structured employee database.

**Data source:** SQLite database populated by `uv run ingest_db`.

**How it works:**
1. Introspects the live database schema via SQLAlchemy.
2. Sends schema + agent-scoped conversation history + current question to the LLM.
3. LLM returns a raw SQL `SELECT` query (no other statement types are permitted).
4. Query is executed against the database.
5. Results are formatted as a markdown table and streamed to the browser.

**Limitations:** Read-only (`SELECT` only). Cannot answer questions about data not present in the database.
