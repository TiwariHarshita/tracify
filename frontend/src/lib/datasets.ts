import { API_ORIGIN, request } from './api';
import type { Dataset } from './workspace';

export interface ColumnProfile {
  key: string; name: string; type: 'number'|'date'|'category'|'text';
  missing_count: number; non_missing_count: number; distinct_count: number;
  reason: string; warnings: string[]; examples: string[];
}
export interface CsvProfile {
  parser_version: string; sha256: string; encoding: string; delimiter: string;
  physical_lines: number; header_line_end: number; total_records: number|null;
  known_records: number; readable_rows: number; unreadable_rows: number;
  unparsed_lines: number; error_count: number; analysis_ready: boolean;
  missing_policy: string; inference_scope: string; columns: ColumnProfile[];
}
export interface CsvRow { record_number: number; line_start: number; line_end: number; cells: string[] }
export interface CsvIssue {
  record_number: number|null; line_start: number; line_end: number;
  code: string; reason: string; raw_excerpt: string; excerpt_truncated: boolean;
}
export interface Page<T> {items:T[];total:number;offset:number;limit:number}
export const datasetsApi = {
  upload: (file: File, delimiter: string) => {
    const body = new FormData(); body.append('file',file); body.append('delimiter',delimiter);
    return request<Dataset>('/datasets/upload', {method:'POST',body});
  },
  profile: (id:string) => request<CsvProfile>('/datasets/'+id+'/profile'),
  preview: (id:string, offset=0) => request<Page<CsvRow>>('/datasets/'+id+'/preview?offset='+offset+'&limit=50'),
  errors: (id:string, offset=0) => request<Page<CsvIssue>>('/datasets/'+id+'/errors?offset='+offset+'&limit=50'),
  rawUrl: (id:string) => API_ORIGIN+'/api/v1/datasets/'+id+'/raw',
};
