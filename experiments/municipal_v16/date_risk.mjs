import {readFileSync} from "node:fs";
function audit(markdown){
 const rows=[...markdown.matchAll(/^\| (20\d\d-\d\d-\d\d) \| ([\d.]+) \| ([\d.]+) \| ([\d.]+) \|$/gm)].map(m=>({date:m[1],mae:Number(m[2])}));
 if(rows.length!==23||new Set(rows.map(x=>x.date)).size!==23||rows.some((x,i)=>x.date<"2016-01-01"||x.date>="2023-01-01"||!Number.isFinite(x.mae)||x.mae<0||x.mae>100||(i&&x.date<=rows[i-1].date)))throw Error("Unexpected historical date panel");
 const upper=(values,level)=>{const k=Math.ceil((values.length+1)*level);return k>values.length?null:values.slice().sort((a,b)=>a-b)[k-1]};
 const results=[];
 for(const level of [.8,.9])for(const mode of ["fixed_initial_9","expanding"]){
  const detail=rows.slice(9).map((row,i)=>{const train=rows.slice(0,mode==="expanding"?i+9:9);const bound=upper(train.map(x=>x.mae),level);if(bound===null||train.at(-1).date>=row.date)throw Error("Invalid calibration");return {date:row.date,training_dates:train.length,upper_pp:bound,observed_date_macro_mae_pp:row.mae,covered:row.mae<=bound}});
  results.push({level,mode,evaluation_dates:detail.length,covered_dates:detail.filter(x=>x.covered).length,mean_upper_pp:detail.reduce((a,x)=>a+x.upper_pp,0)/detail.length,detail});
 }
 return {source:"reports/experiments/v11_campaign/V11.6-results.md",source_precision_pp:.0001,unit:"date-level mean of object MAE, not municipality prediction interval",warmup_dates:9,results};
}
function controls(markdown){
 const a=audit(markdown);let tests=0;const check=x=>{if(!x)throw Error("test failed");tests++};
 check(a.results.length===4);check(a.results.every(x=>x.evaluation_dates===14));check(a.results.every(x=>x.detail.every(y=>y.training_dates>=9)));check(a.results.filter(x=>x.mode==="fixed_initial_9").every(x=>new Set(x.detail.map(y=>y.upper_pp)).size===1));
 const changed=markdown.replace("| 2022-09-25 | 7.4811 |","| 2022-09-25 | 99.0000 |");check(changed!==markdown&&JSON.stringify(a.results.map(x=>x.detail.map(y=>y.upper_pp)))===JSON.stringify(audit(changed).results.map(x=>x.detail.map(y=>y.upper_pp))));
 let rejected=false;try{audit(markdown.replace("2022-09-25","2023-09-25"))}catch{rejected=true}check(rejected);return tests;
}
const markdown=readFileSync(new URL("../../reports/experiments/v11_campaign/V11.6-results.md",import.meta.url),"utf8");
console.log(JSON.stringify({...audit(markdown),tests_passed:controls(markdown)},null,2));
