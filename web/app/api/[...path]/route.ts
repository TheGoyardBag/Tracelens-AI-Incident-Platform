/** Same-origin streaming proxy. The destination is server config, not user input. */
import {NextRequest} from 'next/server';
export const runtime='nodejs';
export const dynamic='force-dynamic';
const allowed=new Set(['incidents','runs','evaluation','audit']);
type Context={params:Promise<{path:string[]}>};
async function proxy(request:NextRequest,context:Context){
  const {path}=await context.params;
  if(!allowed.has(path[0])||path.some(p=>!p||p==='.'||p==='..'||p.includes('/')||p.includes('\\'))){
    return Response.json({detail:'Unknown API path'},{status:404});
  }
  const origin=process.env.API_ORIGIN||'http://127.0.0.1:8000';
  const url=new URL(`/api/${path.map(encodeURIComponent).join('/')}`,origin);
  url.search=request.nextUrl.search;
  const body=request.method==='POST'?await request.text():undefined;
  if(body&&new TextEncoder().encode(body).length>2_000_000){
    return Response.json({detail:'Request exceeds 2 MB limit'},{status:413});
  }
  try{
    const upstream=await fetch(url,{
      method:request.method,body,cache:'no-store',signal:request.signal,
      headers:{'Authorization':request.headers.get('authorization')||'','Content-Type':'application/json'},
    });
    return new Response(upstream.body,{status:upstream.status,headers:{
      'Content-Type':upstream.headers.get('content-type')||'application/json',
      'Cache-Control':'no-store','X-Accel-Buffering':'no',
    }});
  }catch{return Response.json({detail:'Backend unavailable. Start the FastAPI service.'},{status:502});}
}
export const GET=proxy;
export const POST=proxy;
