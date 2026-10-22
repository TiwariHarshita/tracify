import { request } from './api';
import type { Calculation, CalculationResult, Filter } from './analytics';
import type { CsvProfile } from './datasets';
import type { Dataset } from './workspace';

export type ReportBlock = (Calculation & {title:string}) | {id:string;type:'note';title:string;text:string};
export interface Definition {version:1;blocks:ReportBlock[];filters:Filter[]}
export interface EditorReport {id:string;title:string;revision:number;dataset_id:string;dataset:Dataset;profile:CsvProfile;definition:Definition}
export interface ReportEvaluation {report_id:string;revision:number;dataset_sha256:string;complete:boolean;results:CalculationResult[];errors:{block_id:string;message:string}[]}
export const reportEditorApi = {
  load:(id:string)=>request<EditorReport>('/reports/'+id+'/editor'),
  save:(id:string,title:string,definition:Definition,revision:number,sha:string)=>request<EditorReport>('/reports/'+id+'/editor',{
    method:'PATCH',body:JSON.stringify({title,definition,expected_revision:revision,expected_sha256:sha}),
  }),
  evaluate:(id:string,revision:number,sha:string)=>request<ReportEvaluation>('/reports/'+id+'/evaluate',{
    method:'POST',body:JSON.stringify({expected_revision:revision,expected_sha256:sha}),
  }),
};
