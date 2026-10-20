import type {Step} from './types';
export async function api<T>(token:string,path:string,options:RequestInit={}):Promise<T>{
  const response=await fetch(path,{...options,headers:{'Content-Type':'application/json','Authorization':`Bearer ${token}`,...options.headers}});
  if(!response.ok){let detail:unknown;try{detail=(await response.json()).detail;}catch{detail=response.statusText;}
    throw new Error(typeof detail==='string'?detail:JSON.stringify(detail));}
  return response.json() as Promise<T>;
}
/** Stream persisted events. No token is put in URLs or the browser bundle. */
export async function watchRun(token:string,id:string,onStep:(step:Step)=>void,signal:AbortSignal):Promise<void>{
  let cursor=0;
  for(let attempt=0;attempt<3;attempt++){
    const response=await fetch(`/api/runs/${encodeURIComponent(id)}/events?after=${cursor}`,{headers:{Authorization:`Bearer ${token}`},signal});
    if(!response.ok||!response.body)throw new Error('Event stream unavailable');
    const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
    try{
      while(true){
        const {value,done}=await reader.read();if(done)break;
        buffer+=decoder.decode(value,{stream:true});buffer=buffer.replace(/\r\n/g,'\n');
        let end:number;
        while((end=buffer.indexOf('\n\n'))>=0){
          const block=buffer.slice(0,end);buffer=buffer.slice(end+2);
          const lines=block.split('\n');
          const name=lines.find(s=>s.startsWith('event:'))?.slice(6).trim();
          const data=lines.filter(s=>s.startsWith('data:')).map(s=>s.slice(5).trimStart()).join('\n');
          if(name==='done')return;
          if(name==='step'&&data){const step=JSON.parse(data) as Step;if(step.id>cursor){cursor=step.id;onStep(step);}}
        }
      }
    }finally{await reader.cancel().catch(()=>{});}
  }
  throw new Error('Stream interrupted. The run remains saved in the backend; refresh its status.');
}
export const pct=(v:number)=>`${(v*100).toFixed(1)}%`;
export function points(values:number[]):string{
  const max=Math.max(.02,...values);
  return values.map((v,i)=>`${i*420/Math.max(1,values.length-1)},${100-v/max*100}`).join(' ');
}
