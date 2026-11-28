// V14.1h: source-only panel audit. No election observations or model inputs.
import {readFileSync} from 'node:fs';
function audit(csv) {
  const lines=csv.trim().split(/\r?\n/);
  const header=lines.shift().split(",");
  const keys=["reference_year","canton","resource_index_consultation","status"];
  const ix=keys.map(k=>header.indexOf(k));
  if(ix.includes(-1))throw Error("missing columns");
  const groups=new Map(),all=[];
  const cantons="ZH BE LU UR SZ OW NW GL ZG FR SO BS BL SH AR AI SG GR AG TG TI VD VS NE GE JU".split(" ");
  for(const line of lines){
    const l=line.split(",");
    if(l.length!==header.length)throw Error("unexpected CSV shape");
    const [y,c,v,status]=ix.map(i=>l[i]);
    const year=Number(y),value=Number(v);
    if(!cantons.includes(c)||!Number.isInteger(year)||year<2016||year>2022||!v||!Number.isFinite(value)||value<=0||status!=="candidate_not_admitted")throw Error("invalid candidate");
    if(!groups.has(c))groups.set(c,new Map());
    if(groups.get(c).has(year))throw Error("duplicate key");
    groups.get(c).set(year,value);all.push(value);
  }
  if(groups.size!==26||all.length!==182)throw Error("incomplete panel");
  const mean=a=>a.reduce((s,v)=>s+v,0)/a.length;
  const median=a=>{const b=[...a].sort((x,y)=>x-y);return (b[Math.floor((b.length-1)/2)]+b[Math.ceil((b.length-1)/2)])/2;};
  const m=mean(all),ranges=[],changes=[],first=[],last=[];
  let within=0,between=0;
  for(const c of cantons){
    const g=groups.get(c);
    const a=Array.from({length:7},(_,i)=>g.get(2016+i));
    if(a.some(v=>!Number.isFinite(v)))throw Error("missing year");
    const cm=mean(a);
    within+=a.reduce((s,v)=>s+(v-cm)**2,0);
    between+=a.length*(cm-m)**2;
    ranges.push(Math.max(...a)-Math.min(...a));
    for(let i=1;i<a.length;i++)changes.push(Math.abs(a[i]-a[i-1]));
    first.push(a[0]);last.push(a[6]);
  }
  const total=all.reduce((s,v)=>s+(v-m)**2,0);
  if(total<=0||Math.abs(total-within-between)>1e-8*Math.max(1,total))throw Error("variance identity");
  const f=mean(first),l=mean(last);
  const corr=first.reduce((s,v,i)=>s+(v-f)*(last[i]-l),0)/Math.sqrt(first.reduce((s,v)=>s+(v-f)**2,0)*last.reduce((s,v)=>s+(v-l)**2,0));
  if(!Number.isFinite(corr))throw Error("undefined correlation");
  return {rows:all.length,cantons:groups.size,years:7,annual_pairs:changes.length,between_share:between/total,within_share:within/total,mean_abs_annual_change:mean(changes),median_abs_annual_change:median(changes),median_range:median(ranges),correlation_2016_2022:corr,training_rows_admitted:0};
}
function selfTest(csv,audit){
  const original=audit(csv);
  if(Math.abs(original.between_share+original.within_share-1)>1e-10)throw Error("partition");
  const lines=csv.trim().split(/\r?\n/);
  const rejected=[lines.slice(0,-1).join("\n"),[...lines,lines[1]].join("\n"),csv.replace("candidate_not_admitted","admitted"),csv.replace(/^2016,/m,"2023,")];
  for(const sample of rejected){let failed=false;try{audit(sample)}catch{failed=true}if(!failed)throw Error("negative test failed");}
  return 5;
}
const csv=readFileSync(process.argv[2] || 'data/external/fiscal_equalization_v141/resource_index_candidates.csv','utf8');
console.log(JSON.stringify({...audit(csv),checks_passed:selfTest(csv,audit)},null,2));
