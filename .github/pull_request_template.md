## What changed and why

<!-- One or two sentences. Link the issue if there is one. -->

---

## TDD evidence

See `docs/TDD-CONTRACT.md`. Fill all four — never leave one blank.

### RED

<!-- The test written first, and the ACTUAL failure output. Paste it. -->

```
```

### GREEN

<!-- The same focused test passing after the implementation. -->

```
```

### REGRESSION

<!-- `npm run check` fully green — both suites. -->

```
```

### LIVE

Check exactly one. No free-text substitute for either box — a prose paragraph is not a run ID.

- [ ] **Not applicable** — this change does not reach Apify or Airtable.
- [ ] **Run ID + pasted output** — cite an Apify run ID or Airtable record ID(s), and confirm:
  - Videos queried by `Video ID` — exactly one record (invariant 4)
  - Channels did not fork — one row, `@handle` form, not `UC...`
  - `Triage Status` and `Track` untouched on update (invariant 3)

```
```

---

- [ ] No credentials, tokens, or `secrets.` references added to CI
