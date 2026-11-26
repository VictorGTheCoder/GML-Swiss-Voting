// Audit of public PDF byte identity only; no text extraction or data admission.
import {createHash} from "node:crypto";
import {writeFileSync,readFileSync,mkdirSync} from "node:fs";
function classify(a,b){if(a.status!=="pdf"||b.status!=="pdf")return "unavailable";if(!/^[a-f0-9]{64}$/.test(a.sha256)||!/^[a-f0-9]{64}$/.test(b.sha256))throw Error("invalid hash");return a.sha256===b.sha256&&a.bytes===b.bytes?"identical":"different";}
function isPdf(bytes){return bytes.length>=5&&[37,80,68,70,45].every((v,i)=>bytes[i]===v)}
function controls(){const a={status:"pdf",sha256:"a".repeat(64),bytes:100},b={...a,sha256:"b".repeat(64)};let rejected=false;try{classify(a,{...a,sha256:"bad"})}catch{rejected=true}const checks=[classify(a,a)==="identical",classify(a,b)==="different",classify(a,{...a,bytes:101})==="different",classify(a,{status:"error"})==="unavailable",rejected,isPdf([37,80,68,70,45]),!isPdf([60,104,116,109,108]),!isPdf([37,80])];if(!checks.every(Boolean))throw Error("control failed");return checks.length}
const MAX=15*1024*1024;
async function probe(url){
 try{
  const response=await fetch(url,{signal:AbortSignal.timeout(30000),redirect:"follow"});
  if(!response.ok)return {status:"http_error",http:response.status};
  if(!response.body)return {status:"empty"};
  const reader=response.body.getReader();const chunks=[];let total=0;
  while(true){const {done,value}=await reader.read();if(done)break;total+=value.length;if(total>MAX){await reader.cancel();return {status:"too_large"};}chunks.push(value);}
  const bytes=Buffer.concat(chunks);
  if(!isPdf(bytes))return {status:"not_pdf",bytes:total};
  return {status:"pdf",bytes:total,sha256:createHash("sha256").update(bytes).digest("hex"),final_url:response.url};
 }catch(e){return {status:"error",reason:e.name,code:e.cause?.code??null};}
}
const testCount=controls();
if(process.argv.includes("--self-test")){console.log(JSON.stringify({tests_passed:testCount}));}
else{
 const manifest=JSON.parse(readFileSync(new URL("../../data/external/institutional_v151/identity_pairs_v151c.json",import.meta.url),"utf8"));
 const results=[];
 for(const pair of manifest.pairs){const [left,right]=await Promise.all([probe(pair.left),probe(pair.right)]);results.push({id:pair.id,left,right,comparison:classify(left,right)});}
 const result={status:"quarantine",tests_passed:testCount,results,training_rows_admitted:0};
 mkdirSync("reports/generated/v151c",{recursive:true});
 writeFileSync("reports/generated/v151c/identity.json",JSON.stringify(result,null,2)+"\n");
 console.log(JSON.stringify(result,null,2));
}
