import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { ReportResults } from '../components/ReportResults';
import { sharingApi } from '../lib/sharing';
import type { PublicReport } from '../lib/sharing';
import '../workspace.css';
import '../csv.css';
import '../analytics.css';
import '../report.css';

export function PublicReportPage(){
  const {token=''}=useParams(); const [report,setReport]=useState<PublicReport|null>(null); const [error,setError]=useState('');
  useEffect(()=>{let active=true;sharingApi.public(token).then(value=>{if(active)setReport(value);}).catch(cause=>{if(active)setError(cause instanceof Error?cause.message:'Shared report unavailable.');});return()=>{active=false;};},[token]);
  if(error)return <section className="workspace-page"><h1>Shared report unavailable</h1><p className="page-description">{error}</p></section>;
  if(!report)return <section className="workspace-page"><p role="status">Loading shared report…</p></section>;
  return <section className="workspace-page public-report"><span className="eyebrow">Read-only shared report</span><h1>{report.title}</h1><p className="page-description">Frozen report revision {report.report_revision} · Published {new Date(report.published_at).toLocaleString()}</p>
    {report.definition.blocks.map((block,index)=>{const item=report.results.find(result=>result.id===block.id);return <section className="workspace-card report-block" key={block.id}><div className="report-block-heading"><span className="report-kind">{index+1} · {block.type}</span><strong>{block.title}</strong></div>{block.type==='note'?<div className="report-note">{block.text}</div>:item?<ReportResults block={block} item={item} profile={report.profile}/>:null}</section>;})}
  </section>;
}
