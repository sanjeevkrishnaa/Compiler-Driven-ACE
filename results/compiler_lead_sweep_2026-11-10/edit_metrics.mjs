import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Workbook,FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const root=path.dirname(fileURLToPath(import.meta.url));
const target=path.resolve(root,'../../outputs/01a1a8b4-eb78-7a00-9b8b-8e0b77555f04/QAOA_generation_lead_sweep.xlsx');
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(target));
const sheet=wb.worksheets.getItem('Sweep');
if(process.argv.includes('--inspect')){
    console.log((await wb.inspect({kind:'region',sheetId:'Sweep',range:'B6:M21',maxChars:3500,tableMaxRows:17,tableMaxCols:12})).ndjson);
    console.log(wb.help('chart.yAxis',{include:'index,notes',maxChars:2500}).ndjson);
    const p=await wb.render({sheetName:'Sweep',range:'B2:M21',scale:1,format:'png'});
    await fs.writeFile(path.join(root,'metrics-before.png'),new Uint8Array(await p.arrayBuffer()));
    process.exit(0);
}
const before=['Sweep','Runs','Evidence'].map(name=>{const s=wb.worksheets.getItem(name);return {name,values:JSON.stringify(s.getUsedRange().values),formulas:JSON.stringify(s.getUsedRange().formulas)};});
sheet.getRange('B7').values=[['Fidelity']];sheet.getRange('E7').values=[['Wastage']];
for(const cell of ['B7','E7'])sheet.getRange(cell).format.font={name:'Arial',size:10,bold:true,color:'#203864'};
sheet.getRange('C7').formulas=[['=INDEX(G13:G21,MATCH(C6,B13:B21,0))']];
sheet.getRange('G7').formulas=[['=INDEX(I13:I21,MATCH(C6,B13:B21,0))']];
sheet.getRange('C7').setNumberFormat('0.000000');sheet.getRange('G7').setNumberFormat('0.00%');
const chart=sheet.charts.add('line',[sheet.getRange('Q12:Q21'),sheet.getRange('G12:G21'),sheet.getRange('H12:H21')]);
chart.title='Fidelity at use';chart.titleTextStyle.typeface='Arial';chart.titleTextStyle.fontSize=13;
chart.legend={position:'top',textStyle:{typeface:'Arial',fontSize:11}};
chart.xAxis={axisType:'textAxis',textStyle:{typeface:'Arial',fontSize:11}};
chart.yAxis={numberFormatCode:'0.000',numberFormatSourceLinked:false,textStyle:{typeface:'Arial',fontSize:11}};
chart.setPosition('B44','H61');
chart.series.items.forEach((s,i)=>{const fill=['#2563EB','#D97706'][i];s.fill=fill;s.line={fill,style:'solid',width:2};});
wb.recalculate();
if(Math.abs(sheet.getRange('C7').values[0][0]-0.9432337090058882)>1e-10)throw Error('Fidelity summary mismatch');
if(Math.abs(sheet.getRange('G7').values[0][0]-0.013234552043671728)>1e-10)throw Error('Waste summary mismatch');
for(const s of before.filter(s=>s.name!=='Sweep')){
    const now=wb.worksheets.getItem(s.name);
    if(JSON.stringify(now.getUsedRange().values)!==s.values || JSON.stringify(now.getUsedRange().formulas)!==s.formulas)throw Error('Unrelated sheet changed: '+s.name);
}
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:50}});
await fs.writeFile(path.join(root,'metrics-edit-errors.ndjson'),errors.ndjson);
for(const [range,name] of [['B2:M21','metrics-summary'],['B44:H61','fidelity-chart']]){
    const p=await wb.render({sheetName:'Sweep',range,scale:1,format:'png'});
    await fs.writeFile(path.join(root,`${name}.png`),new Uint8Array(await p.arrayBuffer()));
}
await (await SpreadsheetFile.exportXlsx(wb)).save(target);
console.log(JSON.stringify({target,expectedCharts:3,fidelity:sheet.getRange('C7').values[0][0],waste:sheet.getRange('G7').values[0][0]}));
