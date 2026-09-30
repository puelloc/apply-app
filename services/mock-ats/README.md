# mock-ats

Local mock ATS fixtures + a tiny server that records every submit/signup. Used by the S tests
(canary leak, submit guard, profile inspection), the per-ATS adapters (step 6), and the eval set (L1).

## Fixtures (`fixtures/`)

| File | Purpose |
| --- | --- |
| `greenhouse.html` | Greenhouse-style application (personal + questions + EEOC + submit) |
| `lever.html` | Lever-style application |
| `ashby.html` | Ashby-style application |
| `signup.html` | Email + password account creation (S1 canary + step 7 account flow) |
| `canary.txt` | The fake password used by S1 (never a real secret) |

## Server (`server.py`)

Serves the fixtures over HTTP and **appends every POST to `submissions.log`** (and stdout). That is
what lets S1 confirm the signup happened and S2 confirm *zero* submits arrive.

```bash
python3 server.py 8000
```

## S1 canary leak test

`scripts/canary-grep.sh` greps the known leak surfaces for the canary value; zero hits = pass. The
browser-signup step and the browser-profile/screenshot/trace targets are wired in step 5 (when the
browser service exists).
