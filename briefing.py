from datetime import timedelta
import hashlib
import re
from editorial import classify, normalized, watchlist_from_env
from carousel import render
import rss_to_discord as rss


def select(available,state,now,watchlist):
    day=now.astimezone(rss.PARIS).date().isoformat()
    daily=state.setdefault('daily',{'date':day,'count':0})
    if daily['date']!=day:daily.update(date=day,count=0)
    articles=state.setdefault('articles',{})
    titles=state.setdefault('headline_keys',{})
    candidates=[]
    for feed,entries in available:
        f=state['feeds'].setdefault(feed['url'],{'initialized':False,'seen':{}})
        for item in entries:
            published=item['published']
            if item['id'] in f['seen']:continue
            if published is None or published<now-timedelta(hours=24 if not f['initialized'] else rss.MAX_AGE_HOURS):
                f['seen'][item['id']]=now.isoformat();continue
            if published>now:continue
            edit=classify(item,watchlist)
            if not edit:continue
            key=rss.canonical_key(item['link'])
            title_key=hashlib.sha256(re.sub(r'\W+','',normalized(item['title'])).encode()).hexdigest()
            if key in articles or title_key in titles:
                f['seen'][item['id']]=now.isoformat();continue
            candidates.append({**item,'editorial':edit,'feed_url':feed['url'],'key':key,'title_key':title_key})
        f['initialized']=True
    candidates.sort(key=lambda x:(x['editorial']['priority'],-x['published'].timestamp()))
    selected=[];seen_links=set();seen_titles=set();macro=0;scopes=set()
    for item in candidates:
        e=item['editorial']
        if len(selected)>=min(3,max(0,rss.MAX_DAILY_MESSAGES-daily['count'])):break
        if item['key'] in seen_links or item['title_key'] in seen_titles:continue
        if e['kind']=='macro' and macro>=1:continue
        if e['kind']=='company' and e['scope'] in scopes:continue
        selected.append(item);seen_links.add(item['key']);seen_titles.add(item['title_key']);scopes.add(e['scope'])
        macro+=e['kind']=='macro'
    return selected


def publish_briefing(available,state,endpoint,now):
    watchlist=watchlist_from_env()
    if not watchlist:print('::warning::WATCHLIST absent : seules les grandes actualités macro sont sélectionnées.')
    selected=select(available,state,now,watchlist)
    rss.save_state(state)
    if not selected:
        print('Aucune nouvelle information ciblée éligible, ou plafond quotidien atteint.');return 0
    cards=render(selected,now)
    content='**CAP INVESTISSEMENT · Le point à retenir**\nOuvre les images pour parcourir le briefing.\n'
    content+='\n'.join(f"{i}. {x['editorial']['scope']} · Source : <{x['link']}>" for i,x in enumerate(selected,1))
    if len(content)>2000:raise rss.PublishError('Liens trop longs pour le briefing ; aucun envoi effectué.')
    result=rss.discord_post(endpoint,content,files=cards)
    # Only receipt-confirmed messages advance the queue and daily counter.
    state['daily']['count']+=len(selected)
    for x in selected:
        state['feeds'][x['feed_url']]['seen'][x['id']]=now.isoformat()
        state['articles'][x['key']]=now.isoformat()
        state['headline_keys'][x['title_key']]=now.isoformat()
    state['headline_keys']=dict(sorted(state['headline_keys'].items(),key=lambda kv:kv[1],reverse=True)[:10000])
    rss.save_state(state)
    print(f"Carrousel confirmé par Discord : message {result['id']} · salon {result.get('channel_id')} · {len(cards)} images · {len(selected)} informations.")
    return len(selected)
