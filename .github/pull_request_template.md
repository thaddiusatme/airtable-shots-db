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

<!--
Airtable/Apify verification, or an explicit "not applicable" with the reason.
"Not applicable" is correct and expected for anything that does not reach Apify or Airtable.

If it DOES reach them, confirm:
  - Videos queried by `Video ID` — exactly one record (invariant 4)
  - Channels did not fork — one row, `@handle` form, not `UC...`
  - `Triage Status` and `Track` untouched on update (invariant 3)
-->

---

- [ ] No credentials, tokens, or `secrets.` references added to CI
