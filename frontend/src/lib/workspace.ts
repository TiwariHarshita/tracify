import { request } from './api';

export interface Dataset {
  id: string; name: string; sha256: string; source_url: string;
  row_count: number; column_count: number; created_at: string;
}
export interface Report {
  id: string; title: string; dataset_id: string; created_at: string;
}
export const workspaceApi = {
  datasets: () => request<Dataset[]>('/datasets'),
  reports: () => request<Report[]>('/reports'),
  sample: () => request<Dataset>('/datasets/sample', {method:'POST'}),
  create: (dataset_id: string, title: string) => request<Report>('/reports', {
    method:'POST', body:JSON.stringify({dataset_id,title}),
  }),
  rename: (id: string, title: string) => request<Report>('/reports/' + id, {
    method:'PATCH', body:JSON.stringify({title}),
  }),
  deleteReport: (id: string) => request<void>('/reports/' + id, {method:'DELETE'}),
  deleteDataset: (id: string) => request<void>('/datasets/' + id, {method:'DELETE'}),
};
