// Thin client around Apify's streamers/youtube-scraper actor.
//
// Uses the run-sync-get-dataset-items endpoint: it runs the actor and
// returns the dataset items directly in the response, no separate
// run-then-poll-then-fetch-dataset dance needed. Fine for the small,
// bounded (maxResults-capped) runs this normalizer is designed for; Apify
// enforces its own timeout on this endpoint for longer runs.
//
// Actor input field names below are ONLY VERIFIED for a single-video
// startUrls run (see normalizer/lib/__fixtures__ + CLAUDE.md probe notes,
// 2026-07-29). A channel-mode sweep with date bounding has NOT been probed
// yet — the actual field name for date-filtering a channel (assumed
// "oldestPostDate" per repo CLAUDE.md) is unverified against the live actor
// schema. Do not trust that field name without a real channel-mode dry run.

const ACTOR_ID = 'h7sDV53CddomktSi5'; // streamers/youtube-scraper

async function runActorSync({ token, input, timeoutMs = 120000 }) {
  if (!token) throw new Error('APIFY_TOKEN is required');
  if (!input || typeof input !== 'object') throw new Error('Apify actor input is required');

  const url = `https://api.apify.com/v2/acts/${ACTOR_ID}/run-sync-get-dataset-items?token=${encodeURIComponent(token)}`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    const bodyText = await response.text().catch(() => '');
    throw new Error(`Apify run failed (${response.status}): ${bodyText.slice(0, 500)}`);
  }

  return response.json();
}

module.exports = { runActorSync, ACTOR_ID };
