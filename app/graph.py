from langgraph.graph import StateGraph, END
from app.state import AgentState
from app.nodes.classifier import classifier_node
from app.nodes.router import router_node

state_graph = StateGraph(AgentState)
state_graph.add_node("classifier", classifier_node)
state_graph.add_node("router", router_node)
state_graph.set_entry_point("classifier")
state_graph.add_edge("classifier", "router")
state_graph.add_edge("router", END)

graph = state_graph.compile()