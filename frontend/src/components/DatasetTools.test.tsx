import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { AuthProvider } from '../auth/AuthContext';
import { api } from '../lib/api';
import { datasetsApi } from '../lib/datasets';
import { DatasetProfile, UploadPanel } from './DatasetTools';

beforeEach(()=>{
  vi.spyOn(api,'me').mockResolvedValue({id:'user',name:'Ava',email:'ava@example.com',email_verified:true});
});
it('uploads the selected CSV and asks the workspace to open its profile',async()=>{
  const dataset={id:'dataset',name:'Public CSV',source_url:'',sha256:'hash',row_count:1,column_count:1,created_at:''};
  vi.spyOn(datasetsApi,'upload').mockResolvedValue(dataset);
  const saved=vi.fn().mockResolvedValue(undefined);
  render(<AuthProvider><UploadPanel onUploaded={saved}/></AuthProvider>);
  const file=new File(['amount\n3\n'],'public.csv',{type:'text/csv'});
  await userEvent.upload(screen.getByLabelText('CSV file'),file);
  const button=screen.getByRole('button',{name:'Upload and profile'});
  expect(button).toBeEnabled();
  // jsdom's native file-input constraint state is not updated by user-event.
  fireEvent.submit(button.closest('form')!);
  await waitFor(()=>expect(datasetsApi.upload).toHaveBeenCalledWith(file,','));
  await waitFor(()=>expect(saved).toHaveBeenCalledWith(dataset));
});
it('shows an unknown count, explicit error range, and the original-file download',async()=>{
  vi.spyOn(datasetsApi,'profile').mockResolvedValue({
    parser_version:'trace-csv-v1',sha256:'hash',encoding:'UTF-8',delimiter:',',physical_lines:4,header_line_end:1,
    total_records:null,known_records:1,readable_rows:1,unreadable_rows:0,unparsed_lines:2,error_count:1,
    analysis_ready:false,missing_policy:'Only empty cells are missing.',inference_scope:'All readable rows.',columns:[],
  });
  vi.spyOn(datasetsApi,'preview').mockResolvedValue({items:[],total:1,offset:0,limit:50});
  vi.spyOn(datasetsApi,'errors').mockResolvedValue({items:[{
    record_number:null,line_start:3,line_end:4,code:'unparsed_range',reason:'Record boundaries are unknown.',
    raw_excerpt:'broken source',excerpt_truncated:false,
  }],total:1,offset:0,limit:50});
  render(<AuthProvider><DatasetProfile id="dataset" onClose={()=>{}}/></AuthProvider>);
  expect(await screen.findByText('Undetermined')).toBeInTheDocument();
  expect(screen.getByText('Unparsed range · source lines 3–4')).toBeInTheDocument();
  expect(screen.getByText('Record boundaries are unknown.')).toBeInTheDocument();
  expect(screen.getByRole('link',{name:'Download original CSV'})).toHaveAttribute('href','http://localhost:8000/api/v1/datasets/dataset/raw');
});
