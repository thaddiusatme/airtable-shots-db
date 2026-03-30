# Lessons Learned — 2026-03-30 — Git Triage and Project Re-orientation

## What we shipped

Re-orientation session after ~2.5 weeks away from the project. Audited 136 dirty git files,
identified the root cause (macOS file permission drift tracked by git), and resolved everything
cleanly. Committed two changes: (1) `.gitignore` additions for `storyboard_output_*/` and
`gh[0-9]*.txt` plus the `Storyboarder_api.json` IPAdapterAdvanced upgrade (workflow upgrade
from `IPAdapter` → `IPAdapterAdvanced` with explicit `IPAdapterModelLoader` node, weight 0.8,
`composition precise` weight type, steps 20→30, cfg 8→7) and `comfyui/workflows/Storyboarder 4.json`
(new GUI workflow counterpart); (2) refreshed `CURRENT_STATE.md` and `NEXT_SESSION.md` to
document Phase 5 (Storyboard Generation: GH-32/33/51/53/56/57), updated test counts to ~590
(539 Python + 51 Node.js), and captured outstanding work.

## What went well

- **`git diff --stat HEAD | grep -v "| *0$"`** instantly surfaced that 125 of 126 "changed" files
  had zero content changes — this one filter saved the entire audit and pointed directly to the
  file-mode root cause.
- **`CURRENT_STATE.md` + `NEXT_SESSION.md` as session handoff docs** proved their value: even
  after 2.5 weeks away, the project state was fully recoverable from those two files in under
  5 minutes. The pattern of maintaining them is worth keeping.
- **`git log --oneline --since=` with a date** gave an immediate ordered list of everything that
  shipped between the last doc update and today, which drove the CURRENT_STATE.md refresh
  without having to re-read every file.

## What surprised us / went wrong

- **126 files showed as "modified" with zero actual changes.** Root cause: `core.fileMode = true`
  (git default on macOS) was tracking a mass permission change from 644 → 755 across every
  tracked file. Likely caused by a tool or script that ran `chmod -R 755` or extracted an archive.
  Fix: `git config core.fileMode false`. Lesson: when `git status` shows dozens of modified files
  but `git diff` shows tiny or zero line changes, check `git diff --diff-filter=M` and look for
  mode-only diffs.
- **`CURRENT_STATE.md` and `NEXT_SESSION.md` were 2.5 weeks stale**, covering only through GH-40
  (Gemini provider) while six more issues (GH-32, 33, 51, 53, 56, 57) had shipped. The docs
  lagged because the `NEXT_SESSION.md` "first thing next session" list was never executed — the
  GH-40 GitHub post is still outstanding.

## What to do differently next time

- **Always update `CURRENT_STATE.md` and `NEXT_SESSION.md` as the final commit of every
  session**, not as a deferred task. The "First Thing To Do Next" section in `NEXT_SESSION.md`
  is a liability if it accumulates across sessions — treat it as a hard contract: next session
  starts by executing those items before writing new code.
- **Add `storyboard_output_*/` and session debug log patterns (`gh[0-9]*.txt`) to `.gitignore`
  the moment you create those outputs**, not retroactively. The untracked debris (6 output dirs,
  3 text files) should have been gitignored when they were first generated.
- **Run `git diff --stat HEAD | grep -v "| *0$"` as a pre-commit sanity check** on large
  `git status` outputs. A large number of "modified" files with no content diff is almost always
  a file-mode or line-ending issue — catch it before staging anything.

## Technical debt or risks introduced

- **`git config core.fileMode false` is set locally** in `.git/config` — this means a fresh
  clone on this machine will default back to `true` and the permission drift issue could recur.
  The proper fix is to either (a) add `[core] fileMode = false` to a shared `.gitconfig` snippet
  in the repo docs, or (b) normalize all file permissions back to 644 with
  `find . -not -path "./.git/*" -type f -exec chmod 644 {} \;` and then set `core.fileMode true`
  to catch future accidental permission changes. Neither was done today.
- **GH-40 GitHub issue post is still unwritten** — the `NEXT_SESSION.md` from March 13 flagged
  it as the first task, and it remains outstanding. Risk: the gemini-2.0-flash / gemini-2.5-flash
  discrepancy is undocumented in the GitHub issue tracker, which could confuse future contributors.
