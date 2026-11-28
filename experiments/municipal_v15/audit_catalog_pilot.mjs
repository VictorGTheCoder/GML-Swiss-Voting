// V15.1a metadata-only audit; never loads labels or model data.
import { readFileSync } from "node:fs";
function audit(m){
 const fail=(s)=>{throw Error(s)};
 if(m.status!=="quarantine")fail("quarantine only");
 const dates=new Set(),covered=new Set(),ids=new Set(),families=new Map();let rows=0,pairs=0,month=0,excluded=0;
 for(const r of m.rows){
  if(!/^\d{4}$/.test(r.vote_key)||ids.has(r.vote_key))fail("duplicate or malformed object");
  ids.add(r.vote_key);
  if(!/^\d{4}-\d{2}-\d{2}$/.test(r.vote_date)||r.vote_date<"2016-01-01"||r.vote_date>="2023-01-01"||new Date(r.vote_date).toISOString().slice(0,10)!==r.vote_date)fail("invalid vote date");
  if(r.catalog_url!==`https://swissvotes.ch/vote/${r.vote_key.slice(0,-1)}.00/campaign-material`)fail("catalog mismatch");
  dates.add(r.vote_date);const local=new Set();
  if(r.families.length)covered.add(r.vote_date);
  for(const f of r.families){
   if(local.has(f.id)||!f.id)fail("duplicate family");local.add(f.id);
   if(!/^\d{4}-\d{2}(-\d{2})?$/.test(f.doc_date))fail("undated");
   const d=new Date(f.doc_date.length===7?f.doc_date+"-01":f.doc_date);
   if(d.toISOString().slice(0,f.doc_date.length)!==f.doc_date)fail("invalid document date");
   const upper=f.doc_date.length===7?new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth()+1,0)).toISOString().slice(0,10):f.doc_date;
   if(upper>=r.vote_date)fail("not strictly pre-vote");
   if(f.languages.length!==2||new Set(f.languages).size!==2||!f.languages.includes("de")||!f.languages.includes("fr"))fail("unexpected language pair");
   if(families.has(f.id)&&families.get(f.id)!==f.doc_date)fail("shared date conflict");
   families.set(f.id,f.doc_date);pairs++;rows+=f.languages.length;if(f.doc_date.length===7)month+=f.languages.length;
  }
  excluded+=r.excluded.reduce((s,x)=>s+x.count,0);
 }
 for(const p of m.primary_checks)if(!families.has(p.family)||p.publication_proof!==null||p.sha256!==null||p.license!==null)fail("unverified primary gate");
 return {sample_objects:ids.size,sample_dates:dates.size,candidate_objects:m.rows.filter(r=>r.families.length).length,candidate_dates:covered.size,catalog_entries:rows,object_family_pairs:pairs,provisional_distinct_families:families.size,month_precision_entries:month,excluded_catalog_entries:excluded,primary_mirror_checks:m.primary_checks.length,training_rows_admitted:0};
}
function controls(m){const cases=[x=>x.rows.push(x.rows[0]),x=>x.rows[0].families[0].doc_date=x.rows[0].vote_date,x=>x.rows[0].families[0].doc_date="2017-02-30",x=>x.rows[0].families[0].languages=["de","de"],x=>x.rows[0].vote_date="2023-01-01",x=>x.status="admitted"];for(const mutate of cases){const copy=JSON.parse(JSON.stringify(m));mutate(copy);let rejected=false;try{audit(copy)}catch{rejected=true}if(!rejected)throw Error("negative control failed")}return cases.length;}
const manifest=JSON.parse(readFileSync(new URL("../../data/external/institutional_v151/catalog_pilot.json",import.meta.url),"utf8"));
console.log(JSON.stringify({...audit(manifest),negative_controls_passed:controls(manifest)},null,2));
