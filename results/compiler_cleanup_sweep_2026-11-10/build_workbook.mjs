import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';

const root=path.dirname(fileURLToPath(import.meta.url));
const data=JSON.parse(await fs.readFile(path.join(root,'evidence.json'),'utf8'));
const prior=JSON.parse(await fs.readFile(path.resolve(root,'../../results/compiler_lead_sweep_2026-11-10/evidence.json'),'utf8'));
const draft=process.argv.includes('--draft');
if(!draft && data.completed!==18) throw Error('All 18 audited runs are required.');
const wb=Workbook.create();
const sweep=wb.worksheets.add('Sweep'), comparison=wb.worksheets.add('BeforeAfter'), runs=wb.worksheets.add('Runs'), evidence=wb.worksheets.add('Evidence');
const ink='#203864',blue='#2563EB',orange='#D97706';
function style(sheet,range){sheet.showGridLines=false;const f=sheet.getRange(range).format;f.font={name:'Arial',size:10,color:'#243247'};f.verticalAlignment='center';f.rowHeight=23;}
function header(sheet,range){sheet.getRange(range).format={fill:ink,font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},horizontalAlignment:'center',verticalAlignment:'center',wrapText:true,rowHeight:38};}
function value(sheet,cell,v){sheet.getRange(cell).values=[[v]];}
function formula(sheet,cell,v){sheet.getRange(cell).formulas=[[v]];}
const fields=[['Run ID',null],['Route',null],['Lead k',null],['Physics seed','seed'],['Transfers','requests'],['Completed','completed_requests'],
 ['Mean latency (ms)','average_request_latency_ms'],['Completion (ms)','end_to_end_latency_ms'],['Delivered fidelity','average_delivered_epr_fidelity'],
 ['Prepared fidelity at use','average_fidelity_at_utilization'],['Storage (ms)','average_storage_time_ms'],['Ready before demand','pregenerated_hits'],
 ['Generated pairs','generated_compiler_pairs'],['Used pairs','utilized_compiler_pairs'],['Expired pairs','expired_compiler_pairs'],['Remaining pairs','remaining_compiler_pairs'],
 ['Borrowed pairs','borrowed_compiler_pairs'],['Replenishment requests','replacement_preparations_requested'],['Immediate attempts','replacement_attempts_immediate'],
 ['Planned preparations','scheduled_preparations'],['Blocked preparations','planner_blocked_preparations'],['Creation fidelity','average_fidelity_at_creation'],
 ['Admission wait (ms)','average_admission_wait_ms'],['P95 latency (ms)','request_latency_p95_ms'],['Max latency (ms)','request_latency_max_ms'],
 ['Retries','total_retries'],['On-demand fallbacks','on_demand_fallbacks'],['Late compiler uses','late_compiler_pair_uses'],['Audit violations',null]];
const raw=data.records.map(r=>fields.map((f,i)=>i===0?`${r.route.toUpperCase()}-L${r.lead}`:i===1?r.route:i===2?r.lead:i===28?0:r.metrics[f[1]]));
const n=raw.length;
style(runs,`A1:AC${Math.max(n+1,2)}`);runs.getRange('A1:AC1').values=[fields.map(f=>f[0])];
if(n) runs.getRange(`A2:AC${n+1}`).values=raw;
runs.getRange(`A1:AC${n+1}`).format.columnWidth=18;runs.getRange('A:A').format.columnWidth=17;
header(runs,'A1:AC1');runs.getRange('A1:AC1').format.rowHeight=48;
runs.getRange(`C2:H${n+1}`).setNumberFormat('#,##0');runs.getRange(`G2:K${n+1}`).setNumberFormat('0.000000');
runs.getRange(`H2:H${n+1}`).setNumberFormat('0.000');runs.getRange(`L2:U${n+1}`).setNumberFormat('#,##0');
runs.getRange(`V2:Y${n+1}`).setNumberFormat('0.000000');runs.getRange(`Z2:AC${n+1}`).setNumberFormat('#,##0');
runs.freezePanes.freezeRows(1);runs.freezePanes.freezeColumns(3);
runs.tables.add(`A1:AC${n+1}`,true,'RunMeasurements');
// Rates are calculated beside the intact imported measurements.
runs.getRange('AD1:AI1').values=[['Expiry (calc)','Waste (calc)','Utilization (calc)','Ready coverage (calc)','Fallback (calc)','Immediate replacement (calc)']];
header(runs,'AD1:AI1');runs.getRange('AD1:AI1').format.rowHeight=48;
runs.getRange(`AD1:AI${n+1}`).format.columnWidth=21;
runs.getRange(`AD2:AI${n+1}`).format={font:{name:'Arial',size:10,color:'#243247'},numberFormat:'0.00%',verticalAlignment:'center',horizontalAlignment:'right',rowHeight:23};
runs.getRange(`AD2:AI${n+1}`).formulas=raw.map((_,i)=>{const r=i+2;return [`=O${r}/M${r}`,`=SUM(O${r}:P${r})/M${r}`,`=N${r}/M${r}`,`=L${r}/E${r}`,`=AA${r}/E${r}`,`=IF(R${r}=0,"n.a.",S${r}/R${r})`];});
value(runs,`A${n+4}`,'Sources and protocol are indexed by Run ID on Evidence.');
value(runs,`A${n+5}`,'Compiler pair waste includes expired, cancelled and remaining unused pairs; on-demand fallback is excluded.');
runs.getRange('AJ1:AK1').values=[['Cancelled pairs','Cancelled rate (calc)']];header(runs,'AJ1:AK1');
runs.getRange(`AJ1:AK${n+1}`).format.columnWidth=21;
runs.getRange(`AJ2:AK${n+1}`).format={font:{name:'Arial',size:10,color:'#243247'},verticalAlignment:'center',rowHeight:23};
runs.getRange(`AJ2:AJ${n+1}`).values=data.records.map(r=>[r.metrics.cancelled_compiler_pairs]);
runs.getRange(`AJ2:AJ${n+1}`).setNumberFormat('#,##0');runs.getRange(`AK2:AK${n+1}`).setNumberFormat('0.00%');
runs.getRange(`AK2:AK${n+1}`).formulas=data.records.map((_,i)=>[`=AJ${i+2}/M${i+2}`]);
runs.getRange('AL1:AO1').values=[['Reservation-timeout pairs','Timeout rate (calc)','Other expiry / release losses','Other loss rate (calc)']];header(runs,'AL1:AO1');runs.getRange('AL1:AO1').format.rowHeight=48;
runs.getRange(`AL1:AO${n+1}`).format.columnWidth=24;
runs.getRange(`AL2:AO${n+1}`).format={font:{name:'Arial',size:10,color:'#243247'},verticalAlignment:'center',rowHeight:23};
runs.getRange(`AL2:AL${n+1}`).values=data.records.map(r=>[r.reservation_timeout_pairs]);runs.getRange(`AL2:AL${n+1}`).setNumberFormat('#,##0');
runs.getRange(`AM2:AO${n+1}`).formulas=data.records.map((_,i)=>{const r=i+2;return [`=AL${r}/M${r}`,`=O${r}-AL${r}`,`=AN${r}/M${r}`];});
runs.getRange(`AM2:AM${n+1}`).setNumberFormat('0.00%');runs.getRange(`AN2:AN${n+1}`).setNumberFormat('#,##0');runs.getRange(`AO2:AO${n+1}`).setNumberFormat('0.00%');
runs.getRange(`AE2:AE${n+1}`).formulas=data.records.map((_,i)=>[`=SUM(O${i+2}:P${i+2},AJ${i+2})/M${i+2}`]);

const provenance=data.records.map(r=>[`${r.route.toUpperCase()}-L${r.lead}`,r.summary,r.audit,r.metadata,r.trace_sha256,r.source_sha256,r.ace_commit,new Date(r.created_at),r.reused?'Reused':'New',r.engine_version,r.engine_path,r.trace]);
style(evidence,`A1:L${Math.max(n+1,2)}`);
evidence.getRange('A1:L1').values=[['Run ID','Summary source','Audit source','Metadata source','Trace SHA256','Source-set SHA256','Runtime ACE commit','Acquired (UTC)','Measurement','Engine version','Engine module','Trace source']];
if(n)evidence.getRange(`A2:L${n+1}`).values=provenance;
evidence.getRange(`A1:A${n+1}`).format.columnWidth=24;
evidence.getRange(`B1:D${n+1}`).format.columnWidth=95;
evidence.getRange(`E1:F${n+1}`).format.columnWidth=68;
evidence.getRange(`G1:G${n+1}`).format.columnWidth=43;
evidence.getRange(`H1:H${n+1}`).format.columnWidth=25;
evidence.getRange(`I1:J${n+1}`).format.columnWidth=16;
evidence.getRange(`K1:L${n+1}`).format.columnWidth=95;
evidence.getRange(`B2:L${n+1}`).format.wrapText=true;evidence.getRange(`A2:L${n+1}`).format.rowHeight=64;
evidence.getRange(`H2:H${n+1}`).setNumberFormat('yyyy-mm-dd hh:mm:ss');header(evidence,'A1:L1');
evidence.freezePanes.freezeRows(1);evidence.freezePanes.freezeColumns(1);
const protocol=[['Experiment','QAOA-224 exact initial generation lead sweep, L-1 through L-9'],
 ['Decision','Lowest pooled mean request latency across XY and cumulative History routes'],
 ['Source implementation','codex/l2-borrow-refill; completion cleanup 38aad24, identical source fingerprints across all runs'],
 ['Physical model','Pinned SeQUeNCe 0.8.1. EPR delivery only; local data-qubit teleportation gates are excluded.'],
 ['Mapping / physics seed','Mapping seed 42; physics seed 60. One matched seed is a screening comparison.'],
 ['Workload size','29,605 transfers on each routing trace; 59,210 transfers per lead across both routes.'],
 ['Hardware','4x4 mesh; 8 communication memories per core; compiler quota 6; generation capacity 8.'],
 ['Ordering / admission','Trace-order preparations; per-qubit event admission; ready-first; current demand has priority.'],
 ['Timing','Exact lead on communication-active layers; empty-layer gap 0.00001 ms; reservation window 50 ms.'],
 ['Sweep limit','Planner coherence limit is 10 active layers; admissible preparation age must be strictly less than 10.'],
 ['Borrow / replenish','Same-edge earlier demand can borrow; replacement is attempted immediately, subject to resources.'],
 ['Replenishment exception','The initial plan uses exact L-k; replenishment can launch later at consumption time.'],
 ['Already-started targets','Do not redundantly prepare a target that entered service during the borrowing handoff.'],
 ['Delivered fidelity','Average over all delivered pairs, including on-demand fallback; weighted by transfer count.'],
 ['Prepared fidelity','Average fidelity of consumed compiler pairs only; weighted by utilized-pair count.'],
 ['Waste','(Expired + cancelled + remaining) / generated compiler pairs. Cleanup discards remain waste.'],
 ['Expiry categories','Recorded expiry includes rejected or failed-handoff pair losses. Reservation-timeout counts are separately recorded.'],
 ['Coverage','Requests with a compiler pair ready before first application submission / all requests.'],
 ['Pooling','Mean request latency and delivered fidelity weighted by transfer count; total completion is averaged by route.'],
 ['Fresh reruns','All 18 cases rerun after cleanup. No pre-cleanup measurements reused.'],
 ['Before-cleanup source',path.resolve(root,'../../results/compiler_lead_sweep_2026-11-10/evidence.json')],
 ['Validation','Every run: full completion, zero physical/order audit violations, exact initial lead, pair conservation, immediate replacement counts.'],
 ['Limitations','Same mapping and one physics seed; no cross-seed confidence interval or statistical generalization.'],
 ['Defaults','This sweep does not change the default lead.']];
const ps=Math.max(24,n+5);evidence.getRange(`A${ps}:B${ps+protocol.length-1}`).values=protocol;
evidence.getRange(`A${ps}:A${ps+protocol.length-1}`).format={font:{name:'Arial',size:10,bold:true,color:ink},columnWidth:24,wrapText:true};
evidence.getRange(`B${ps}:B${ps+protocol.length-1}`).format={font:{name:'Arial',size:10,color:'#243247'},wrapText:true,columnWidth:95};
evidence.getRange(`A${ps}:B${ps+protocol.length-1}`).format.rowHeight=40;

style(sweep,'B2:Q42');sweep.tabColor=ink;sweep.getRange('B:M').format.columnWidth=15;
sweep.getRange('B3:M3').format.borders={bottom:{style:'thin',color:'#CBD5E1'}};
sweep.getRange('B:B').format.columnWidth=12;sweep.getRange('G:H').format.columnWidth=17;
sweep.getRange('B2').format.font={name:'Arial',size:16,bold:true,color:ink};
value(sweep,'B2','QAOA generation-lead sweep after cleanup');
value(sweep,'B4','Trace-order borrowing with immediate replenishment. Compiler quota 6/8. Physics seed 60.');
sweep.getRange('B4:M4').format.font={name:'Arial',size:10,italic:true,color:'#52627A'};
value(sweep,'B6','Best lead');value(sweep,'E6','Mean latency (ms)');value(sweep,'I6','Route winners');
for(const a of ['B6','E6','I6'])sweep.getRange(a).format.font={name:'Arial',size:10,bold:true,color:ink};
formula(sweep,'C6',data.completed===18?'=INDEX(B13:B21,MATCH(MIN(E13:E21),E13:E21,0))':'="pending"');
sweep.getRange('C6').setNumberFormat('"L-"0');
formula(sweep,'G6',data.completed===18?'=MIN(E13:E21)':'="pending"');sweep.getRange('G6').setNumberFormat('0.000000');
formula(sweep,'J6',data.completed===18?'="XY L-"&INDEX(B13:B21,MATCH(MIN(C13:C21),C13:C21,0))&", History L-"&INDEX(B13:B21,MATCH(MIN(D13:D21),D13:D21,0))':'="pending"');
value(sweep,'B7','Fidelity'); formula(sweep,'C7','=IF(ISNUMBER(C6),INDEX(G13:G21,MATCH(C6,B13:B21,0)),"pending")'); sweep.getRange('C7').setNumberFormat('0.000000');
value(sweep,'E7','Wastage'); formula(sweep,'G7','=IF(ISNUMBER(C6),INDEX(I13:I21,MATCH(C6,B13:B21,0)),"pending")'); sweep.getRange('G7').setNumberFormat('0.00%');
value(sweep,'B8','Selection: lowest pooled mean request latency. Separate route results remain visible.');
value(sweep,'B9','One matched physics seed. Initial generation lead only; replenishment remains immediate.');
value(sweep,'B10',`${data.completed} of 18 fresh post-cleanup runs audited. Cancellations remain included in waste.`);
sweep.getRange('B8:M10').format.font={name:'Arial',size:10,color:'#52627A'};
sweep.getRange('B12:M12').values=[['Lead','XY mean (ms)','History mean (ms)','Pooled mean (ms)','Mean completion (s)','Delivered fidelity','Prepared fidelity','Pooled waste','Ready coverage','Latency rank','XY waste','History waste']];
header(sweep,'B12:M12');
const formulas=[];
for(let lead=1;lead<=9;lead++){
    const row=lead+12;value(sweep,`B${row}`,lead);
    const xi=data.records.findIndex(r=>r.route==='xy'&&r.lead===lead),hi=data.records.findIndex(r=>r.route==='history'&&r.lead===lead);
    if(xi<0||hi<0){formulas.push(Array(11).fill('="pending"'));continue;}
    const x=xi+2,h=hi+2;
    formulas.push([`=Runs!G${x}`,`=Runs!G${h}`,
      `=(C${row}*Runs!E${x}+D${row}*Runs!E${h})/SUM(Runs!E${x},Runs!E${h})`,
      `=SUM(Runs!H${x},Runs!H${h})/2000`,
      `=(Runs!I${x}*Runs!E${x}+Runs!I${h}*Runs!E${h})/SUM(Runs!E${x},Runs!E${h})`,
      `=(Runs!J${x}*Runs!N${x}+Runs!J${h}*Runs!N${h})/SUM(Runs!N${x},Runs!N${h})`,
      `=SUM(Runs!O${x}:P${x},Runs!AJ${x},Runs!O${h}:P${h},Runs!AJ${h})/SUM(Runs!M${x},Runs!M${h})`,
      `=SUM(Runs!L${x},Runs!L${h})/SUM(Runs!E${x},Runs!E${h})`,
      `=1+COUNTIFS($E$13:$E$21,"<"&E${row})`,
      `=Runs!AE${x}`,`=Runs!AE${h}`]);
}
sweep.getRange('C13:M21').formulas=formulas;sweep.getRange('B13:B21').setNumberFormat('"L-"0');
sweep.getRange('C13:F21').setNumberFormat('0.000');sweep.getRange('G13:H21').setNumberFormat('0.000000');
sweep.getRange('I13:J21').setNumberFormat('0.00%');sweep.getRange('K13:K21').setNumberFormat('0');
sweep.getRange('L13:M21').setNumberFormat('0.00%');
for(let r=13;r<=21;r++)if(r%2===0)sweep.getRange(`B${r}:M${r}`).format.fill='#F2F5FA';
sweep.getRange('B13:M21').conditionalFormats.addCustom('$K13=1',{fill:'#DDEBF7',font:{bold:true,color:ink}});
value(sweep,'Q12','Lead label');sweep.getRange('Q13:Q21').formulas=Array.from({length:9},(_,i)=>[`="L-"&B${13+i}`]);
function makeChart(title,columns,start,end,format){
    const chart=sweep.charts.add('line',[sweep.getRange('Q12:Q21'),...columns.map(c=>sweep.getRange(`${c}12:${c}21`))]);
    chart.title=title;chart.titleTextStyle.typeface='Arial';chart.titleTextStyle.fontSize=13;
    chart.legend={position:'top',textStyle:{typeface:'Arial',fontSize:11}};
    chart.xAxis={axisType:'textAxis',textStyle:{typeface:'Arial',fontSize:11}};
    chart.yAxis={numberFormatCode:format,numberFormatSourceLinked:false,textStyle:{typeface:'Arial',fontSize:11}};
    chart.setPosition(start,end);
    chart.series.items.forEach((s,i)=>{const color=[blue,orange,ink][i];s.fill=color;s.line={fill:color,style:'solid',width:2};});
    return chart;
}
makeChart('Mean request latency (ms)',['C','D','E'],'B24','H41','0.00');
makeChart('Compiler pair waste',['L','M'],'I24','O41','0.0%');
makeChart('Fidelity at use',['G','H'],'B44','H61','0.000');
style(comparison,'B2:U17');comparison.getRange('B:U').format.columnWidth=17;
comparison.getRange('B2').values=[['Cleanup: before and after']];comparison.getRange('B2').format.font={name:'Arial',size:16,bold:true,color:ink};
value(comparison,'B4','Pooled XY + History. Negative latency, makespan and waste changes mean lower values.');
comparison.getRange('B6:U6').values=[['Lead','Before mean (ms)','After mean (ms)','Latency change','Before makespan (s)','After makespan (s)','Makespan change','Before fidelity','After fidelity','Fidelity delta (pp)','Before waste','After waste','Waste delta (pp)','Before expiry','After expiry','After cancelled','Before generated','After generated','Before unused','After unused']];
header(comparison,'B6:U6');comparison.getRange('B6:U6').format.rowHeight=46;comparison.freezePanes.freezeColumns(2);
for(let lead=1;lead<=9;lead++){
 const row=lead+6, sr=lead+12, a=prior.aggregate.find(a=>a.lead===lead);
 const old=prior.records.filter(r=>r.lead===lead), oldGen=old.reduce((n,r)=>n+r.metrics.generated_compiler_pairs,0);
 const oldExp=old.reduce((n,r)=>n+r.metrics.expired_compiler_pairs,0),oldUnused=old.reduce((n,r)=>n+r.metrics.expired_compiler_pairs+r.metrics.remaining_compiler_pairs,0);
 value(comparison,`B${row}`,lead);value(comparison,`C${row}`,a.mean_latency_ms);value(comparison,`F${row}`,a.mean_completion_s);
 value(comparison,`I${row}`,a.delivered_fidelity);value(comparison,`L${row}`,a.waste);value(comparison,`O${row}`,oldExp/oldGen);
 value(comparison,`R${row}`,oldGen);value(comparison,`T${row}`,oldUnused);
 const x=data.records.findIndex(r=>r.route==='xy'&&r.lead===lead)+2,h=data.records.findIndex(r=>r.route==='history'&&r.lead===lead)+2;
 if(x<2||h<2)continue;
 for(const [col,f] of Object.entries({D:`=Sweep!E${sr}`,E:`=D${row}/C${row}-1`,G:`=Sweep!F${sr}`,H:`=G${row}/F${row}-1`,J:`=Sweep!G${sr}`,K:`=(J${row}-I${row})*100`,M:`=Sweep!I${sr}`,N:`=(M${row}-L${row})*100`,P:`=SUM(Runs!O${x},Runs!O${h})/SUM(Runs!M${x},Runs!M${h})`,Q:`=SUM(Runs!AJ${x},Runs!AJ${h})/SUM(Runs!M${x},Runs!M${h})`,S:`=SUM(Runs!M${x},Runs!M${h})`,U:`=SUM(Runs!O${x}:P${x},Runs!AJ${x},Runs!O${h}:P${h},Runs!AJ${h})`}))formula(comparison,`${col}${row}`,f);
 if(row%2===0)comparison.getRange(`B${row}:U${row}`).format.fill='#F2F5FA';
}
comparison.getRange('B7:B15').setNumberFormat('"L-"0');comparison.getRange('C7:H15').setNumberFormat('0.000');
for(const col of ['E','H','L','M','O','P','Q'])comparison.getRange(`${col}7:${col}15`).setNumberFormat('0.00%');
comparison.getRange('I7:K15').setNumberFormat('0.000000');comparison.getRange('N7:N15').setNumberFormat('0.000');comparison.getRange('R7:U15').setNumberFormat('#,##0');
wb.recalculate();
const inspection=await wb.inspect({kind:'region',sheetId:'Sweep',range:'B6:M21',maxChars:5000,tableMaxRows:20,tableMaxCols:12});
await fs.writeFile(path.join(root,'workbook_inspection.ndjson'),inspection.ndjson);
if(!draft){
    const actual=sweep.getRange('C6').values[0][0];
    if(actual!==data.winner.lead)throw Error(`Winner differs: ${actual} vs ${data.winner.lead}`);
    const bestIndex=data.records.findIndex(r=>r.route==='xy'&&r.lead===data.winner.lead)+2;
    const oldValue=runs.getRange(`G${bestIndex}`).values[0][0];
    value(runs,`G${bestIndex}`,oldValue+100);wb.recalculate();
    if(sweep.getRange('C6').values[0][0]===actual)throw Error('Ranking did not recalculate after a source change.');
    value(runs,`G${bestIndex}`,oldValue);wb.recalculate();
    if(sweep.getRange('C6').values[0][0]!==actual)throw Error('Ranking not restored.');
}
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:50},summary:'Formula error scan'});
await fs.writeFile(path.join(root,'workbook_errors.ndjson'),errors.ndjson);
for(const [sheetName,range,label] of [['Sweep','B2:O42','sweep'],['Sweep','B44:H61','fidelity'],['Runs',`A1:M${Math.min(n+1,20)}`,'runs'],['Runs',`N1:AC${Math.min(n+1,20)}`,'run-counts'],['Runs',`AD1:AK${Math.min(n+1,20)}`,'run-rates'],['Runs',`AL1:AO${Math.min(n+1,20)}`,'loss-reasons'],['BeforeAfter','B2:U16','before-after'],['Evidence',`A1:D${Math.min(n+1,8)}`,'evidence'],['Evidence',`A${ps}:B${ps+protocol.length-1}`,'protocol']]){
    const blob=await wb.render({sheetName,range,scale:1,format:'png'});
    await fs.writeFile(path.join(root,`${label}-preview.png`),new Uint8Array(await blob.arrayBuffer()));
}
if(!draft){
    const outputDir=path.resolve(root,'../../outputs/01a1a8b4-eb78-7a00-9b8b-8e0b77555f04');
    await fs.mkdir(outputDir,{recursive:true});
    const output=await SpreadsheetFile.exportXlsx(wb);
    const target=path.join(outputDir,'QAOA_generation_lead_sweep_post_cleanup.xlsx');await output.save(target);
    console.log(JSON.stringify({target,winner:data.winner,routeWinners:data.route_winners}));
}else console.log('Draft render complete; no XLSX exported.');
