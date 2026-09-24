import os,time
from collections import defaultdict,deque
from fastapi import FastAPI,Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.routes import router
from app.database.db import engine,SessionLocal
from app.models.entities import Base,User,Organization,OrganizationMember
from app.security.auth import hash_password

Base.metadata.create_all(bind=engine)
app=FastAPI(title='SecureDoc AI API',version='1.1.0')
origins=[x.strip() for x in os.getenv('CORS_ORIGINS','http://localhost:3000,http://127.0.0.1:3000').split(',') if x.strip()]
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_credentials=True,allow_methods=['GET','POST','PATCH','DELETE','OPTIONS'],allow_headers=['Authorization','Content-Type'])
_hits=defaultdict(deque)
@app.middleware('http')
async def security_middleware(request:Request,call_next):
    key=request.client.host if request.client else 'unknown'; now=time.time(); q=_hits[key]
    while q and q[0]<now-60:q.popleft()
    if len(q)>=120:return JSONResponse({'detail':'Too many requests. Please try again shortly.'},status_code=429)
    q.append(now)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'; response.headers['X-Frame-Options']='DENY'; response.headers['Referrer-Policy']='strict-origin-when-cross-origin'; response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'; response.headers['Cache-Control']='no-store' if request.url.path.startswith('/api') else response.headers.get('Cache-Control','')
    return response
app.include_router(router,prefix='/api')
def seed_demo():
    db=SessionLocal()
    try:
        if not db.query(User).filter_by(email='demo@securedoc.local').first():
            u=User(name='Demo User',email='demo@securedoc.local',password_hash=hash_password('Demo@123456')); db.add(u); db.flush(); o=Organization(name='Acme Trading Ltd.'); db.add(o); db.flush(); db.add(OrganizationMember(organization_id=o.id,user_id=u.id,role='owner')); db.commit()
    finally: db.close()
seed_demo()
@app.get('/health')
def health(): return {'status':'ok','service':'securedoc-ai-api','version':'1.1.0'}
