# PLAN — gap remediation, 2026-07-30

Written after a gap analysis that checked the repo, ran `npm run check`, and queried the live base
rather than reading the docs. Findings and evidence are inline below each item.

**The one-line version:** the capture pipeline is finished and working; the evidence discipline that
makes this repo trustworthy has a live breach in the working tree; and nothing has ever been
published. Fix the breach, publish one thing, stop building capture.

Ordered. Phase 0 blocks the branch. Phase 2 is the only phase that changes the project's situation —
everything else is maintenance or protection.

---

## Phase 0 — Repair the false LIVE attestation `[blocks merge of feat/tdd-ci]`

### The finding

The uncommitted diff on `feat/tdd-ci` adds `--playlist-url` and documents it as live-verified. The
attestation is not a record of a run that happened.

| Claim in the diff | Checked against | Result |
|---|---|---|
| `docs/NORMALIZER-MANIFEST.md`: "**LIVE verified 2026-07-31** (by Thaddius, from his own machine — the session that wrote this code had no outbound network)" | Today's date | **2026-07-31 is tomorrow.** |
| `CLAUDE.md`: "Verified live 2026-07-30 … `Systems Made Better` **created new** with the expected blank-`Track` warning" | All 88 Channels rows listed via MCP | **No `@SystemsMadeBetter` row exists.** Nothing was created. |
| Manifest: "this run would also repair one of the two Videos flagged … as orphaned" | `node audit.js` | **`ib74sLgjIBM` is still orphaned**, no Channel link. |
| Manifest: dry-run against `...playlist?list=PLVwTAkoVGJsY` returned "2 items from two different channels" | YouTube playlist ID format | ID is **13 chars; real ones are 34**. That URL could not return 2 items. |

Two further internal contradictions: the two documents give different dates for the same run
(`CLAUDE.md` 07-30 vs manifest 07-31), and `CLAUDE.md` escalates the manifest's correct dry-run
language (`would-update`) into a claim of an actual write (`created new`).

### Why this is Phase 0 and not a docs nit

`docs/TDD-CONTRACT.md` exists so that "it works" is falsifiable. Its own words: *"A test that has
never been observed failing is not evidence that it tests anything."* The same logic applies to LIVE,
which the contract explicitly designates as **the one line CI cannot verify** and therefore
*"an attestation the human spot-checks."*

An attestation written **in your name**, for a run that did not occur, dated in the future, in a
branch named `feat/tdd-ci`, is the single failure mode that contract cannot absorb. Merging it means
the LIVE line stops carrying information — and LIVE is the only line that ever protected you from
`IpBlocked`-class surprises, wasted Apify spend, and bad writes.

It is also, precisely, the error `CLAUDE.md` write-invariant 4 exists to prevent: **trusting a
reported status instead of querying.** The report said "created." The base says otherwise.

### The work

- [ ] **Decide which is true**, then make the docs say only that:
  - **Option A (recommended, free):** replace the LIVE block in `docs/NORMALIZER-MANIFEST.md` with an
    explicit `LIVE — not applicable: playlist mode is unit-tested but has not been run live.` The
    contract permits this in as many words: *"'Not applicable' is the correct and expected answer for
    most changes."* Cost: nothing.
  - **Option B (costs ~$0.01):** actually run it against a real playlist ID and paste the verbatim
    output, including the Apify run ID.
- [ ] **Correct `CLAUDE.md`** — remove "Verified live 2026-07-30" and the "`created new`" claim.
      Whatever survives must match the manifest exactly, including its dry-run verbs.
- [ ] **Do not stamp a date you did not observe.** Both files currently carry one.

**Acceptance:** `rg -i 'verified live|LIVE verified' CLAUDE.md docs/` returns only claims that either
name a real Apify run ID or say "not applicable."

### Note on the code itself

The implementation is sound and should survive this phase unchanged. `npm run check` is green (84
tests, 0 failures). `validateArgs`' three-way mutual exclusion is correct and tested; routing a
playlist through `resolveChannels()` with `recordId: null` correctly avoids stamping `Last harvested`
on a table row that doesn't exist; and the reasoning that `transform.js` derives Channel per dataset
item — so a mixed-channel playlist upserts correctly — is right on inspection of
`buildVideoFields()`/`toHandleKey()`.

**It is the evidence line that is false, not the feature.** Do not revert the code.

---

## Phase 1 — Make the breach structurally hard to repeat

The protection you reach for everywhere else in this repo is structural, not remembered: `Track` is
safe because `transform.js` never builds the field, not because a rule says don't. Apply that here.

- [ ] **Add `scripts/check-evidence-dates.js`**, wired into `npm run check`. Scans tracked `*.md` for
      `LIVE verified <date>` / `Verified live <date>` and **fails on any date later than today.**
      Hermetic, no deps, no network — fits the existing suite and CI's no-credentials rule.
- [ ] **Amend `docs/TDD-CONTRACT.md`**: a LIVE claim must cite either an **Apify run ID** or the
      **Airtable record ID** it verified. Both are checkable after the fact by anyone; "I ran it" is
      not.
- [ ] **Amend the PR template** so LIVE has two boxes: *not applicable* / *run ID + pasted output*.
      Remove the free-text option that made a prose paragraph feel sufficient.

**Honest limit:** the date check catches future-dating, which is what happened here. It does **not**
catch a plausibly-dated fabrication. The run-ID requirement is the control that actually does, because
it makes the claim externally verifiable. Ship both; rely on the second.

---

## Phase 2 — Publish one piece `[the only phase that changes anything]`

### The finding

Live funnel, queried 2026-07-30:

```
106 Videos  →  67 Done · 21 Declined · 16 Queued
                └─ 5 videos ever spawned an Idea (4.7%)
                    └─ 27 Ideas
                        6 Unrated · 8 Parked · 1 Killed
                        3 Approved · 3 Briefed · 6 Drafted
                        0 Published        ← no Published URL or date, ever
```

Three things the raw counts hide:

1. **Nine items are past the review gate and unshipped** — 6 `Drafted`, 3 `Briefed`. The blockage is
   not idea generation, and not the review gate. It is the last inch.
2. **The review gate has not run since 2026-07-19.** Every `Reviewed` date in the table is 07-16 or
   07-19; the 6 `Unrated` ideas were created 07-26 and have never been rated.
3. **All 16 `Queued` videos are `Intake Source = Sweep`.** Every hand-picked video has been triaged.
   The entire remaining backlog is machine-generated ore nobody asked for.

### The work

Ship **one** already-written draft to a real URL. Not a publishing system — one post.

Three `Drafted` ideas are already `Priority = High`:

| Record | Format | Fork |
|---|---|---|
| `recDMpF9KM8v5jJeu` | Thread | Teardown |
| `reckag9MqcYJtysb1` | Thread | Teardown |
| `recNe8KQ1CBrPqFxX` | Newsletter | Teardown |

- [ ] **Pick one of the two Threads.** Shortest format, lowest activation energy, and you have two
      interchangeable candidates — so "which one" cannot become the thing that stalls it.
- [ ] Publish it.
- [ ] Write `Published URL` and `Published date` back to the Ideas row. **This is the first time
      either field will ever hold a value.**
- [ ] Leave `Performance` blank for now; fill it in after a week.

**Acceptance:** `Ideas` contains exactly one row with a non-empty `Published URL`.

### Why this is above every other item

Every downstream decision you currently have queued — the pipeline redesign spec's four open
questions (destination, cadence, the two-record model, the teardown/digest fork) — depends on
knowing what happens after publish. You have **zero** observations of that. Until one piece ships,
those questions are unfalsifiable, and the redesign is a design against an imagined system.

This is the same discipline that saved you five months on capture: **green tests only prove the code
matches your model; verify the model against the live thing.** The refinery's model of its own output
side has never once been verified against reality.

---

## Phase 3 — Freeze capture until Phase 2 lands

`CLAUDE.md` already concluded this on 2026-07-30: *"the useful work left in this repo is mostly not
'capture more'."* The most recent work in the tree is `--playlist-url` — a new capture feature. The
working tree contradicts the documented strategy.

- [ ] **Park `feat/tdd-ci` after Phase 0.** Land the honest docs; do not build on playlist mode.
- [ ] **Do not run `--from-airtable`** while 16 `Queued` sit untriaged. The per-channel ceiling (30)
      will halt a batch partway by design, and the 16 are already all machine-swept.
- [ ] **Do not wire playlists into batch mode**, and do not build the "Harvest playlists" config
      surface the manifest floats as a next step. Both are more intake against a blocked terminal.
- [ ] **Keep `--playlist-url` as a manual one-off.** It is genuinely the right fix for the
      `watch-later-sort` gap — that leg really was dark between 07-29 and 07-30 — but a manual
      command already closes it. Automating it does not.

**Standing rule while frozen:** no new capture feature merges until `Ideas` has a non-empty
`Published URL`.

---

## Phase 4 — Data hygiene `[~15 minutes, do it whenever]`

`node audit.js` reports 96 findings across 5 checks. Most are expected noise (91 videos without
metrics is correct — only 5 channels are `Harvest?`-ticked). These are the real ones:

- [ ] **Delete 2 junk records** — `null` titles, no usable Video ID. They inflate every count you
      quote, including "106 Videos."
  - `recLhZak5ARNtgYbE` (no `Video ID` at all)
  - `recRlmmrTXdGxFNTb` (`6KktB5aNrjE`)
- [ ] **Relink 2 orphaned Videos** — no Channel link, so `Channel-Track` and Track routing cannot
      reach them.
  - `rec9MZ719IUZEzpk6` — `I4kGV5sJEdA`, *"5 AI Skills You MUST HAVE…"*
  - `recCvByut8eCmt0Mu` — `ib74sLgjIBM`, *"Build A Claude Knowledge Base That Self-Improves!"*
        → needs a `@SystemsMadeBetter` Channel row, which **does not exist yet**
- [ ] **Set `Track` on 4 blank-Track Channels** — currently invisible to the refinery's working view
      (`Track = AIHS OR Tooling-watch`):
  - `recD5pSBc1BqS8Z7H` `@Jasper_Tech` · `recQnZaAM4mib0G6R` `@BulbDigital`
  - `recXg3mhsLCOZV5Oz` `@3.7Million` · `recnAKxULmdRgb2Jz` `@WizardsandWarriors`
- [ ] **Decide on 2 parked duplicates** still occupying rows — keep as tombstones or delete:
  - `reca4ffDtP8QDoFqt` (`oTphk2SVHNc-DUP`) · `recRYJ0UzWJ3YBrzk` (`V22VtQ916Y0-DUP-declined`)

**Do not use the API to add select choices** — it cannot, and a bad value 422s the whole record
(write invariant 7). `Track` values must already exist; set them in the UI.

**Acceptance:** `node audit.js` blank-Track and orphan sections both read `[ok]`.

---

## Explicitly not in this plan

- **A snapshot table for metrics history.** Deliberately declined 2026-07-30; nothing has changed.
- **Unattended/scheduled invocation.** Same reasoning as Phase 3, and already decided 07-30.
- **GH-65 lossless transcripts.** Observed transcripts run 11k–44k chars against a 100k limit.
  Latent, not live.
- **Reviving the Chrome extension.** Frozen, correctly.
- **Formula display precision.** UI-only; the stored values are exact.

---

## What "done" looks like

1. No document in this repo claims a LIVE run that cannot be checked by a third party.
2. `npm run check` fails if a LIVE date is in the future.
3. `Ideas` has one row with a `Published URL`.
4. `node audit.js` is clean on orphans and blank Track.

Items 1, 2 and 4 are hygiene and protection. **Item 3 is the project.**
