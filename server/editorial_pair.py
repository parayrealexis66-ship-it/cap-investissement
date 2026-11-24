"""Publish the approved journal entry and analysis in their respective channels."""
import hashlib
import json
import os

from setup import API, SetupError, match, normalized, own_message


def publish():
    api = API(os.environ["DISCORD_BOT_TOKEN"])
    guild = os.environ["DISCORD_GUILD_ID"]
    if normalized(api.call("GET", "/guilds/" + guild)["name"]) != "capinvestissement":
        raise SetupError("Serveur inattendu")
    articles = json.loads(os.environ["EDITORIAL_PAIR"])
    if len(articles) != 2 or any(not (0 < len(a["body"]) <= 4096 and 0 < len(a["title"]) <= 256) for a in articles):
        raise SetupError("Format éditorial invalide")
    channels = api.call("GET", "/guilds/" + guild + "/channels")
    targets = [match(channels, {"type": 0, "name": name}) for name in ("mes-achats", "analyses-entreprises")]
    if not all(targets):
        raise SetupError("Salon introuvable")
    bot = api.call("GET", "/users/@me")
    for channel, article in zip(targets, articles):
        marker = hashlib.sha256(article["title"].encode()).hexdigest()[:20]
        path = "/channels/" + channel["id"] + "/messages"
        message = own_message(api, channel["id"], bot["id"], (marker,))
        if not message:
            embed = {"title": article["title"], "description": article["body"], "color": 0x287557, "footer": {"text": marker}}
            message = api.call("POST", path, {"embeds": [embed], "allowed_mentions": {"parse": []}, "nonce": marker, "enforce_nonce": True})
        receipt = api.call("GET", path + "/" + message["id"])
        if receipt["channel_id"] != channel["id"] or receipt["embeds"][0]["description"] != article["body"]:
            raise SetupError("Publication à vérifier")
        print("Article confirmé dans", channel["name"], "message", message["id"])


if __name__ == "__main__":
    publish()
