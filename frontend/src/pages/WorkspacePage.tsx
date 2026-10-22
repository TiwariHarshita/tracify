import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { ApiError, readableError } from '../lib/api';
import { workspaceApi } from '../lib/workspace';
import type { Dataset, Report } from '../lib/workspace';
import { Feedback } from '../components/Feedback';
import { UploadPanel, DatasetProfile } from '../components/DatasetTools';
import '../workspace.css';
import { CalculationTester } from '../components/CalculationTester';
import { reportEditorApi } from '../lib/reportEditor';

export function WorkspacePage() {
  const { user, refresh } = useAuth();
  const navigate=useNavigate();
  const [profileId,setProfileId]=useState('');
  const [calculationId,setCalculationId]=useState('');
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [datasetId, setDatasetId] = useState('');
  const [title, setTitle] = useState('Restaurant tips report');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function load() {
    const [data, saved] = await Promise.all([workspaceApi.datasets(), workspaceApi.reports()]);
    setDatasets(data); setReports(saved);
    setDatasetId(previous => data.some(item => item.id === previous) ? previous : (data[0]?.id || ''));
  }
  function failure(cause: unknown) {
    setError(readableError(cause));
    if (cause instanceof ApiError && cause.status === 401) void refresh();
  }
  useEffect(() => {
    let active = true;
    Promise.all([workspaceApi.datasets(), workspaceApi.reports()]).then(([data,saved]) => {
      if (!active) return;
      setDatasets(data); setReports(saved); setDatasetId(data[0]?.id || '');
    }).catch(cause => { if(active) failure(cause); })
      .finally(() => { if(active) setLoading(false); });
    return () => { active = false; };
  }, []);
  async function mutate(action: () => Promise<unknown>) {
    setBusy(true); setError('');
    try { await action(); await load(); }
    catch(cause) { failure(cause); }
    finally { setBusy(false); }
  }
  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void mutate(async () => {const report=await workspaceApi.create(datasetId, title.trim());navigate("/app/reports/"+report.id);});
  }
  return <section className="workspace-page">
    <span className="eyebrow">Your workspace</span><h1>Welcome, {user?.name}.</h1>
    <p className="page-description">Upload a CSV or use the public sample, then inspect its server profile.</p>
    <UploadPanel disabled={busy} onUploaded={async item=>{await load();setDatasetId(item.id);setProfileId(item.id);}} />
    {profileId&&<DatasetProfile key={profileId} id={profileId} onClose={()=>setProfileId('')} />}
    {calculationId&&<CalculationTester key={calculationId} id={calculationId} onClose={()=>setCalculationId('')} />}
    {error && <div style={{marginTop:20}}><Feedback>{error}</Feedback>
      <button className="button secondary" onClick={() => void mutate(load)} disabled={busy}>Reload workspace</button></div>}
    {loading ? <p className="phase3-loading" role="status">Loading your workspace…</p> : <>
      <section className="workspace-card"><div className="workspace-card-heading"><div><h2>Datasets</h2><p>Uploaded files and public samples, kept in your own workspace.</p></div>
        <button className="button primary" disabled={busy} onClick={() => void mutate(workspaceApi.sample)}>{busy ? 'Working…' : 'Use public sample'}</button></div>
        {!datasets.length && <p className="workspace-empty">Load the restaurant tips CSV to get started.</p>}
        {datasets.map(dataset => <div className="workspace-row" key={dataset.id}><div><strong>{dataset.name}</strong><small>{dataset.row_count} readable rows · {dataset.column_count} columns{dataset.source_url&&<> · <a href={dataset.source_url} target="_blank" rel="noreferrer">Public source ↗</a></>}</small></div>
          <div className="dataset-row-buttons"><button className="text-button" onClick={()=>setProfileId(dataset.id)}>View profile</button><button className="text-button" onClick={()=>setCalculationId(dataset.id)}>Calculate</button><button className="text-button" disabled={busy} onClick={() => {if(window.confirm('Delete this dataset? Reports using it must be deleted first.')) void mutate(async()=>{await workspaceApi.deleteDataset(dataset.id);if(profileId===dataset.id)setProfileId('');if(calculationId===dataset.id)setCalculationId('');});}}>Delete</button></div></div>)}
      </section>
      <section className="workspace-card"><h2>Create a report draft</h2><p className="workspace-card-description">Choose a dataset and give your report a name.</p>
        <form className="new-report-form" onSubmit={create}><div className="field"><label htmlFor="report-title">Report title</label><input id="report-title" required maxLength={120} value={title} onChange={event=>setTitle(event.target.value)} disabled={busy} /></div>
          <div className="field"><label htmlFor="report-dataset">Dataset</label><select id="report-dataset" required value={datasetId} onChange={event=>setDatasetId(event.target.value)} disabled={busy || !datasets.length}><option value="">Choose a dataset</option>{datasets.map(item=><option value={item.id} key={item.id}>{item.name}</option>)}</select></div>
          <button className="button primary" disabled={busy || !datasetId || !title.trim()}>Create draft</button></form>
      </section>
      <section className="workspace-card"><h2>Saved drafts</h2><p className="workspace-card-description">Open a saved report to edit blocks, filters, and calculation panels.</p>
        {!reports.length && <p className="workspace-empty">No report drafts yet.</p>}
        {reports.map(report=><div className="workspace-row" key={report.id}><div><strong>{report.title}</strong><small>{datasets.find(item=>item.id===report.dataset_id)?.name || 'Dataset'} · Draft</small></div><div className="workspace-row-actions">
          <Link className="text-button" to={"/app/reports/"+report.id}>Open report</Link>
          <button className="text-button" disabled={busy} onClick={()=>void mutate(async()=>{const current=await reportEditorApi.load(report.id);const next=window.prompt('Report title',current.title);if(next?.trim())await reportEditorApi.save(report.id,next.trim(),current.definition,current.revision,current.dataset.sha256);})}>Rename</button>
          <button className="text-button" disabled={busy} onClick={()=>{if(window.confirm('Delete this report draft?')) void mutate(()=>workspaceApi.deleteReport(report.id));}}>Delete</button></div></div>)}
      </section>
    </>}
  </section>;
}
