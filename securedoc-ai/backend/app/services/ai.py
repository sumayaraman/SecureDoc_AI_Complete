import json, os
from typing import Any, Protocol
from app.services.extractor import parse_invoice

SCHEMA_HINT='''Return ONLY valid JSON with keys: vendor_name, invoice_number, invoice_date, due_date, subtotal, discount, tax, total, currency, confidence, items. items is an array of {description, quantity, unit_price, total}. Use null for unknown values and numeric values for money. confidence is 0-100. Never invent values.'''

class AIProvider(Protocol):
    async def extract_invoice(self,text:str,filename:str)->dict[str,Any]: ...

class RuleProvider:
    async def extract_invoice(self,text:str,filename:str): return parse_invoice(text,filename)

class OpenAICompatibleProvider:
    async def extract_invoice(self,text:str,filename:str):
        import httpx
        base=os.getenv('AI_BASE_URL','https://api.openai.com/v1').rstrip('/')
        key=os.getenv('AI_API_KEY','')
        model=os.getenv('AI_MODEL','gpt-4o-mini')
        if not key: raise RuntimeError('AI_API_KEY is not configured')
        prompt=f"{SCHEMA_HINT}\nFilename: {filename}\nInvoice text:\n{text[:120000]}"
        headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'}
        payload={'model':model,'temperature':0,'messages':[{'role':'system','content':'You extract invoice data accurately.'},{'role':'user','content':prompt}]}
        async with httpx.AsyncClient(timeout=90) as client:
            r=await client.post(f'{base}/chat/completions',headers=headers,json=payload); r.raise_for_status(); data=r.json()
        content=data['choices'][0]['message']['content'].strip().replace('```json','').replace('```','').strip()
        result=json.loads(content)
        result.setdefault('items',[]); result.setdefault('confidence',0)
        return result

class OllamaProvider:
    async def extract_invoice(self,text:str,filename:str):
        import httpx
        url=os.getenv('OLLAMA_URL','http://localhost:11434').rstrip('/')+'/api/chat'
        model=os.getenv('AI_MODEL','llama3.2')
        prompt=f"{SCHEMA_HINT}\nFilename: {filename}\nInvoice text:\n{text[:120000]}"
        payload={'model':model,'stream':False,'format':'json','messages':[{'role':'system','content':'You extract invoice data accurately.'},{'role':'user','content':prompt}]}
        async with httpx.AsyncClient(timeout=120) as client:
            r=await client.post(url,json=payload); r.raise_for_status(); data=r.json()
        result=json.loads(data['message']['content']); result.setdefault('items',[]); result.setdefault('confidence',0); return result

class AIService:
    def __init__(self,provider:AIProvider|None=None):
        if provider: self.provider=provider
        else:
            kind=os.getenv('AI_PROVIDER','rules').lower()
            self.provider=OllamaProvider() if kind=='ollama' else OpenAICompatibleProvider() if kind in ('openai','openai_compatible') else RuleProvider()
    async def extract_invoice(self,text:str,filename:str): return await self.provider.extract_invoice(text,filename)
