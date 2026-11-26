import {createHash} from 'node:crypto';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
function inspectHeader(t, expected) {
  const end=t.search(/(?:^|\n)\s*DATA\s*=/i);
  if(end<0) throw Error("No PX DATA marker");
  const h=t.slice(0,end);
  if(!/(?:^|\n)\s*STUB\s*=/i.test(h)||!/(?:^|\n)\s*HEADING\s*=/i.test(h)) throw Error("No PX dimensions");
  const entries=[...h.matchAll(/(?:^|\n)\s*VALUES(?:\[[^\]]+\])?\s*\(\s*"([^"]+)"\s*\)\s*=\s*([^;]*);/gi)].map(m=>({name:m[1],values:[...m[2].matchAll(/"((?:[^"]|"")*)"/g)].map(a=>a[1])}));
  const years=entries.filter(e=>e.values.length>1&&e.values.every(v=>/^(19|20)\d{2}$/.test(v)));
  if(!years.length) throw Error("No unambiguous year dimension");
  const maxYears=[...new Set(years.map(e=>Math.max(...e.values.map(Number))))];
  if(maxYears.length!==1||maxYears[0]!==expected) throw Error("Unexpected latest observation year: "+maxYears.join(","));
  const geo=entries.filter(e=>/gemeinde|commune|municipalit|district|bezirk/i.test(e.name));
  const updates=[...h.matchAll(/(?:^|\n)\s*(LAST-UPDATED|CREATION-DATE|REFPERIOD|CONTACT|MATRIX)(?:\[[^\]]+\])?\s*=\s*([^;]*);/gi)].map(m=>({key:m[1],value:m[2].trim().slice(0,300)}));
  return {latest_year:expected,year_dimensions:years.map(e=>({name:e.name,count:e.values.length})),dimensions:entries.map(e=>({name:e.name,count:e.values.length})),geography_dimensions:geo.map(e=>({name:e.name,count:e.values.length})),update_metadata:updates,admitted:0};
}
function selfTest(){
 const sample=(year,geo="Gemeinde")=>`STUB="Jahr";\nHEADING="${geo}";\nVALUES("Jahr")="2015","${year}";\nVALUES("${geo}")="1 A","2 B";\nDATA= 1 2 3 4;`;
 let n=0; const ok=(x)=>{if(!x)throw Error("self test failed");n++};const rejects=(s,y)=>{let rejected=false;try{inspectHeader(s,y)}catch{rejected=true}ok(rejected)};
 ok(inspectHeader(sample(2018),2018).latest_year===2018);
 ok(inspectHeader(sample(2018),2018).geography_dimensions[0].count===2);
 ok(inspectHeader(sample(2018,"Canton"),2018).geography_dimensions.length===0);
 ok(inspectHeader(sample(2018),2018).admitted===0);
 rejects(sample(2025),2018); rejects("<html>error</html>",2018); rejects('DATA=1;',2018);
 rejects(sample(2018).replace('"2015","2018"','"old","new"'),2018);
 return n;
}
if(process.argv.includes('--self-test')) { console.log('Synthetic controls passed: '+selfTest()); }
else {
 const sources=JSON.parse(await readFile(new URL('./stru_vintages.json',import.meta.url),'utf8'));
 const results=[];
 for(const source of sources) {
   const url='https://dam-api.bfs.admin.ch/hub/api/dam/assets/'+source.asset+'/master';
   const record={...source,url,admitted:0};
   try {
     const response=await fetch(url,{signal:AbortSignal.timeout(120000),redirect:'error'});
     record.http_status=response.status;
     record.content_type=response.headers.get('content-type');
     if(!response.ok)throw Error('HTTP '+response.status);
     const bytes=Buffer.from(await response.arrayBuffer());
     if(bytes.length>60_000_000)throw Error('Unexpected source size');
     record.bytes=bytes.length;
     record.sha256=createHash('sha256').update(bytes).digest('hex');
     const header=new TextDecoder('windows-1252').decode(bytes.subarray(0,8_000_000));
     record.header=inspectHeader(header,source.year);
     record.status='header_verified_quarantine';
   } catch(e) { record.status='blocked';record.error=String(e); }
   results.push(record);
 }
 const output={version:'V17.2b',source_count:sources.length,header_verified:results.filter(r=>r.status==='header_verified_quarantine').length,admitted:0,results};
 await mkdir('artifacts/v172b',{recursive:true});
 await writeFile('artifacts/v172b/manifest.json',JSON.stringify(output,null,2)+'\n');
 console.log(JSON.stringify(output));
 if(!output.header_verified)process.exitCode=1;
}
