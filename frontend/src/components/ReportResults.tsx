import type { CalculationResult } from '../lib/analytics';
import type { CsvProfile } from '../lib/datasets';
import type { ReportBlock } from '../lib/reportEditor';
import { CalculationReceipt } from './CalculationReceipt';

type Row = Record<string,string|number|null>;
const display=(value:string|number|null|undefined)=>value===null||value===undefined?'Missing / no value':String(value);

function ResultTable({rows,labels={}}:{rows:Row[];labels?:Record<string,string>}) {
  const keys=rows[0]?Object.keys(rows[0]):[];
  if(!rows.length)return <p className="report-hint">No rows match the report filters.</p>;
  return <div className="csv-scroll"><table><thead><tr>{keys.map(key=><th key={key}>{labels[key]||key.replaceAll('_',' ')}</th>)}</tr></thead><tbody>{rows.map((row,index)=><tr key={index}>{keys.map(key=><td key={key}>{display(row[key])}</td>)}</tr>)}</tbody></table></div>;
}

function Plot({block,result,profile}:{block:Extract<ReportBlock,{type:'chart'}>;result:CalculationResult;profile:CsvProfile}) {
  const rows=result.result.rows;
  const groupType=profile.columns.find(column=>column.key===block.group_by)?.type;
  const points=rows.map(row=>({label:display(row.group_value),raw:display(row.value),
    y:row.value===null?null:Number(row.value),
    x:row.group_value===null?null:groupType==='date'?Date.parse(String(row.group_value)):Number(row.group_value)}));
  const usable=points.filter(point=>point.y!==null&&Number.isFinite(point.y)&&(block.chart_type==='bar'||(point.x!==null&&Number.isFinite(point.x))));
  if(!usable.length)return <p className="report-hint">No plottable values. Every returned group is retained in the data table below.</p>;
  const width=block.chart_type==='bar'?Math.max(640,points.length*50):640;
  const height=240,left=35,right=width-20,top=20,bottom=190;
  const values=usable.map(point=>point.y as number);
  const low=Math.min(0,...values),high=Math.max(0,...values),span=high-low||1;
  const y=(value:number)=>bottom-(value-low)/span*(bottom-top);
  const xs=usable.map(point=>point.x as number),xLow=Math.min(...xs),xHigh=Math.max(...xs);
  const x=(value:number)=>left+(value-xLow)/(xHigh-xLow||1)*(right-left);
  let path='',continuing=false;
  if(block.chart_type==='line')for(const point of points){
    if(point.y===null||point.x===null||!Number.isFinite(point.y)||!Number.isFinite(point.x)){continuing=false;continue;}
    path+=(continuing?' L ':' M ')+x(point.x)+' '+y(point.y);continuing=true;
  }
  return <div className="report-plot"><svg role="img" aria-label={block.title+' '+block.chart_type+' chart'} viewBox={`0 0 ${width} ${height}`} style={{minWidth:block.chart_type==='bar'?width:undefined}}>
    <line x1={left} y1={y(0)} x2={right} y2={y(0)} stroke="#a8b59e"/>
    {block.chart_type==='bar'?points.map((point,index)=>{
      const slot=(right-left)/points.length;
      return <g key={index}>
        {point.y!==null&&Number.isFinite(point.y)&&<rect x={left+index*slot+slot*.18} y={Math.min(y(point.y),y(0))} width={slot*.64} height={Math.abs(y(point.y)-y(0))} fill="#527c56"><title>{point.label+': '+point.raw}</title></rect>}
        <text x={left+(index+.5)*slot} y={bottom+20} textAnchor="middle" fontSize="10" fill="#596652">{point.label.length>12?point.label.slice(0,12)+'…':point.label}<title>{point.label}</title></text>
      </g>;
    }):<><path d={path} stroke="#527c56" strokeWidth="2.5" fill="none"/>{points.map((point,index)=>point.y!==null&&point.x!==null&&Number.isFinite(point.y)&&Number.isFinite(point.x)&&<circle key={index} cx={x(point.x)} cy={y(point.y)} r="4" fill="#335d3e"><title>{point.label+': '+point.raw}</title></circle>)}<text x={left} y={bottom+22} fontSize="10" fill="#596652">{usable[0]?.label}</text><text x={right} y={bottom+38} textAnchor="end" fontSize="10" fill="#596652">{usable.at(-1)?.label}</text></>}
  </svg></div>;
}

export function ReportResults({block,item,profile}:{block:ReportBlock;item:CalculationResult;profile:CsvProfile}) {
  const rows=item.result.rows;
  return <div className="report-result">
    {block.type==='metric'&&!block.group_by?<div className="report-metric"><span>{block.operation}{block.column&&' of '+profile.columns.find(column=>column.key===block.column)?.name}</span><strong>{display(rows[0]?.value)}</strong></div>:
      block.type==='chart'?<><Plot block={block} result={item} profile={profile}/><p className="report-hint">Hover a bar or point for its exact server value. Missing values or missing line positions are kept in the data table; gaps are not joined.</p><details className="report-data"><summary>View chart data ({rows.length} groups)</summary><ResultTable rows={rows}/></details></>:
      <ResultTable rows={rows} labels={Object.fromEntries((item.result.columns||[]).map(column=>[column.key,column.name]))}/>}
    <CalculationReceipt receipt={item.receipt}/>
  </div>;
}
