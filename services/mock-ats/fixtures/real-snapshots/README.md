# Real-form snapshots (for the L1 eval set)

Real ATS form HTML captured from actual applications, then sanitized so no real data or company
identifiers leak into the repo. These feed the L1 eval set (step 10) so field-mapping accuracy is
measured against realistic forms, not just mocks.

**Capture is GATED on rule 8** — no real job sites until N1–N6, S1, and S2 pass.

## Capture procedure (once rule 8 is satisfied)

1. In a review/browser session, open a real application form.
2. Save the page HTML ("Save page as") to a temp file outside the repo.
3. Write every company/job identifier (company name, job title, email domain) to a `terms.txt`, one per line.
4. Sanitize it:

   ```bash
   python3 ../sanitize.py captured.html terms.txt > snapshot-<ats>-<n>.html
   ```

5. Commit only the sanitized file; delete the raw capture and `terms.txt`.

## What `sanitize.py` redacts

- email addresses → `REDACTED@example.invalid`
- phone numbers  → `REDACTED-PHONE`
- URLs           → `REDACTED-URL`
- every term in `terms.txt` → `REDACTED`

Snapshots live here, named `snapshot-<ats>-<n>.html` (e.g. `snapshot-greenhouse-01.html`).
