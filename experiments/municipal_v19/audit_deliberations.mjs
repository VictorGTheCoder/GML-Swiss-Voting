import { readFileSync } from "node:fs";

function measure(c) {
  const validDate = s => /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(s)) && new Date(s).toISOString().slice(0,10) === s;
  if (!validDate(c.vote_date) || !validDate(c.edition_date) || c.edition_date >= c.vote_date || c.vote_date >= "2023-01-01" || c.admitted !== 0) throw Error("Temporal/admission gate");
  if (new Set(c.projects.map(p=>p.project)).size !== c.projects.length || new Set(c.projects.map(p=>p.act)).size !== c.projects.length) throw Error("Duplicate project");
  return c.projects.map(p=>{
    if (!p.events.length || new Set(p.events).size !== p.events.length) throw Error("Duplicate or empty events");
    const ds=p.events.map(e=>{const [d,ch,...rest]=e.split(" ");if(!validDate(d)||d>c.edition_date||!["CN","CE"].includes(ch)||rest.length)throw Error("Invalid event");return d;});
    return {project:p.project,act:p.act,council_days:p.events.length,calendar_days:new Set(ds).size,cn_days:p.events.filter(e=>e.endsWith(" CN")).length,ce_days:p.events.filter(e=>e.endsWith(" CE")).length};
  });
}

function selfTest(c) {
  const check=(condition)=>{if(!condition)throw Error("Assertion failed");};
  const reject=(mutate)=>{const x=JSON.parse(JSON.stringify(c));mutate(x);let failed=false;try{measure(x);}catch{failed=true;}check(failed);};
  const m=measure(c);check(m[0].council_days===14 && m[1].council_days===12);check(m[0].calendar_days===12 && m[1].calendar_days===10);
  reject(x=>x.projects[0].events.push(x.projects[0].events[0]));
  reject(x=>x.projects[0].events.push(x.vote_date+" CN"));
  reject(x=>x.projects[1].act=x.projects[0].act);
  reject(x=>x.admitted=1);
  reject(x=>x.projects[0].events.push("2016-02-30 CN"));
  reject(x=>x.vote_date="2023-01-01");
  return 8;
}

const c=JSON.parse(readFileSync(new URL("./deliberations_pilot.json",import.meta.url),"utf8"));
console.log(JSON.stringify({version:"V19.3a",status:"pilot_metadata_only",projects:measure(c),source_families:1,vote_dates:1,target_rows_admitted:0,targeted_checks:selfTest(c)},null,2));
