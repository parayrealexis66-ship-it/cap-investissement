from datetime import timedelta
from zoneinfo import ZoneInfo
import hashlib
import re
import os
from editorial import classify, normalized, watchlist_from_env
from carousel import render
from translation import french_items
import rss_to_discord as rss


def execution_summary(available, watchlist, state, status, sent=0, images=0):
    """Report operational status without publishing the private watchlist."""
    path = os.environ.get('GITHUB_STEP_SUMMARY')
    if not path:
        return
    lines = [
        '## Bilan du briefing Discord', '',
        f'- Résultat : {status}',
        f'- Sources chargées : {len(available)}',
        f'- Articles lus : {sum(len(entries) for _, entries in available)}',
        f'- Ciblage entreprises : {"actif" if watchlist else "inactif — secret WATCHLIST manquant ou vide"}',
        f'- Informations confirmées par Discord pendant ce passage : {sent}',
        f'- Images confirmées pendant ce passage : {images}',
        f'- Compteur quotidien : {state.get("daily", {}).get("count", 0)}/{rss.MAX_DAILY_MESSAGES}',
    ]
    if not watchlist:
        lines += ['', 'Ajouter `WATCHLIST` dans Settings → Secrets and variables → Actions pour activer les actualités des entreprises suivies. La liste reste confidentielle.']
    with open(path, 'a', encoding='utf-8') as output:
        output.write('\n'.join(lines) + '\n')


def company_keys(editorial):
    if editorial['kind'] != 'company':
        return set()
    return {hashlib.sha256(normalized(name).encode()).hexdigest()
            for name in editorial['scope'].split(' / ')}


def select(available,state,now,watchlist):
    day=now.astimezone(rss.PARIS).date().isoformat()
    daily=state.setdefault('daily',{'date':day,'count':0})
    if daily['date'] != day:
        daily.clear()
        daily.update(date=day, count=0)
    articles=state.setdefault('articles',{})
    titles=state.setdefault('headline_keys',{})
    candidates=[]
    read_feed_keys = set()
    for feed,entries in available:
        if feed.get('kind') == 'close':
            continue
        feed_key = feed.get('state_key', feed['url'])
        f=state['feeds'].setdefault(feed_key,{'initialized':False,'seen':{}})
        for item in entries:
            published=item['published']
            if item['id'] in f['seen']:continue
            if published is None or published<now-timedelta(hours=24 if not f['initialized'] else rss.MAX_AGE_HOURS):
                f['seen'][item['id']]=now.isoformat();continue
            if published>now:continue
            edit=classify(item,watchlist)
            if not edit or (feed.get('kind') == 'macro' and edit['kind'] != 'macro'):
                continue
            key=rss.canonical_key(item['link'])
            title_key=hashlib.sha256(re.sub(r'\W+','',normalized(item['title'])).encode()).hexdigest()
            if key in articles or title_key in titles:
                f['seen'][item['id']]=now.isoformat();continue
            candidates.append({**item,'editorial':edit,'feed_url':feed_key,'key':key,'title_key':title_key})
        read_feed_keys.add(feed_key)
    for feed_key in read_feed_keys:
        state['feeds'][feed_key]['initialized'] = True
    candidates.sort(key=lambda item: (item['editorial']['priority'], -item['published'].timestamp()))
    selected = []
    seen_links, seen_titles = set(), set()
    companies = set(daily.get('companies', []))
    macro_sent = daily.get('macro', 0)
    capacity = min(3, max(0, rss.MAX_DAILY_MESSAGES - daily['count']))
    # Reserve a slot for macro when a qualifying story is available.
    for kind in ('macro', 'company'):
        for item in candidates:
            if len(selected) >= capacity:
                break
            editorial = item['editorial']
            keys = company_keys(editorial)
            if editorial['kind'] != kind or companies & keys:
                continue
            if item['key'] in seen_links or item['title_key'] in seen_titles:
                continue
            if kind == 'macro' and (macro_sent >= 2 or any(x['editorial']['kind'] == 'macro' for x in selected)):
                break
            if kind == 'company' and macro_sent == 0 and daily['count'] + len(selected) >= rss.MAX_DAILY_MESSAGES - 1:
                break
            selected.append(item)
            seen_links.add(item['key'])
            seen_titles.add(item['title_key'])
            companies.update(keys)
    return sorted(selected, key=lambda item: item['editorial']['kind'] == 'macro')


def safe_text(value, limit):
    return re.sub(r'([\\`*_{}\[\]()<>~|])', r'\\\1', value.replace('\n', ' '))[:limit]


def publish_close(available, state, endpoint, now):
    new_york = ZoneInfo('America/New_York')
    local = now.astimezone(new_york)
    session = local.date().isoformat()
    close = rss.completed_us_close(now)
    if close is None or state.get('last_close') == session:
        return
    reports = []
    for feed, entries in available:
        if feed.get('kind') != 'close':
            continue
        for item in entries:
            if item.get('language', 'fr') != 'fr' or not item['published'] or item['published'] > now:
                continue
            published = item['published'].astimezone(new_york)
            if published.date() != local.date() or published < close:
                continue
            title = normalized(item['title'])
            if not re.search(r"\bwall street\s+(?:a\s+)?(?:clotur\w*|termin\w*|fin(?:it|i|issent))\s+(?:la seance\s+)?(?:en\b|sur\b|dans\b|a l.equilibre)", title):
                continue
            reports.append(item)
    if not reports:
        return
    report = max(reports, key=lambda item: item['published'])
    excerpt = report.get('summary', '')
    if normalized(report['title']) in normalized(excerpt):
        excerpt = ''
    content = f"**Récap de clôture américaine · {local:%d/%m/%Y}**\n{safe_text(report['title'], 240)}"
    if excerpt:
        content += f"\n{safe_text(excerpt, 450)}"
    content += f"\n{safe_text(report['source'], 80)} · [Lire le bilan](<{report['link']}>)"
    if len(content) > 2000:
        return
    rss.discord_post(endpoint, content)
    state['last_close'] = session
    rss.save_state(state)
    print('Récap de clôture confirmé par Discord.')


def publish_briefing(available,state,endpoint,now):
    watchlist=watchlist_from_env()
    if not watchlist:print('::warning::WATCHLIST absent : seules les grandes actualités macro sont sélectionnées.')
    eligible = available
    if not os.environ.get('DEEPL_API_KEY', '').strip().endswith(':fx'):
        eligible = [(feed, french_items(entries)) for feed, entries in available]
    candidates = select(eligible, state, now, watchlist)
    selected = french_items(candidates)
    if len(selected) < len(candidates):
        french = [(feed, [item for item in entries if item.get('language', 'fr') == 'fr'])
                  for feed, entries in available]
        selected = select(french, state, now, watchlist)
    rss.save_state(state)
    if not selected:
        status = 'Plafond quotidien atteint.' if state['daily']['count'] >= rss.MAX_DAILY_MESSAGES else 'Aucune nouvelle information ciblée éligible.'
        print(status)
        execution_summary(available, watchlist, state, status)
        return 0
    content='\n\n'.join(
        f"**{safe_text(x['title'], 240)}**\n"
        f"{x['editorial']['topic']} · {safe_text(x['source'], 80)} · "
        f"<t:{int(x['published'].timestamp())}:t> · [Lire la source](<{x['link']}>)"
        for x in selected)
    try:
        cards=render(selected,now)
        if len(content)>2000:raise rss.PublishError('Liens trop longs pour le briefing ; aucun envoi effectué.')
        result=rss.discord_post(endpoint,content,files=cards)
    except Exception:
        execution_summary(available, watchlist, state, 'Échec du rendu ou de la publication : livraison non confirmée.')
        raise
    # Only receipt-confirmed messages advance the queue and daily counter.
    daily = state['daily']
    daily['count'] += len(selected)
    companies = set(daily.get('companies', []))
    for item in selected:
        companies.update(company_keys(item['editorial']))
    daily['companies'] = sorted(companies)
    daily['macro'] = daily.get('macro', 0) + sum(item['editorial']['kind'] == 'macro' for item in selected)
    for x in selected:
        state['feeds'][x['feed_url']]['seen'][x['id']]=now.isoformat()
        state['articles'][x['key']]=now.isoformat()
        state['headline_keys'][x['title_key']]=now.isoformat()
    state['headline_keys']=dict(sorted(state['headline_keys'].items(),key=lambda kv:kv[1],reverse=True)[:10000])
    rss.save_state(state)
    execution_summary(available, watchlist, state, 'Publication confirmée par Discord.', len(selected), len(cards))
    print(f"Carrousel confirmé par Discord : message {result['id']} · salon {result.get('channel_id')} · {len(cards)} images · {len(selected)} informations.")
    return len(selected)
