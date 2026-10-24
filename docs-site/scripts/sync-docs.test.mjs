import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = fileURLToPath(new URL('..', import.meta.url));
execFileSync(process.execPath, ['scripts/sync-docs.mjs'], { cwd: root });
const page = (name) => readFile(new URL(`../src/content/docs/${name}`, import.meta.url), 'utf8');

test('unpublished source files render as repository paths, not broken site links', async () => {
  const text = await page('upstream/index.md');
  assert.match(text, /仓库路径：`backend\/bot\/app\/web\/webapp\/legacy_business\.py`/);
  assert.doesNotMatch(text, /\]\([^)]*\.py\)/);
});

test('the API artifact remains downloadable from nested documentation pages', async () => {
  const text = await page('development/independent-services.md');
  assert.match(text, /\]\(\/openapi\.json\)/);
  assert.doesNotMatch(text, /\]\(\.\.\/openapi\.json\)/);
});

test('agent rules remain repository files without generated root pages', async () => {
  const text = await page('reference/handoff.md');
  assert.ok(text.includes('仓库路径：`AGENTS.md`'));
  assert.ok(text.includes('仓库路径：`CONTRIBUTING.md`'));
  await assert.rejects(page('reference/agents.md'), { code: 'ENOENT' });
  await assert.rejects(page('reference/contributing.md'), { code: 'ENOENT' });
});

test('compatibility anchors do not create duplicate headings', async () => {
  const text = await page('getting-started/overview.md');
  assert.ok(text.includes('<a id='));
  assert.doesNotMatch(text, /^# /m);
});
