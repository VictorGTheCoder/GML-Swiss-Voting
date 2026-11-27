// V18.2b: verify original PDF first-page printed pagination, no model admission.
import {readFile,writeFile,mkdir} from "node:fs/promises";
import {createHash} from "node:crypto";
import {execFileSync} from "node:child_process";
import {strict as assert} from "node:assert";
const sha=b=>createHash("sha256").update(b).digest("hex");
const input=JSON.parse(await readFile("data/external/fedlex_v182/pdf_candidates.json","utf8"));
const base="https://fedlex.data.admin.ch/eli/";
const endpoint="https://fedlex.data.admin.ch/sparqlendpoint";
function safeAct(x,m){
  return typeof m.act==="string" && m.act.startsWith(base+x.family+"/"+x.year+"/") && /^\d+$/.test(m.act.split("/").at(-1)) && /^\d{4}-\d{2}-\d{2}$/.test(m.date) && m.date.startsWith(x.year+"-") && m.date<x.vote_date && new Date(m.date).toISOString().slice(0,10)===m.date && x.vote_date>="2016-01-01" && x.vote_date<"2023-01-01" && x.status==="candidate_not_admitted";
}
function safePdf(act,uri){
  const u=new URL(uri);
  const expected="/filestore/fedlex.data.admin.ch"+new URL(act).pathname+"/fr/";
  return u.protocol==="https:"&&["www.fedlex.admin.ch","fedlex.data.admin.ch"].includes(u.hostname)&&!u.port&&!u.username&&!u.password&&!u.search&&!u.hash&&u.pathname.startsWith(expected)&&/^\/(?:pdf-a|pdf|pdf-x)\/[A-Za-z0-9._-]+\.pdf$/.test(u.pathname.slice(expected.length-1));
}
function printedPage(text,page){
  // Do not confuse an in-body article, year or page reference with a printed page.
  const lines=text.split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
  return lines.length>=3 && [...lines.slice(0,3),...lines.slice(-3)].some(s=>s===String(page));
}
function query(m){
  return "PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>\nSELECT DISTINCT ?url ?m ?format ?userFormat WHERE { <"+m.act+"> jolux:isRealizedBy ?e. ?e jolux:language <http://publications.europa.eu/resource/authority/language/FRA>; jolux:isEmbodiedBy ?m. ?m jolux:isExemplifiedBy ?url. OPTIONAL { ?m jolux:format ?format. } OPTIONAL { ?m jolux:userFormat ?userFormat. } FILTER(?format IN (<http://publications.europa.eu/resource/authority/file-type/PDF>, <http://publications.europa.eu/resource/authority/file-type/PDFX>) || ?userFormat IN (<https://fedlex.data.admin.ch/vocabulary/user-format/pdf-a>, <https://fedlex.data.admin.ch/vocabulary/user-format/pdf-x>)) } LIMIT 20";
}
function tests(){
  assert.equal(input.candidates.length,12);
  assert.equal(input.candidates.reduce((a,x)=>a+x.provisional_matches.length,0),14);
  assert.equal(input.candidates.filter(x=>x.provisional_matches.length===1).length,11);
  for(const x of input.candidates) for(const m of x.provisional_matches) assert(safeAct(x,m));
  const x=input.candidates[0],m=x.provisional_matches[0];
  assert(!safeAct(x,{...m,date:x.vote_date}));
  assert(!safeAct({...x,vote_date:"2023-01-01"},m));
  assert(!safeAct(x,{...m,act:base+"cc/2015/1"}));
  assert(safePdf(m.act,"https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch"+new URL(m.act).pathname+"/fr/pdf-a/test.pdf"));
  assert(safePdf(m.act,"https://fedlex.data.admin.ch/filestore/fedlex.data.admin.ch"+new URL(m.act).pathname+"/fr/pdf-a/test.pdf"));
  assert(!safePdf(m.act,"https://fedlex.data.admin.ch.evil.example/filestore/fedlex.data.admin.ch"+new URL(m.act).pathname+"/fr/pdf-a/test.pdf"));
  assert(!safePdf(m.act,"https://fedlex.data.admin.ch/filestore/fedlex.data.admin.ch"+new URL(m.act).pathname+"/de/pdf-a/test.pdf"));
  assert(!safePdf(m.act,"https://fedlex.data.admin.ch/filestore/fedlex.data.admin.ch"+new URL(m.act).pathname+"/fr/html/test.pdf"));
  assert(!safePdf(m.act,"https://example.com/test.pdf"));
  assert(!safePdf(m.act,"https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/2015/1/fr/pdf-a/test.pdf"));
  assert(printedPage("Title\nBody\nOther\n4403",4403));
  assert(!printedPage("Title\nBody 4403\nOther",4403));
  assert(!printedPage("Title\nA\nB\n4403\nC\nD\nEnd",4403));
  assert(query(m).includes("LIMIT 20"));
  console.log("SELF_TEST_OK");
}
tests();
async function limited(url,max,accept){
  const r=await fetch(url,{signal:AbortSignal.timeout(20000),redirect:"error",headers:{Accept:accept}});
  if(!r.ok)throw Error("HTTP "+r.status);
  const chunks=[];let size=0;
  for await(const chunk of r.body){size+=chunk.length;if(size>max)throw Error("response limit");chunks.push(Buffer.from(chunk));}
  return Buffer.concat(chunks);
}
if(!process.argv.includes("--self-test")){
  await mkdir("artifacts/v182b",{recursive:true});
  const rows=[];
  for(const x of input.candidates){
    const matches=[];
    for(const m of x.provisional_matches){
      let rec={act:m.act,date:m.date,docDate:m.docDate,status:"not_verified"};
      try{
        const q=query(m),u=new URL(endpoint);u.searchParams.set("query",q);
        const raw=await limited(u,262144,"application/sparql-results+json");
        rec={...rec,query_sha256:sha(q),response_sha256:sha(raw)};
        const bindings=JSON.parse(raw).results?.bindings;
        if(!Array.isArray(bindings)||bindings.length>=20)throw Error("invalid/truncated metadata");
        rec.binding_count=bindings.length;
        const rawUrls=[...new Set(bindings.map(b=>b.url?.value).filter(u=>typeof u==="string"))];
        const urls=rawUrls.filter(u=>{try{return safePdf(m.act,u)}catch{return false}});
        rec.rejected_url_count=rawUrls.length-urls.length;
        rec.rejected_hosts=[...new Set(rawUrls.filter(u=>!urls.includes(u)).map(u=>{try{return new URL(u).hostname}catch{return "invalid"}}))];
        rec.pdf_candidates=urls;
        // Multiple versions require manual review. Do not pick based on page match.
        if(urls.length!==1)throw Error(urls.length===0?"No allowed PDF URL":"Multiple allowed PDF URLs");
        const pdf=await limited(urls[0],10*1024*1024,"application/pdf");
        if(pdf.subarray(0,5).toString()!=="%PDF-")throw Error("not PDF");
        const text=execFileSync("pdftotext",["-f","1","-l","1","-layout","-","-"],{input:pdf,encoding:"utf8",timeout:15000,maxBuffer:1024*1024});
        rec={...rec,pdf_sha256:sha(pdf),bytes:pdf.length,first_page_text_sha256:sha(text),first_page_chars:text.length,printed_page_match:printedPage(text,x.page),status:printedPage(text,x.page)?"page_candidate_not_admitted":"page_unverified"};
      }catch(e){rec.error=String(e.message??e);}
      matches.push(rec);
    }
    rows.push({family:x.family,year:x.year,page:x.page,vote_date:x.vote_date,matches});
  }
  const summary={revision:"V18.2b-r1",rows,objects:rows.length,unique_page_candidates:rows.filter(r=>r.matches.filter(m=>m.printed_page_match).length===1).length,unverified_attempts:rows.flatMap(r=>r.matches).filter(m=>m.status==="not_verified").length,training_rows_admitted:0};
  await writeFile("artifacts/v182b/manifest.json",JSON.stringify(summary,null,2)+"\n",{flag:"wx"});
  console.log("SUMMARY",JSON.stringify(summary));
}
