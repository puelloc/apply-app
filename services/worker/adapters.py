"""Per-ATS field selectors: canonical profile fields -> ATS form selectors.

The worker reads these to fill each ATS's form. Selectors match the fixtures in
services/mock-ats/fixtures and are the target the workflow/agent produces.
"""

from __future__ import annotations

GREENHOUSE = {
    "first_name": "input[name=first_name]",
    "last_name": "input[name=last_name]",
    "email": "input[name=email]",
    "phone": "input[name=phone]",
    "location": "input[name=location]",
    "resume": "input[name=resume]",
    "linkedin": "input[name=linkedin]",
    "website": "input[name=website]",
    "source": "input[name=source]",
    "years": "input[name=years]",
    "work_auth": "select[name=work_auth]",
    "salary": "input[name=salary]",
    "cover_letter": "textarea[name=cover_letter]",
}

LEVER = {
    "name": "input[name=name]",
    "email": "input[name=email]",
    "phone": "input[name=phone]",
    "resume": "input[name=resume]",
    "linkedin": "input[name=linkedin]",
    "website": "input[name=website]",
    "why": "textarea[name=why]",
}

ASHBY = {
    "first_name": "input[name=first_name]",
    "last_name": "input[name=last_name]",
    "email": "input[name=email]",
    "phone": "input[name=phone]",
    "resume": "input[name=resume]",
    "links": "textarea[name=links]",
    "notes": "textarea[name=notes]",
}

ADAPTERS = {"greenhouse": GREENHOUSE, "lever": LEVER, "ashby": ASHBY}


def selector(ats: str, field: str) -> str | None:
    return ADAPTERS.get(ats, {}).get(field)


def fields(ats: str) -> list[str]:
    return list(ADAPTERS.get(ats, {}).keys())
