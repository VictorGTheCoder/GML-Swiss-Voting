// V18.2a: bounded metadata acquisition, never model features or referendum results.
import {readFile,writeFile,mkdir} from "node:fs/promises";
import {createHash} from "node:crypto";
import {resolve} from "node:path";
function validate(rows){
  const dateOK=d=>typeof d==="string"&&/^\d{4}-\d{2}-\d{2}$/.test(d)&&Number.isFinite(Date.parse(d))&&new Date(d).toISOString().slice(0,10)===d;
  const key=x=>`${x.family}:${x.year}:${x.page}`;
  const keys=new Set();
  for(const x of rows){
    if(!dateOK(x.vote_date)||x.vote_date<"2016-01-01"||x.vote_date>="2023-01-01"||!["fga","oc"].includes(x.family)||!Number.isInteger(x.year)||x.year<1849||x.year>Number(x.vote_date.slice(0,4))||!Number.isInteger(x.page)||x.page<1||!/^\d{2}\.\d{3}$/.test(x.affair)||!x.needle||!x.source.startsWith("https://www.parlament.ch/")||x.status!=="candidate_not_admitted"||keys.has(key(x)))throw Error("Invalid/duplicate candidate "+key(x));
    keys.add(key(x));
  }
  return {objects:rows.length,dates:new Set(rows.map(x=>x.vote_date)).size,affairs:new Set(rows.map(x=>x.affair)).size,prior_publication_year:rows.filter(x=>x.year<Number(x.vote_date.slice(0,4))).length,exact_publication_date_required:rows.length,training_rows_admitted:0};
}
function query(x){
  validate([x]);
  // Historic printed pages are not ELI sequence numbers. Search by title and date only.
  // Normalize apostrophes across typography; exact printed reference must be verified manually.
  const needle=x.needle.toLowerCase().replaceAll("’","'");
  return `PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT DISTINCT ?act ?date ?docDate ?title WHERE {
 ?act a jolux:Act; jolux:legalResourceFamilyType <https://fedlex.data.admin.ch/vocabulary/resource-family/${x.family}>; jolux:publicationDate ?date; jolux:isRealizedBy ?expression.
 ?expression jolux:language <http://publications.europa.eu/resource/authority/language/FRA>; jolux:title ?title.
 OPTIONAL { ?act jolux:dateDocument ?docDate. }
 FILTER(?date >= "${x.year}-01-01"^^xsd:date && ?date < "${x.year+1}-01-01"^^xsd:date && ?date < "${x.vote_date}"^^xsd:date)
 FILTER(CONTAINS(REPLACE(LCASE(STR(?title)), "’", "'"), ${JSON.stringify(needle)}))
} ORDER BY ?date ?act LIMIT 20`;
}
function verifyResponse(x,body){
  const rows=body?.results?.bindings;
  if(!Array.isArray(rows)||rows.length>20)throw Error("Unexpected result shape");
  const found=[];
  for(const row of rows){
    const act=row.act?.value,date=row.date?.value,title=row.title?.value,docDate=row.docDate?.value??null;
    if(typeof act!=="string"||!act.startsWith(`https://fedlex.data.admin.ch/eli/${x.family}/${x.year}/`)||typeof date!=="string"||!/^\d{4}-\d{2}-\d{2}$/.test(date)||!Number.isFinite(Date.parse(date))||new Date(date).toISOString().slice(0,10)!==date||!date.startsWith(`${x.year}-`)||date>=x.vote_date||typeof title!=="string"||!title.toLowerCase().replaceAll("’","'").includes(x.needle.toLowerCase().replaceAll("’","'")))throw Error("Unexpected date/title/family in response");
    found.push({act,date,title,docDate});
  }
  return found;
}
function selfTest(rows){
  const s=validate(rows);
  if(s.objects!==12||s.dates!==3||s.affairs!==11||s.prior_publication_year!==9)throw Error("Pilot population mismatch");
  const rejects=f=>{let rejected=false;try{f()}catch{rejected=true}if(!rejected)throw Error("Negative control accepted")};
  const x=rows[0];
  rejects(()=>validate([...rows,x]));
  rejects(()=>validate([{...x,vote_date:"2016-02-30"}]));
  rejects(()=>validate([{...x,vote_date:"2023-01-01"}]));
  rejects(()=>validate([{...x,year:2017}]));
  rejects(()=>validate([{...x,status:"admitted"}]));
  const q=query(x);
  if(!q.includes('?date < "2016-02-28"')||!q.includes("LIMIT 20")||q.includes("4403"))throw Error("Unsafe query");
  const binding={act:{value:"https://fedlex.data.admin.ch/eli/fga/2015/synthetic"},date:{value:"2015-06-01"},title:{value:"Pénalisation du mariage"}};
  if(verifyResponse(x,{results:{bindings:[binding]}}).length!==1)throw Error("Valid response rejected");
  rejects(()=>verifyResponse(x,{results:{bindings:[{...binding,date:{value:"2016-02-28"}}]}}));
  rejects(()=>verifyResponse(x,{results:{bindings:[{...binding,title:{value:"Unrelated"}}]}}));
  rejects(()=>verifyResponse(x,{results:{bindings:[{...binding,act:{value:"https://fedlex.data.admin.ch/eli/cc/2015/1"}}]}}));
  return {...s,targeted_checks:11};
}
const input=JSON.parse(await readFile("data/external/fedlex_v182/candidates.json","utf8"));
const summary=selfTest(input.candidates);
console.log("PILOT",JSON.stringify(summary));
if(!process.argv.includes("--self-test")){
  const results=[];
  const endpoint="https://fedlex.data.admin.ch/sparqlendpoint";
  for(const x of input.candidates){
    const q=query(x);
    const u=new URL(endpoint);u.searchParams.set("query",q);
    try{
      const res=await fetch(u,{headers:{Accept:"application/sparql-results+json"},signal:AbortSignal.timeout(15000),redirect:"error"});
      if(!res.ok)throw Error("HTTP "+res.status);
      const raw=await res.text();
      if(Buffer.byteLength(raw)>262144)throw Error("Oversized response");
      const matches=verifyResponse(x,JSON.parse(raw));
      results.push({family:x.family,year:x.year,page:x.page,vote_date:x.vote_date,query_sha256:createHash("sha256").update(q).digest("hex"),response_sha256:createHash("sha256").update(raw).digest("hex"),matches,status:matches.length===0?"none":matches.length===1?"unique_candidate_not_admitted":"ambiguous"});
    }catch(e){results.push({family:x.family,year:x.year,page:x.page,vote_date:x.vote_date,status:"error",error:String(e)});}
  }
  const out={...summary,retrieved:new Date().toISOString(),endpoint,unique_candidates:results.filter(x=>x.status==="unique_candidate_not_admitted").length,errors:results.filter(x=>x.status==="error").length,results};
  await mkdir(resolve("artifacts/v182a"),{recursive:true});
  await writeFile("artifacts/v182a/manifest.json",JSON.stringify(out,null,2)+"\n",{flag:"wx"});
  console.log("SUMMARY",JSON.stringify(out));
}
