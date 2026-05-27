from typing import TypedDict, List
from pydantic import BaseModel, Field


class Blog(BaseModel):
    title: str = Field(default="", description="the title of the blog post")
    content: str = Field(default="", description="The main content of the blog post")


class SEOMeta(BaseModel):
    keywords: List[str] = Field(default_factory=list, description="SEO keywords")
    meta_description: str = Field(default="", description="Meta description (max 160 chars)")
    slug: str = Field(default="", description="URL-friendly slug")
    tags: List[str] = Field(default_factory=list, description="Blog tags")


class BlogState(TypedDict):
    # ── Input ──────────────────────────────
    topic: str
    language: str            # e.g. "English", "French", "Tamil"
    output_format: str       # "markdown" | "html" | "json"

    # ── Validation ─────────────────────────
    topic_valid: bool
    error: str

    # ── Research & Planning ─────────────────
    research_context: str
    outline: str

    # ── Blog Content ────────────────────────
    blog: Blog

    # ── SEO ────────────────────────────────
    seo: SEOMeta

    # ── Quality Loop ───────────────────────
    quality_score: int
    quality_feedback: str
    rewrite_count: int

    # ── Final Output ───────────────────────
    formatted_output: str
