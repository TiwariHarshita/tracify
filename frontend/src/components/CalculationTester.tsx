import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { useAuth } from '../auth/AuthContext';
import { ApiError, readableError } from '../lib/api';
import { datasetsApi } from '../lib/datasets';
import type { CsvProfile } from '../lib/datasets';
import { analyticsApi } from '../lib/analytics';
import type { Calculation, CalculationResult, Evaluation, Filter, Operation } from '../lib/analytics';
import { Feedback } from './Feedback';
import { CalculationReceipt } from './CalculationReceipt';
import '../analytics.css';

export function CalculationOutput({item}:{item:CalculationResult}) {
  const rows=item.result.rows;
  const keys=rows[0]?Object.keys(rows[0]):[];
  const labels=Object.fromEntries((item.result.columns||[]).map(column=>[column.key,column.name]));
  return <article className="calculation-result"><h3>{item.id} · {item.type}{item.result.chart_type&&' ('+item.result.chart_type+' data)'}</h3>
    {rows.length?<div className="csv-scroll"><table><thead><tr>{keys.map(key=><th key={key}>{labels[key]||key}</th>)}</tr></thead><tbody>{rows.map((row,index)=><tr key={index}>{keys.map(key=><td key={key}>{row[key]===null?<em>Missing / no value</em>:String(row[key])}</td>)}</tr>)}</tbody></table></div>:<p>No rows match.</p>}
    <CalculationReceipt receipt={item.receipt}/>
  </article>;
}

export function CalculationTester({id,onClose}:{id:string;onClose:()=>void}) {
  const {refresh}=useAuth();
  const [profile,setProfile]=useState<CsvProfile|null>(null);
  const [column,setColumn]=useState('');
  const [operation,setOperation]=useState<Operation>('sum');
  const [group,setGroup]=useState('');
  const [category,setCategory]=useState('');
  const [label,setLabel]=useState('');
  const [dateColumn,setDateColumn]=useState('');
  const [start,setStart]=useState('');const [end,setEnd]=useState('');
  const [result,setResult]=useState<Evaluation|null>(null);
  const [error,setError]=useState('');const [busy,setBusy]=useState(false);
  useEffect(()=>{
    let active=true;
    datasetsApi.profile(id).then(value=>{if(active){setProfile(value);const number=value.columns.find(item=>item.type==='number');setColumn(number?.key||'');if(!number)setOperation('count');}})
      .catch(cause=>{if(active){setError(readableError(cause));if(cause instanceof ApiError&&cause.status===401)void refresh();}});
    return()=>{active=false;};
  },[id,refresh]);
  async function run(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();if(!profile)return;
    setError('');setResult(null);setBusy(true);
    const filters:Filter[]=[];
    if(category)filters.push({type:'category',column:category,values:[label]});
    if(dateColumn)filters.push({type:'date_range',column:dateColumn,start,end});
    const calculations:Calculation[]=[{id:'metric',type:'metric',operation,column:column||null,group_by:group||null},
      {id:'top_rows',type:'table',sort_by:column||profile.columns[0].key,direction:'desc',limit:10}];
    if(group)calculations.push({id:'bar_data',type:'chart',chart_type:'bar',operation,column:column||null,group_by:group});
    try{setResult(await analyticsApi.evaluate(id,{expected_sha256:profile.sha256,filters,calculations}));}
    catch(cause){setError(readableError(cause));if(cause instanceof ApiError&&cause.status===401)void refresh();}
    finally{setBusy(false);}
  }
  return <section className="workspace-card calculation-tester">
    <div className="workspace-card-heading"><h2>Test server calculations</h2><button className="text-button" onClick={onClose}>Close calculations</button></div>
    <p className="workspace-card-description">Run a metric and top-rows table together. A category split also returns bar-chart data. These settings are temporary; open a saved report to build and keep its blocks.</p>
    {error&&<Feedback>{error}</Feedback>}
    {!profile&&!error&&<p role="status">Loading calculation columns…</p>}
    {profile&&!profile.analysis_ready&&<Feedback>This CSV has unreadable records. Fix it and upload again before calculating.</Feedback>}
    {profile&&profile.analysis_ready&&<form onSubmit={run} onChange={()=>setResult(null)}><fieldset disabled={busy} className="calculation-fields">
      <div className="field"><label htmlFor="calc-operation">Operation</label><select id="calc-operation" value={operation} onChange={event=>{const next=event.target.value as Operation;setOperation(next);if(next!=='count'){const eligible=profile.columns.filter(item=>item.type==='number'||((next==='min'||next==='max')&&item.type==='date'));if(!eligible.some(item=>item.key===column))setColumn(eligible[0]?.key||'');}}}>{['sum','average','count','min','max'].map(value=><option key={value} disabled={value!=='count'&&!profile.columns.some(item=>item.type==='number'||((value==='min'||value==='max')&&item.type==='date'))}>{value}</option>)}</select></div>
      <div className="field"><label htmlFor="calc-column">Value column</label><select id="calc-column" value={column} onChange={event=>setColumn(event.target.value)}>{operation==='count'&&<option value="">All rows</option>}{profile.columns.filter(item=>operation==='count'||item.type==='number'||((operation==='min'||operation==='max')&&item.type==='date')).map(item=><option key={item.key} value={item.key}>{item.name}</option>)}</select></div>
      <div className="field"><label htmlFor="calc-group">Split by category</label><select id="calc-group" value={group} onChange={event=>setGroup(event.target.value)}><option value="">No split</option>{profile.columns.filter(item=>item.type==='category').map(item=><option key={item.key} value={item.key}>{item.name}</option>)}</select></div>
      <div className="field"><label htmlFor="calc-category">Category filter</label><select id="calc-category" value={category} onChange={event=>setCategory(event.target.value)}><option value="">No category filter</option>{profile.columns.filter(item=>item.type==='category'||item.type==='text').map(item=><option key={item.key} value={item.key}>{item.name}</option>)}</select></div>
      <div className="field"><label htmlFor="calc-label">Exact category value</label><input id="calc-label" value={label} disabled={!category||busy} onChange={event=>setLabel(event.target.value)} maxLength={512} placeholder="For Tips: Sun or Dinner" /></div>
      <div className="field"><label htmlFor="calc-date">Date filter column</label><select id="calc-date" value={dateColumn} onChange={event=>setDateColumn(event.target.value)}><option value="">No date filter</option>{profile.columns.filter(item=>item.type==='date').map(item=><option key={item.key} value={item.key}>{item.name}</option>)}</select></div>
      <div className="field"><label htmlFor="calc-start">From (UTC day)</label><input id="calc-start" type="date" value={start} required={!!dateColumn} disabled={!dateColumn||busy} onChange={event=>setStart(event.target.value)}/></div>
      <div className="field"><label htmlFor="calc-end">Through (UTC day)</label><input id="calc-end" type="date" value={end} min={start} required={!!dateColumn} disabled={!dateColumn||busy} onChange={event=>setEnd(event.target.value)}/></div>
      <button className="button primary" disabled={busy||(!column&&operation!=='count')}>{busy?'Calculating on server…':'Run calculations'}</button>
    </fieldset></form>}
    {result&&<div aria-live="polite">{result.results.map(item=><CalculationOutput key={item.id} item={item}/>)}</div>}
  </section>;
}
