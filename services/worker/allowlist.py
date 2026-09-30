"""Build the per-job domain allowlist for the egress proxy.

The egress proxy (services/egress-proxy) applies a suffix-based allowlist on top of its
private-range denial. This module computes the suffixes a job may reach: the ATS host, its apex
(for same-org SSO/asset redirects), plus a fixed set of CDN/font/SSO hosts ATS pages load.

Caveat: for multi-tenant ATS (e.g. Workday's `*.myworkdayjobs.com`) the apex is broad. The exact
host is always included, so the job's specific tenant is allowed; tightening the apex per ATS is a
step-6 refinement once ATS detection lands.
"""

from __future__ import annotations

from urllib.parse import urlparse

# Domains ATS pages commonly load that aren't the ATS itself: CDNs, fonts, SSO, captcha, media.
_COMMON_SUFFIXES = [
    "googleapis.com", "gstatic.com", "google.com", "googletagmanager.com",
    "google-analytics.com", "googlesyndication.com", "doubleclick.net",
    "cloudflare.com", "cloudflareinsights.com", "cdnjs.cloudflare.com",
    "jsdelivr.net", "unpkg.com",
    "hcaptcha.com", "recaptcha.net", "okta.com", "auth0.com",
    "stripe.com", "js.stripe.com",
    "linkedin.com", "licdn.com",
]


def apex(host: str) -> str:
    """Registrable domain (last two labels) — the suffix that covers same-org subdomains."""
    parts = host.lower().split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host.lower()


def build_allowlist(application_url: str, extra: list[str] | None = None) -> list[str]:
    """Return deduped, lowercased allowlist suffixes for a job's application URL."""
    host = (urlparse(application_url).hostname or "").lower()
    suffixes = [host, apex(host)] if host else []
    suffixes.extend(_COMMON_SUFFIXES)
    suffixes.extend(extra or [])

    out: list[str] = []
    seen: set[str] = set()
    for s in suffixes:
        s = s.strip().lower().lstrip(".")
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out
