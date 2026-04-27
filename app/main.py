import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from app.node_graph.graph import graph
from app.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(title="Multi-Agent Chat")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket client connected")
    history: list[BaseMessage] = []
    try:
        while True:
            user_text = await websocket.receive_text()
            logger.info("Received message: %s", user_text)
            history.append(HumanMessage(content=user_text))

            await websocket.send_json({"type": "start"})

            full_response = ""
            error_text = None

            async for event in graph.astream_events(
                {"messages": history, "agent_name": None, "error": None},
                version="v2",
            ):
                if event["event"] == "on_chain_end" and event["name"] == "classifier":
                    agent_name = event["data"].get("output", {}).get("agent_name", "")
                    await websocket.send_json({"type": "agent", "name": agent_name})

                elif event["event"] == "on_chain_end" and event["name"] == "router":
                    output = event["data"].get("output", {})
                    if output.get("error"):
                        error_text = output["error"]
                    elif output.get("messages"):
                        content = output["messages"][-1].content
                        for chunk in content.splitlines(keepends=True):
                            await websocket.send_json({"type": "chunk", "text": chunk})
                            full_response += chunk

            if error_text:
                logger.error("Graph returned error: %s", error_text)
                await websocket.send_json({"type": "error", "text": f"Error: {error_text}"})
            else:
                history.append(AIMessage(content=full_response))
                logger.info("Response sent to client")
                await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")


def main():
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)