import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from src.graphs.graph_builder import GraphBuilder
from src.llms.groqllm import GroqLLM
from src.states.blogstate import Blog, SEOMeta

import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="Blog Generation Agent",
    description="AI-powered blog generation using LangGraph & Groq with Tavily research",
    version="2.0.0"
)

os.environ["LANGSMITH_API_KEY"] = os.getenv("LANGCHAIN_API_KEY", "")


# ── Request / Response Models ──────────────────────────────────────────────────

class BlogRequest(BaseModel):
    topic: str = Field(..., description="The topic to generate a blog post about", examples=["OpenText"])
    language: str = Field(default="English", description="Language for the blog post", examples=["English", "French", "Spanish", "German", "Telugu", "Hindi"])
    output_format: str = Field(default="markdown", description="Output format: markdown | html | json", examples=["markdown", "html", "json"])


class SEOResponse(BaseModel):
    keywords: List[str]
    meta_description: str
    slug: str
    tags: List[str]


class BlogContent(BaseModel):
    title: str = Field(description="Blog post title")
    content: str = Field(description="Full blog post body")
    word_count: int = Field(description="Approximate word count")
    reading_time_minutes: int = Field(description="Estimated reading time in minutes")


class BlogResponse(BaseModel):
    status: str = Field(description="Request status", examples=["success"])
    topic: str = Field(description="The requested topic")
    language: str = Field(description="Language the blog was written in")
    output_format: str = Field(description="Format of the formatted_output field")
    quality_score: int = Field(description="Quality score (1-10) from the quality checker")
    rewrite_count: int = Field(description="Number of rewrites performed")
    seo: SEOResponse = Field(description="SEO metadata")
    blog: BlogContent = Field(description="Blog title and content")
    formatted_output: str = Field(description="Final output in requested format")


# ── Helper ─────────────────────────────────────────────────────────────────────

def estimate_reading_time(text: str) -> tuple[int, int]:
    """Returns (word_count, reading_time_minutes) assuming 200 wpm."""
    words = len(text.split())
    minutes = max(1, round(words / 200))
    return words, minutes


def _safe_blog(blog) -> Blog:
    if isinstance(blog, Blog):
        return blog
    if isinstance(blog, dict):
        return Blog(**blog)
    return Blog()


def _safe_seo(seo) -> SEOMeta:
    if isinstance(seo, SEOMeta):
        return seo
    if isinstance(seo, dict):
        return SEOMeta(**seo)
    return SEOMeta()


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.post("/blogs", response_model=BlogResponse, summary="Generate a blog post")
async def create_blogs(request: BlogRequest):
    topic = request.topic.strip()
    language = request.language.strip() or "English"
    output_format = request.output_format.strip().lower() or "markdown"

    if not topic:
        raise HTTPException(status_code=400, detail="'topic' must not be empty.")
    if output_format not in ("markdown", "html", "json"):
        raise HTTPException(status_code=400, detail="output_format must be 'markdown', 'html', or 'json'.")

    groqllm = GroqLLM()
    llm = groqllm.get_llm()

    graph_builder = GraphBuilder(llm)
    graph = graph_builder.setup_graph(usecase="topic")

    state = graph.invoke({
        "topic": topic,
        "language": language,
        "output_format": output_format,
        "topic_valid": True,
        "error": "",
        "research_context": "",
        "outline": "",
        "blog": Blog(),
        "seo": SEOMeta(),
        "quality_score": 0,
        "quality_feedback": "",
        "rewrite_count": 0,
        "formatted_output": "",
    })

    # Handle invalid topic
    if not state.get("topic_valid", True):
        raise HTTPException(status_code=422, detail=state.get("error", "Invalid topic."))

    blog = _safe_blog(state.get("blog"))
    seo = _safe_seo(state.get("seo"))
    word_count, reading_time = estimate_reading_time(blog.content)

    return BlogResponse(
        status="success",
        topic=state.get("topic", topic),
        language=language,
        output_format=output_format,
        quality_score=state.get("quality_score", 0),
        rewrite_count=state.get("rewrite_count", 0),
        seo=SEOResponse(
            keywords=seo.keywords,
            meta_description=seo.meta_description,
            slug=seo.slug,
            tags=seo.tags,
        ),
        blog=BlogContent(
            title=blog.title,
            content=blog.content,
            word_count=word_count,
            reading_time_minutes=reading_time,
        ),
        formatted_output=state.get("formatted_output", blog.content),
    )


@app.get("/health", summary="Health check")
async def health():
    return {"status": "ok", "version": "2.0.0"}


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
