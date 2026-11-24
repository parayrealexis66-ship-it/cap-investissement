"""Install the investor psychology channel without touching other channels."""
from setup import API, SetupError, match, normalized, own_message
import os

def install(api, guild):
    if normalized(api.call('GET', '/guilds/' + guild)['name']) != 'capinvestissement':
        raise SetupError('Serveur inattendu')
    path = '/guilds/' + guild + '/channels'
    channels = api.call('GET', path)
    parent = match(channels, {'name': 'INVESTIR ENSEMBLE', 'type': 4})
    if not parent:
        raise SetupError('Catégorie introuvable')
    spec = {'name': '🧠・psychologie-de-l-investisseur', 'type': 0}
    channel = match(channels, spec)
    if not channel:
        channel = api.call('POST', path, {**spec, 'parent_id': parent['id'],
            'topic': 'Patience, discipline et retours d’expérience : comment tenir un plan écrit avant que le cours ne bouge ?'})
    actual = api.call('GET', '/channels/' + channel['id'])
    if actual['guild_id'] != guild or actual.get('parent_id') != parent['id']:
        raise SetupError('Emplacement du salon à vérifier')
    article = os.environ.get('ARTICLE_PSYCHOLOGIE', '').strip()
    if article:
        if len(article) > 4000:
            raise SetupError('Article trop long pour la publication')
        marker = 'CAP Investissement · Psychologie · 01'
        channel_path = '/channels/' + actual['id'] + '/messages'
        bot = api.call('GET', '/users/@me')
        message = own_message(api, actual['id'], bot['id'], (marker,))
        payload = {'embeds': [{'title': 'Le plus difficile, c’est de tenir son plan',
                    'description': article, 'color': 0x244D3D, 'footer': {'text': marker}}],
                   'allowed_mentions': {'parse': []}}
        if not message:
            message = api.call('POST', channel_path, payload)
        elif message['embeds'][0].get('description') != article:
            message = api.call('PATCH', channel_path + '/' + message['id'], payload)
        if not message.get('pinned'):
            api.call('PUT', channel_path + '/pins/' + message['id'])
        if not api.call('GET', channel_path + '/' + message['id']).get('pinned'):
            raise SetupError('Épinglage non confirmé')
        print('Article publié et épinglé.')
    print('Salon confirmé : https://discord.com/channels/' + guild + '/' + actual['id'])

if __name__ == '__main__':
    install(API(os.environ['DISCORD_BOT_TOKEN']), os.environ['DISCORD_GUILD_ID'])
