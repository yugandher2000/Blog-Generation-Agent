import json
import os
import re

from langchain_community.tools.tavily_search import TavilySearchResults

from src.states.blogstate import BlogState, Blog, SEOMeta


def _get_blog(state: BlogState) -> Blog:
    """Helper: safely extract Blog from state regardless of type."""
    blog = state.get("blog", Blog())
    if isinstance(blog, Blog):
        return blog
    if isinstance(blog, dict):
        return Blog(**blog)
    return Blog()


def _parse_json(text: str) -> dict:
    """Helper: extract first JSON object from LLM response text."""
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return {}


class BlogNode:
    """All pipeline nodes for the blog generation agent."""

    def __init__(self, llm):
        self.llm = llm

    # ── 1. Topic Validator ──────────────────────────────────────────────────────
    def topic_validator(self, state: BlogState):
        """Validate and optionally refine the blog topic."""
        topic = state.get("topic", "")
        prompt = f"""You are a content moderator. Evaluate if this blog topic is valid,
safe, and appropriate: "{topic}"

Return ONLY valid JSON:
{{"is_valid": true, "refined_topic": "improved topic here", "reason": "explanation"}}"""

        response = self.llm.invoke(prompt)
        try:
            result = _parse_json(response.content)
            is_valid = result.get("is_valid", True)
            refined = result.get("refined_topic", topic)
            reason = result.get("reason", "")
            return {
                "topic_valid": is_valid,
                "topic": refined if is_valid else topic,
                "error": "" if is_valid else reason,
            }
        except Exception:
            return {"topic_valid": True, "error": ""}

    # ── 2. Research Node (Tavily) ───────────────────────────────────────────────
    def research_node(self, state: BlogState):
        """Fetch real-world facts using Tavily web search."""
        topic = state.get("topic", "")
        try:
            tool = TavilySearchResults(
                max_results=5,
                tavily_api_key=os.getenv("TAVILY_API_KEY"),
            )
            results = tool.invoke(topic)
            research_text = "\n\n".join(
                f"[Source {i + 1}] {r.get('content', '')}"
                for i, r in enumerate(results)
                if r.get("content")
            )
        except Exception as e:
            research_text = f"Research unavailable: {e}"
            print(f"[research_node] Tavily error: {e}")

        return {"research_context": research_text}

    # ── 3. Outline Generator ───────────────────────────────────────────────────
    def outline_generator(self, state: BlogState):
        """Generate a structured blog outline from the topic and research."""
        topic = state.get("topic", "")
        language = state.get("language", "English")
        research = state.get("research_context", "")

        prompt = f"""You are an expert blog strategist. Create a detailed blog outline for: "{topic}"

Research Context:
{research[:2000]}

Include:
- Introduction
- 5-7 main sections with 2-3 subsections each
- Key points and statistics to cover in each section
- Conclusion

Write the outline in {language}. Use Markdown formatting."""

        response = self.llm.invoke(prompt)
        return {"outline": response.content}

    # ── 4. Title Creation ──────────────────────────────────────────────────────
    def title_creation(self, state: BlogState):
        """Create an SEO-friendly blog title using the outline."""
        topic = state.get("topic", "")
        language = state.get("language", "English")
        outline = state.get("outline", "")

        prompt = f"""You are an expert blog writer. Generate ONE creative, SEO-friendly blog title
for the topic: "{topic}"

Blog Outline:
{outline[:600]}

Write the title in {language}. Return ONLY the title text, nothing else."""

        response = self.llm.invoke(prompt)
        return {"blog": Blog(title=response.content.strip())}

    # ── 5. Content Generation ─────────────────────────────────────────────────
    def content_generation(self, state: BlogState):
        """Generate full blog content guided by outline and research."""
        topic = state.get("topic", "")
        language = state.get("language", "English")
        outline = state.get("outline", "")
        research = state.get("research_context", "")
        blog = _get_blog(state)

        prompt = f"""You are an expert blog writer. Write a detailed, engaging blog post.

Title: {blog.title}
Topic: {topic}

Follow this outline strictly:
{outline}

Use these research facts where relevant:
{research[:2000]}

Requirements:
- Use Markdown formatting (##, ###, **, bullet points, tables)
- Write in {language}
- Minimum 800 words
- Include real examples and statistics from the research
- Make it professional and engaging"""

        response = self.llm.invoke(prompt)
        return {"blog": Blog(title=blog.title, content=response.content)}

    # ── 6. SEO Optimizer ──────────────────────────────────────────────────────
    def seo_optimizer(self, state: BlogState):
        """Extract SEO keywords, meta description, slug and tags."""
        blog = _get_blog(state)
        topic = state.get("topic", "")

        prompt = f"""You are an SEO expert. Analyze this blog and generate SEO metadata.

Topic: {topic}
Blog Title: {blog.title}
Content Preview: {blog.content[:1000]}

Return ONLY valid JSON:
{{
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "meta_description": "Compelling 155-160 character description here",
  "slug": "url-friendly-slug-here",
  "tags": ["tag1", "tag2", "tag3", "tag4"]
}}"""

        response = self.llm.invoke(prompt)
        try:
            result = _parse_json(response.content)
            return {
                "seo": SEOMeta(
                    keywords=result.get("keywords", []),
                    meta_description=result.get("meta_description", ""),
                    slug=result.get("slug", ""),
                    tags=result.get("tags", []),
                )
            }
        except Exception:
            return {"seo": SEOMeta()}

    # ── 7. Quality Checker ────────────────────────────────────────────────────
    def quality_checker(self, state: BlogState):
        """Score blog quality 1-10 and provide improvement feedback."""
        blog = _get_blog(state)

        prompt = f"""You are a senior blog editor. Score this blog content on a scale of 1-10.

Blog Title: {blog.title}
Content:
{blog.content[:2000]}

Evaluate: readability, depth, structure, engagement, use of examples.

Return ONLY valid JSON:
{{"score": 8, "feedback": "Specific improvement suggestions. Be detailed if score < 7."}}"""

        response = self.llm.invoke(prompt)
        try:
            result = _parse_json(response.content)
            score = max(1, min(10, int(result.get("score", 7))))
            return {
                "quality_score": score,
                "quality_feedback": result.get("feedback", ""),
            }
        except Exception:
            return {"quality_score": 7, "quality_feedback": ""}

    # ── 8. Content Rewriter ───────────────────────────────────────────────────
    def content_rewriter(self, state: BlogState):
        """Rewrite blog content based on quality checker feedback."""
        blog = _get_blog(state)
        feedback = state.get("quality_feedback", "")
        language = state.get("language", "English")
        rewrite_count = state.get("rewrite_count", 0)

        prompt = f"""You are an expert blog editor. Significantly improve this blog based on the feedback.

Feedback to address:
{feedback}

Current Blog:
{blog.content}

Requirements:
- Address ALL feedback points
- Keep the same title
- Write in {language}
- Use Markdown formatting
- Maintain or increase length"""

        response = self.llm.invoke(prompt)
        return {
            "blog": Blog(title=blog.title, content=response.content),
            "rewrite_count": rewrite_count + 1,
        }

    # ── 9. Translator ─────────────────────────────────────────────────────────
    def translator(self, state: BlogState):
        """Translate blog to target language if not English."""
        language = state.get("language", "English")
        if language.strip().lower() == "english":
            return {}  # no-op

        blog = _get_blog(state)
        prompt = f"""You are a professional translator. Translate this blog post to {language}.

Title: {blog.title}

Content:
{blog.content}

Rules:
- Preserve ALL Markdown formatting (##, ###, **, *, -, |, >, ```)
- Translate naturally, not word-for-word
- First line of your response = translated title
- Remaining lines = translated content"""

        response = self.llm.invoke(prompt)
        lines = response.content.strip().split('\n')
        translated_title = lines[0].strip() if lines else blog.title
        translated_content = '\n'.join(lines[1:]).strip() if len(lines) > 1 else response.content
        return {"blog": Blog(title=translated_title, content=translated_content)}

    # ── 10. Formatter ─────────────────────────────────────────────────────────
    def formatter(self, state: BlogState):
        """Convert final blog to requested output format (markdown/html/json)."""
        output_format = state.get("output_format", "markdown").lower()
        blog = _get_blog(state)
        seo = state.get("seo", SEOMeta())
        seo_obj = seo if isinstance(seo, SEOMeta) else SEOMeta(**seo) if isinstance(seo, dict) else SEOMeta()

        if output_format == "html":
            try:
                import markdown as md_lib
                html_content = md_lib.markdown(blog.content, extensions=["tables", "fenced_code"])
                html_title = md_lib.markdown(blog.title)
            except ImportError:
                html_content = f"<pre>{blog.content}</pre>"
                html_title = f"<h1>{blog.title}</h1>"
            formatted = (
                f'<!DOCTYPE html>\n<html>\n<head>\n'
                f'  <meta charset="UTF-8">\n'
                f'  <title>{blog.title}</title>\n'
                f'  <meta name="description" content="{seo_obj.meta_description}">\n'
                f'  <meta name="keywords" content="{", ".join(seo_obj.keywords)}">\n'
                f'</head>\n<body>\n{html_title}\n{html_content}\n</body>\n</html>'
            )
        elif output_format == "json":
            formatted = json.dumps({
                "title": blog.title,
                "content": blog.content,
                "seo": {
                    "keywords": seo_obj.keywords,
                    "meta_description": seo_obj.meta_description,
                    "slug": seo_obj.slug,
                    "tags": seo_obj.tags,
                },
            }, indent=2, ensure_ascii=False)
        else:  # markdown (default)
            formatted = f"{blog.title}\n\n{blog.content}"

        return {"formatted_output": formatted}
