"""Search with a street and building number, never suite/floor/building labels."""
import re
import unicodedata

def street_address(value):
    text=re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(value or ''))).strip()
    text=re.sub(r'((?:대로|로))\s+(\d+(?:번)?길)',r'\1\2',text)
    match=re.search(r'[가-힣A-Za-z0-9·.]+(?:대로|로|길)\s*\d+(?:-\d+)?(?=\s|$|[,(])',text)
    if match:return text[:match.end()].strip()
    match=re.search(r'(?:동|가|리)\s+(?:산\s*)?\d+(?:-\d+)?(?=\s|$|[,(])',text)
    if match:return text[:match.end()].strip()
    from .regions import normalize_region
    for district in re.finditer(r'([가-힣]+)\s+[가-힣]+(?:구|시|군)(?=\s|$)',text):
        if normalize_region(district[1]):return district[0]
    return ''

def place_query(place,suffix=''):
    return ' '.join(p for p in [str(place.get('name') or '').strip(),street_address(place.get('address')),suffix] if p)
