const API=process.env.NEXT_PUBLIC_API_URL||'http://localhost:8000/api';
export async function api(path:string,options:RequestInit={}){
  const token=typeof window!=='undefined'?localStorage.getItem('securedoc_token'):null;
  const headers=new Headers(options.headers);
  if(!headers.has('Content-Type') && options.body && !(options.body instanceof FormData)) headers.set('Content-Type','application/json');
  if(token) headers.set('Authorization',`Bearer ${token}`);
  let r: Response;
  try {
    r=await fetch(`${API}${path}`,{...options,headers});
  } catch(err:any) {
    if(err.name==='TypeError' || (err.message && err.message.toLowerCase().includes('fetch'))) {
      throw new Error('Could not connect to the backend server. If using a free-tier host, it may take 45–60 seconds to wake up. Please try again.');
    }
    throw err;
  }
  const data=await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(data.detail||'Request failed');
  return data;
}
export async function uploadFile(file:File){const form=new FormData();form.append('file',file);return api('/documents/upload',{method:'POST',body:form});}
export async function getDocumentStatus(documentId:number|string){return api(`/documents/${documentId}/status`);}
export async function getProcessingJobStatus(jobId:number|string){return api(`/processing-jobs/${jobId}`);}
export async function downloadBlob(path:string,filename:string){const token=typeof window!=='undefined'?localStorage.getItem('securedoc_token'):null;const r=await fetch(`${API}${path}`,{headers:token?{Authorization:`Bearer ${token}`}:{}});if(!r.ok)throw new Error('Download failed');const b=await r.blob();const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=filename;a.click();URL.revokeObjectURL(a.href)}

