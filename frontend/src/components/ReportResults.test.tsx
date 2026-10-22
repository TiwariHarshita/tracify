import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import type { CalculationResult } from '../lib/analytics';
import type { CsvProfile } from '../lib/datasets';
import { ReportResults } from './ReportResults';

const profile={columns:[{key:'c1',name:'time',type:'date'}]} as CsvProfile;
const item:CalculationResult={id:'c',type:'chart',result:{chart_type:'line',rows:[{group_value:'2026-10-01T00:00:00Z',value:'0.300000000000000001'},{group_value:'2026-10-02T00:00:00Z',value:null},{group_value:null,value:'2.0'}]},receipt:{description:'Server explanation.',queries:[{sql:'SELECT SUM(c0) FROM source',parameters:[]}],postprocessing:'Exact.',total_rows:3,matched_rows:3,included_rows:2,excluded_rows:1,excluded_by_filters:0,excluded_missing_value:1,excluded_by_limit:0,dataset_sha256:'hash',parser_version:'parser',calculation_version:'calc',source_relation:'All original records.',column_mapping:[]}};
it('uses exact server values in chart titles and keeps missing groups and values in the table',()=>{
  render(<ReportResults block={{id:'c',type:'chart',title:'Timeline',chart_type:'line',operation:'sum',column:'c0',group_by:'c1'}} item={item} profile={profile}/>);
  expect(screen.getByRole('img',{name:'Timeline line chart'})).toBeInTheDocument();
  expect(screen.getByText('2026-10-01T00:00:00Z: 0.300000000000000001')).toBeInTheDocument();
  fireEvent.click(screen.getByText('View chart data (3 groups)'));
  expect(screen.getByRole('cell',{name:'0.300000000000000001'})).toBeInTheDocument();
  expect(screen.getByRole('cell',{name:'2.0'})).toBeInTheDocument();
  expect(screen.getAllByRole('cell',{name:'Missing / no value'})).toHaveLength(2);
  fireEvent.click(screen.getByText('How was this calculated?'));
  expect(screen.getByText('2 included · 1 excluded')).toBeInTheDocument();
});
