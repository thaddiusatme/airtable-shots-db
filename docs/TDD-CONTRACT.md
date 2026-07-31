# TDD contract

Every change to this repo — human or agent — runs one command and reports four lines of evidence.
That is the whole contract. It exists so a claim like "tests pass" is falsifiable: GitHub re-runs the
same command on every pull request, and the human reviews the evidence instead of supervising each
step.

## The one command

```bash
npm run setup   # once per clone — installs chrome-extension's only dep, jsdom
npm run check   # both suites: chrome-extension, then normalizer
```

`check` runs tests only, so it is fast to re-run inside a red/green loop. It fails fast: if the
extension suite goes red, the normalizer suite does not run. That is deliberate — one clear red.

For a tight loop on one file, `node --test <path>` is fine; `npm run check` is what counts as
regression evidence.

## The four evidence lines

Report all four in the pull request. The template gives you the boxes.

- **RED** — the test you wrote first, and the *actual* failure output. Not "it failed" — paste it.
  A test that has never been observed failing is not evidence that it tests anything.
- **GREEN** — the same focused test passing after the implementation.
- **REGRESSION** — `npm run check` fully green. Both suites.
- **LIVE** — Airtable/Apify verification, **or an explicit "not applicable."** Never blank.

## What LIVE means, and when it is "not applicable"

Unit tests here are hermetic by construction: `normalizer/lib/airtable-client.test.js` stubs
`globalThis.fetch`, and nothing in either suite reads `process.env` or touches the network. Green
tests therefore prove the code matches *our model* of Airtable and Apify — not that the model is
right. LIVE is where you check the model.

When the change touches the Apify → Airtable path, LIVE means the verification in
`.claude/skills/apify-harvest/SKILL.md` and the write invariants in `CLAUDE.md`:

- Query Videos by `Video ID` and confirm exactly one record — a reported `error` can be a false
  negative after a successful save (invariant 4; a misread status flag caused a duplicate on
  2026-07-26).
- Confirm Channels did not fork: one row per channel, `Channel Handle` in `@handle` form, never
  `UC...`.
- Confirm `Triage Status` and `Track` were not touched on update (invariant 3).

**"Not applicable" is the correct and expected answer for most changes** — anything that does not
reach Apify or Airtable. Say so explicitly rather than leaving the box empty.

**LIVE is not free.** A `--dry-run` still runs the actor and still costs roughly $0.004/video. Do not
reach for a live run to satisfy a checkbox.

## What CI does and does not do

`.github/workflows/check.yml` runs `npm run check` on pull requests and on pushes to `master`. It has
**no `AIRTABLE_API_KEY`, no `AIRTABLE_BASE_ID`, no `APIFY_TOKEN`, and no `secrets.` reference at
all** — and it should stay that way. CI verifies RED, GREEN, and REGRESSION. It cannot verify LIVE,
which is why LIVE is an attestation the human spot-checks.

There is deliberately **no pre-commit hook.** TDD has a red stage; a hook that blocks every commit
containing a failing test fights the process. The gate runs before push and in GitHub instead.

## Filing the pull request

`gh pr create --body "..."` **silently ignores** `.github/pull_request_template.md`. Use
`--body-file`, or the prefilled editor, or paste the four boxes yourself.

## Rules this contract does not restate

- Airtable write invariants — `CLAUDE.md`, "Write invariants". Read them before touching
  `normalizer/lib/`.
- Harvest verification and the error playbook — `.claude/skills/apify-harvest/SKILL.md`.
- Why capture works the way it does — `docs/archive/FINDINGS-youtube-automation.md` §1.
