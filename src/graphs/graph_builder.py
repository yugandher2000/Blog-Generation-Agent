from langgraph.graph import StateGraph, START, END
from src.llms.groqllm import GroqLLM
from src.states.blogstate import BlogState
from src.nodes.blog_node import BlogNode


# ── Conditional Edge Routing Functions ────────────────────────────────────────

def route_after_validation(state: BlogState) -> str:
    """Route to research if topic is valid, else END."""
    if state.get("topic_valid", True):
        return "research_node"
    return END


def route_after_quality(state: BlogState) -> str:
    """Loop back to rewriter if score < 7 and rewrites < 3, else proceed."""
    score = state.get("quality_score", 10)
    rewrite_count = state.get("rewrite_count", 0)
    if score < 7 and rewrite_count < 3:
        return "content_rewriter"
    return "translator"


# ── Graph Builder ─────────────────────────────────────────────────────────────

class GraphBuilder:
    def __init__(self, llm):
        self.llm = llm
        self.graph = StateGraph(BlogState)

    def build_topic_graph(self):
        """
        Full enhanced pipeline:
        START → topic_validator → research_node → outline_generator
              → title_creation → content_generation → seo_optimizer
              → quality_checker ⟲ content_rewriter (loop ≤3)
              → translator → formatter → END
        """
        node = BlogNode(self.llm)

        # ── Register all nodes ────────────────────────────────────────────────
        self.graph.add_node("topic_validator",    node.topic_validator)
        self.graph.add_node("research_node",      node.research_node)
        self.graph.add_node("outline_generator",  node.outline_generator)
        self.graph.add_node("title_creation",     node.title_creation)
        self.graph.add_node("content_generation", node.content_generation)
        self.graph.add_node("seo_optimizer",      node.seo_optimizer)
        self.graph.add_node("quality_checker",    node.quality_checker)
        self.graph.add_node("content_rewriter",   node.content_rewriter)
        self.graph.add_node("translator",         node.translator)
        self.graph.add_node("formatter",          node.formatter)

        # ── Wire edges ────────────────────────────────────────────────────────
        self.graph.add_edge(START, "topic_validator")

        # Conditional: valid topic → research, invalid → END
        self.graph.add_conditional_edges(
            "topic_validator",
            route_after_validation,
            {"research_node": "research_node", END: END},
        )

        self.graph.add_edge("research_node",      "outline_generator")
        self.graph.add_edge("outline_generator",  "title_creation")
        self.graph.add_edge("title_creation",     "content_generation")
        self.graph.add_edge("content_generation", "seo_optimizer")
        self.graph.add_edge("seo_optimizer",      "quality_checker")

        # Conditional: low quality → rewrite (loop), good quality → translate
        self.graph.add_conditional_edges(
            "quality_checker",
            route_after_quality,
            {"content_rewriter": "content_rewriter", "translator": "translator"},
        )

        # Rewrite loops back to quality_checker for re-evaluation
        self.graph.add_edge("content_rewriter", "quality_checker")

        self.graph.add_edge("translator", "formatter")
        self.graph.add_edge("formatter",  END)

        return self.graph

    def setup_graph(self, usecase: str):
        if usecase == "topic":
            self.build_topic_graph()
        return self.graph.compile()


# ── LangGraph Studio entry-point ──────────────────────────────────────────────
llm = GroqLLM().get_llm()
graph_builder = GraphBuilder(llm)
graph = graph_builder.build_topic_graph().compile()
