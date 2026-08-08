# Live evidence — business-owned playlist migration and drain

**LIVE verified 2026-08-04.** The six source playlists were read with a separate
`youtube.readonly` credential for personal channel **Myung Cho**
(`UCQZ9ujr3drYwJ-OuQ03t0FQ`). Destinations were created and managed with the
existing `youtube.force-ssl` credential for **The AI Humble Servant**
(`UCQa5rETk8YLryqNlJzWJ2PA`). Refresh tokens were stored in `.env` and never
printed.

## Migration validation

The migration preflight found 105 addressable source entries and zero
unavailable entries. After the resumable apply, a full read-back reported zero
pending writes: every destination contained the exact source video-ID sequence,
including order and duplicates, before draining.

| Playlist | Source count | Ordered source SHA-256 | Business destination |
|---|---:|---|---|
| AI (Claude) | 42 | `6efbb5cc13078ced44f0ab1be0d16dcc3ba7445f0e125aa6036204d870e5742f` | [`PLTJ-2ZXfYpxM`](https://www.youtube.com/playlist?list=PLTJ-2ZXfYpxM) |
| Content Creation | 35 | `9a04c9d52ce6f8d6dea97ad3bbc435242f7f199996e1a9c68e61e5d23b01c9fc` | [`PLF9bKYfkt-fQ`](https://www.youtube.com/playlist?list=PLF9bKYfkt-fQ) |
| Business & Productivity | 8 | `0199c625b9bbecda0992befbe007c774d975c7f066a31b3e809e53602f555997` | [`PLFN18u6eRm4s`](https://www.youtube.com/playlist?list=PLFN18u6eRm4s) |
| Tech & Development | 10 | `6223718cdf3fa5f3ecb90e7d1a29f20eed3d133d085eeef234f75e71ff65d4af` | [`PLcfSwgzg-O8w`](https://www.youtube.com/playlist?list=PLcfSwgzg-O8w) |
| Education & World | 7 | `deb048a79d8002051d3b3613986b9c31c628d58bbf8a76610cf71b5bf8fedc1c` | [`PLaHx3tpNgX4s`](https://www.youtube.com/playlist?list=PLaHx3tpNgX4s) |
| Finance & Business | 3 | `b942130a49b4c29aa352ae68f6b1dbf8553bd45a5df364534e60088e6626681c` | [`PLUF_xK0hS7zQ`](https://www.youtube.com/playlist?list=PLUF_xK0hS7zQ) |

Every destination metadata read returned:

- owner channel `UCQa5rETk8YLryqNlJzWJ2PA`;
- `privacyStatus = unlisted`;
- the expected title;
- zero unavailable destination entries.

The source playlists were re-read after migration and drain. Their counts and
ordered hashes still match the table above, proving the personal playlists were
not modified.

## Drain validation

The Airtable-backed dry-run examined all 105 business playlist entries and
found 12 with exactly one matching Video record and a nonempty verified
transcript:

| Playlist | Eligible and deleted | Retained after apply |
|---|---:|---:|
| AI (Claude) | 8 | 34 |
| Content Creation | 1 | 34 |
| Business & Productivity | 3 | 5 |
| Tech & Development | 0 | 10 |
| Education & World | 0 | 7 |
| Finance & Business | 0 | 3 |

Apply deleted all 12 by business playlist-item ID, with zero errors, zero
deferred items, and read-back verification that each playlist-item ID was
absent. A second dry-run returned `eligible=0`, `retained=93`, and `errors=0`.
Airtable was read-only throughout.

## TDD evidence

- **RED:** the first playlist suite failed because `playlist-manager` did not
  exist; the eventual-consistency test later failed until bounded validation
  retries were implemented.
- **GREEN:** playlist-drain focused suite passes.
- **REGRESSION:** `npm run check` passes the extension, normalizer, and
  playlist-drain suites.
- **LIVE:** destination playlist IDs, ordered source hashes, ownership,
  privacy, source preservation, deletion counts, and the zero-eligible
  post-drain read are recorded above.
