import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { AuthProvider } from '../auth/AuthContext';
import { api, ApiError } from '../lib/api';
import { datasetsApi } from '../lib/datasets';
import { analyticsApi } from '../lib/analytics';
import type { Evaluation } from '../lib/analytics';
import type { CsvProfile } from '../lib/datasets';
import { CalculationTester } from './CalculationTester';

const profile:CsvProfile={
  sha256:'a'.repeat(64),parser_version:'trace-csv-v1',encoding:'UTF-8',delimiter:',',physical_lines:3,header_line_end:1,total_records:2,known_records:2,readable_rows:2,unreadable_rows:0,unparsed_lines:0,error_count:0,analysis_ready:true,missing_policy:'Empty cells',inference_scope:'All rows',
  columns:[{key:'c0',name:'amount',type:'number',missing_count:0,non_missing_count:2,distinct_count:2,reason:'Numbers',warnings:[],examples:[]},{key:'c1',name:'day',type:'category',missing_count:0,non_missing_count:2,distinct_count:2,reason:'Labels',warnings:[],examples:[]}],
};
const response:Evaluation={dataset_id:'dataset',dataset_sha256:profile.sha256,calculation_version:'trace-analytics-v1',results:[{
  id:'metric',type:'metric',result:{rows:[{value:'0.300000000000000001'}]},receipt:{description:'Sum of amount for the selected day.',queries:[{sql:'SELECT SUM("c0") FROM source WHERE "c1" IN (?)',parameters:['Sun']}],postprocessing:'Exact decimal string.',total_rows:2,matched_rows:1,included_rows:1,excluded_rows:1,excluded_by_filters:1,excluded_missing_value:0,excluded_by_limit:0,dataset_sha256:profile.sha256,parser_version:'trace-csv-v1',calculation_version:'trace-analytics-v1',source_relation:'Verified original bytes.',column_mapping:[{key:'c0',name:'amount',inferred_type:'number',sql_type:'DECIMAL(38,18)'}]},
}]};
beforeEach(()=>{
  vi.spyOn(api,'me').mockResolvedValue({id:'user',name:'Ava',email:'ava@example.com',email_verified:true});
  vi.spyOn(datasetsApi,'profile').mockResolvedValue(profile);
});
it('batches calculations with a dataset version and shared filter, displays exact server values and query',async()=>{
  const evaluate=vi.spyOn(analyticsApi,'evaluate').mockResolvedValue(response);
  render(<AuthProvider><CalculationTester id="dataset" onClose={()=>{}}/></AuthProvider>);
  await screen.findByLabelText('Operation');
  fireEvent.change(screen.getByLabelText('Split by category'),{target:{value:'c1'}});
  fireEvent.change(screen.getByLabelText('Category filter'),{target:{value:'c1'}});
  fireEvent.change(screen.getByLabelText('Exact category value'),{target:{value:'Sun'}});
  fireEvent.click(screen.getByRole('button',{name:'Run calculations'}));
  await waitFor(()=>expect(evaluate).toHaveBeenCalledWith('dataset',{
    expected_sha256:profile.sha256,filters:[{type:'category',column:'c1',values:['Sun']}],calculations:[
      {id:'metric',type:'metric',operation:'sum',column:'c0',group_by:'c1'},
      {id:'top_rows',type:'table',sort_by:'c0',direction:'desc',limit:10},
      {id:'bar_data',type:'chart',chart_type:'bar',operation:'sum',column:'c0',group_by:'c1'},
    ],
  }));
  expect(await screen.findByText('0.300000000000000001')).toBeInTheDocument();
  fireEvent.click(screen.getByText('How was this calculated?'));
  expect(screen.getByText('SELECT SUM("c0") FROM source WHERE "c1" IN (?)')).toBeInTheDocument();
  expect(screen.getByText('1 included · 1 excluded')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Operation'),{target:{value:'average'}});
  expect(screen.queryByText('0.300000000000000001')).not.toBeInTheDocument();
});
it('shows server failures and permits retry',async()=>{
  vi.spyOn(analyticsApi,'evaluate').mockRejectedValueOnce(new ApiError(409,'Dataset version changed.')).mockResolvedValue(response);
  render(<AuthProvider><CalculationTester id="dataset" onClose={()=>{}}/></AuthProvider>);
  fireEvent.click(await screen.findByRole('button',{name:'Run calculations'}));
  expect(await screen.findByText('Dataset version changed.')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Run calculations'}));
  expect(await screen.findByText('0.300000000000000001')).toBeInTheDocument();
});
it('blocks the tester for datasets with unreadable records',async()=>{
  vi.mocked(datasetsApi.profile).mockResolvedValue({...profile,analysis_ready:false,error_count:1});
  render(<AuthProvider><CalculationTester id="dataset" onClose={()=>{}}/></AuthProvider>);
  expect(await screen.findByText('This CSV has unreadable records. Fix it and upload again before calculating.')).toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Run calculations'})).not.toBeInTheDocument();
});
