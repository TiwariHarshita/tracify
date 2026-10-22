import { request } from './api';

export type Operation = 'sum'|'average'|'count'|'min'|'max';
export type Filter = {type:'category';column:string;values:string[]} | {type:'date_range';column:string;start:string;end:string}
  | {type:'number_range';column:string;minimum?:string;maximum?:string} | {type:'missing';column:string;missing:boolean};
export type Calculation = {id:string;type:'metric';operation:Operation;column:string|null;group_by:string|null}
  | {id:string;type:'chart';chart_type:'bar'|'line';operation:Operation;column:string|null;group_by:string}
  | {id:string;type:'table';sort_by:string;direction:'asc'|'desc';limit:number};
export interface EvaluateRequest { expected_sha256:string; filters:Filter[]; calculations:Calculation[] }
export interface Receipt {
  description:string; queries:{sql:string;parameters:(string|number)[]}[]; postprocessing:string;
  total_rows:number;matched_rows:number;included_rows:number;excluded_rows:number;
  excluded_by_filters:number;excluded_missing_value:number;excluded_by_limit:number;
  dataset_sha256:string;parser_version:string;calculation_version:string;source_relation:string;
  column_mapping:{key:string;name:string;inferred_type:string;sql_type:string}[];
}
export interface CalculationResult {
  id:string;type:'metric'|'chart'|'table';result:{rows:Record<string,string|number|null>[];chart_type?:'bar'|'line';columns?:{key:string;name:string}[]};receipt:Receipt;
}
export interface Evaluation { dataset_id:string;dataset_sha256:string;calculation_version:string;results:CalculationResult[] }
export const analyticsApi = {
  evaluate:(id:string,body:EvaluateRequest)=>request<Evaluation>('/datasets/'+id+'/evaluate',{method:'POST',body:JSON.stringify(body)}),
};
