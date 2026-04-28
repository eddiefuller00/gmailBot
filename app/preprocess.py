from __future__ import annotations

import re


THREAD_MARKERS = [
    r"^On .+ wrote:$",
    r"^From:\s",
    r"^Sent:\s",
    r"^-----Original Message-----$",
]

HTML_COMMENT_PATTERN = re.compile(r"<!--.*?-->", flags=re.DOTALL | re.IGNORECASE)
SCRIPT_STYLE_PATTERN = re.compile(
    r"<(?:script|style)\b[^>]*>.*?</(?:script|style)>",
    flags=re.DOTALL | re.IGNORECASE,
)
ANCHOR_WITH_HREF_PATTERN = re.compile(
    r"<a\b[^>]*\bhref=['\"]([^'\"]+)['\"][^>]*>.*?</a>",
    flags=re.DOTALL | re.IGNORECASE,
)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
ANGLE_BRACKET_URL_PATTERN = re.compile(r"<(https?://[^>\s]+)>", flags=re.IGNORECASE)
CSS_DECLARATION_PATTERN = re.compile(r"\b[a-z-]{2,30}\s*:\s*[^;]{0,120};", flags=re.IGNORECASE)
CSS_SELECTOR_PATTERN = re.compile(
    r"(?:^|\s)[.#][a-z0-9_-]{2,40}\s*(?=\{)",
    flags=re.IGNORECASE,
)
CURLY_BLOCK_PATTERN = re.compile(r"\{[^{}]{0,280}\}")
CSS_MEDIA_QUERY_FRAGMENT_PATTERN = re.compile(
    r"\(\s*(?:max|min)-width\s*:\s*\d{2,4}px\s*\)",
    flags=re.IGNORECASE,
)
CSS_PSEUDO_SELECTOR_PATTERN = re.compile(
    r"[.#][a-z0-9_-]{2,60}:[a-z-]{2,30}",
    flags=re.IGNORECASE,
)
CSS_CLASS_TOKEN_PATTERN = re.compile(
    r"[.#]css-[a-z0-9_-]{2,60}",
    flags=re.IGNORECASE,
)
CSS_PROPERTY_NOISE_PATTERN = re.compile(
    r"\b(?:"
    r"margin|padding|font-family|text-decoration|border-spacing|border-collapse|"
    r"(?:max|min)-width|line-height|display|text-size-adjust|"
    r"-webkit-text-size-adjust|-ms-text-size-adjust"
    r")\s*:\s*[^;\n]{0,100}(?:!important)?;?",
    flags=re.IGNORECASE,
)

HTML_NOISE_TERMS = [
    "x-apple-data-detectors-type",
    "mso-",
    "@media",
    "#outlook",
    "font-family",
    "text-size-adjust",
    "border-collapse",
    "webkit",
]


def _strip_html_css_noise(text: str) -> str:
    text = ANGLE_BRACKET_URL_PATTERN.sub(r" \1 ", text)
    text = HTML_COMMENT_PATTERN.sub(" ", text)
    text = SCRIPT_STYLE_PATTERN.sub(" ", text)
    text = ANCHOR_WITH_HREF_PATTERN.sub(r" \1 ", text)
    text = CSS_DECLARATION_PATTERN.sub(" ", text)
    text = CSS_SELECTOR_PATTERN.sub(" ", text)
    text = CSS_MEDIA_QUERY_FRAGMENT_PATTERN.sub(" ", text)
    text = CSS_PSEUDO_SELECTOR_PATTERN.sub(" ", text)
    text = CSS_CLASS_TOKEN_PATTERN.sub(" ", text)
    text = CSS_PROPERTY_NOISE_PATTERN.sub(" ", text)
    for _ in range(3):
        text = CURLY_BLOCK_PATTERN.sub(" ", text)
    text = HTML_TAG_PATTERN.sub(" ", text)

    for term in HTML_NOISE_TERMS:
        text = re.sub(re.escape(term), " ", text, flags=re.IGNORECASE)
    return text


def clean_email_body(body: str) -> str:
    lines = body.splitlines()
    cleaned_lines: list[str] = []

    for line in lines:
        if any(re.match(pattern, line.strip()) for pattern in THREAD_MARKERS):
            break
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)
    text = _strip_html_css_noise(text)
    text = re.sub(r"\n--\s*\n.*", "", text, flags=re.DOTALL)
    text = re.sub(r"[{}<>#]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
