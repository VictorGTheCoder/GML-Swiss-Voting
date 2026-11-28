// V17.1 ElCom source-only audit; no electoral data read.
import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
function validate(rows,year){
  if(!Number.isInteger(year)||year<2016||year>2022)throw Error("year outside development");
  const seen=new Set(),out=[];
  for(const row of rows){
    const get=k=>row[k]?.value;
    const uri=get("municipality"), m=/^https?:\/\/ld\.admin\.ch\/municipality\/([1-9]\d*)$/.exec(uri||"");
    if(!m||seen.has(m[1]))throw Error("invalid or duplicate municipality");
    seen.add(m[1]);
    const numeric=k=>{const v=get(k);if(typeof v!=="string"||!v.trim()||!Number.isFinite(Number(v)))throw Error("invalid "+k);return Number(v)};
    const n=numeric("rows"),operators=numeric("operators"),min=numeric("min"),max=numeric("max");
    if(!Number.isInteger(n)||!Number.isInteger(operators)||operators<1||n<operators||min<0||max<min)throw Error("invalid counts or range");
    out.push({year,bfs_id:Number(m[1]),rows:n,operators,min_rp_kwh:min,max_rp_kwh:max,status:"quarantine"});
  }
  if(!out.length)throw Error("empty response");
  return out.sort((a,b)=>a.bfs_id-b.bfs_id);
}
function selfTest(){
  const row=(id="261",n="1",o="1",min="20",max="20")=>Object.fromEntries(Object.entries({municipality:"https://ld.admin.ch/municipality/"+id,rows:n,operators:o,min,max}).map(([k,value])=>[k,{value}]));
  let checks=0;
  const assert=x=>{if(!x)throw Error("self test failed");checks++};
  const reject=(rs,y)=>{let ok=false;try{validate(rs,y)}catch{ok=true}assert(ok)};
  assert(validate([row()],2016)[0].status==="quarantine");
  assert(validate([row("261","2","2","10","30")],2022)[0].operators===2);
  reject([row(),row()],2016);reject([row()],2023);reject([],2016);reject([row("abc")],2016);reject([row("261","1","2")],2016);reject([row("261","1","1","21","20")],2016);reject([row("261","1","1","","20")],2016);
  return checks;
}
const tests=selfTest();
console.log(JSON.stringify({synthetic_checks:tests}));
if(process.argv.includes('--self-test')) process.exit(0);
const endpoint='https://ld.admin.ch/query';
const output='artifacts/v171-elcom';
await mkdir(output,{recursive:true});
const summary=[];
for(let year=2016;year<=2022;year++){
  const query=`PREFIX cube: <https://cube.link/>
PREFIX d: <https://energy.ld.admin.ch/elcom/electricityprice/dimension/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?municipality (COUNT(?obs) AS ?rows) (COUNT(DISTINCT ?operator) AS ?operators) (MIN(?total) AS ?min) (MAX(?total) AS ?max)
FROM <https://lindas.admin.ch/elcom/electricityprice>
WHERE {
 <https://energy.ld.admin.ch/elcom/electricityprice> cube:observationSet/cube:observation ?obs .
 ?obs d:period "${year}"^^xsd:gYear ; d:category <https://energy.ld.admin.ch/elcom/electricityprice/category/H4> ; d:product <https://energy.ld.admin.ch/elcom/electricityprice/product/standard> ; d:municipality ?municipality ; d:operator ?operator ; d:total ?total .
} GROUP BY ?municipality ORDER BY ?municipality`;
  try {
    const response=await fetch(endpoint,{method:'POST',headers:{'Accept':'application/sparql-results+json','Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({query}),signal:AbortSignal.timeout(60000)});
    if(!response.ok)throw Error('HTTP '+response.status);
    const raw=Buffer.from(await response.arrayBuffer());
    const rows=validate(JSON.parse(raw.toString('utf8')).results.bindings,year);
    await writeFile(output+'/'+year+'.json',JSON.stringify(rows,null,2)+'\n');
    const record={year,source_sha256:createHash('sha256').update(raw).digest('hex'),query_sha256:createHash('sha256').update(query).digest('hex'),municipalities:rows.length,multiple_operators:rows.filter(x=>x.operators>1).length,multiple_rows:rows.filter(x=>x.rows>1).length,admitted:0, status:'quarantine'};
    summary.push(record);console.log(JSON.stringify(record));
  } catch(error){const record={year,status:'blocked',error:String(error),admitted:0};summary.push(record);console.log(JSON.stringify(record));}
}
await writeFile(output+'/manifest.json',JSON.stringify({endpoint,synthetic_checks:tests,summary,admitted:0},null,2)+'\n');
if(summary.every(x=>x.status==='blocked'))process.exitCode=1;
