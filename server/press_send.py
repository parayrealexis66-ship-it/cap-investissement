"""Deliver the approved press review to the existing press channel."""
from io import BytesIO
import hashlib
import json
import os
import uuid
import urllib.request

from press_render import render
from setup import API, SetupError, normalized, match, own_message


def publish():
    data = json.loads(os.environ['REVUE_PRESSE'])
    token = os.environ['DISCORD_BOT_TOKEN']
    guild = os.environ['DISCORD_GUILD_ID']
    api = API(token)
    if normalized(api.call('GET', '/guilds/' + guild)['name']) != 'capinvestissement':
        raise SetupError('Serveur inattendu')
    channel = match(api.call('GET', '/guilds/' + guild + '/channels'),
                    {'type': 0, 'name': 'presse-et-actu'})
    if not channel or channel['guild_id'] != guild:
        raise SetupError('Salon introuvable')
    buf = BytesIO()
    render(data, buf)
    pdf = buf.getvalue()
    marker = 'Revue de presse du ' + data['date']
    bot = api.call('GET', '/users/@me')
    path = '/channels/' + channel['id'] + '/messages'
    message = own_message(api, channel['id'], bot['id'], (marker,))
    filename = 'Revue-Cap-Investissement.pdf'
    if not message:
        payload = {'embeds': [{'title': marker, 'description': 'La sélection de la semaine et les points à suivre figurent dans le PDF.', 'footer': {'text': marker}}],
                   'allowed_mentions': {'parse': []}, 'nonce': hashlib.sha256(marker.encode()).hexdigest()[:24],
                   'enforce_nonce': True}
        boundary = uuid.uuid4().hex
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="payload_json"\r\n\r\n'.encode()
                + json.dumps(payload).encode()
                + f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="files[0]"; filename="{filename}"\r\nContent-Type: application/pdf\r\n\r\n'.encode()
                + pdf + f'\r\n--{boundary}--\r\n'.encode())
        req = urllib.request.Request('https://discord.com/api/v10' + path, data=body,
              headers={'Authorization': 'Bot ' + token, 'User-Agent': 'CapServerSetup/1.0',
                       'Content-Type': 'multipart/form-data; boundary=' + boundary})
        with api.opener.open(req, timeout=30) as res:
            message = json.load(res)
    receipt = api.call('GET', path + '/' + message['id'])
    if not any(a['filename'] == filename and a['size'] == len(pdf) for a in receipt['attachments']):
        raise SetupError('Pièce jointe non confirmée')
    print('Publication et pièce jointe confirmées.')


if __name__ == '__main__':
    publish()
