import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { ApiError, readableError } from '../lib/api';
import { reportEditorApi } from '../lib/reportEditor';
import type { Definition, EditorReport, ReportBlock, ReportEvaluation } from '../lib/reportEditor';
import { BlockFields, GlobalFilters, newBlock } from '../components/ReportControls';
import { ReportResults } from '../components/ReportResults';
import { Feedback } from '../components/Feedback';
import '../workspace.css';
import '../csv.css';
import '../analytics.css';
import '../report.css';

export function ReportEditorPage() {
  const {reportId=''}=useParams();
  const {refresh}=useAuth();
  const epoch=useRef(0);
  const [report,setReport]=useState<EditorReport|null>(null);
  const [definition,setDefinition]=useState<Definition>({version:1,blocks:[],filters:[]});
  const [title,setTitle]=useState('');
  const [dirty,setDirty]=useState(false);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [conflict,setConflict]=useState(false);
  const [status,setStatus]=useState('');
  const [output,setOutput]=useState<ReportEvaluation|null>(null);
  function failure(cause:unknown) {
    setError(readableError(cause));
    if(cause instanceof ApiError&&cause.status===409)setConflict(true);
    if(cause instanceof ApiError&&cause.status===401)void refresh();
  }
  function accept(value:EditorReport) {
    setReport(value);setTitle(value.title);setDefinition(value.definition);setDirty(false);setConflict(false);setOutput(null);
  }
  useEffect(()=>{
    let active=true;++epoch.current;setBusy(false);setLoading(true);setError('');setReport(null);setOutput(null);setDirty(false);setStatus('');
    reportEditorApi.load(reportId).then(value=>{if(active)accept(value);}).catch(cause=>{if(active)failure(cause);}).finally(()=>{if(active)setLoading(false);});
    return()=>{active=false;++epoch.current;};
  },[reportId]);
  useEffect(()=>{
    function warn(event:BeforeUnloadEvent){if(dirty){event.preventDefault();event.returnValue='';}}
    window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);
  },[dirty]);
  function edit(next:Definition) {setDefinition(next);setDirty(true);setOutput(null);setStatus('');}
  function update(block:ReportBlock) {edit({...definition,blocks:definition.blocks.map(item=>item.id===block.id?block:item)});}
  function move(index:number,direction:number) {const blocks=[...definition.blocks];[blocks[index],blocks[index+direction]]=[blocks[index+direction],blocks[index]];edit({...definition,blocks});}
  async function reload() {
    if(dirty&&!window.confirm('Discard your local changes and load the saved report?'))return;
    const ticket=epoch.current;setBusy(true);setError('');setStatus('');
    try{const value=await reportEditorApi.load(reportId);if(ticket===epoch.current)accept(value);}
    catch(cause){if(ticket===epoch.current)failure(cause);}finally{if(ticket===epoch.current)setBusy(false);}
  }
  async function persist(calculate:boolean) {
    if(!report)return;
    const ticket=epoch.current;setBusy(true);setError('');setStatus('');setOutput(null);
    try{
      let saved=report;
      if(dirty){saved=await reportEditorApi.save(reportId,title,definition,report.revision,report.dataset.sha256);if(ticket!==epoch.current)return;accept(saved);}
      if(calculate){
        const result=await reportEditorApi.evaluate(reportId,saved.revision,saved.dataset.sha256);
        if(ticket!==epoch.current)return;
        if(result.revision!==saved.revision||result.dataset_sha256!==saved.dataset.sha256)throw new ApiError(409,'The calculation belongs to another report version. Reload before calculating.');
        setOutput(result);setStatus(result.complete?'Calculated saved revision '+saved.revision+'.':'Fix the marked blocks and calculate again. No partial results are shown.');
      }else setStatus('Saved revision '+saved.revision+'.');
    }catch(cause){if(ticket===epoch.current)failure(cause);}finally{if(ticket===epoch.current)setBusy(false);}
  }
  function submit(event:FormEvent<HTMLFormElement>) {event.preventDefault();const action=(event.nativeEvent as SubmitEvent).submitter?.getAttribute('value');void persist(action==='calculate');}
  return <section className="workspace-page report-editor">
    <Link className="report-back" to="/app" onClick={event=>{if(dirty&&!window.confirm('Leave without saving your report changes?'))event.preventDefault();}}>← Workspace</Link>
    <span className="eyebrow">Report builder</span><h1>{report?.title||'Your report'}</h1>
    {error&&<Feedback>{error}</Feedback>}
    {loading&&<p role="status">Loading saved report…</p>}
    {!loading&&!report&&<button className="button secondary" disabled={busy} onClick={()=>void reload()}>Retry loading report</button>}
    {report&&<>
      <p className="page-description">{report.dataset.name} · {report.profile.readable_rows} readable rows · Revision {report.revision} · {dirty?'Unsaved changes':'Saved'}</p>
      {conflict&&<div className="report-conflict"><p>Your draft is still on this page. Reloading discards local changes, so copy any edits you want to keep first.</p><button className="button secondary" disabled={busy} onClick={()=>void reload()}>Reload saved version</button></div>}
      {!report.profile.analysis_ready&&<Feedback>This dataset has unreadable records and cannot be calculated.</Feedback>}
      <form onSubmit={submit}><fieldset className="report-form" disabled={busy}>
        <section className="workspace-card report-toolbar"><div className="field"><label htmlFor="editor-title">Report title</label><input id="editor-title" required maxLength={120} value={title} onChange={event=>{setTitle(event.target.value);setDirty(true);setOutput(null);setStatus('');}}/></div>
          <div className="report-actions"><button className="button secondary" type="submit" value="save" disabled={busy||conflict||!dirty}>Save report</button><button className="button primary" type="submit" value="calculate" disabled={busy||conflict||!report.profile.analysis_ready}>{busy?'Working…':'Save and calculate'}</button></div>
        </section>
        {status&&<p className="report-status" role="status">{status}</p>}
        <GlobalFilters filters={definition.filters} profile={report.profile} onChange={filters=>edit({...definition,filters})}/>
        <div className="report-add"><h2>Blocks</h2><div className="report-actions">{(['metric','chart','table','note'] as const).map(type=><button type="button" className="button secondary" key={type} disabled={definition.blocks.length>=20} onClick={()=>edit({...definition,blocks:[...definition.blocks,newBlock(type,report.profile)]})}>Add {type}</button>)}</div><p className="report-hint">Up to 20 blocks. Save and calculate after changing blocks or filters.</p></div>
        {!definition.blocks.length&&<section className="workspace-card"><p className="workspace-empty">Add a metric, chart, table or note to start your report.</p></section>}
        {definition.blocks.map((block,index)=>{
          const item=output?.results.find(result=>result.id===block.id);
          const issue=output?.errors.find(error=>error.block_id===block.id);
          return <section className="workspace-card report-block" key={block.id} aria-label={'Block '+(index+1)+': '+block.title}>
            <div className="report-block-heading"><span className="report-kind">{index+1} · {block.type}</span><div className="report-actions"><button type="button" className="text-button" disabled={index===0} onClick={()=>move(index,-1)} aria-label={'Move '+block.title+' up'}>↑ Up</button><button type="button" className="text-button" disabled={index===definition.blocks.length-1} onClick={()=>move(index,1)} aria-label={'Move '+block.title+' down'}>↓ Down</button><button type="button" className="text-button" onClick={()=>{if(window.confirm('Remove this block?'))edit({...definition,blocks:definition.blocks.filter(item=>item.id!==block.id)});}} aria-label={'Remove '+block.title}>Remove</button></div></div>
            <div className="field"><label htmlFor={block.id+'-title'}>Block title</label><input id={block.id+'-title'} value={block.title} required maxLength={120} onChange={event=>update({...block,title:event.target.value})}/></div>
            <BlockFields block={block} profile={report.profile} onChange={update}/>
            {block.type==='note'&&<div className="report-note">{block.text||'Your note will appear here.'}</div>}
            {issue&&<Feedback>{issue.message}</Feedback>}
            {item&&<ReportResults block={block} item={item} profile={report.profile}/>}
            {block.type!=='note'&&!item&&!issue&&<p className="report-hint">{dirty?'Changes have not been calculated.':'Save and calculate to show this block’s result.'}</p>}
          </section>;
        })}
      </fieldset></form>
    </>}
  </section>;
}
