---
name: airtable-ui-fallback
description: Drive the Airtable web UI directly (via the browser tools) for the handful of Airtable operations the Airtable MCP server cannot do — chiefly adding choices to an existing singleSelect/multipleSelects field, but the same record-modal technique applies to any other UI-only action (deleting a scheduled automation trigger, changing a view's grid options, etc.). Use this whenever an Airtable MCP tool errors out, is missing entirely (e.g. there is no delete_records-equivalent for some resource), or its schema makes clear it can't do what's needed (e.g. update_field only accepts a formula, never `choices`). Don't attempt workarounds like typecast or guessing at option names — go straight to the browser. Also use this if the user says a base needs a manual UI step, an Airtable field needs new dropdown options, or asks you to "just add it in Airtable yourself."
---

# Airtable UI fallback

The Airtable MCP server covers most base operations, but a few things are UI-only:

- **Adding choices to an existing `singleSelect`/`multipleSelects` field.** `update_field`'s schema
  only accepts `name`, `description`, and `options.formula` — there is no `choices` parameter for
  editing an existing select's option list. `create_field` can set initial choices on a **new**
  field, but once the field exists, growing its option list is a manual step. This mirrors the
  "Airtable API cannot add select choices" limitation documented for record writes (a 422 on an
  unrecognized option, no `typecast`) — it holds for schema edits too.
- Anything else the connected MCP server's tool list simply doesn't expose (check by searching the
  tool list before concluding this — a missing delete/rename/etc. tool is the actual trigger for
  this skill, not a guess).

Don't try to route around this with `typecast: true` on a record write, or by inventing a REST call —
those are exactly the shortcuts the write invariants in most Airtable-project `CLAUDE.md` files warn
against. The UI is the correct tool for the job here, not a workaround.

## Why the record-detail modal, not the grid

Airtable's grid is a virtualized canvas. In a browser session that Airtable doesn't recognize as
"supported" (the yellow banner reading "The browser you're currently using is not supported"), the
accessibility tree returned by `read_page` frequently maps to stale or wrong pixel coordinates —
clicking a `ref` for a column-menu button can land on a totally different column, and horizontal
scroll gestures on the grid body often do nothing visible. Chasing this by re-scrolling and re-reading
the tree wastes many turns.

The **expanded record modal** (the vertical single-record detail view) doesn't have this problem —
it's laid out as ordinary stacked form fields, each at a stable, unambiguous screen position. Every
field is visible without horizontal scrolling, and a screenshot immediately after opening it
disambiguates every field by its on-screen label. Use the modal, not the grid, for any interaction
that requires precision.

## Steps

1. **Open the table**: `navigate` to `https://airtable.com/<baseId>/<tableId>`. If a cookie
   consent banner appears, dismiss it (prefer "Reject All" / decline non-essential, matching the
   project's privacy defaults) before doing anything else.

2. **Get into the record modal.** If the table has zero records (common for a brand-new table you
   just created via the API), you need one to expand:
   - Click "Add record" (or the `+` at the bottom of the grid) to create a blank row.
   - Press `Escape` to exit the inline text-edit that creation drops you into.
   - **Hover** over the new row first, *then* click the expand icon (⤢) that appears next to the
     row checkbox — clicking that icon without a preceding hover frequently misses, because the
     icon only renders on hover and a bare click can land before it's painted. If it still doesn't
     open, read the page (`filter: interactive`), locate the `toolbar "Row N actions"` node, and
     click its first child by pixel coordinate from a fresh screenshot rather than by `ref` (see
     above on why `ref` coordinates can't be trusted here).
   - If the table already has a real record, right-click it and choose **Expand record** from the
     context menu instead of creating a throwaway one.

3. **Take a screenshot of the open modal and read field labels off it directly.** Don't guess
   y-coordinates from a previous screenshot taken before the modal opened — the modal's internal
   layout (and sometimes the whole page's zoom level) can shift between screenshots in this
   environment. Re-screenshot after every modal-opening action before clicking a field.

4. **To add a select choice**: click the field's dropdown box. A list of existing choices opens.
   Type the new option's exact name — Airtable shows `Add option: <name>` below the existing
   choices. Click that row to create and apply it in one step. Repeat by re-clicking the same
   dropdown for each additional choice.

   **Verify you're in the right field before typing.** Fields sit close together vertically, and a
   dropdown that opens *upward or downward* from where you clicked can cover the field below or
   above it, so a click that looks like it hit field A can actually open field B's dropdown. After
   clicking, screenshot and confirm the dropdown's header/context matches the field you intended
   before typing anything. If you opened the wrong one, press `Escape` immediately — do **not**
   type into it, since a stray keystroke sequence can create an unwanted option on the wrong field.

5. **Clean up any throwaway record.** If you created a blank record purely to reach the modal
   (step 2), delete it when done: close the modal, right-click the row in the grid, **Delete
   record**. Confirm the grid shows the original record count afterward (e.g. "0 records" if the
   table was empty before you started).

6. **Verify the result through the API, not just visually.** Once back in a normal tool-calling
   context, call the MCP server's schema-read tool (e.g. `get_table_schema`) for the field you
   edited and confirm every intended choice is present with the right name. Screenshots can lie
   about what actually got saved server-side (draft state, a dropdown that silently didn't commit,
   etc.) — the schema read is the real confirmation, the same way a Metricool or Apify write is only
   confirmed by reading it back, never by trusting a UI paint.

## Non-negotiables carried over from the base project's write invariants

- Never touch fields you weren't asked to change. If a click accidentally opens the wrong field's
  dropdown, escape out without typing rather than trying to "undo" by picking something plausible.
- Never guess an option name close enough to what's already there — check the existing choices in
  the dropdown before typing, so you don't create a near-duplicate (`Sending` vs `sending` vs `Send`).
- If the UI action is destructive or affects shared state (deleting a real record, not a throwaway
  one you just created; changing a view other people use), confirm with the user first — this skill
  covers the mechanics of driving the UI, not a blanket license to act on the base unsupervised.
