from unittest.mock import Mock

import mongomock
import pytest
from backend import Backend
from deal_exclusions import excluded_deal
from superdeal_local_live_worker import handle_message
from superdeal_telegram_capture import process_next, utcnow


@pytest.mark.parametrize('text', [
    'Buy https://web.lehlah.club/deal/123',
    'https://WEB.LEHLAH.CLUB/?id=99',
    'Deal (https://web.lehlah.club)',
    'web.lehlah.club',
    'https://web.lehlah.club:443/deals',
    'https://web.lehlah.club./deals',
    'Deal https://web.lehlah.club.',
    'Headphones https://amazon.in/dp/123 and https://web.lehlah.club/offer',
])
def test_matching_domain_is_excluded(text):
    assert excluded_deal(text)


@pytest.mark.parametrize('text', ['https://web.lehlah.club.evil.example/x',
    'https://notweb.lehlah.club/x', 'https://web.lehlah.clubs/x',
    'https://amazon.in/dp/123', 'https://lehlah.club/x', None, ''])
def test_other_hosts_are_not_excluded(text):
    assert not excluded_deal(text)


def backend():
    b = Backend(mongomock.MongoClient().db, converter=Mock(), llm=Mock())
    b.setup()
    return b


def test_live_worker_keeps_raw_and_skips_without_calling_any_provider():
    b = backend()
    text = 'Mixed offers https://amazon.in/dp/1 https://web.lehlah.club/deal'
    status, raw_id = handle_message(b, 'fixture', '1', text, None)
    assert status == 'SKIPPED'
    assert b.db.raw.find_one({})['text'] == text
    doc = b.db.pipeline_status.find_one({})
    assert str(doc['raw_id']) == raw_id
    assert doc['status'] == 'SKIPPED' and doc['skip_reason'] == 'EXCLUDED_DOMAIN'
    assert doc['products_published'] == 0
    b.converter.assert_not_called()
    b.llm.assert_not_called()
    assert b.db.ek_raw.count_documents({}) == b.db.fact_table.count_documents({}) == 0
    assert handle_message(b, 'fixture', '1', text, None)[0] == 'SKIPPED'
    assert b.db.raw.count_documents({}) == 1


def test_previously_pending_raw_is_checked_again_before_conversion():
    b = backend()
    raw_id = b.ingest('fixture', '2', 'https://web.lehlah.club/x')
    b.db.pipeline_status.update_one({'raw_id':raw_id}, {'$set':{'status':'PENDING'}})
    assert b.process(raw_id) == 0
    b.converter.assert_not_called()
    assert b.db.pipeline_status.find_one({'raw_id':raw_id})['status'] == 'SKIPPED'


def test_excluded_domain_revealed_by_earnkaro_stops_before_research_or_llm(monkeypatch):
    b = backend()
    monkeypatch.setenv('SUPERDEAL_PRE_LLM_RESEARCH', '1')
    research = Mock(side_effect=AssertionError('Must not browse excluded deals'))
    monkeypatch.setattr('pre_llm_research.research_message', research)
    text = 'Headphones https://original.example/short'
    b.converter.return_value = {'response_text':'https://web.lehlah.club/deal'}
    raw_id = b.ingest('fixture', '3', text)
    assert b.process(raw_id) == 0
    assert b.db.raw.find_one({'_id':raw_id})['text'] == text
    assert b.db.ek_raw.find_one({'raw_id':raw_id})
    assert b.db.pipeline_status.find_one({'raw_id':raw_id})['status'] == 'SKIPPED'
    b.llm.assert_not_called()
    research.assert_not_called()
    assert b.db.fact_table.count_documents({}) == 0


def test_unrelated_messages_remain_pending():
    b = backend()
    raw_id = b.ingest('fixture', '4', 'Headphones https://amazon.in/dp/123')
    assert b.db.pipeline_status.find_one({'raw_id':raw_id})['status'] == 'PENDING'


def test_independent_capture_inbox_is_preserved_and_marked_skipped():
    b = backend()
    text = 'Deal https://web.lehlah.club/example'
    b.db.telegram_inbox.insert_one({'channel':'fixture','message_id':'5','text':text,
                                  'state':'CAPTURED','received_at':utcnow()})
    assert process_next(b, ['fixture']) is True
    inbox = b.db.telegram_inbox.find_one({})
    assert inbox['text'] == text and inbox['pipeline_status'] == 'SKIPPED'
    assert inbox['state'] == 'HANDLED'
    assert b.db.raw.find_one({'_id':inbox['raw_id']})['text'] == text
    b.converter.assert_not_called()
