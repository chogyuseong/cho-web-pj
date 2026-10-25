import sqlite3
import pytest
from app.request_intent import interpret
from app import store


@pytest.mark.parametrize('text',[
    '카페는 안 좋아해. 전시 보고 싶어',
    '카페는 별로야. 전시 추천해줘',
    '커피는 못 마셔. 전시가 좋아',
    '카페 좋아하지 않아. 전시 보자',
])
def test_colloquial_negative_preferences_are_not_positive_intents(text):
    result=interpret(text)
    assert 'cafe' in result['excluded'] and 'cafe' not in result['intents']
    assert 'culture' in result['intents']


def test_positive_preference_not_reversed():
    result=interpret('카페 좋아해. 박물관은 안 좋아해')
    assert 'cafe' in result['intents'] and 'museum' in result['excluded']


def test_database_connections_close_and_rollback_on_context_exit():
    with store.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS close_test(value TEXT)')
    with pytest.raises(RuntimeError if store.postgres_enabled() else sqlite3.ProgrammingError):db.execute('SELECT 1')
    with pytest.raises(RuntimeError):
        with store.connect() as conn:
            conn.execute("INSERT INTO close_test VALUES('rollback')")
            raise RuntimeError('test rollback')
    with store.connect() as check:assert check.execute('SELECT count(*) FROM close_test').fetchone()[0]==0
