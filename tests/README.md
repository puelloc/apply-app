# tests/

Verification tests live here as they are built. Status for every test (O1–L1) is tracked in
`docs/PLAN.md` under **Verification log**; never mark a test passed without pasted-back evidence.

Suites (built in later steps):

| Suite | Tests | Build step |
| --- | --- | --- |
| Network isolation | N1–N6 | 1 |
| Mock ATS + canary | S1–S5 (S1 in CI) | 2 |
| Email | E1–E4 | 7 |
| Resilience | R1–R4 | 11 |
| Model eval | L1 | 10 |

Step-0 spikes (P1–P5, O1–O6, W1–W3) run on the Pi / Ollama box via `scripts/spikes/`, not in this
folder.
