import hashlib
import math
import os
import re
from functools import lru_cache
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from .config import RUNTIME
from .catalog import text

class DemoEmbeddings(Embeddings):
    """네트워크 없는 문자 bigram 해시. 의미 임베딩이나 실제 RAG 품질로 보고하지 않는다."""
    def embed_documents(self,texts):return [self.embed_query(t) for t in texts]
    def embed_query(self,text):
        vector=[0.0]*256
        clean=re.sub(r'\s+','',text.lower())
        for i in range(max(1,len(clean)-1)):
            key=hashlib.sha256(clean[i:i+2].encode()).digest()
            vector[int.from_bytes(key[:2],'little')%256]+=1
        norm=math.sqrt(sum(v*v for v in vector)) or 1
        return [v/norm for v in vector]

def embedding_mode():return os.getenv('EMBEDDING_MODE','demo')

@lru_cache
def embedder(mode):
    if mode=='demo':return DemoEmbeddings()
    if not os.getenv('GMS_KEY'):raise ValueError('실제 임베딩에는 GMS 키가 필요합니다.')
    from langchain_openai import OpenAIEmbeddings
    return OpenAIEmbeddings(api_key=os.environ['GMS_KEY'],base_url=os.getenv('GMS_BASE_URL','https://gms.ssafy.io/gmsapi/api.openai.com/v1/'),
        model=os.getenv('EMBEDDING_MODEL','text-embedding-3-small'),request_timeout=30,max_retries=1)

@lru_cache
def client():
    import chromadb
    from chromadb.config import Settings
    return chromadb.PersistentClient(path=str(RUNTIME/'chroma'),settings=Settings(anonymized_telemetry=False))

def collections(mode):
    # 모델 변경 시 임베딩 차원·공간 충돌을 막기 위해 모델명을 컬렉션에 포함한다.
    model='hash256-v1' if embedding_mode()=='demo' else os.getenv('EMBEDDING_MODEL','text-embedding-3-small')
    suffix=hashlib.sha256(model.encode()).hexdigest()[:10]
    return tuple(client().get_or_create_collection(f'{mode}-{kind}-{suffix}',embedding_function=None) for kind in ('places','documents'))

def index_places(rows,mode):
    metadata,_=collections(mode);ids=[p['id'] for p in rows]
    for offset in range(0,len(rows),40):
        batch=rows[offset:offset+40];texts=[text(p) for p in batch]
        metadata.upsert(ids=[p['id'] for p in batch],documents=texts,embeddings=embedder(embedding_mode()).embed_documents(texts),
            metadatas=[dict(place_id=p['id'],title=p['name'],source=p['source'],type='metadata',checked_at=p['checked_at']) for p in batch])
    stale=list(set(metadata.get()['ids'])-set(ids))
    if stale:metadata.delete(ids=stale)
    return metadata.count()

def index_documents(docs,mode,size=None,overlap=None):
    size=size or int(os.getenv('CHUNK_SIZE','700'))
    overlap=int(os.getenv('CHUNK_OVERLAP','100')) if overlap is None else overlap
    if size<50 or overlap<0 or overlap>=size:raise ValueError('청크 크기는 50 이상, 중복 길이는 크기 미만이어야 합니다.')
    splitter=RecursiveCharacterTextSplitter(chunk_size=size,chunk_overlap=overlap)
    _,collection=collections(mode)
    for doc in docs:
        owner=doc['place_id']+'::'+doc['id']
        chunks=splitter.split_text(doc['body'])
        ids=[hashlib.sha256(f'{owner}:{i}:{chunk}'.encode()).hexdigest() for i,chunk in enumerate(chunks)]
        old=collection.get(where={'owner':owner})['ids']
        if chunks:
            collection.upsert(ids=ids,documents=chunks,embeddings=embedder(embedding_mode()).embed_documents(chunks),
                metadatas=[dict(owner=owner,place_id=doc['place_id'],document_id=doc['id'],title=doc['title'],type=doc['type'],
                    source=doc['source'],collected_at=doc['collected_at'],license=doc['license'],chunk=i) for i in range(len(chunks))])
        stale=list(set(old)-set(ids))
        if stale:collection.delete(ids=stale)
    return collection.count()

def retrieve(ids,question,mode,k=4):
    k=max(1,min(k,20));metadata,docs=collections(mode)
    evidence=[]
    if ids:
        rows=metadata.get(ids=ids)
        for body,meta in zip(rows['documents'],rows['metadatas']):evidence.append(dict(body=body,**meta))
        scope={'place_id':{'$in':ids}}
        matching=docs.get(where=scope,include=[])['ids']
        if matching:
            # 청크 갱신 후 전역 개수가 아닌 필터 결과 개수로 Top-k를 제한한다.
            results=docs.query(query_embeddings=[embedder(embedding_mode()).embed_query(question)],where=scope,n_results=min(k,len(matching)))
            for body,meta in zip(results['documents'][0],results['metadatas'][0]):evidence.append(dict(body=body,**meta))
    unique=[];seen=set()
    for e in evidence:
        key=(e['source'],e['body'])
        if key not in seen:unique.append(dict(e,number=len(unique)+1));seen.add(key)
    return unique

def search_places(question,mode,k=20):
    meta,_=collections(mode)
    if not meta.count():return []
    result=meta.query(query_embeddings=[embedder(embedding_mode()).embed_query(question)],n_results=min(k,meta.count()))
    return result['ids'][0]
