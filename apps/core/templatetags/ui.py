"""Small presentation helpers used across templates."""
import bleach
import markdown as md
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

ALLOWED_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "code", "del", "em", "h1", "h2", "h3",
    "h4", "h5", "h6", "hr", "i", "li", "ol", "p", "pre", "s", "span", "strong",
    "sub", "sup", "table", "tbody", "td", "th", "thead", "tr", "ul",
}
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel", "target"],
    "code": ["class"],
    "span": ["class"],
    "th": ["align"],
    "td": ["align"],
}
ALLOWED_PROTOCOLS = {"http", "https", "mailto"}


@register.filter(name="markdownify")
def markdownify(value):
    """Render Markdown to sanitized HTML."""
    if not value:
        return ""
    html = md.markdown(
        str(value),
        extensions=["fenced_code", "tables", "sane_lists", "nl2br"],
        output_format="html",
    )
    clean = bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
    return mark_safe(clean)


@register.filter(name="percentage")
def percentage(value, total):
    try:
        total = float(total)
        if total <= 0:
            return 0
        return round((float(value) / total) * 100, 1)
    except (TypeError, ValueError):
        return 0


@register.filter(name="initials")
def initials(value):
    text = (value or "").strip()
    if not text:
        return "AI"
    parts = text.split()
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()
