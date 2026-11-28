"""Apply Discord member access and process explicit rule confirmations."""
import json
import os
import re
import time
import unicodedata
from urllib.error import HTTPError
from urllib.request import Request, urlopen

GUILD = os.environ["GUILD"]
BASE = "/guilds/" + GUILD
VIEW, SEND, HISTORY = 1 << 10, 1 << 11, 1 << 16
THREADS = (1 << 35) | (1 << 36) | (1 << 38)
DISCUSS = SEND | (1 << 15) | (1 << 38)
RULES = """**Bienvenue sur Cap Investissement**
Ici on échange avec respect. Cite et date tes sources, distingue les faits de ton opinion et masque les noms, numéros de compte et montants privés sur tes captures. Demande l’accord de l’auteur avant de repartager son contenu. Les analyses et les trades partagés servent à comprendre une décision. Chacun reste responsable de ses opérations.
**Accès gratuit** · Échanges, Suggestions, Débuter en bourse et Annonces.
**Espace abonné** · Analyses, actualités, documentation et échanges sur les trades clôturés, gagnants comme perdants.
Pour ouvrir l’espace gratuit, réponds à ce message avec **oui je confirme**, en gardant la mention du bot activée. La validation est traitée périodiquement."""
FREE = {"echanges", "suggestions", "debuterenbourse", "annonces"}
PREMIUM = {"analysesentreprises", "actualitesmarches", "presseetactu", "mesachats", "discussion", "psychologiedelinvestisseur", "vossucces", "vosflops"}
ALIASES = {"exchange":"echanges", "general":"echanges", "analyseentreprise":"analysesentreprises", "presseactu":"presseetactu", "psychologieinvestisseur":"psychologiedelinvestisseur"}

def api(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request("https://discord.com/api/v10" + path, method=method, data=data,
                  headers={"Authorization":"Bot " + os.environ["BOT_TOKEN"], "Content-Type":"application/json", "User-Agent":"DiscordBot (Cap Investissement, 1.0)"})
    for attempt in range(6):
        try:
            with urlopen(req, timeout=30) as response:
                body = response.read()
                return json.loads(body) if body else None
        except HTTPError as exc:
            if exc.code == 429 and attempt < 5:
                time.sleep(float(json.load(exc)["retry_after"]) + 1)
                continue
            raise RuntimeError("Discord HTTP " + str(exc.code)) from None

def key(name):
    return "".join(c for c in unicodedata.normalize("NFKD", name).lower() if c.isascii() and c.isalnum())

def single(items):
    if len(items) != 1:
        raise RuntimeError("Objet Discord manquant ou ambigu")
    return items[0]

def role(name, roles, create):
    matches = [r for r in roles if key(r["name"]) == key(name)]
    if not matches and create:
        matches = [api("POST", BASE + "/roles", {"name":name,"permissions":"0","mentionable":False})]
    found = single(matches)
    if found["managed"] or int(found["permissions"]) != 0:
        raise RuntimeError("Le rôle existant a des privilèges incompatibles")
    return found["id"]

def access(rows, ident, allow=0, deny=0):
    row = rows.setdefault(ident, {"id":ident, "type":0, "allow":"0", "deny":"0"})
    row["allow"] = str((int(row["allow"]) & ~deny) | allow)
    row["deny"] = str((int(row["deny"]) & ~allow) | deny)

def recent(path):
    before = ""
    while True:
        batch = api("GET", path + "?limit=100" + ("&before=" + before if before else ""))
        yield from batch
        if len(batch) < 100:
            return
        before = batch[-1]["id"]

def run():
    setup = os.environ["MODE"] == "setup"
    channels = api("GET", BASE + "/channels")
    roles = api("GET", BASE + "/roles")
    welcome = single([c for c in channels if key(c["name"]) == "commencerici"])
    path = "/channels/" + welcome["id"] + "/messages"
    bot = api("GET", "/users/@me")["id"]
    free = role("Membre confirmé", roles, setup)
    marker = next((m for m in recent(path) if m["author"]["id"] == bot and m["content"] == RULES), None)
    if setup:
        paid = role("Abonné", roles, True)
        base_view = bool(int(single([r for r in roles if r["id"] == GUILD])["permissions"]) & VIEW)
        plans = []
        names = set()
        for c in channels:
            if c["type"] == 4:
                continue
            k = ALIASES.get(key(c["name"]), key(c["name"]))
            original = c["permission_overwrites"]
            rows = {p["id"]:dict(p) for p in original}
            default = rows.get(GUILD, {})
            visible = bool(int(default.get("allow",0)) & VIEW or (base_view and not int(default.get("deny",0)) & VIEW))
            if k not in FREE | PREMIUM | {"commencerici"} and not visible:
                continue
            if k in names and k in FREE | PREMIUM | {"commencerici"}:
                raise RuntimeError("Salons ambigus")
            names.add(k)
            for ident,p in rows.items():
                if ident in (GUILD,free,paid,bot):
                    continue
                if int(p["allow"]) & (VIEW | (SEND | THREADS if k == "presseetactu" else 0)):
                    known = next((r for r in roles if r["id"] == ident), {})
                    if not (known.get("managed") or int(known.get("permissions",0)) & 8):
                        raise RuntimeError("Dérogation existante à vérifier avant la bascule")
            if k == "commencerici":
                access(rows, GUILD, VIEW | SEND | HISTORY)
            else:
                access(rows, GUILD, deny=VIEW)
                if k in FREE:
                    access(rows, free, VIEW | HISTORY | (SEND if k in {"echanges","suggestions"} else 0))
                else:
                    access(rows, free, deny=VIEW)
                access(rows, paid, VIEW | HISTORY | (DISCUSS if k in {"psychologiedelinvestisseur","vossucces","vosflops","echanges","suggestions"} else 0))
                if k == "presseetactu":
                    for ident in (GUILD,free,paid):
                        access(rows, ident, deny=SEND | THREADS)
            if rows != {p["id"]:p for p in original}:
                # Keep the bot's pre-existing channel access after hiding @everyone.
                if k != "commencerici" and visible:
                    rows.setdefault(bot, {"id":bot,"type":1,"allow":"0","deny":"0"})
                    access(rows, bot, VIEW | HISTORY)
                plans.append((c["id"], original, list(rows.values())))
        if not FREE | {"vossucces","vosflops","presseetactu"} <= names:
            raise RuntimeError("Salons attendus manquants, séparation suspendue")
        if not marker:
            marker = api("POST", path, {"content":RULES,"allowed_mentions":{"parse":[]}})
        done = []
        try:
            for ident,original,target in plans:
                channel_path = "/channels/" + ident
                done.append((channel_path,original))
                result = api("PATCH", channel_path, {"permission_overwrites":target})
                if {p["id"]:p for p in result["permission_overwrites"]} != {p["id"]:p for p in target}:
                    raise RuntimeError("Droits retournés différents de la configuration demandée")
        except Exception:
            failures = 0
            for channel_path,original in reversed(done):
                try:
                    api("PATCH",channel_path,{"permission_overwrites":original})
                except Exception:
                    failures += 1
            if failures:
                raise RuntimeError("Retour arrière incomplet") from None
            raise
    if not marker:
        raise RuntimeError("Le règlement doit être installé")
    confirmed = set()
    for msg in recent(path):
        if int(msg["id"]) <= int(marker["id"]):
            break
        if msg["author"].get("bot") or msg.get("type") not in (0,19):
            continue
        answer = re.sub(r"<@!?" + bot + r">", "", msg.get("content","")).strip().casefold()
        if " ".join(answer.split()) == "oui je confirme":
            confirmed.add(msg["author"]["id"])
    for uid in confirmed:
        try:
            member = api("GET", BASE + "/members/" + uid)
        except RuntimeError as exc:
            if str(exc) == "Discord HTTP 404":
                continue
            raise
        if free not in member["roles"]:
            api("PUT", BASE + "/members/" + uid + "/roles/" + free)
    print("Vérification terminée")

if __name__ == "__main__":
    run()
