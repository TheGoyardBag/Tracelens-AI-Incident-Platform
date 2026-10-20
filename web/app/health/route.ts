export const dynamic='force-dynamic';
export async function GET(){
  try{
    const response=await fetch(`${process.env.API_ORIGIN||'http://127.0.0.1:8000'}/health`,{cache:'no-store'});
    return Response.json(await response.json(),{status:response.status});
  }catch{return Response.json({status:'unavailable',llm_ready:false},{status:503});}
}
