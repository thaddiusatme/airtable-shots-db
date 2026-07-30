// Parse the inline SRT subtitle text Apify's streamers/youtube-scraper returns
// (subtitlesFormat: "srt", read from the dataset item's subtitles[].srt field —
// no KVS fetch needed since it comes back inline when saveSubsToKVS is false).
//
// Two things make this NOT standard SRT, observed from a real dataset item
// (qdRw7oHDXJw, 2026-07-29 — see normalizer/lib/__fixtures__/):
//
// 1. Timestamp fields are not zero-padded. Standard SRT requires HH:MM:SS,mmm;
//    this feed emits e.g. "00:04:2,560" (seconds field un-padded). A standard
//    SRT parser / regex expecting exactly 2 digits per field will misparse or
//    reject these lines.
// 2. Every real caption cue is immediately followed by a "shadow" cue — same
//    end time, near-identical start, text = a single space. This is an
//    artifact of YouTube's rolling auto-captions (each word/phrase re-emitted
//    as the line builds) surfacing as a literal duplicate blank block. Naively
//    parsing every cue doubles the segment count with blank-text entries.
//
// This parser tolerates (1) via a digit-count-agnostic timestamp regex and
// drops (2) by discarding any cue whose text is empty after trimming.

const TIMESTAMP_RE = /(\d+):(\d+):(\d+)[,.](\d+)/;

function timestampToSeconds(ts) {
  const match = TIMESTAMP_RE.exec(ts);
  if (!match) return null;
  const [, h, m, s, ms] = match;
  // ms field is fractional seconds regardless of digit count (usually 3, i.e.
  // milliseconds) — normalize by dividing by 10^digitCount rather than
  // assuming exactly 3 digits.
  const fractionSeconds = Number(ms) / Math.pow(10, ms.length);
  return Number(h) * 3600 + Number(m) * 60 + Number(s) + fractionSeconds;
}

// Parse SRT text into an ordered [{ text, start }] array. start is seconds
// (float). Blocks with blank/whitespace-only text are dropped. Never throws
// on malformed input — unparseable blocks are skipped.
function parseSrt(srtText) {
  if (typeof srtText !== 'string' || srtText.trim() === '') return [];

  const blocks = srtText.replace(/\r\n/g, '\n').split(/\n\s*\n/);
  const segments = [];

  for (const block of blocks) {
    const lines = block.split('\n').map((l) => l.trim()).filter((l) => l !== '');
    if (lines.length < 2) continue;

    // First non-blank line is the cue index (may or may not be numeric —
    // don't require it). Find the timestamp line by regex instead of by
    // fixed position, since malformed blocks sometimes drop the index line.
    const timestampLineIdx = lines.findIndex((l) => l.includes('-->'));
    if (timestampLineIdx === -1) continue;

    const [startRaw] = lines[timestampLineIdx].split('-->');
    const start = timestampToSeconds(startRaw.trim());
    if (start === null) continue;

    const text = lines
      .slice(timestampLineIdx + 1)
      .join(' ')
      .replace(/\s+/g, ' ')
      .trim();

    if (text === '') continue; // drop shadow/blank cues

    segments.push({ text, start });
  }

  return segments;
}

module.exports = { parseSrt, timestampToSeconds };
