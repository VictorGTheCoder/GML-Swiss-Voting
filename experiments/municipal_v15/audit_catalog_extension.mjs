// Metadata only; no targets or feature admission.
import {readFileSync} from "node:fs";
function audit(m,prior){
 const fail=s=>{throw Error(s)};
 if(m.status!=="quarantine"||prior.status!=="quarantine")fail("quarantine");
 const ids=new Set(),dates=new Set(),fam=new Map(),newDates=new Set(),newFam=new Set();
 let entries=0,pairs=0,covered=0,newEntries=0,newPairs=0,yearOnly=0,single=0;
 const oldIds=new Set(prior.rows.map(r=>r.vote_key)),oldDates=new Set(prior.rows.map(r=>r.vote_date));
 for(const [i,data] of [prior,m].entries()) for(const r of data.rows){
  if(!/^\d{4}$/.test(r.vote_key)||ids.has(r.vote_key))fail("object identity");
  if(!/^\d{4}-\d{2}-\d{2}$/.test(r.vote_date)||r.vote_date<"2016-01-01"||r.vote_date>="2023-01-01"||new Date(r.vote_date).toISOString().slice(0,10)!==r.vote_date)fail("vote date");
  if(r.catalog_url!==`https://swissvotes.ch/vote/${r.vote_key.slice(0,-1)}.00/campaign-material`)fail("catalog mismatch");
  ids.add(r.vote_key);dates.add(r.vote_date);
  if(i){if(oldIds.has(r.vote_key)||oldDates.has(r.vote_date))fail("not independent sample date");newDates.add(r.vote_date)}
  if(r.families.length)covered++;
  const local=new Set();
  for(const f of r.families){
   if(!f.id||local.has(f.id))fail("duplicate family");
   local.add(f.id);
   if(!/^\d{4}(-\d{2}(-\d{2})?)?$/.test(f.doc_date))fail("date format");
   const d=new Date(f.doc_date.length===4?f.doc_date+"-01-01":f.doc_date.length===7?f.doc_date+"-01":f.doc_date);
   if(d.toISOString().slice(0,f.doc_date.length)!==f.doc_date)fail("invalid date");
   const upper=f.doc_date.length===4?f.doc_date+"-12-31":f.doc_date.length===7?new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth()+1,0)).toISOString().slice(0,10):f.doc_date;
   if(upper>=r.vote_date)fail("not pre-vote");
   if(!f.languages.length||new Set(f.languages).size!==f.languages.length||f.languages.some(l=>!["de","fr","it"].includes(l)))fail("languages");
   if(fam.has(f.id)&&fam.get(f.id)!==f.doc_date)fail("family date mismatch");
   fam.set(f.id,f.doc_date);entries+=f.languages.length;pairs++;
   if(i){newEntries+=f.languages.length;newPairs++;newFam.add(f.id);if(f.doc_date.length===4)yearOnly++;if(f.languages.length===1)single++}
  }
 }
 const evidence=new Set();
 for(const e of m.evidence){if(!newFam.has(e.family)||evidence.has(e.family)||e.sha256!==null||e.license!==null)fail("evidence gate");evidence.add(e.family)}
 return {new_objects:m.rows.length,new_dates:newDates.size,new_entries:newEntries,new_object_family_pairs:newPairs,new_distinct_families:newFam.size,new_year_precision_pairs:yearOnly,new_single_language_pairs:single,combined_objects:ids.size,combined_dates:dates.size,combined_candidate_objects:covered,combined_entries:entries,combined_object_family_pairs:pairs,combined_distinct_families:fam.size,evidence_families:evidence.size,training_rows_admitted:0};
}
function controls(m,p){const mutations=[x=>x.rows.push(x.rows[0]),x=>x.rows[0].families[0].doc_date=x.rows[0].vote_date,x=>x.rows[0].families[0].doc_date="2020-02-30",x=>x.rows[0].families[0].languages=["de","de"],x=>x.rows[0].vote_date="2023-01-01",x=>x.status="admitted",x=>x.rows[0].families[0].doc_date="2021",x=>x.rows[2].families[0].doc_date="2021-03-23",x=>x.evidence[0].license="certified",x=>x.rows[0].vote_date="2017-09-24"];for(const mutate of mutations){const copy=JSON.parse(JSON.stringify(m));mutate(copy);let rejected=false;try{audit(copy,p)}catch{rejected=true}if(!rejected)throw Error("negative control failed")}return mutations.length;}
const read=(name)=>JSON.parse(readFileSync(new URL("../../data/external/institutional_v151/"+name,import.meta.url),"utf8"));
const m=read("catalog_extension_v151b.json"),p=read("catalog_pilot.json");
console.log(JSON.stringify({...audit(m,p),negative_controls_passed:controls(m,p)},null,2));
