"""Durable raw Telegram capture, independent of affiliate/LLM processing."""
from __future__ import annotations
import asyncio
import inspect
import re
import threading
from datetime import datetime, timezone
from pymongo import ASCENDING
from superdeal.telegram_user import normalize_user_channel, TELEGRAM_WEB_CHAT_RE

def utcnow():
    return datetime.now(timezone.utc)

async def awaited(value):
    return await value if inspect.isawaitable(value) else value

async def messages(iterator):
    if hasattr(iterator,'__aiter__'):
        async for item in iterator:
            yield item
    else:
        for item in iterator:
            yield item

class TelegramInbox:
    def __init__(self, db):
        self.db=db

    def setup(self):
        self.db.telegram_inbox.create_index([('channel',ASCENDING),('state',ASCENDING),('received_at',ASCENDING)])
        self.db.telegram_capture_channels.create_index('channel',unique=True)

    def seed(self, channel, last_id):
        self.db.telegram_capture_channels.update_one({'channel':channel},{'$setOnInsert':{
            'channel':channel,'last_scanned_id':int(last_id),'started_at':utcnow()}},upsert=True)

    def capture(self, channel, message, *, edited=False):
        mid=int(message.id)
        text=str(getattr(message,'raw_text',None) or getattr(message,'message',None) or '')
        edit_at=getattr(message,'edit_date',None)
        revision=('edit:'+str(edit_at or 'unknown')) if edited else 'original'
        key=f'{channel}:{mid}:{revision}'
        doc={'_id':key,'channel':channel,'message_id':str(mid),'text':text,
             'message_at':getattr(message,'date',None),'edit_at':edit_at,
             'telegram_payload':message.to_json() if callable(getattr(message,'to_json',None)) else None,
             'received_at':utcnow(),'grouped_id':str(getattr(message,'grouped_id','') or ''),
             'media_type':type(message.media).__name__ if getattr(message,'media',None) is not None else None,
             'is_edit':edited,'state':'CAPTURED' if text.strip() and not edited else 'ARCHIVED'}
        self.db.telegram_inbox.update_one({'_id':key},{'$setOnInsert':doc},upsert=True)
        self.db.telegram_capture_channels.update_one({'channel':channel},{'$set':{
            'last_received_at':utcnow(),'last_received_message_id':str(mid)}},upsert=True)
        return key

    def checkpoint(self, channel):
        return int((self.db.telegram_capture_channels.find_one({'channel':channel}) or {}).get('last_scanned_id',0))

    async def reconcile(self, client, entity, channel):
        # The durable scan cursor advances only after each message is stored.
        # NewMessage callbacks never advance it, so a missed event cannot hide a gap.
        cursor=self.checkpoint(channel)
        count=0
        async for message in messages(client.iter_messages(entity,min_id=cursor,reverse=True,limit=None)):
            await asyncio.to_thread(self.capture,channel,message)
            await asyncio.to_thread(self.db.telegram_capture_channels.update_one,
                {'channel':channel},{'$max':{'last_scanned_id':int(message.id)}})
            count+=1
        await asyncio.to_thread(self.db.telegram_capture_channels.update_one,{'channel':channel},
            {'$set':{'last_reconciled_at':utcnow(),'capture_error':None}})
        return count

def process_next(backend, active_channels):
    """Use the durable inbox as the queue, never one future per received event."""
    doc=backend.db.telegram_inbox.find_one(
        {'channel':{'$in':list(active_channels)},'state':{'$in':['CAPTURED','RAW_STORED']}},
        sort=[('received_at',ASCENDING)])
    if doc is None:
        return False
    raw_id=backend.ingest(doc['channel'],doc['message_id'],doc['text'],observed_at=doc.get('message_at'))
    backend.db.telegram_inbox.update_one({'_id':doc['_id']},{'$set':{'state':'RAW_STORED','raw_id':raw_id}})
    status=(backend.db.pipeline_status.find_one({'raw_id':raw_id}) or {}).get('status')
    if status=='PENDING':
        backend.process(raw_id)
        status=(backend.db.pipeline_status.find_one({'raw_id':raw_id}) or {}).get('status')
    # Existing FAILED/PUBLISHED/PROCESSING jobs are never replayed.
    backend.db.telegram_inbox.update_one({'_id':doc['_id']},{'$set':{
        'state':'HANDLED','pipeline_status':status,'handled_at':utcnow()}})
    print(f'PIPELINE channel={doc["channel"]} id={doc["message_id"]} status={status}',flush=True)
    return True

def processing_loop(backend, active_channels, stop):
    while not stop.is_set():
        try:
            if not process_next(backend,active_channels):
                stop.wait(1)
        except Exception as exc:
            # Recheck durable state; process() has its own atomic claim and
            # terminal FAILED status, so this cannot rerun failed provider work.
            print(f'PIPELINE_ERROR type={type(exc).__name__}',flush=True)
            stop.wait(3)

async def resolve_channel(client, configured):
    web=TELEGRAM_WEB_CHAT_RE.fullmatch(configured.strip())
    if web:
        target=abs(int(web[1]))
        from telethon import utils
        for dialog in await awaited(client.get_dialogs(limit=None)):
            entity=dialog.entity
            if abs(int(utils.get_peer_id(entity)))==target or int(entity.id)==target:
                return entity
        raise ValueError('Channel is not accessible to the signed-in Telegram account')
    target=normalize_user_channel(configured)
    if target.lstrip('-').isdigit():
        target=int(target)
    return await awaited(client.get_entity(target))

async def monitor(reader, backend, configured, *, capture_only=False, interval=20):
    from telethon import events, utils
    inbox=TelegramInbox(backend.db)
    await asyncio.to_thread(inbox.setup)
    client=reader.client
    registry={}
    available=set()
    stop=threading.Event()
    worker=None
    tasks=[]
    interval=max(5,int(interval))

    async def register(config):
        entity=await resolve_channel(client,config)
        peer=int(utils.get_peer_id(entity))
        stable=f'telegram:{int(entity.id)}'
        if peer not in registry:
            latest=await awaited(client.get_messages(entity,limit=1))
            # First installation starts now, not from old channel history.
            # Later starts resume the previously stored scan cursor.
            await asyncio.to_thread(inbox.seed,stable,int(latest[0].id) if latest else 0)
            registry[peer]=(entity,stable)
            available.add(stable)
        print(f'LISTENING {config} ({stable})',flush=True)

    async def record(event, edited=False):
        item=registry.get(int(event.chat_id or 0))
        if item is None:
            return
        try:
            key=await asyncio.to_thread(inbox.capture,item[1],event.message,edited=edited)
            print(f'CAPTURED channel={item[1]} id={event.message.id} edited={edited}',flush=True)
        except Exception as exc:
            # Original messages remain recoverable via the independent scan.
            print(f'CAPTURE_ERROR channel={item[1]} id={event.message.id} type={type(exc).__name__}',flush=True)
            if edited:
                # Keep this revision alive during a temporary storage outage.
                while True:
                    await asyncio.sleep(3)
                    try:
                        await asyncio.to_thread(inbox.capture,item[1],event.message,edited=True)
                        break
                    except Exception:
                        continue

    async def on_new(event):
        await record(event)

    async def on_edit(event):
        await record(event,edited=True)

    client.add_event_handler(on_new,events.NewMessage())
    client.add_event_handler(on_edit,events.MessageEdited())
    async def channel_loop(config):
        peer=None
        while True:
            try:
                if peer is None:
                    entity=await resolve_channel(client,config)
                    candidate_peer=int(utils.get_peer_id(entity))
                    await register(config)
                    peer=candidate_peer
                entity,stable=registry[peer]
                await inbox.reconcile(client,entity,stable)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f'CHANNEL_ERROR channel={config} type={type(exc).__name__}',flush=True)
                # One inaccessible/flood-limited channel never stops the others.
            await asyncio.sleep(interval)

    try:
        # Resolve/start channels independently; failures are retried below.
        async def initial(config):
            try:
                await register(config)
            except Exception as exc:
                print(f'CHANNEL_ERROR channel={config} type={type(exc).__name__}',flush=True)
        await asyncio.gather(*(initial(config) for config in configured))
        if not capture_only:
            worker=threading.Thread(target=processing_loop,args=(backend,available,stop),
                name='superdeal-pipeline',daemon=True)
            worker.start()
        tasks=[asyncio.create_task(channel_loop(config)) for config in configured]
        print(f'MONITORING configured={len(configured)} active={len(registry)} '
              f'capture_only={capture_only} reconcile_seconds={interval}; raw inbox=telegram_inbox',flush=True)
        await awaited(client.run_until_disconnected())
    finally:
        client.remove_event_handler(on_new)
        client.remove_event_handler(on_edit)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        stop.set()
        if worker:
            # Unprocessed messages stay in MongoDB for the next run.
            await asyncio.to_thread(worker.join,5)
