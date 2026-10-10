import type {WakePolicy} from './wake';
export type Row = Record<string, string | number | null>;
export type Quote = Row & {quote_id:string; drawing_id:string; product_name:string; requested_qty:number; status:string};
export type Document = {title:string;document_id:string; filename:string; content:string; source:string; status:string};
export type TableInfo = {table:string;label:string;count:number;exists:boolean};
export type Workspace = {kpi: Record<string,number>;quotes:Quote[];tables:TableInfo[];questions:Record<string,string[]>;meta:{wake:WakePolicy;company:string;version:string;demo_data:boolean;as_of:string;backend:string;ai_configured:boolean;local_dev_ai?:boolean;model:string;retrieved_at:string}};
export type Evidence = {filename:string;document_id?:string;text:string};
export type Answer = {ignored?:boolean;demo_data?:boolean;answer_id?:string;captured_at?:string;summary?:string;retrieved_at?:string;context?:{quote_id:string|null;as_of:string};unknowns?:string[];text:string;sources:string[];evidence:Evidence[];data_tools:string[];records:Row[];searched_documents:boolean;mode:'ai'|'demo'};
export async function request<T>(path:string, init?:RequestInit):Promise<T> {
 const response = await fetch('/api'+path, init);
 if (!response.ok) {const data = await response.json().catch(()=>({})); throw new Error(typeof data.detail === 'string' ? data.detail : `요청을 처리하지 못했습니다 (${response.status}).`);}
 return response.json();
}

export type User={id:string;username:string;name:string;organization:string;role:'operator'|'reviewer'|'admin'};
export type WorkItem={id:string;title:string;quote_id:string|null;kind:string;status:string;creator_id:string;assignee_id:string;version:number;created_at:string;updated_at:string;snapshot:{question:string;answer:Answer}|null;snapshots?:{question:string;answer:Answer}[];notes:{text:string;author:string;at:string}[];events:{action:string;actor:string;at:string;request_id:string}[];handoff:{sender_id:string;recipient_id:string;request:string;sent_at:string;acknowledged_at:string|null}|null};
export type JourneyEvent='task_opened'|'voice_started'|'voice_cancelled'|'transcript_ready'|'transcript_edited'|'question_submitted'|'answer_ready'|'evidence_opened'|'task_saved'|'handoff_sent'|'handoff_acknowledged'|'task_resumed'|'review_completed';
export function clientId(){
 if(globalThis.crypto?.randomUUID)return globalThis.crypto.randomUUID();
 const bytes=new Uint8Array(16);globalThis.crypto?.getRandomValues?.(bytes);
 return `${Date.now().toString(36)}-${Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('')||Math.random().toString(36).slice(2)}`;
}
// Telemetry is disabled until an explicit storage and retention policy is configured.
export function track(_event:JourneyEvent,_extra:{source?:'voice'|'text'|'suggestion';mode?:'demo'|'ai';duration_ms?:number;work?:string}={}){}
