import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { useAuth } from '../auth/AuthContext';
import { Feedback } from './Feedback';
import { ApiError, readableError } from '../lib/api';
import { datasetsApi } from '../lib/datasets';
import type { CsvIssue, CsvProfile, CsvRow, Page } from '../lib/datasets';
import type { Dataset } from '../lib/workspace';
import '../csv.css';

export function UploadPanel({onUploaded,disabled=false}:{onUploaded:(item:Dataset)=>Promise<void>;disabled?:boolean}) {
  const {refresh}=useAuth();
  const [file,setFile]=useState<File|null>(null);
  const [delimiter,setDelimiter]=useState(',');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  async function upload(event:FormEvent<HTMLFormElement>) {
    event.preventDefault(); if(!file)return;
    if(file.size>5*1024*1024){setError('Choose a CSV no larger than 5 MiB.');return;}
    setBusy(true);setError('');
    try {
      const result=await datasetsApi.upload(file,delimiter);
      await onUploaded(result);
    } catch(cause) {
      setError(readableError(cause));
      if(cause instanceof ApiError && cause.status===401)void refresh();
    } finally {setBusy(false);}
  }
  return <section className="workspace-card">
    <h2>Upload a CSV</h2><p className="workspace-card-description">UTF-8 · up to 5 MiB · 50,000 records · 100 columns. Every unreadable record is reported.</p>
    {error && <Feedback>{error}</Feedback>}
    <form className="csv-upload-form" onSubmit={upload}>
      <div className="field"><label htmlFor="csv-file">CSV file</label><input id="csv-file" type="file" accept=".csv,text/csv" required disabled={busy||disabled} onChange={event=>{setFile(event.target.files?.[0]||null);setError('');}} /></div>
      <div className="field"><label htmlFor="csv-delimiter">Delimiter</label><select id="csv-delimiter" value={delimiter} disabled={busy||disabled} onChange={event=>setDelimiter(event.target.value)}><option value=",">Comma</option><option value=";">Semicolon</option><option value={'\t'}>Tab</option></select></div>
      <button className="button primary" disabled={busy||disabled||!file}>{busy?'Parsing on server…':'Upload and profile'}</button>
    </form>
  </section>;
}

function Pagination({offset,total,busy,onChange}:{offset:number;total:number;busy:boolean;onChange:(offset:number)=>void}) {
  return <div className="csv-pagination"><span>{total?offset+1:0}–{Math.min(offset+50,total)} of {total}</span>
    <button className="button secondary" disabled={busy||offset===0} onClick={()=>onChange(Math.max(0,offset-50))}>Previous</button>
    <button className="button secondary" disabled={busy||offset+50>=total} onClick={()=>onChange(offset+50)}>Next</button></div>;
}

export function DatasetProfile({id,onClose}:{id:string;onClose:()=>void}) {
  const {refresh}=useAuth();
  const [profile,setProfile]=useState<CsvProfile|null>(null);
  const [rows,setRows]=useState<Page<CsvRow>|null>(null);
  const [issues,setIssues]=useState<Page<CsvIssue>|null>(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(true);
  const [rowOffset,setRowOffset]=useState(0);
  const [issueOffset,setIssueOffset]=useState(0);
  useEffect(()=>{
    let active=true;setBusy(true);setError('');
    Promise.all([datasetsApi.profile(id),datasetsApi.preview(id,rowOffset),datasetsApi.errors(id,issueOffset)])
      .then(([p,r,e])=>{if(active){setProfile(p);setRows(r);setIssues(e);}})
      .catch(cause=>{if(active){setError(readableError(cause));if(cause instanceof ApiError&&cause.status===401)void refresh();}})
      .finally(()=>{if(active)setBusy(false);});
    return()=>{active=false;};
  },[id,rowOffset,issueOffset,refresh]);
  return <section className="workspace-card csv-profile">
    <div className="workspace-card-heading"><h2>Dataset profile</h2><button className="text-button" onClick={onClose}>Close profile</button></div>
    {error&&<Feedback>{error}</Feedback>}
    {busy&&<p role="status">Loading server profile…</p>}
    {profile&&<>
      <div className="csv-summary"><div><span>Total data records</span><strong>{profile.total_records??'Undetermined'}</strong></div><div><span>Readable rows</span><strong>{profile.readable_rows}</strong></div><div><span>Unreadable records</span><strong>{profile.unreadable_rows}</strong></div><div><span>Unparsed source lines</span><strong>{profile.unparsed_lines}</strong></div></div>
      {!profile.analysis_ready&&<Feedback>Fix the unreadable records and upload the corrected CSV before creating a report. {profile.total_records===null&&'A syntax error makes the record count in the remaining source lines unknown; that complete range is listed below.'}</Feedback>}
      <p className="csv-policy">{profile.missing_policy} Types and missing counts use every readable row. Source lines include the header; data record numbers do not.</p>
      <div className="csv-scroll"><table><thead><tr><th>Column</th><th>Guessed type</th><th>Missing</th><th>Distinct values</th><th>Reason</th></tr></thead><tbody>{profile.columns.map(column=><tr key={column.key}><td>{column.name}</td><td><span className="csv-type">{column.type}</span></td><td>{column.missing_count}</td><td>{column.distinct_count}</td><td>{column.reason}</td></tr>)}</tbody></table></div>
      <p className="csv-version">Parser: {profile.parser_version} · SHA-256: <code>{profile.sha256}</code><br /><a href={datasetsApi.rawUrl(id)}>Download original CSV</a></p>
      <h3>Readable rows</h3>
      {rows&&<><div className="csv-scroll"><table><thead><tr><th>Data record</th><th>Source lines</th>{profile.columns.map(column=><th key={column.key}>{column.name}</th>)}</tr></thead><tbody>{rows.items.map(row=><tr key={row.record_number}><td>{row.record_number}</td><td>{row.line_start}–{row.line_end}</td>{row.cells.map((value,index)=><td className="csv-cell" key={index}>{value.trim()?value:<span className="csv-missing">missing</span>}</td>)}</tr>)}</tbody></table></div><Pagination offset={rowOffset} total={rows.total} busy={busy} onChange={setRowOffset}/></>}
      <h3>Unreadable records and unparsed ranges</h3>
      {issues&&<>{issues.total===0?<p className="csv-policy">No unreadable records.</p>:issues.items.map((issue,index)=><article className="csv-issue" key={issueOffset+index}><strong>{issue.record_number===null?'Unparsed range':'Data record '+issue.record_number} · source lines {issue.line_start}–{issue.line_end}</strong><p>{issue.reason}</p><pre>{issue.raw_excerpt}</pre>{issue.excerpt_truncated&&<small>Excerpt only. Download the original CSV for the complete source.</small>}</article>)}<Pagination offset={issueOffset} total={issues.total} busy={busy} onChange={setIssueOffset}/></>}
    </>}
  </section>;
}
