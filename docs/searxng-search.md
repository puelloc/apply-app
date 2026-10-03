# SearXNG Search (self-hosted)

Free keyless meta-search via the self-hosted SearXNG instance on the LAN. Use this for web searches —
the built-in `web_search` plugin's endpoint is misconfigured (points at a chat endpoint), so search
goes through `curl` + the SearXNG JSON API instead.

**Instance:** `https://search.siggy-lab.org` (HTTP 301-redirects to HTTPS). JSON API confirmed working.

## Detection

```bash
curl -s --max-time 10 "https://search.siggy-lab.org/search?q=test&format=json" | head -c 200
```

Should return `{"query": "test", "results": [...]}`.

## Search (curl, preferred)

```bash
curl -s --max-time 10 "https://search.siggy-lab.org/search?q=<url-encoded-query>&format=json&limit=10"
```

Common params:

| Param | Meaning |
| --- | --- |
| `q` | Query (URL-encoded) |
| `format=json` | Machine-readable output (always request this) |
| `engines` | Comma-separated engine names (e.g. `google,bing,ddg`) |
| `limit` | Max results per engine (default 10) |
| `categories` | `general`, `news`, `science`, … |
| `safesearch` | 0=none, 1=moderate, 2=strict |
| `time_range` | `day`, `week`, `month`, `year` |

## Parse results

```bash
curl -s "https://search.siggy-lab.org/search?q=fastapi&format=json&limit=5" \
  | python3 -c "
import json, sys
for r in json.load(sys.stdin).get('results', []):
    print(r.get('title',''))
    print(r.get('url',''))
    print((r.get('content','') or '')[:200])
    print()
"
```

Each result has `title`, `url`, `content` (snippet), `engine`, `parsed_url`, `published_date`.

## Workflow

SearXNG returns snippets, not full pages. Search first, then `web_fetch` the most relevant URL for
full content.

## Pitfalls

- URL-encode the query (`+` for spaces, or use `urllib.parse.quote`).
- Always `format=json` + `--max-time` to avoid hangs.
- Instance is LAN-internal (`search.siggy-lab.org`); it is reachable from the agent sandbox.
