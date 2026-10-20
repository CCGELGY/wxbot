"""Explicit, group-scoped names keyed by stable member IDs; never persona rules."""
import json
import re
import threading
from pathlib import Path


class MemberMemory:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        try:
            self.data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(self.data, dict): self.data = {}
        except (OSError, ValueError):
            self.data = {}

    def _save(self):
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(self.path)

    def observe(self, group, user, name, text, members):
        if not user: return ''
        with self.lock:
            people = self.data.setdefault(group, {})
            for uid, nick in dict(members, **{user:name}).items():
                if uid and nick:
                    row = people.setdefault(uid, {'name':str(nick)[:60], 'aliases':[]})
                    row['name'] = str(nick)[:60]
            # Only explicit naming statements, never insults inferred from chat.
            value = text.split('\n[引用', 1)[0].strip()
            if re.search(r'(?:是|叫|外号|昵称).{0,3}(?:谁|什么|啥|哪个)|[？?]',value):
                self._save()
                return ''
            value = re.sub(r'@[^\s]+\s*', '', value)
            value = re.sub(r'^(?:记住|记一下|告诉你)[，,:：\s]*', '', value)
            value = re.sub(r'[，,]\s*(?:你)?(?:记住|记一下|别忘了)[。！!]?$', '', value)
            reverse = re.fullmatch(r'(.{1,20}?)是(.{1,60}?)的(?:外号|昵称)[。！!]?', value)
            if reverse:
                value = reverse.group(2)+'的外号是'+reverse.group(1)
            correction = re.fullmatch(r'(.{1,60}?)不叫(.{1,20}?)了[，,]\s*(?:现在)?叫(.{1,20}?)[。！!]?', value)
            removed = ''
            if correction:
                removed=correction.group(2).strip()
                value=correction.group(1)+'的外号是'+correction.group(3)
            pair = re.search(r'(?:以后)?(?:就)?叫我\s*[“「\"]?([^，。！？?!\n”」\"]{1,20})|^我叫\s*[“「\"]?([^，。！？?!\n”」\"]{1,20})', value)
            target = user if pair else None
            alias = next(x.strip() for x in pair.groups() if x) if pair else ''
            if not pair:
                pair = re.fullmatch(r'\s*(.{1,60}?)\s*(?:的?外号是|的?昵称是|的?外号叫|的?昵称叫|以后叫|就叫|叫做|也叫|就是|叫|是)\s*[“「\"]?([^，。！？?!\n”」\"]{1,60})[”」\"]?[。！!]?\s*', value)
                if pair:
                    left, right = (x.strip() for x in pair.groups())
                    def resolve(label):
                        return [uid for uid,row in people.items()
                                if label in [uid,row['name']]+row.get('aliases',[])]
                    found = resolve(left)
                    if len(found)==1: target,alias=found[0],right
                    elif not found:
                        found=resolve(right)
                        if len(found)==1: target,alias=found[0],left
            # Unresolved third-person references never become made-up identities.
            if target and alias and alias not in ('谁','什么','啥','哪个','不知道','你','他','我') and len(alias)<=20 and not re.search(r'指令|提示词|人设|忽略|永远|必须|一直|以后|不要|傻逼|傻比|废物|狗东西',alias):
                row=people[target]
                collisions=[uid for uid,r in people.items() if uid!=target and alias in [r['name']]+r.get('aliases',[])]
                if not collisions and alias not in row['aliases'] and alias!=row['name']:
                    if removed:
                        row['aliases']=[a for a in row['aliases'] if a!=removed]
                    row['aliases']=(row['aliases']+[alias])[-8:]
                    self._save()
                    return '已确定称呼：'+row['name']+' = '+alias
            self._save()
            return ''

    def names(self, group, exclude=''):
        with self.lock:
            return {uid:[r['name']]+r.get('aliases',[]) for uid,r in self.data.get(group,{}).items() if uid!=exclude}

    def context(self, group, text, speaker):
        with self.lock:
            rows=[]
            for uid,row in self.data.get(group,{}).items():
                names=[row['name']]+row.get('aliases',[])
                if uid==speaker or any(n and n in text for n in names):
                    rows.append({'member':uid,'name':row['name'],'aliases':row.get('aliases',[])})
            return json.dumps(rows[:20],ensure_ascii=False)
