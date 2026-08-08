# Business-owned YouTube playlist migration and drain

This package copies six personal-channel playlists into playlists owned by
`The AI Humble Servant` and removes business playlist entries only after a
matching Airtable Video has a verified transcript. It never modifies the
personal source playlists or Airtable records.

## Credentials

The repo-root `.env` supplies:

- `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` — one Desktop-app OAuth client.
- `GOOGLE_PERSONAL_CLIENT_ID` and `GOOGLE_PERSONAL_CLIENT_SECRET` — optional
  second Desktop-app client when Google has pinned the shared client grant to
  the business channel. Set both or neither.
- `GOOGLE_REFRESH_TOKEN` — business-channel token with `youtube.force-ssl`.
- `GOOGLE_PERSONAL_READ_REFRESH_TOKEN` — personal-channel token with
  `youtube.readonly`.
- `AIRTABLE_API_KEY` and `AIRTABLE_BASE_ID` — read by the drain preflight.

Obtain the personal read token with:

```bash
npm run oauth:personal --prefix playlist-drain
```

The script displays the authorized channel title and ID before saving. Type
`yes` only when it shows the personal channel that owns the source playlists.
The token is written directly to `.env` and is never printed.

## Migration

```bash
npm run migrate --prefix playlist-drain
npm run migrate --prefix playlist-drain -- --apply
```

The first command is always read-only. Apply mode creates unlisted business
playlists, copies entries sequentially, persists each destination ID in
`playlists.json`, and verifies exact video ID order. A destination must be an
exact prefix of its source before a resume can append anything. The command
stops after 175 YouTube writes by default; use `--max-writes N` to lower that
ceiling. Quota exhaustion is resumable.

Unavailable source entries are reported by position and make the migration
partial. A partial playlist is not considered cut over. Source ID markers in
destination descriptions allow a created playlist to be recovered if the
process stops before its ID is persisted.

## Drain

```bash
npm run drain --prefix playlist-drain
npm run drain --prefix playlist-drain -- --apply
```

Dry-run is the default. An item is eligible only when exactly one Airtable
Videos record matches its `Video ID` and either `Transcript (Full)` is nonblank
or `Transcript (Timestamped)` parses as a nonempty array. Apply mode deletes
using the business playlist-item ID and verifies the ID is absent afterward.
Missing transcripts and duplicate Airtable matches remain in the playlist.
`404 playlistItemNotFound` is treated as already removed for safe retries.

There is deliberately no scheduler. Both mutations require an explicit
`--apply` invocation.

The initial six-playlist rollout and first transcript-verified drain were
completed 2026-08-04. See
[`docs/PLAYLIST-MIGRATION-LIVE-2026-08-04.md`](../docs/PLAYLIST-MIGRATION-LIVE-2026-08-04.md)
for destination URLs, ordered source hashes, and post-drain evidence.
