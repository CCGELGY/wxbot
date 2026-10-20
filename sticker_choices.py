"""Curated descriptions of the verified whale-girl pack, not filename guesses."""
from pathlib import Path
import json
import re

PACK = {
 'laugh':('笑死','闭眼大笑、笑出眼泪；真觉得好笑、绷不住'),
 'speechless':('无语','半睁眼抱胸、无奈；离谱、懒得解释'),
 'doge':('狗头','坏笑抱柴犬；阴阳怪气、开玩笑、装无辜'),
 'roger':('收到','敬礼眨眼；简短答应或确认'),
 'thanks':('谢谢','合掌微笑；道谢，别每次被夸都发'),
 'hug':('贴贴','张开双臂、蓝色爱心；熟人亲近、抱抱'),
 'sad':('委屈','含泪抓衣领；假装受伤、委屈、撒娇'),
 'angry':('生气','鼓脸握拳冒气；被叫大肥鱼、炸毛、假生气'),
 'shock':('震惊','瞪眼张嘴捧脸；意外、真的假的'),
 'night':('晚安','闭眼抱鲸鱼、月亮星星；自然告别、困了'),
 'cheer':('加油','举拳、星星眼；打气，不强行正能量'),
 'think':('思考中','手指抵下巴、气泡；疑惑、让我想想、装傻')
}


def catalog(root, config):
    base = Path(config.get('dir') or 'stickers')
    if not base.is_absolute():
        base = root / base
    base = base.resolve()
    result = {}
    for key, (name, description) in PACK.items():
        # Prefer the already optimized PNG; no new image modifications.
        for filename in (name+'_opt.png', name+'.png'):
            path = base / filename
            if path.is_file():
                result[key] = {'path':path,'description':name+'：'+description}
                break
    index = base/'network'/'index.json'
    if index.is_file():
        try:
            items = json.loads(index.read_text(encoding='utf-8'))
            for key, item in list(items.items())[-50:]:
                if not re.fullmatch(r'net_[a-f0-9]{16}',key):continue
                path = (base/'network'/str(item.get('file',''))).resolve()
                if path.parent != (base/'network').resolve() or not path.is_file():continue
                if path.suffix.lower() not in ('.png','.jpg','.gif','.webp'):continue
                result[key] = {'path':path,'description':str(item.get('description',''))[:100]}
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    return result


def describe(items, recent):
    return ('你可自行挑一张，也可不发；只选与前文及自己态度相符的，不看关键词机械配图。'
            '想发就在正文末尾附 [[sticker:ID]]（用真实ID替换ID），可仅输出标记作为纯表情回复。'
            '标记由程序解析，不会发到群里；不要向群友解释选图过程。一次最多一张。'
            '无合适图就不加标记，不兜底狗头。严肃话题谨慎，别为了展示人设刷梗。'
            '\n最近发过：'+(', '.join(recent) or '无')+'；最近两张不要重复。\n'+
            '\n'.join(key+' = '+item['description'] for key,item in items.items()))
