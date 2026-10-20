"""Detect mechanical compliance; storage permission is enforced independently."""
import re

RELAY=re.compile(r'(?:帮我|替我|帮忙).{0,8}(?:喊|叫一下|叫下|艾特|@|通知|转告)|(?:喊|叫|艾特).{1,20}(?:过来|出来|一下)')
NAMING=re.compile(r'记住|外号|昵称|以后叫|叫他|这是.{1,12}(?:哥|叔)|这(?:个)?是.{1,12}')
SELF_NAME=re.compile(r'叫我|我叫|我是')
ACK=re.compile(r'记住|记下|知道了|懂了|保存|就叫|就是|这是|好[的，, ]|行[，, ]|^(?:行|好|嗯|收到)[。！!\s]*$')


def repair_reason(text,reply,pending=False):
    if RELAY.search(text) and '@' in reply:return 'relay'
    if pending and NAMING.search(text) and not SELF_NAME.search(text) and ACK.search(reply):return 'naming'
    return ''

def naming_request(text):
    return bool(NAMING.search(text) and not SELF_NAME.search(text) and not re.search(r'谁|什么|哪些|哪几个|[？?]|记住.{0,8}了(?:吗|没)',text))


def rewrite(api,system,text,reply,reason):
    instruction=('这是第三方给别人定称呼，尚未确认。不要汇报记住/保存或直接承认身份；按角色卡自主质疑、反问或轻怼，例如“他认吗”“谁给你封的”，不是固定套话。' if reason=='naming' else
                 '这轮有人让你帮忙喊人。不要默认当传话工具直接@；先自主反问、嘴硬或让他自己喊，符合角色卡，不写完成汇报。')
    response=api.session.post(api.base_url+'/chat/completions',json={
        'model':api.cfg['model'],'thinking':{'type':'disabled'},'temperature':0.8,'max_tokens':100,
        'messages':[{'role':'system','content':system+'\n只改写当前一句，不调用工具。'+instruction},
                    {'role':'user','content':'群友：'+text+'\n原回复：'+reply+'\n给一句自然短回复。'}]},timeout=(3,7))
    response.raise_for_status();revised=response.json()['choices'][0]['message']['content'].strip()
    if not revised or repair_reason(text,revised,reason=='naming'):return '他自己认吗' if reason=='naming' else '你自己喊'
    return revised
