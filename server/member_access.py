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
PREVIOUS_RULES = RULES
RULES = RULES.replace("La validation est traitée périodiquement.", "Le bot vérifie les réponses environ toutes les 15 minutes. Dès que tu vois Échanges, ton accès gratuit est ouvert.").replace("**Espace abonné**", "Dans Mes achats, les captures et la rediffusion sont interdites.\n**Espace abonné**")
OLD_RULES = RULES
RULES = RULES[:RULES.index("Pour ouvrir l’espace gratuit")] + "Pour ouvrir Échanges, ajoute la réaction ✅ à ce règlement ou réponds en mentionnant le bot avec **oui je confirme** ou **j’ai lu et j’accepte**. La vérification a lieu environ toutes les 15 minutes."
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
    marker = next((m for m in recent(path) if m["author"]["id"] == bot and m["content"] in (RULES, OLD_RULES, PREVIOUS_RULES)), None)
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
        elif marker["content"] != RULES:
            api("PATCH", path + "/" + marker["id"], {"content":RULES, "allowed_mentions":{"parse":[]}})
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
        discussion = single([c for c in channels if c["type"] == 2 and key(c["name"]) == "discussion"])
        calls = [c for c in channels if c["type"] == 2 and key(c["name"]) == "calloneone"]
        if calls:
            live_call = single(calls)
            everyone = single([p for p in live_call["permission_overwrites"] if p["id"] == GUILD])
            if live_call["user_limit"] != 2 or int(everyone["deny"]) & (VIEW | (1 << 20)) != (VIEW | (1 << 20)):
                print("Configuration du vocal à examiner")
        success = single([c for c in channels if key(c["name"]) == "vossucces"])
        flop = single([c for c in channels if key(c["name"]) == "vosflops"])
        def siblings(items):
            return sorted((c for c in items if c.get("parent_id") == success["parent_id"] and c["type"] in (0,5,15,16)), key=lambda c:(c["position"],int(c["id"])))
        order = [c["id"] for c in siblings(channels)]
        if flop["parent_id"] != success["parent_id"]:
            raise RuntimeError("Catégories différentes")
        order.remove(flop["id"])
        order.insert(order.index(success["id"]) + 1, flop["id"])
        if order != [c["id"] for c in siblings(channels)]:
            api("PATCH", BASE + "/channels", [{"id":ident,"position":i} for i,ident in enumerate(order)])
        actual = [c["id"] for c in siblings(api("GET",BASE + "/channels"))]
        if actual.index(flop["id"]) != actual.index(success["id"]) + 1:
            raise RuntimeError("Ordre non confirmé")
    if not marker:
        raise RuntimeError("Le règlement doit être installé")
    confirmed = set()
    reaction_path = path + "/" + marker["id"] + "/reactions/%E2%9C%85"
    if setup:
        api("PUT", reaction_path + "/@me")
    after = "0"
    while True:
        users = api("GET", reaction_path + "?limit=100&after=" + after)
        confirmed.update(u["id"] for u in users if not u.get("bot"))
        if len(users) < 100:
            break
        after = users[-1]["id"]
    granted = 0
    unreadable = 0
    for msg in recent(path):
        if int(msg["id"]) <= int(marker["id"]):
            break
        if msg["author"].get("bot") or msg.get("type") not in (0,19):
            continue
        answer = re.sub(r"<@!?" + bot + r">", "", msg.get("content","")).strip().casefold()
        if not answer:
            unreadable += 1
        if key(answer) in {"ouijeconfirme", "jailuetjaccepte"}:
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
            refreshed = api("GET", BASE + "/members/" + uid)
            if free not in refreshed["roles"]:
                raise RuntimeError("Attribution non confirmée")
            granted += 1
    print(f"Confirmations reconnues={len(confirmed)} nouveaux rôles vérifiés={granted} messages sans texte={unreadable}")

if __name__ == "__main__":
    run()
