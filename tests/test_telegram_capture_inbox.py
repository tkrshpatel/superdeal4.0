"""Capture durability, per-channel isolation and publication independence."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
import mongomock
import pytest
from superdeal_telegram_capture import TelegramInbox, process_next

def msg(i,text='deal',media=None):
    return SimpleNamespace(id=i,raw_text=text,date=datetime.now(timezone.utc),
        edit_date=None,media=media,grouped_id=None,to_json=lambda:'{"id":'+str(i)+'}')

def inbox():
    db=mongomock.MongoClient().db
    box=TelegramInbox(db);box.setup()
    return box,db

def test_raw_capture_is_independent_and_media_only_messages_are_stored():
    box,db=inbox();box.seed('telegram:1',10)
    box.capture('telegram:1',msg(11,''))
    box.capture('telegram:1',msg(12,'',SimpleNamespace()))
    box.capture('telegram:1',msg(13,'caption',SimpleNamespace()))
    assert db.telegram_inbox.count_documents({})==3
    assert db.telegram_inbox.count_documents({'state':'ARCHIVED'})==2
    assert db.telegram_inbox.find_one({'message_id':'13'})['text']=='caption'
    assert db.raw.count_documents({})==0
    assert box.checkpoint('telegram:1')==10

def test_duplicate_messages_and_edits_do_not_restart_publication():
    box,db=inbox();box.seed('telegram:1',0)
    original=msg(1)
    box.capture('telegram:1',original)
    box.capture('telegram:1',original)
    original.raw_text='changed';original.edit_date=datetime.now(timezone.utc)
    box.capture('telegram:1',original,edited=True)
    assert db.telegram_inbox.count_documents({})==2
    assert db.telegram_inbox.find_one({'is_edit':False})['text']=='deal'
    assert db.telegram_inbox.find_one({'is_edit':True})['state']=='ARCHIVED'

def test_recovery_stores_every_message_across_more_than_one_page_and_channel():
    box,db=inbox()
    class Client:
        def iter_messages(self,entity,**kwargs):
            assert kwargs['reverse'] is True and kwargs['limit'] is None
            return iter(msg(i) for i in range(kwargs['min_id']+1,306))
    client=Client()
    async def run():
        box.seed('telegram:1',5);box.seed('telegram:2',5)
        await asyncio.gather(box.reconcile(client,1,'telegram:1'),box.reconcile(client,2,'telegram:2'))
        await box.reconcile(client,1,'telegram:1')
    asyncio.run(run())
    assert db.telegram_inbox.count_documents({})==600
    assert box.checkpoint('telegram:1')==305
    assert box.checkpoint('telegram:2')==305

def test_capture_failure_does_not_advance_scan_cursor_and_other_channel_continues():
    box,db=inbox();box.seed('telegram:1',10);box.seed('telegram:2',10)
    class Client:
        def iter_messages(self,entity,**kwargs):
            return iter([msg(11),msg(12)])
    real=box.capture
    def fail(channel,message,**kwargs):
        if channel=='telegram:1' and message.id==12:
            raise RuntimeError('temporary Mongo outage')
        return real(channel,message,**kwargs)
    box.capture=fail
    async def run():
        result=await asyncio.gather(box.reconcile(Client(),1,'telegram:1'),
            box.reconcile(Client(),2,'telegram:2'),return_exceptions=True)
        assert isinstance(result[0],RuntimeError)
        assert result[1]==2
    asyncio.run(run())
    assert box.checkpoint('telegram:1')==11
    assert box.checkpoint('telegram:2')==12

def test_restart_resumes_checkpoint_without_rewinding_history():
    box,db=inbox();box.seed('telegram:1',100)
    box.seed('telegram:1',999)
    assert box.checkpoint('telegram:1')==100
    assert db.telegram_inbox.count_documents({})==0

def test_pending_pipeline_is_independent_and_runs_once():
    box,db=inbox();box.seed('telegram:1',0)
    box.capture('telegram:1',msg(1))
    backend=MagicMock();backend.db=db
    backend.ingest.return_value='raw1'
    db.pipeline_status.insert_one({'raw_id':'raw1','status':'PENDING'})
    backend.process.side_effect=lambda raw:db.pipeline_status.update_one({'raw_id':raw},{'$set':{'status':'PUBLISHED'}})
    assert process_next(backend,['telegram:1'])
    assert not process_next(backend,['telegram:1'])
    backend.process.assert_called_once_with('raw1')
    assert db.telegram_inbox.find_one({})['pipeline_status']=='PUBLISHED'

def test_failed_job_is_not_replayed():
    box,db=inbox();box.capture('telegram:1',msg(1))
    backend=MagicMock();backend.db=db;backend.ingest.return_value='raw1'
    db.pipeline_status.insert_one({'raw_id':'raw1','status':'FAILED'})
    assert process_next(backend,['telegram:1'])
    backend.process.assert_not_called()

def test_raw_message_survives_publication_failure():
    box,db=inbox();box.capture('telegram:1',msg(1,'earnkaro will fail'))
    backend=MagicMock();backend.db=db;backend.ingest.return_value='raw1'
    db.pipeline_status.insert_one({'raw_id':'raw1','status':'PENDING'})
    def fail(raw):
        db.pipeline_status.update_one({'raw_id':raw},{'$set':{'status':'FAILED'}})
        raise RuntimeError('provider failure')
    backend.process.side_effect=fail
    with pytest.raises(RuntimeError):
        process_next(backend,['telegram:1'])
    assert db.telegram_inbox.find_one({})['text']=='earnkaro will fail'
    assert process_next(backend,['telegram:1'])
    backend.process.assert_called_once()

def test_unconfigured_channels_are_not_published():
    box,db=inbox();box.capture('telegram:other',msg(1))
    backend=MagicMock();backend.db=db
    assert not process_next(backend,['telegram:1'])
    backend.ingest.assert_not_called()


def test_monitor_keeps_healthy_channels_running_when_one_cannot_resolve(monkeypatch):
    from superdeal_telegram_capture import monitor
    from telethon import utils
    monkeypatch.setattr(utils,'get_peer_id',lambda entity:-1000000-entity.id)
    box,db=inbox()
    class Client:
        def __init__(self): self.handlers=[]
        async def get_entity(self,target):
            if target=='inaccessible': raise ValueError('not joined')
            return SimpleNamespace(id=int(target))
        async def get_messages(self,entity,limit): return [msg(10)]
        def iter_messages(self,entity,**kwargs):
            return iter([msg(11,'caption from channel '+str(entity.id))])
        def add_event_handler(self,callback,event_filter): self.handlers.append(callback)
        def remove_event_handler(self,callback): self.handlers.remove(callback)
        async def run_until_disconnected(self):
            await asyncio.sleep(.1)
    client=Client()
    backend=MagicMock();backend.db=db
    asyncio.run(monitor(SimpleNamespace(client=client),backend,['1','inaccessible','2'],capture_only=True,interval=5))
    assert db.telegram_inbox.count_documents({})==2
    assert set(db.telegram_inbox.distinct('channel'))=={'telegram:1','telegram:2'}
    assert client.handlers==[]
    backend.ingest.assert_not_called()
    backend.process.assert_not_called()
