from app.request_intent import interpret, matches, search_terms
from app.models import Conditions

def test_specific_sport_does_not_match_other_sports():
    assert interpret('실내 클라이밍')['intents']==['climbing']
    assert interpret('실내 클라이밍')['patch']['setting']=='indoor'
    assert matches({'name':'볼더링 클라이밍 센터'},'climbing')
    assert not matches({'name':'볼링장','category':'레저·활동'},'climbing')

def test_sports_multiple_and_exclusion():
    assert interpret('클라이밍, 볼링')['intents']==['climbing','bowling']
    result=interpret('볼링 말고 탁구')
    assert result['intents']==['table_tennis']
    assert result['excluded']==['bowling']
    assert interpret('실내 클라이밍만')['exclusive']

def test_each_sport_is_distinct():
    for word,key in [('탁구','table_tennis'),('배드민턴','badminton'),('스케이트','skating'),('스크린 골프','screen_golf')]:
        assert interpret(word)['intents']==[key]
        assert matches({'name':word+' 센터'},key)
