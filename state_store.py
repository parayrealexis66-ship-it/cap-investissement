"""Persist public news delivery state on a dedicated GitHub branch; no webhook stored."""
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BRANCH = 'bot-state'
PATH = '.state/seen.json'


def request(path, method='GET', payload=None):
    url = 'https://api.github.com/repos/' + os.environ['GITHUB_REPOSITORY'] + path
    req = urllib.request.Request(url, method=method, data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'], 'Accept':'application/vnd.github+json', 'X-GitHub-Api-Version':'2022-11-28', 'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise RuntimeError(f'GitHub state storage HTTP {exc.code}') from None


def main(mode):
    remote = request('/contents/'+PATH+'?ref='+BRANCH)
    local = Path(PATH)
    if mode == 'restore':
        if remote:
            content = base64.b64decode(remote['content'])
            data = json.loads(content)
            if data.get('version') != 2 or not isinstance(data.get('feeds'),dict):
                raise ValueError('Invalid remote state')
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(content)
            print('État durable restauré depuis bot-state.')
        else:
            print('Premier démarrage du stockage durable ; reprise du cache existant si disponible.')
        return
    if not local.exists():
        return
    content = local.read_bytes()
    if remote and base64.b64decode(remote['content']) == content:
        print('État déjà sauvegardé.'); return
    if request('/git/ref/heads/'+BRANCH) is None:
        base = request('/git/ref/heads/main')
        request('/git/refs', 'POST', {'ref':'refs/heads/'+BRANCH,'sha':base['object']['sha']})
    payload = {'message':'Update public RSS delivery history','branch':BRANCH,'content':base64.b64encode(content).decode()}
    if remote: payload['sha']=remote['sha']
    request('/contents/'+PATH, 'PUT', payload)
    print('État durable sauvegardé dans bot-state.')


if __name__ == '__main__':
    try:
        main(sys.argv[1])
    except Exception:
        print('::error::Impossible de synchroniser le suivi durable GitHub. Publication interrompue ou sauvegarde à reprendre.', file=sys.stderr)
        sys.exit(1)
