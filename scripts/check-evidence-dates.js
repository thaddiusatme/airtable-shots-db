#!/usr/bin/env node
// Fails if any tracked *.md file claims a LIVE-verification date in the future.
// Guards against exactly the failure this script was written after: a LIVE
// attestation dated tomorrow, for a run that never happened.

const { execFileSync } = require('node:child_process');
const fs = require('node:fs');

const PATTERN = /(?:LIVE verified|Verified live)\s+(\d{4}-\d{2}-\d{2})/gi;

function trackedMarkdownFiles() {
  return execFileSync('git', ['ls-files', '*.md', '**/*.md'], { encoding: 'utf8' })
    .split('\n')
    .filter(Boolean);
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

function main() {
  const cutoff = today();
  const failures = [];

  for (const file of trackedMarkdownFiles()) {
    const text = fs.readFileSync(file, 'utf8');
    for (const match of text.matchAll(PATTERN)) {
      const date = match[1];
      if (date > cutoff) {
        failures.push(`${file}: "${match[0]}" is dated in the future (today is ${cutoff})`);
      }
    }
  }

  if (failures.length > 0) {
    console.error('check-evidence-dates: future-dated LIVE claim(s) found:\n');
    for (const f of failures) console.error(`  - ${f}`);
    console.error('\nA LIVE claim records a run that already happened. Fix the date, or if the');
    console.error('run has not happened yet, replace the claim with "LIVE — not applicable".');
    process.exit(1);
  }

  console.log(`check-evidence-dates: ok (${trackedMarkdownFiles().length} files scanned, none future-dated)`);
}

main();
