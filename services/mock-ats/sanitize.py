"""Sanitize a captured real-form snapshot for the eval set.

Removes obvious personal/company identifiers before a snapshot is committed, so no real data or
company info leaks into the repo. Company-specific terms are redacted from a terms file.

Usage:  python3 sanitize.py <captured.html> <terms.txt> > snapshot.html
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "REDACTED@example.invalid"),
    (re.compile(r"\+?\d[\d\s().-]{7,}\d"), "REDACTED-PHONE"),
    (re.compile(r"https?://[^\s\"'<>]+"), "REDACTED-URL"),
]


def sanitize(text: str, terms: list[str]) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    for term in terms:
        text = re.sub(re.escape(term), "REDACTED", text, flags=re.IGNORECASE)
    return text


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python3 sanitize.py <captured.html> [terms.txt]", file=sys.stderr)
        raise SystemExit(2)
    text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
    terms: list[str] = []
    if len(sys.argv) > 2:
        terms = [line.strip() for line in Path(sys.argv[2]).read_text().splitlines() if line.strip()]
    sys.stdout.write(sanitize(text, terms))


if __name__ == "__main__":
    main()
