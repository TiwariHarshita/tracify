import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { AuthProvider } from '../auth/AuthContext';
import { api, ApiError } from '../lib/api';
import { reportEditorApi } from '../lib/reportEditor';
import type { EditorReport } from '../lib/reportEditor';
import { ReportEditorPage } from './ReportEditorPage';

const profile={sha256:'a'.repeat(64),parser_version:'trace-csv-v1',encoding:'UTF-8',delimiter:',',physical_lines:3,header_line_end:1,total_records:2,known_records:2,readable_rows:2,unreadable_rows:0,unparsed_lines:0,error_count:0,analysis_ready:true,missing_policy:'Empty cells',inference_scope:'All rows',columns:[
  {key:'c0',name:'amount',type:'number' as const,missing_count:0,non_missing_count:2,distinct_count:2,reason:'Numbers',warnings:[],examples:[]},
  {key:'c1',name:'day',type:'category' as const,missing_count:0,non_missing_count:2,distinct_count:2,reason:'Labels',warnings:[],examples:[]},
]};
const initial:EditorReport={id:'r',title:'My report',revision:1,dataset_id:'d',dataset:{id:'d',name:'Public Tips',sha256:profile.sha256,source_url:'',row_count:2,column_count:2,created_at:''},profile,definition:{version:1,blocks:[],filters:[]}};
const receipt={description:'Exact server calculation.',queries:[{sql:'SELECT SUM("c0") FROM source',parameters:[]}],postprocessing:'Exact decimals.',total_rows:2,matched_rows:2,included_rows:2,excluded_rows:0,excluded_by_filters:0,excluded_missing_value:0,excluded_by_limit:0,dataset_sha256:profile.sha256,parser_version:'trace-csv-v1',calculation_version:'trace-analytics-v1',source_relation:'Verified original.',column_mapping:[{key:'c0',name:'amount',inferred_type:'number',sql_type:'DECIMAL(38,18)'}]};
function mount(){return render(<MemoryRouter initialEntries={['/app/reports/r']}><AuthProvider><Link to="/app/reports/second">Other report</Link><Routes><Route path="/app/reports/:reportId" element={<ReportEditorPage/>}/></Routes></AuthProvider></MemoryRouter>);}
beforeEach(()=>{
  vi.spyOn(api,'me').mockResolvedValue({id:'u',name:'Ava',email:'ava@example.com',email_verified:true});
  vi.spyOn(reportEditorApi,'load').mockResolvedValue(structuredClone(initial));
  vi.spyOn(window,'confirm').mockReturnValue(true);
});
it('adds all four types, reorders, saves global filters, and evaluates the saved revision',async()=>{
  let saved=structuredClone(initial);
  const save=vi.spyOn(reportEditorApi,'save').mockImplementation(async(_id,title,definition,revision)=>{saved={...saved,title,definition,revision:revision+1};return saved;});
  const evaluate=vi.spyOn(reportEditorApi,'evaluate').mockImplementation(async()=>({report_id:'r',revision:saved.revision,dataset_sha256:profile.sha256,complete:true,errors:[],results:saved.definition.blocks.filter(block=>block.type==='metric').map(block=>({id:block.id,type:'metric',result:{rows:[{value:'0.300000000000000001'}]},receipt}))}));
  mount();
  await screen.findByLabelText('Report title');
  for(const name of ['Add metric','Add chart','Add table','Add note'])fireEvent.click(screen.getByRole('button',{name}));
  fireEvent.change(screen.getByLabelText('Note text'),{target:{value:'A useful note.'}});
  fireEvent.click(screen.getByRole('button',{name:'Move Note up'}));
  fireEvent.click(screen.getByRole('button',{name:'Add category filter'}));
  fireEvent.change(screen.getByLabelText('Exact values (one per line)'),{target:{value:'Sun\nSat'}});
  fireEvent.click(screen.getByRole('button',{name:'Save and calculate'}));
  await waitFor(()=>expect(evaluate).toHaveBeenCalledWith('r',2,profile.sha256));
  expect(save.mock.calls[0][2].blocks.map(block=>block.type)).toEqual(['metric','chart','note','table']);
  expect(save.mock.calls[0][2].filters).toEqual([{type:'category',column:'c1',values:['Sun','Sat']}]);
  expect(await screen.findByText('0.300000000000000001')).toBeInTheDocument();
  fireEvent.click(screen.getByText('How was this calculated?'));
  expect(screen.getByText('SELECT SUM("c0") FROM source')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Exact values (one per line)'),{target:{value:'Sun'}});
  expect(screen.queryByText('0.300000000000000001')).not.toBeInTheDocument();
  expect(screen.getByText(/Unsaved changes/)).toBeInTheDocument();
});
it('keeps a stale draft on conflict and reloads only after confirmation',async()=>{
  const withNote:EditorReport={...structuredClone(initial),definition:{version:1,filters:[],blocks:[{id:'note',type:'note',title:'Context',text:'Original'}]}};
  vi.mocked(reportEditorApi.load).mockResolvedValueOnce(withNote).mockResolvedValueOnce({...withNote,title:'Other tab',revision:3});
  vi.spyOn(reportEditorApi,'save').mockRejectedValue(new ApiError(409,'This report changed in another tab.'));
  mount();
  fireEvent.change(await screen.findByLabelText('Note text'),{target:{value:'Keep my local note'}});
  fireEvent.click(screen.getByRole('button',{name:'Save report'}));
  expect(await screen.findByText('This report changed in another tab.')).toBeInTheDocument();
  expect(screen.getByLabelText('Note text')).toHaveValue('Keep my local note');
  expect(screen.getByRole('button',{name:'Save and calculate'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'Reload saved version'}));
  expect(await screen.findByRole('heading',{name:'Other tab'})).toBeInTheDocument();
  expect(window.confirm).toHaveBeenCalled();
  expect(screen.getByLabelText('Note text')).toHaveValue('Original');
});
it('renders saved notes as plain text and removes blocks after confirmation',async()=>{
  vi.mocked(reportEditorApi.load).mockResolvedValue({...structuredClone(initial),definition:{version:1,filters:[],blocks:[{id:'note',type:'note',title:'Context',text:'<script>window.bad=true</script>'}]}});
  const {container}=mount();
  await screen.findByLabelText('Note text');
  expect(container.querySelector('.report-note')?.textContent).toBe('<script>window.bad=true</script>');
  expect(container.querySelector('script')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Remove Context'}));
  expect(screen.queryByLabelText('Note text')).not.toBeInTheDocument();
  expect(screen.getByText(/Unsaved changes/)).toBeInTheDocument();
});
it('shows block-local failures without disabling editing or showing partial numbers',async()=>{
  vi.mocked(reportEditorApi.load).mockResolvedValue({...structuredClone(initial),definition:{version:1,filters:[],blocks:[{id:'m',type:'metric',title:'Total',operation:'sum',column:'c0',group_by:null}]}});
  vi.spyOn(reportEditorApi,'evaluate').mockResolvedValue({report_id:'r',revision:1,dataset_sha256:profile.sha256,complete:false,errors:[{block_id:'m',message:'Repair this block.'}],results:[]});
  mount();await screen.findByLabelText('Report title');
  fireEvent.click(screen.getByRole('button',{name:'Save and calculate'}));
  expect(await screen.findByText('Repair this block.')).toBeInTheDocument();
  expect(screen.getByLabelText('Value column')).toBeEnabled();
  expect(screen.queryByText('How was this calculated?')).not.toBeInTheDocument();
});

it('ignores a late save response after navigating to another report',async()=>{
  const first:EditorReport={...structuredClone(initial),definition:{version:1,filters:[],blocks:[{id:'n',type:'note',title:'Note',text:'First'}]}};
  vi.mocked(reportEditorApi.load).mockResolvedValueOnce(first).mockResolvedValueOnce({...first,id:'second',title:'Second report'});
  let resolve!:(value:EditorReport)=>void;
  const pending=new Promise<EditorReport>(done=>{resolve=done;});
  const save=vi.spyOn(reportEditorApi,'save').mockReturnValue(pending);
  mount();
  fireEvent.change(await screen.findByLabelText('Note text'),{target:{value:'Local edit'}});
  fireEvent.click(screen.getByRole('button',{name:'Save report'}));
  await waitFor(()=>expect(save).toHaveBeenCalled());
  fireEvent.click(screen.getByRole('link',{name:'Other report'}));
  await screen.findByRole('heading',{name:'Second report'});
  await act(async()=>resolve({...first,title:'Late old report',revision:2}));
  expect(screen.getByRole('heading',{name:'Second report'})).toBeInTheDocument();
  expect(screen.queryByRole('heading',{name:'Late old report'})).not.toBeInTheDocument();
});
