from __future__ import annotations

import re


THREAD_MARKERS = [
    r"^On .+ wrote:$",
    r"^From:\s",
    r"^Sent:\s",
    r"^-----Original Message-----$",
]


def clean_email_body(body: str) -> str:
    lines = body.splitlines()
    cleaned_lines: list[str] = []

    for line in lines:
        if any(re.match(pattern, line.strip()) for pattern in THREAD_MARKERS):
            break
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)
    text = re.sub(r"\n--\s*\n.*", "", text, flags=re.DOTALL)
    text = re.sub(r"\s+", " ", text).strip()
    return text

