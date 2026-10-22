import type { CsvProfile } from '../lib/datasets';
import type { Filter, Operation } from '../lib/analytics';
import type { ReportBlock } from '../lib/reportEditor';

export function newBlock(type:ReportBlock['type'],profile:CsvProfile):ReportBlock {
  const id='block_'+crypto.randomUUID();
  const numeric=profile.columns.find(column=>column.type==='number')?.key;
  const column=numeric||null;
  if(type==='note')return {id,type,title:'Note',text:''};
  if(type==='table')return {id,type,title:'Top rows',sort_by:numeric||profile.columns[0].key,direction:'desc',limit:10};
  if(type==='chart')return {id,type,title:'Chart',chart_type:'bar',operation:numeric?'sum':'count',column,
    group_by:profile.columns.find(column=>column.type==='category'||column.type==='date')?.key||''};
  return {id,type,title:'Metric',operation:numeric?'sum':'count',column,group_by:null};
}

export function BlockFields({block,profile,onChange}:{block:ReportBlock;profile:CsvProfile;onChange:(block:ReportBlock)=>void}) {
  const prefix=block.id;
  if(block.type==='note')return <div className="field"><label htmlFor={prefix+'-text'}>Note text</label><textarea id={prefix+'-text'} rows={4} maxLength={10000} value={block.text} onChange={event=>onChange({...block,text:event.target.value})}/></div>;
  if(block.type==='table')return <div className="report-fields">
    <div className="field"><label htmlFor={prefix+'-sort'}>Sort by</label><select id={prefix+'-sort'} value={block.sort_by} onChange={event=>onChange({...block,sort_by:event.target.value})}>{profile.columns.map(column=><option key={column.key} value={column.key}>{column.name}</option>)}</select></div>
    <div className="field"><label htmlFor={prefix+'-direction'}>Order</label><select id={prefix+'-direction'} value={block.direction} onChange={event=>onChange({...block,direction:event.target.value as 'asc'|'desc'})}><option value="desc">Highest first</option><option value="asc">Lowest first</option></select></div>
    <div className="field"><label htmlFor={prefix+'-limit'}>Rows to show</label><input id={prefix+'-limit'} type="number" required min={1} max={100} value={block.limit} onChange={event=>onChange({...block,limit:Number(event.target.value)})}/></div>
  </div>;
  const valueColumns=profile.columns.filter(column=>block.operation==='count'||column.type==='number'||(block.type==='metric'&&['min','max'].includes(block.operation)&&column.type==='date'));
  function operation(next:Operation) {
    if(block.type==='note'||block.type==='table')return;
    let column=block.column;
    const current=profile.columns.find(item=>item.key===column);
    if(next!=='count'&&(!current||(current.type!=='number'&&!(block.type==='metric'&&['min','max'].includes(next)&&current.type==='date')))) {
      column=profile.columns.find(item=>item.type==='number'||(block.type==='metric'&&['min','max'].includes(next)&&item.type==='date'))?.key||null;
    }
    onChange({...block,operation:next,column} as ReportBlock);
  }
  const groups=profile.columns.filter(column=>block.type==='metric'?column.type==='category':block.chart_type==='bar'?['category','date'].includes(column.type):['date','number'].includes(column.type));
  return <div className="report-fields">
    {block.type==='chart'&&<div className="field"><label htmlFor={prefix+'-chart'}>Chart type</label><select id={prefix+'-chart'} value={block.chart_type} onChange={event=>{
      const chart_type=event.target.value as 'bar'|'line';
      const allowed=profile.columns.filter(column=>chart_type==='bar'?['category','date'].includes(column.type):['number','date'].includes(column.type));
      onChange({...block,chart_type,group_by:allowed.some(column=>column.key===block.group_by)?block.group_by:allowed[0]?.key||''});
    }}><option value="bar">Bar</option><option value="line">Line</option></select></div>}
    <div className="field"><label htmlFor={prefix+'-operation'}>Operation</label><select id={prefix+'-operation'} value={block.operation} onChange={event=>operation(event.target.value as Operation)}>{['sum','average','count','min','max'].map(value=><option key={value} disabled={value!=='count'&&!profile.columns.some(item=>item.type==='number'||(block.type==='metric'&&['min','max'].includes(value)&&item.type==='date'))}>{value}</option>)}</select></div>
    <div className="field"><label htmlFor={prefix+'-value'}>Value column</label><select id={prefix+'-value'} value={block.column||''} required={block.operation!=='count'} onChange={event=>onChange({...block,column:event.target.value||null})}>{block.operation==='count'&&<option value="">All rows</option>}{valueColumns.map(column=><option key={column.key} value={column.key}>{column.name}</option>)}</select></div>
    <div className="field"><label htmlFor={prefix+'-group'}>{block.type==='chart'?'Horizontal axis':'Split by category'}</label><select id={prefix+'-group'} value={block.group_by||''} required={block.type==='chart'} onChange={event=>onChange({...block,group_by:event.target.value||null} as ReportBlock)}><option value="">{block.type==='chart'?'Choose an axis':'No split'}</option>{groups.map(column=><option key={column.key} value={column.key}>{column.name}</option>)}</select></div>
  </div>;
}

export function GlobalFilters({filters,profile,onChange}:{filters:Filter[];profile:CsvProfile;onChange:(filters:Filter[])=>void}) {
  function update(index:number,value:Filter){onChange(filters.map((item,i)=>i===index?value:item));}
  const categories=profile.columns.filter(column=>['category','text'].includes(column.type));
  const dates=profile.columns.filter(column=>column.type==='date');
  const numbers=profile.columns.filter(column=>column.type==='number');
  function add(type:Filter['type']) {
    const column=(type==='category'?categories:type==='date_range'?dates:type==='number_range'?numbers:profile.columns)[0]?.key;
    if(!column)return;
    const filter:Filter=type==='category'?{type,column,values:['']}:type==='date_range'?{type,column,start:'',end:''}:type==='number_range'?{type,column,minimum:'0'}:{type,column,missing:true};
    onChange([...filters,filter]);
  }
  return <section className="report-section"><h2>Report filters</h2><p className="report-hint">Applied together (AND) to every metric, chart and table. Category choices within one filter use OR. Category values are exact and case-sensitive.</p>
    {filters.map((filter,index)=>{
      const prefix='filter-'+index;
      const columns=filter.type==='category'?categories:filter.type==='date_range'?dates:filter.type==='number_range'?numbers:profile.columns;
      return <div className="report-filter" key={index}><span className="report-filter-type">{filter.type.replace('_',' ')}</span>
        <div className="field"><label htmlFor={prefix+'-column'}>Filter {index+1} column</label><select id={prefix+'-column'} value={filter.column} onChange={event=>update(index,{...filter,column:event.target.value})}>{columns.map(column=><option key={column.key} value={column.key}>{column.name}</option>)}</select></div>
        {filter.type==='category'&&<div className="field report-filter-values"><label htmlFor={prefix+'-values'}>Exact values (one per line)</label><textarea id={prefix+'-values'} rows={2} value={filter.values.join('\n')} onChange={event=>update(index,{...filter,values:event.target.value.split('\n')})}/></div>}
        {filter.type==='date_range'&&<><div className="field"><label htmlFor={prefix+'-start'}>From (UTC day)</label><input id={prefix+'-start'} type="date" required value={filter.start} onChange={event=>update(index,{...filter,start:event.target.value})}/></div><div className="field"><label htmlFor={prefix+'-end'}>Through (UTC day)</label><input id={prefix+'-end'} type="date" required min={filter.start} value={filter.end} onChange={event=>update(index,{...filter,end:event.target.value})}/></div></>}
        {filter.type==='number_range'&&<><div className="field"><label htmlFor={prefix+'-min'}>Minimum (inclusive)</label><input id={prefix+'-min'} inputMode="decimal" maxLength={100} value={filter.minimum||''} onChange={event=>update(index,{...filter,minimum:event.target.value||undefined})}/></div><div className="field"><label htmlFor={prefix+'-max'}>Maximum (inclusive)</label><input id={prefix+'-max'} inputMode="decimal" maxLength={100} value={filter.maximum||''} onChange={event=>update(index,{...filter,maximum:event.target.value||undefined})}/></div></>}
        {filter.type==='missing'&&<div className="field"><label htmlFor={prefix+'-missing'}>Keep rows where</label><select id={prefix+'-missing'} value={String(filter.missing)} onChange={event=>update(index,{...filter,missing:event.target.value==='true'})}><option value="true">Value is missing</option><option value="false">Value is present</option></select></div>}
        <button type="button" className="text-button" onClick={()=>onChange(filters.filter((_,i)=>i!==index))} aria-label={'Remove filter '+(index+1)}>Remove</button>
      </div>;
    })}
    {!filters.length&&<p className="report-hint">No filters. All readable rows are eligible.</p>}
    <div className="report-actions"><button type="button" className="button secondary" disabled={filters.length>=10||!categories.length} onClick={()=>add('category')}>Add category filter</button><button type="button" className="button secondary" disabled={filters.length>=10||!dates.length} onClick={()=>add('date_range')}>Add date filter</button><button type="button" className="button secondary" disabled={filters.length>=10||!numbers.length} onClick={()=>add('number_range')}>Add number filter</button><button type="button" className="button secondary" disabled={filters.length>=10} onClick={()=>add('missing')}>Add missing filter</button></div>
  </section>;
}
