"""Create or locate the dedicated portfolio channel."""
import os
from setup import API, SetupError, match, normalized

def main():
    api = API(os.environ["DISCORD_BOT_TOKEN"])
    guild = os.environ["DISCORD_GUILD_ID"]
    if normalized(api.call("GET", "/guilds/" + guild)["name"]) != "capinvestissement":
        raise SetupError("Serveur inattendu")
    path = "/guilds/" + guild + "/channels"
    channels = api.call("GET", path)
    parent = match(channels, {"type": 4, "name": "INVESTIR ENSEMBLE"})
    if not parent:
        raise SetupError("Catégorie introuvable")
    spec = {"type": 0, "name": "📊・mon-portefeuille"}
    channel = match(channels, spec)
    if not channel:
        channel = api.call("POST", path, dict(spec, parent_id=parent["id"],
            topic="Mon compte-titres en pourcentages, à la date de chaque relevé."))
    receipt = api.call("GET", "/channels/" + channel["id"])
    if receipt["guild_id"] != guild or receipt["parent_id"] != parent["id"]:
        raise SetupError("Emplacement du salon à vérifier")
    print("Salon confirmé", channel["id"])

if __name__ == "__main__":
    main()
