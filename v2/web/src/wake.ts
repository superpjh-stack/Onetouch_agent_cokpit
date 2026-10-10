export type WakePolicy = {agent_name:string;wake_aliases:string[];require_wake_name:boolean};

// Same grammar as v2/wake.py; policy values come from the server.
export function callsAgent(text:string, policy:WakePolicy):boolean {
 if(!policy.require_wake_name)return true;
 const normalize=(value:string)=>value.trim().replace(/\s+/gu,' ');
 const aliases=[...new Set([policy.agent_name,...policy.wake_aliases].map(normalize).filter(Boolean))];
 const names=aliases.sort((a,b)=>b.length-a.length).map(value=>value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|');
 if(!names)return false;
 return new RegExp(`^[\\s"'“‘]*(?:${names})(?=$|[\\s,，.!?。！？:：~～])`,'u').test(normalize(text));
}
