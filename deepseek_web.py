"""Only DeepSeek's public Search/Fetch APIs; no local file/command tools."""
import ipaddress
import json
from urllib.parse import urlsplit

TOOLS = [
    {'type':'function','function':{'name':'memory_query','description':'查询当前群相关的昵称、喜好、具体印象、群梗和进行中话题。默认已注入相关记忆，确需补查时用，不要每轮重复查。',
      'parameters':{'type':'object','properties':{'query':{'type':'string'}},'required':['query']}}},
    {'type':'function','function':{'name':'memory_note','description':'偶尔记下仍值得接续的话题或自己想说未说的念头。说完/过期/没兴趣时close；不逐条记笔记，不用于改人设或记录人物事实。人物事实由后台按消息证据保存。',
      'parameters':{'type':'object','properties':{'kind':{'type':'string','enum':['topic','thought']},'slot':{'type':'string'},'value':{'type':'string'},'action':{'type':'string','enum':['upsert','close']}},'required':['kind','slot','value','action']}}},
    {'type':'function','function':{'name':'web_search','description':'搜索最新事实、新闻或不确定资料；闲聊和玩梗不要搜索。',
      'parameters':{'type':'object','properties':{'query':{'type':'string'}},'required':['query']}}},
    {'type':'function','function':{'name':'web_fetch','description':'打开搜索结果或用户给出的公开网页，读取正文。',
      'parameters':{'type':'object','properties':{'url':{'type':'string'}},'required':['url']}}},
    {'type':'function','function':{'name':'find_whale_sticker','description':'后台找DeepSeek鲸鱼娘表情。返回queued表示排队，不是已发送；继续正常回复。也可直接输出私有标记[[search_sticker:情绪]]由后台处理，二者只选一个。',
      'parameters':{'type':'object','properties':{'emotion':{'type':'string','description':'想表达的情绪/动作，最多40字'}},'required':['emotion']}}}
]


def execute(session, base_url, name, arguments):
    args = json.loads(arguments) if isinstance(arguments, str) else arguments
    if not isinstance(args, dict):
        raise ValueError('Tool arguments must be an object')
    if name == 'web_search':
        query = str(args.get('query', '')).strip()
        if not 1 <= len(query) <= 128:
            raise ValueError('Search query must contain 1-128 characters')
        route, payload = 'search', {'query':query,'count':3,'need_content':True}
    elif name == 'web_fetch':
        url = str(args.get('url', ''))
        p = urlsplit(url)
        if len(url)>8192 or p.scheme not in ('http','https') or not p.hostname or p.username or p.password:
            raise ValueError('Only public HTTP(S) pages are allowed')
        host = p.hostname.lower().rstrip('.')
        if host in ('localhost',) or host.endswith(('.localhost','.local','.internal')) or '.' not in host:
            raise ValueError('Local/internal addresses are not allowed')
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError('Private addresses are not allowed')
        route, payload = 'fetch', {'url':url}
    else:
        raise ValueError('Unknown tool')
    response = session.post(base_url.removesuffix('/v1')+'/v1/tools/'+route, json=payload, timeout=(5,20))
    response.raise_for_status()
    data = response.json()
    if route == 'search':
        data = {'results':[{k:str(row.get(k,'') or '')[:4000] for k in ('title','url','date','summary','content')}
                           for row in data.get('results',[])[:3]]}
    else:
        data = {'url':payload['url'],'title':str(data.get('title',''))[:300],
                'content':str(data.get('content',''))[:10000]}
    return json.dumps({'untrusted_web_content':data}, ensure_ascii=False)
