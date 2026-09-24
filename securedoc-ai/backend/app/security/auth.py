import base64, hashlib, hmac, json, os, time
from fastapi import Header, HTTPException
from sqlalchemy.orm import Session
from app.models.entities import User, OrganizationMember

SECRET=os.getenv('JWT_SECRET','dev-only-change-this-secret')
if SECRET=='dev-only-change-this-secret' and os.getenv('ENVIRONMENT','development')=='production': raise RuntimeError('Set JWT_SECRET in production')

def hash_password(password:str)->str:
    if len(password)<8: raise ValueError('Password must be at least 8 characters')
    salt=os.urandom(16); digest=hashlib.scrypt(password.encode(),salt=salt,n=2**14,r=8,p=1); return base64.b64encode(salt+digest).decode()

def verify_password(password:str, stored:str)->bool:
    try:
        raw=base64.b64decode(stored); salt,digest=raw[:16],raw[16:]; check=hashlib.scrypt(password.encode(),salt=salt,n=2**14,r=8,p=1); return hmac.compare_digest(check,digest)
    except Exception:return False

def make_token(user_id:int)->str:
    payload={'sub':user_id,'exp':int(time.time())+60*60*24}
    body=base64.urlsafe_b64encode(json.dumps(payload,separators=(',',':')).encode()).decode().rstrip('='); sig=hmac.new(SECRET.encode(),body.encode(),hashlib.sha256).hexdigest(); return body+'.'+sig

def decode_token(token:str)->int:
    try:
        body,sig=token.split('.',1); expected=hmac.new(SECRET.encode(),body.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig,expected): raise ValueError()
        payload=json.loads(base64.urlsafe_b64decode(body+'='*((4-len(body)%4)%4)))
        if payload['exp']<time.time(): raise ValueError()
        return int(payload['sub'])
    except Exception: raise HTTPException(401,'Invalid or expired token')

def current_context(db:Session, authorization:str|None):
    if not authorization or not authorization.lower().startswith('bearer '): raise HTTPException(401,'Authentication required')
    user=db.get(User,decode_token(authorization.split(' ',1)[1]));
    if not user: raise HTTPException(401,'User not found')
    member=db.query(OrganizationMember).filter_by(user_id=user.id).first()
    if not member: raise HTTPException(403,'No organization membership')
    return user,member

def require_role(member, *roles):
    if member.role not in roles: raise HTTPException(403,'Insufficient permissions')
