const { test } = require('node:test');
const assert = require('node:assert/strict');

const {
  findBlankTrackChannels,
  findMisconfiguredHarvestChannels,
  findVideosWithNoChannel,
  findDuplicateVideoIds,
  findVideosMissingMetrics,
} = require('./audit');

test('findBlankTrackChannels reports only channels with no Track', () => {
  const channels = [
    { recordId: 'rec1', handle: '@A', channelName: 'A', track: 'AIHS' },
    { recordId: 'rec2', handle: '@B', channelName: 'B', track: null },
    { recordId: 'rec3', handle: '@C', channelName: 'C', track: '' },
  ];
  const findings = findBlankTrackChannels(channels);
  assert.equal(findings.length, 2);
  assert.match(findings[0], /@B/);
  assert.match(findings[1], /@C/);
});

test('findMisconfiguredHarvestChannels reports Harvest? ticked with no Source URL', () => {
  const channels = [
    { recordId: 'rec1', handle: '@A', channelName: 'A', harvest: true, sourceUrl: 'https://x' },
    { recordId: 'rec2', handle: '@B', channelName: 'B', harvest: true, sourceUrl: null },
    { recordId: 'rec3', handle: '@C', channelName: 'C', harvest: false, sourceUrl: null },
  ];
  const findings = findMisconfiguredHarvestChannels(channels);
  assert.equal(findings.length, 1);
  assert.match(findings[0], /@B/);
});

test('findVideosWithNoChannel reports videos with an empty Channel link', () => {
  const videos = [
    { recordId: 'rec1', videoId: 'v1', title: 'T1', channelLinks: ['recChan'] },
    { recordId: 'rec2', videoId: 'v2', title: 'T2', channelLinks: [] },
    { recordId: 'rec3', videoId: 'v3', title: 'T3', channelLinks: null },
  ];
  const findings = findVideosWithNoChannel(videos);
  assert.equal(findings.length, 2);
  assert.match(findings[0], /v2/);
  assert.match(findings[1], /v3/);
});

test('findDuplicateVideoIds reports only ids shared by more than one record', () => {
  const videos = [
    { recordId: 'rec1', videoId: 'dup' },
    { recordId: 'rec2', videoId: 'dup' },
    { recordId: 'rec3', videoId: 'unique' },
    { recordId: 'rec4', videoId: null },
  ];
  const findings = findDuplicateVideoIds(videos);
  assert.equal(findings.length, 1);
  assert.match(findings[0], /dup — rec1, rec2/);
});

test('findVideosMissingMetrics reports videos with no Metrics Captured At', () => {
  const videos = [
    { recordId: 'rec1', videoId: 'v1', title: 'T1', triageStatus: 'Queued', metricsCapturedAt: '2026-07-30T00:00:00.000Z' },
    { recordId: 'rec2', videoId: 'v2', title: 'T2', triageStatus: 'Queued', metricsCapturedAt: null },
  ];
  const findings = findVideosMissingMetrics(videos);
  assert.equal(findings.length, 1);
  assert.match(findings[0], /v2/);
});
