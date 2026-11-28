// Metadata-only audit; no electoral outcomes, no features or admission.
import {readFileSync} from 'node:fs';
function audit(csv,evidence){
 const lines=csv.trim().split(/\r?\n/), header=lines.shift().split(",");
 const rows=lines.map(l=>{const v=l.split(",");if(v.length!==header.length)throw Error("unexpected CSV quoting");return Object.fromEntries(header.map((h,i)=>[h,v[i]]));});
 const bykey=new Map(rows.map(x=>[x.vote_key+"/"+x.wave,x]));
 if(bykey.size!==rows.length)throw Error("duplicate candidate");
 const seen=new Set(), out={candidate_rows:rows.length,source_urls:new Set(rows.map(x=>x.source_url)).size,evidence_rows:0,exact_value_and_release_matches:0,fieldwork_end_matches:0,fieldwork_end_conflicts:0,fieldwork_end_not_reported:0,verified_evidence_dates:0,training_rows_admitted:0};
 const dates=new Set();
 for(const e of evidence){const k=e.vote_key+"/"+e.wave, row=bykey.get(k);if(!row||seen.has(k))throw Error("unknown or duplicate evidence");seen.add(k);
 if(e.yes!==Number(row.yes_share_pp)||e.published!==row.stated_release_date)throw Error("value or release mismatch");
 if(Date.parse(row.vote_date)-Date.parse(e.published)<11*86400000)throw Error("late evidence");
 if(!e.url.startsWith("https://")||e.url===row.source_url)throw Error("missing distinct citation");
 if(e.fieldwork_end===null)out.fieldwork_end_not_reported++;
 else if(e.fieldwork_end>e.published)throw Error("fieldwork after publication");
 else if(e.fieldwork_end===row.fieldwork_end)out.fieldwork_end_matches++;
 else out.fieldwork_end_conflicts++;
 dates.add(row.vote_date);out.evidence_rows++;out.exact_value_and_release_matches++;
 }
 out.verified_evidence_dates=dates.size;return out;
}
const csv=readFileSync(new URL('../../data/external/polls_v132/candidates.csv',import.meta.url),'utf8');
const evidence=JSON.parse(readFileSync(new URL('../../data/external/polls_v132/corroboration_v132i.json',import.meta.url),'utf8')).evidence;
console.log(JSON.stringify(audit(csv,evidence),null,2));
