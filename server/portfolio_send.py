"""Publish and pin an approved, dated portfolio snapshot."""
from io import BytesIO
import hashlib
import json
import os
import uuid
import urllib.request

from portfolio_render import render
from setup import API, SetupError, normalized, match, own_message


def publish():
    data = json.loads(os.environ['PORTFOLIO_SNAPSHOT'])
    token = os.environ['DISCORD_BOT_TOKEN']
    guild = os.environ['DISCORD_GUILD_ID']
    api = API(token)
    if normalized(api.call('GET', '/guilds/' + guild)['name']) != 'capinvestissement':
        raise SetupError('Serveur inattendu')
    channel = match(api.call('GET', '/guilds/' + guild + '/channels'),
                    {'type': 0, 'name': 'mon-portefeuille'})
    if not channel or channel['guild_id'] != guild:
        raise SetupError('Salon introuvable')
    buf = BytesIO()
    render(data, buf)
    png = buf.getvalue()
    marker = 'Compte-titres hors liquidités · Relevé du ' + data['date']
    bot = api.call('GET', '/users/@me')
    path = '/channels/' + channel['id'] + '/messages'
    message = own_message(api, channel['id'], bot['id'], (marker,))
    filename = 'Portefeuille.png'
    if not message:
        payload = {'embeds': [{'title': marker, 'description': 'Je partage cette répartition pour montrer comment j’applique ma stratégie. Chaque position reflète mon prix d’entrée, mon horizon et le risque que j’ai accepté. Les poids correspondent au relevé daté ci-dessus. Cet exemple personnel ne constitue pas une invitation à reproduire mes achats.', 'image': {'url': 'attachment://Portefeuille.png'}, 'footer': {'text': marker}}],
                   'allowed_mentions': {'parse': []}, 'nonce': hashlib.sha256(marker.encode()).hexdigest()[:24],
                   'enforce_nonce': True}
        boundary = uuid.uuid4().hex
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="payload_json"\r\n\r\n'.encode()
                + json.dumps(payload).encode()
                + f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="files[0]"; filename="{filename}"\r\nContent-Type: image/png\r\n\r\n'.encode()
                + png + f'\r\n--{boundary}--\r\n'.encode())
        req = urllib.request.Request('https://discord.com/api/v10' + path, data=body,
              headers={'Authorization': 'Bot ' + token, 'User-Agent': 'CapServerSetup/1.0',
                       'Content-Type': 'multipart/form-data; boundary=' + boundary})
        with api.opener.open(req, timeout=30) as res:
            message = json.load(res)
    receipt = api.call('GET', path + '/' + message['id'])
    if not any(a['filename'] == filename and a['size'] == len(png) for a in receipt['attachments']):
        raise SetupError('Pièce jointe non confirmée')
    if not receipt.get('pinned'):
        api.call('PUT', path + '/pins/' + message['id'])
    if not api.call('GET', path + '/' + message['id']).get('pinned'):
        raise SetupError('Épinglage non confirmé')
    print('Graphique et épinglage confirmés.')


if __name__ == '__main__':
    publish()
