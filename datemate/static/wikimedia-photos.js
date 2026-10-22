/* 공식 공개 CORS API. 사용자가 보는 장소의 QID→P18만 조회하며 이름 검색으로 다른 장소 사진을 섞지 않는다. */
let photoApiQueue=Promise.resolve();
function photoText(value){return String(value||'').replace(/<[^>]*>/g,' ').replace(/&amp;/g,'&').replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/\s+/g,' ').trim().slice(0,800);}
function publicPhotoJson(host,params){
  const run=photoApiQueue.catch(()=>{}).then(async()=>{
    const response=await fetch('https://'+host+'/w/api.php?'+new URLSearchParams({...params,format:'json',origin:'*'}),{credentials:'omit',signal:AbortSignal.timeout(12000)});
    if(!response.ok)throw Error('사진 자료 공급자 응답 실패');
    const data=await response.json();if(data.error)throw Error('사진 자료 조회 실패');return data;
  });
  photoApiQueue=run.catch(()=>{}).then(()=>new Promise(resolve=>setTimeout(resolve,1000)));
  return run;
}
async function discoverPlacePhotos(place,data){
  if(!data.wikidata_id||!/^Q[1-9][0-9]*$/.test(data.wikidata_id)||data.photos.length)return data;
  const key='datemate-photos-v2:'+data.wikidata_id;
  try{const cached=JSON.parse(localStorage.getItem(key));if(cached?.expires>Date.now())return {...data,photos:cached.photos};}catch{}
  const claims=await publicPhotoJson('www.wikidata.org',{action:'wbgetclaims',entity:data.wikidata_id,property:'P18'});
  const titles=[...new Set((claims.claims?.P18||[]).filter(c=>c.rank!=='deprecated').map(c=>c.mainsnak?.datavalue?.value).filter(value=>typeof value==='string'&&/\.jpe?g$/i.test(value)))].slice(0,5);
  if(!titles.length)return data;
  const response=await publicPhotoJson('commons.wikimedia.org',{action:'query',titles:titles.map(t=>'File:'+t).join('|'),prop:'imageinfo',iiprop:'url|extmetadata|mime',iiurlwidth:1280,iiextmetadatalanguage:'ko'});
  const photos=[];
  for(const page of Object.values(response.query?.pages||{})){
    const info=page.imageinfo?.[0];if(!info||info.mime!=='image/jpeg')continue;
    const meta=info.extmetadata||{},license=photoText(meta.LicenseShortName?.value),author=photoText(meta.Artist?.value),licenseUrl=meta.LicenseUrl?.value;
    if(!/^(CC BY(-SA)? [1-4]\.0|CC0|Public domain)$/i.test(license)||!author||!licenseUrl)continue;
    const image=info.thumburl||info.url,source=info.descriptionurl;
    try{if(!['upload.wikimedia.org','thumb.wikimedia.org'].includes(new URL(image).hostname)||new URL(image).protocol!=='https:'||new URL(source).hostname!=='commons.wikimedia.org'||new URL(licenseUrl).hostname!=='creativecommons.org')continue;}catch{continue;}
    photos.push({id:String(page.pageid),image_url:image,url:info.url,source,title:place.name+' 대표 사진',
      caption:place.description||'서울 '+place.name+'의 공개 대표 사진입니다. 촬영 정보는 사진 원문에서 확인할 수 있습니다.',source_caption:photoText(meta.ImageDescription?.value),author,license,license_url:licenseUrl,
      checked_at:new Date().toISOString().slice(0,10),taken_at:photoText(meta.DateTimeOriginal?.value)||null,
      association:'Wikidata '+data.wikidata_id+'의 P18 대표 이미지',changes:'원본 변경 없음 · 공급자 축소 이미지 표시'});
  }
  try{localStorage.setItem(key,JSON.stringify({photos,expires:Date.now()+7*86400000}));}catch{}
  return {...data,photos,status:photos.length?'available':'not_found'};
}
