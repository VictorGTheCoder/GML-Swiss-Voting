import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { writeFileSync } from 'node:fs';

const endpoint = 'https://lindas.admin.ch/query';
const query = `PREFIX cube: <https://cube.link/>
PREFIX schema: <http://schema.org/>
PREFIX dct: <http://purl.org/dc/terms/>
SELECT DISTINCT ?cube ?title WHERE {
  ?cube a cube:Cube .
  ?cube (schema:name|<https://schema.org/name>|dct:title) ?title .
  FILTER(REGEX(STR(?title), "Volksinitiativ|Referend|initiative populaire|référendum|iniziativ|referendum", "i"))
} ORDER BY ?cube ?title LIMIT 100`;

function validate(payload) {
  assert.deepEqual([...payload.head.vars].sort(), ['cube', 'title']);
  const bindings = payload.results.bindings;
  assert(Array.isArray(bindings) && bindings.length <= 100);
  return bindings.map(row => {
    assert.deepEqual(Object.keys(row).sort(), ['cube', 'title']);
    assert.equal(row.cube.type, 'uri');
    const url = new URL(row.cube.value);
    assert(['http:', 'https:'].includes(url.protocol));
    assert.equal(row.title.type, 'literal');
    assert(typeof row.title.value === 'string' && row.title.value.length > 0 && row.title.value.length <= 2000);
    return { cube: row.cube.value, title: row.title.value, language: row.title['xml:lang'] ?? null };
  });
}

function selfTest() {
  const good = { head: { vars: ['cube', 'title'] }, results: { bindings: [
    { cube: { type: 'uri', value: 'https://example.org/cube' }, title: { type: 'literal', value: 'Test' } }
  ] } };
  assert.equal(validate(good).length, 1);
  assert.deepEqual(validate({ ...good, results: { bindings: [] } }), []);
  assert.throws(() => validate({ ...good, head: { vars: ['cube', 'title', 'outcome'] } }));
  assert.throws(() => validate({ ...good, results: { bindings: Array(101).fill(good.results.bindings[0]) } }));
  const wrong = structuredClone(good);
  wrong.results.bindings[0].cube.value = 'file:///tmp/data';
  assert.throws(() => validate(wrong));
  const extra = structuredClone(good);
  extra.results.bindings[0].outcome = { value: 'not allowed' };
  assert.throws(() => validate(extra));
  console.log('6 catalogue controls passed');
}

async function acquire(path) {
  const url = new URL(endpoint);
  url.searchParams.set('query', query);
  const response = await fetch(url, { headers: { accept: 'application/sparql-results+json' }, redirect: 'error', signal: AbortSignal.timeout(45000) });
  if (!response.ok) throw Error('HTTP ' + response.status);
  const parts = [];
  let size = 0;
  for await (const chunk of response.body) {
    size += chunk.length;
    if (size > 1024 * 1024) throw Error('Catalogue response exceeds 1 MiB');
    parts.push(chunk);
  }
  const bytes = Buffer.concat(parts);
  const candidates = validate(JSON.parse(bytes.toString('utf8')));
  const result = { endpoint, query, retrieved_at: new Date().toISOString(), metadata_sha256: createHash('sha256').update(bytes).digest('hex'), response_bytes: size, candidate_rows: candidates.length, distinct_cubes: new Set(candidates.map(x => x.cube)).size, truncated_possible: candidates.length === 100, candidates, observations_read: 0, admitted: 0 };
  writeFileSync(path, JSON.stringify(result, null, 2) + '\n', { flag: 'wx' });
  console.log('CATALOGUE', JSON.stringify(result));
}

selfTest();
if (process.argv[2] && process.argv[2] !== '--self-test') await acquire(process.argv[2]);
