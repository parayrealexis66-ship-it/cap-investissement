"""One-shot Discord server setup. No user token, deletions or permission edits."""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
import urllib.error
from pathlib import Path

class SetupError(Exception):
    pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

class API:
    def __init__(self, token):
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect())
    def call(self, method, path, data=None):
        if not path.startswith('/') or '://' in path:
            raise SetupError('Chemin API invalide')
        request=urllib.request.Request('https://discord.com/api/v10'+path,
            data=None if data is None else json.dumps(data).encode(), method=method,
            headers={'Authorization':'Bot '+self.token,'Content-Type':'application/json','User-Agent':'CapServerSetup/1.0'})
        for attempt in range(4):
            try:
                with self.opener.open(request,timeout=25) as response:
                    body=response.read()
                    return json.loads(body) if body else None
            except urllib.error.HTTPError as exc:
                if exc.code==429 and attempt<3:
                    try: delay=float(json.loads(exc.read()).get('retry_after',1))
                    except (ValueError,TypeError): delay=1
                    if 0<=delay<=30:
                        time.sleep(max(1,delay));continue
                raise SetupError(f'Discord HTTP {exc.code} : vérifier le jeton, le serveur et les permissions. Aucun secret affiché.') from None
            except (OSError,ValueError):
                # Do not retry uncertain writes: the next run reconciles the actual server.
                raise SetupError('Connexion interrompue : résultat incertain. Relancer pour réconcilier le serveur.') from None

def normalized(value):
    text=''.join(c for c in unicodedata.normalize('NFKD',value.casefold()) if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]','',text)

def match(channels,spec):
    names={normalized(n) for n in [spec['name']]+spec.get('aliases',[])}
    found=[c for c in channels if c['type']==spec['type'] and normalized(c['name']) in names]
    if len(found)>1: raise SetupError('Plusieurs salons correspondent à '+spec['name']+' : aucune sélection arbitraire.')
    return found[0] if found else None

def own_message(api,channel_id,bot_id,marker):
    before=''
    for _ in range(100):
        page=api.call('GET',f'/channels/{channel_id}/messages?limit=100'+before)
        for message in page:
            if message['author']['id']==bot_id and any(e.get('footer',{}).get('text')==marker for e in message.get('embeds',[])):
                return message
        if len(page)<100:return None
        before='&before='+page[-1]['id']
    raise SetupError('Historique trop long : arrêt pour éviter un doublon.')

def setup(api,guild_id,config,apply=False):
    bot=api.call('GET','/users/@me')
    if not bot.get('bot'):raise SetupError('Un compte bot est requis.')
    guild=api.call('GET','/guilds/'+guild_id)
    if normalized(guild['name'])!=normalized(config['server_name']):
        raise SetupError('Le serveur ne correspond pas à CAP Investissement. Vérifier DISCORD_GUILD_ID.')
    channels=api.call('GET',f'/guilds/{guild_id}/channels')
    # Resolve all ambiguities before any mutation.
    for spec in config['channels']:match(channels,spec)
    ids={}; actions=[]
    for spec in config['channels']:
        existing=match(channels,spec)
        data={'name':spec['name']}
        if spec.get('parent'):data['parent_id']=ids[spec['parent']]
        if spec.get('topic') and spec['type']==0:data['topic']=spec['topic']
        if existing:
            cid=existing['id']
            changes={k:v for k,v in data.items() if existing.get(k)!=v}
            if changes:
                actions.append('Mettre à jour : '+spec['name'])
                if apply:api.call('PATCH','/channels/'+cid,changes)
        else:
            actions.append('Créer : '+spec['name'])
            cid='preview-'+spec['key']
            if apply:
                created=api.call('POST',f'/guilds/{guild_id}/channels',{**data,'type':spec['type']})
                cid=created['id'];channels.append(created)
        ids[spec['key']]=cid
        if spec.get('message'):
            marker='CAP SETUP · '+spec['key']
            message=None if cid.startswith('preview-') else own_message(api,cid,bot['id'],marker)
            payload={'embeds':[{'title':spec['title'],'description':spec['message'],'color':0x102C25,'footer':{'text':marker}}],'allowed_mentions':{'parse':[]}}
            if not apply:
                actions.append('Vérifier le message épinglé : '+spec['name']);continue
            if message:
                if message.get('embeds',[{}])[0].get('description')!=spec['message'] or message['embeds'][0].get('title')!=spec['title']:
                    api.call('PATCH',f'/channels/{cid}/messages/{message["id"]}',payload)
            else:
                payload.update(nonce=hashlib.sha256((guild_id+marker).encode()).hexdigest()[:24],enforce_nonce=True)
                message=api.call('POST',f'/channels/{cid}/messages',payload)
            if not message.get('pinned'):
                api.call('PUT',f'/channels/{cid}/messages/pins/{message["id"]}')
            check=api.call('GET',f'/channels/{cid}/messages/{message["id"]}')
            if not check.get('pinned'):raise SetupError('Épinglage non confirmé.')
            actions.append('Message installé et épinglé : '+spec['name'])
    if apply:
        current={c['id']:c for c in api.call('GET',f'/guilds/{guild_id}/channels')}
        for spec in config['channels']:
            actual=current[ids[spec['key']]]
            if actual['name']!=spec['name'] or (spec.get('parent') and actual.get('parent_id')!=ids[spec['parent']]):
                raise SetupError('Organisation finale non confirmée.')
    return actions

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    token=os.environ.get('DISCORD_BOT_TOKEN','').strip();gid=os.environ.get('DISCORD_GUILD_ID','').strip()
    if not token or not re.fullmatch(r'\d{15,22}',gid):raise SetupError('Configurer DISCORD_BOT_TOKEN et DISCORD_GUILD_ID dans les secrets Actions.')
    config=json.loads(Path(__file__).with_name('content.json').read_text())
    actions=setup(API(token),gid,config,args.apply)
    report=('Installation vérifiée' if args.apply else 'Aperçu sans modification')+'\n\n'+'\n'.join('- '+x for x in actions)
    print(report)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write(report+'\n')
if __name__=='__main__':
    try:main()
    except SetupError as exc:print('::error::'+str(exc));sys.exit(1)
