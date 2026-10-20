"""Optional LangGraph implementation of the offline evidence workflow.

Install `.[graph]`. The API uses the dependency-free workflow by default.
This adapter is intentionally separate from durable job storage and approvals.
"""
from typing import TypedDict, Any
from .tools import ToolBox
from .investigate import collect_offline, draft_offline, validate_diagnosis

class State(TypedDict,total=False):
    ranking: dict
    diagnosis: dict
    evidence: list

def build_graph(incident,predictor,emit):
    from langgraph.graph import StateGraph, START, END
    box=ToolBox(incident)
    def rank(state):return {"ranking":predictor.rank(incident)}
    def gather(state):
        collect_offline(state["ranking"],box,emit)
        return {"evidence":list(box.registry.items.values())}
    def draft(state):return {"diagnosis":draft_offline(state["ranking"],box).model_dump()}
    def validate(state):
        from tracelens.schema import Diagnosis
        validate_diagnosis(Diagnosis.model_validate(state["diagnosis"]),box)
        return {}
    graph=StateGraph(State)
    for name,fn in [("rank",rank),("gather",gather),("draft",draft),("validate",validate)]:graph.add_node(name,fn)
    graph.add_edge(START,"rank");graph.add_edge("rank","gather");graph.add_edge("gather","draft")
    graph.add_edge("draft","validate");graph.add_edge("validate",END)
    return graph.compile()
