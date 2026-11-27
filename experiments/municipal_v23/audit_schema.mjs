import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';

const endpoint = 'https://lindas.admin.ch/query';
const cubes = ['popular-initiative', 'referendum'].map(x => 'https://politics.ld.admin.ch/political-rights/' + x + '/1');
const allowedMetadata = ['http://schema.org/license', 'https://schema.org/license', 'http://purl.org/dc/terms/license', 'http://schema.org/datePublished', 'https://schema.org/datePublished', 'http://purl.org/dc/terms/issued', 'http://schema.org/dateModified', 'https://schema.org/dateModified'];
const iris = xs => xs.map(x => '<' + x + '>').join(' ');
// Only schema paths and dataset-level metadata; never traverse observationSet.
const query = `PREFIX cube: <https://cube.link/>
PREFIX sh: <http://www.w3.org/ns/shacl#>
PREFIX schema: <http://schema.org/>
SELECT DISTINCT ?cube ?kind ?field ?value WHERE {
  VALUES ?cube { ${iris(cubes)} }
  {
    ?cube cube:observationConstraint/sh:property ?shape .
    ?shape sh:path ?field .
    FILTER(isIRI(?field))
    BIND("dimension" AS ?kind)
    OPTIONAL {
      ?shape (schema:name|<https://schema.org/name>) ?value .
      FILTER(LANG(?value) IN ("", "de", "fr", "en"))
    }
  } UNION {
    VALUES ?field { ${iris(allowedMetadata)} }
    ?cube ?field ?value .
    FILTER(isIRI(?value) || isLiteral(?value))
    BIND("metadata" AS ?kind)
  }
} ORDER BY ?cube ?kind ?field ?value LIMIT 300`;

function validate(payload) {
  assert.deepEqual([...payload.head.vars].sort(), ['cube','field','kind','value']);
  const rows = payload.results.bindings;
  assert(Array.isArray(rows) && rows.length <= 300);
  return rows.map(row => {
    assert(Object.keys(row).every(k => ['cube','kind','field','value'].includes(k)));
    assert.equal(row.cube?.type, 'uri');
    assert(cubes.includes(row.cube.value));
    assert.equal(row.kind?.type, 'literal');
    assert(['dimension','metadata'].includes(row.kind.value));
    assert.equal(row.field?.type, 'uri');
    assert(['http:', 'https:'].includes(new URL(row.field.value).protocol));
    if (row.kind.value === 'metadata') assert(allowedMetadata.includes(row.field.value) && row.value);
    if (row.value) {
      assert(['uri','literal','typed-literal'].includes(row.value.type));
      assert(typeof row.value.value === 'string' && row.value.value.length <= 2000);
      if (row.kind.value === 'dimension') assert.equal(row.value.type, 'literal');
    }
    return {cube: row.cube.value, kind: row.kind.value, field: row.field.value,
      value: row.value?.value ?? null, language: row.value?.['xml:lang'] ?? null};
  });
}

function selfTest() {
  const good = {head:{vars:['cube','kind','field','value']},results:{bindings:[
    {cube:{type:'uri',value:cubes[0]},kind:{type:'literal',value:'dimension'},
     field:{type:'uri',value:'https://example.org/date'}}
  ]}};
  assert.equal(validate(good).length,1);
  assert.deepEqual(validate({...good,results:{bindings:[]}}),[]);
  const invalid = mutate => {const x=structuredClone(good); mutate(x.results.bindings[0]); assert.throws(()=>validate(x));};
  invalid(r=>r.cube.value='https://example.org/foreign');
  invalid(r=>r.kind.value='observation');
  invalid(r=>r.field.value='file:///tmp/data');
  invalid(r=>r.outcome={value:'forbidden'});
  invalid(r=>{r.kind.value='metadata';r.value={type:'literal',value:'wrong'};});
  invalid(r=>r.value={type:'uri',value:'https://example.org/observation'});
  assert.throws(()=>validate({...good,results:{bindings:Array(301).fill(good.results.bindings[0])}}));
  assert.throws(()=>validate({...good,head:{vars:['cube','kind','field','value','outcome']}}));
  console.log('10 schema controls passed');
}

async function acquire(path) {
  const url = new URL(endpoint); url.searchParams.set('query',query);
  const res = await fetch(url,{headers:{accept:'application/sparql-results+json'},redirect:'error',signal:AbortSignal.timeout(45000)});
  if(!res.ok) throw Error('HTTP '+res.status);
  const parts=[]; let size=0;
  for await(const chunk of res.body){size+=chunk.length;if(size>1024*1024) throw Error('Response exceeds 1 MiB');parts.push(chunk);}
  const bytes=Buffer.concat(parts), rows=validate(JSON.parse(bytes.toString('utf8')));
  const manifestBytes=readFileSync('reports/datasets/municipal_v2_20261123/data_manifest.json');
  const existing=JSON.parse(manifestBytes).political;
  const existingFields=[...new Set([...existing.source_fields,'dat-message','dat-parl','pa-iv','nrja','nrnein','srja','srnein'])].sort();
  const inventory=cubes.map(cube=>({cube,dimension_count:new Set(rows.filter(r=>r.cube===cube&&r.kind==='dimension').map(r=>r.field)).size,
    metadata_fields:[...new Set(rows.filter(r=>r.cube===cube&&r.kind==='metadata').map(r=>r.field))].sort()}));
  const result={endpoint,query,retrieved_at:new Date().toISOString(),metadata_sha256:createHash('sha256').update(bytes).digest('hex'),
    response_bytes:size,rows:rows.length,truncated_possible:rows.length===300,inventory,fields:rows,
    baseline_manifest_sha256:createHash('sha256').update(manifestBytes).digest('hex'),existing_source_fields:existingFields,
    novelty_status:'manual_review_required',observations_read:0,admitted:0};
  writeFileSync(path,JSON.stringify(result,null,2)+'\n',{flag:'wx'});console.log('SCHEMA',JSON.stringify(result));
}
selfTest();
if(process.argv[2]&&process.argv[2]!=='--self-test') await acquire(process.argv[2]);
