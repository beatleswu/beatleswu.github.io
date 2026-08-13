import assert from 'node:assert/strict';
import fsSync from 'node:fs';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '../..');
const UX = await fs.readFile(path.join(ROOT, 'sgf_admin_workbench_ux_v2.js'), 'utf8');

function findChrome() {
  const candidates = [
    process.env.CHROME_BIN,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  ].filter(Boolean);
  return candidates.find((candidate) => fsSync.existsSync(candidate));
}

const itemOpen = {
  id: 1, question_id: 431, record_index: 0, issue_type: 'ALTERNATIVE_CORRECT_MOVE',
  candidate_move: { x: 15, y: 3 }, source_types: ['PLAYER_REPORT'], report_count: 1,
  status: 'OPEN', authority: { accepted_moves: [{ x: 3, y: 3 }] },
  position_identity: '431:0:root', first_report_at: '2026-08-14T00:00:00Z',
  updated_at: '2026-08-14T00:00:00Z', provenance: { fixture: 'browser' },
};
const record = { id: 431, content: '(;GM[1]FF[4]SZ[19])', accepted_moves: [{ x: 3, y: 3 }], enabled: true };
const repair = {
  id: 7, review_item_id: 1, action: 'ADD_ALTERNATIVE_CORRECT_MOVE', status: 'STAGED',
  candidate_move: { x: 15, y: 3 }, proposed_state: { accepted_moves: [{ x: 3, y: 3 }, { x: 15, y: 3 }] },
  source_provenance: { workflow: { validation: { status: 'PASS', errors: [] } } },
};

let staged = false;
let batchCreated = false;
const server = http.createServer(async (request, response) => {
  const url = new URL(request.url, 'http://127.0.0.1');
  const json = (status, payload) => {
    response.writeHead(status, { 'content-type': 'application/json; charset=utf-8' });
    response.end(JSON.stringify(payload));
  };
  if (url.pathname === '/') {
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
    response.end('<!doctype html><html><head><meta charset="utf-8"></head><body><script src="/sgf_admin_workbench_ux_v2.js"></script></body></html>');
    return;
  }
  if (url.pathname === '/sgf_admin_workbench_ux_v2.js') {
    response.writeHead(200, { 'content-type': 'text/javascript; charset=utf-8' }); response.end(UX); return;
  }
  if (url.pathname === '/api/question/431') { json(200, record); return; }
  if (url.pathname === '/api/admin/sgf-workbench/bootstrap') {
    json(200, { ok: true, items: [staged ? { ...itemOpen, status: 'STAGED', staged_repairs: [repair] } : itemOpen], staged_count: staged ? 1 : 0,
      production_mutation: false, canonical_mutation: false, security: { csrf_header: 'X-CSRF', csrf_token: 'fixture' } }); return;
  }
  if (url.pathname === '/api/admin/sgf-workbench/items') {
    json(200, { ok: true, items: [staged ? { ...itemOpen, status: 'STAGED', staged_repairs: [repair] } : itemOpen] }); return;
  }
  if (url.pathname === '/api/admin/sgf-workbench/items/1' && request.method === 'GET') {
    json(200, { ok: true, item: { ...itemOpen, status: staged ? 'STAGED' : 'OPEN', staged_repairs: staged ? [repair] : [] } }); return;
  }
  if (url.pathname === '/api/admin/sgf-workbench/items/1/stage' && request.method === 'POST') {
    staged = true; json(200, { ok: true, staged: true, production_mutation: false, repair }); return;
  }
  if (url.pathname === '/api/admin/sgf-workbench/items/1/validate' && request.method === 'POST') {
    json(200, { ok: true, status: 'PASS', validation: { status: 'PASS', errors: [], canonical_mutation: false }, production_mutation: false }); return;
  }
  if (url.pathname === '/api/admin/sgf-workbench/batches' && request.method === 'POST') {
    batchCreated = true; json(200, { ok: true, batch: { id: 10, batch_key: 'fixture-batch', status: 'STAGED' }, production_mutation: false }); return;
  }
  if (url.pathname === '/api/admin/sgf-workbench/batches/10/ready' && request.method === 'POST') {
    assert.equal(batchCreated, true); json(200, { ok: true, ready_for_apply: true, apply_enabled: false, production_mutation: false,
      batch: { id: 10, batch_key: 'fixture-batch', status: 'READY_FOR_APPLY' } }); return;
  }
  json(404, { error: 'not_found' });
});

await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
const { port } = server.address();
const executablePath = findChrome();
assert.ok(executablePath, 'Chrome executable is required for this browser contract');
const browser = await chromium.launch({ headless: true, executablePath });
const page = await browser.newPage({ viewport: { width: 1024, height: 768 } });
const browserErrors = [];
page.on('pageerror', (error) => browserErrors.push(error.message));
try {
  await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: '開始審題' }).click();
  await page.locator('#v2-review').waitFor({ state: 'visible' });
  await page.getByRole('button', { name: /還有其他正解/ }).click();
  const board = await page.locator('#v2-go-board').boundingBox();
  assert.ok(board, 'review board is visible');
  await page.mouse.click(board.x + board.width * 0.8, board.y + board.height * 0.2);
  await page.getByRole('button', { name: '暫存這項修改' }).click();
  await page.getByRole('button', { name: /待套用修改/ }).first().click();
  await page.locator('#v2-pending-view').waitFor({ state: 'visible' });
  await page.getByRole('button', { name: '驗證並準備批次' }).click();
  await page.getByText('READY_FOR_APPLY').waitFor({ state: 'visible' });
  assert.equal(browserErrors.length, 0, browserErrors.join('\n'));
  console.log('SGF_WORKBENCH_BROWSER_WORKFLOW=PASS');
} finally {
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
