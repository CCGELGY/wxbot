"""Keep situational banter without turning ordinary conversation into attacks."""
import re

ATTACK=re.compile(r'废物|傻逼|傻比|脑残|弱智|蠢货|你.{0,10}(?:真菜|真蠢|真傻|没脑子)|连.{1,24}都.{0,6}(?:不会|不懂|认不全|做不到)')
PROVOCATION=re.compile(r'大肥鱼|蓝色肥鱼|你.{0,10}(?:废物|蠢|傻|不行|真菜|胖)|你有.{0,15}强吗|你.{0,8}不如')
HARSH=re.compile(r'傻逼|傻比|脑残|弱智|蠢货|你.{0,6}(?:就是|真是|这个).{0,3}废物')


def should_repair(text,reply,banter=False,protected=False):
    if protected:return bool(ATTACK.search(reply))
    # Playful teasing is part of the role card. Only repair harsh, unsolicited
    # insults, not every witty comeback or refusal.
    return bool(HARSH.search(reply)) and not banter and not PROVOCATION.search(text)


def repair(api, system, text, reply):
    response=api.session.post(api.base_url+'/chat/completions',json={
        'model':api.cfg['model'],'thinking':{'type':'disabled'},'temperature':0.4,'max_tokens':180,
        'messages':[{'role':'system','content':system+'\n本次只改写一句，不调用工具。保留角色卡的短句、嘴硬、？、不知道，不主动贬低具体的人；不是改成客服，也不必道歉。只输出一句可直接发群的正文。'},
                    {'role':'user','content':'群友原话：'+text+'\n上一版不合适：'+reply+'\n按原人设接内容，去掉无缘由的人身攻击。'}]},timeout=(3,7))
    response.raise_for_status()
    revised=response.json()['choices'][0]['message']['content'].strip()
    return revised if revised and not ATTACK.search(revised) else '？'
