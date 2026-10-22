import { API_ORIGIN, request } from './api';
import type { Definition } from './reportEditor';
import type { CalculationResult } from './analytics';
import type { CsvProfile } from './datasets';

export interface ShareLink {id:string;expires_at:string|null;revoked_at?:string|null;created_at:string}
export interface NewShareLink extends ShareLink {url_token:string}
export interface PublicReport {title:string;definition:Definition;profile:Pick<CsvProfile,'columns'>;results:CalculationResult[];report_revision:number;dataset_sha256:string;published_at:string}

export const sharingApi={
  create:(reportId:string,revision:number,sha:string,expires_at:string|null)=>request<NewShareLink>('/reports/'+reportId+'/share-links',{method:'POST',body:JSON.stringify({expected_revision:revision,expected_sha256:sha,expires_at})}),
  list:(reportId:string)=>request<ShareLink[]>('/reports/'+reportId+'/share-links'),
  revoke:(reportId:string,linkId:string)=>request<void>('/reports/'+reportId+'/share-links/'+linkId,{method:'DELETE'}),
  public:async(token:string):Promise<PublicReport>=>{
    const response=await fetch(API_ORIGIN+'/api/v1/public/shares/'+encodeURIComponent(token),{cache:'no-store'});
    if(!response.ok)throw new Error('This shared report is unavailable, expired, or revoked.');
    return response.json() as Promise<PublicReport>;
  },
};
