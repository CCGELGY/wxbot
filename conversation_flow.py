"""Event-driven observation and unfinished-message waiting; never blocks polling."""
import re
import threading
import time

UNFINISHED=re.compile(r'(?:我跟你讲|你知道|等一下|等下|等我|但是|所以说|然后|那个|就是|对了|还有)[，,：:\s]*$')


class Observation:
    def __init__(self, seconds=300):
        self.seconds=seconds;self.states={};self.lock=threading.RLock()

    def replied(self, group, user, now=None):
        now=time.monotonic() if now is None else now
        with self.lock:self.states[group]={'phase':'observing','user':user,'until':now+self.seconds}

    def release(self, group, user=None):
        with self.lock:
            row=self.states.get(group)
            if row and (user is None or row['user']==user):row['phase']='diving'

    def state(self, group, now=None):
        now=time.monotonic() if now is None else now
        with self.lock:
            row=self.states.get(group)
            if not row:return {'phase':'diving','remaining':0}
            if row['until']<=now:row['phase']='diving'
            return {'phase':row['phase'],'remaining':max(0,row['until']-now) if row['phase']=='observing' else 0}


class Inbox:
    def __init__(self, callback, config=None):
        self.callback=callback;self.config=config or {};self.pending={};self.busy=set()
        self.lock=threading.Condition();self.closed=False;self.thread=None

    def start(self):
        self.thread=threading.Thread(target=self._worker,name='chat-waits',daemon=True);self.thread.start()

    def submit(self, group, message, now=None):
        now=time.monotonic() if now is None else now
        user=message.get('sender_username','');key=(group['_username'],user)
        text=message.get('content','')
        with self.lock:
            if self.closed:return
            row=self.pending.get(key)
            unfinished=bool(len(text)<80 and UNFINISHED.search(text))
            if row:
                # Keep sequence and quoted destination; no periodic replay.
                row['messages'].append(dict(message));row['messages']=row['messages'][-12:]
                row['due']=min(row['first']+float(self.config.get('unfinished_max_sec',60)),
                               now+float(self.config.get('continuation_quiet_sec',10))) if row['waiting'] else now+float(self.config.get('burst_quiet_sec',1.2))
                row['waiting']=row['waiting'] or unfinished
            else:
                row={'g':dict(group),'messages':[dict(message)],'first':now,'waiting':unfinished,
                     'due':now+float(self.config.get('unfinished_max_sec',60) if unfinished else self.config.get('initial_coalesce_sec',0.15))}
                if message.get('_await_image') and not unfinished:
                    row['due'] = now + float(self.config.get('image_wait_sec', 1.5))
                self.pending[key]=row
            self.lock.notify_all()

    def take_due(self, now=None):
        now=time.monotonic() if now is None else now
        with self.lock:
            due=[]
            for key,row in list(self.pending.items()):
                if len(self.busy)>=2:break
                if row['due']<=now and key[0] not in self.busy:
                    self.pending.pop(key);self.busy.add(key[0]);due.append((key,row))
            return due

    def _deliver(self, key, row):
        try:
            with self.lock:
                if self.closed:return
            messages=row['messages'];combined=dict(messages[-1])
            combined['content']='\n'.join(m['content'] for m in messages)
            combined['_image_refs'] = [r for m in messages for r in m.get('_image_refs', [])][-8:]
            combined['_image_only'] = all(m.get('_image_only', False) for m in messages)
            # A direct wake in the first fragment still applies to its continuation.
            quotes=[m.get('_quote_target','none') for m in messages]
            combined['_quote_target']='other' if 'other' in quotes else ('self' if 'self' in quotes else 'none')
            combined['_incomplete_timeout']=row['waiting'] and len(messages)==1
            self.callback(row['g'],combined)
        finally:
            with self.lock:self.busy.discard(key[0]);self.lock.notify_all()

    def _worker(self):
        while True:
            with self.lock:
                if self.closed:return
            for key,row in self.take_due():
                threading.Thread(target=self._deliver,args=(key,row),name='chat-group',daemon=True).start()
            with self.lock:self.lock.wait(0.05)

    def stop(self):
        with self.lock:self.closed=True;self.pending.clear();self.lock.notify_all()
        if self.thread:self.thread.join(timeout=1)
