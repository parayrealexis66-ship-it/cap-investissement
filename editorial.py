"""Local editorial rules. Private watchlist is read only from an Actions secret."""
import os
import re
import unicodedata


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))


def watchlist_from_env():
    # One company per line; aliases on the same line separated by |.
    defaults = [('Robinhood', 'Robinhood Markets'), ('Eramet',)]
    settings = '\n'.join(os.environ.get(key, '') for key in ('WATCHLIST', 'WATCHLIST_EXTRA'))
    for line in re.split(r'[\n,;]+', settings):
        aliases = tuple(dict.fromkeys(alias.strip() for alias in line.split('|') if alias.strip()))
        if not aliases:
            continue
        names = {normalized(alias) for alias in aliases}
        overlapping = [group for group in defaults if names.intersection(map(normalized, group))]
        if overlapping:
            aliases = tuple(dict.fromkeys(alias for group in overlapping + [aliases] for alias in group))
            defaults = [group for group in defaults if group not in overlapping]
        defaults.append(aliases)
    return defaults


def contains(text, alias):
    return bool(re.search(r'(?<!\w)'+re.escape(normalized(alias))+r'(?!\w)',text))


def classify(item, watchlist):
    t=normalized(item['title'])
    matches = [names[0] for names in watchlist if names and any(contains(t, name) for name in names)]
    if matches:
        if re.search(r'resultat|earnings|guidance|prevision|benefice|revenue|chiffre d.affaires', t):
            topic, note = 'RÉSULTATS', 'À vérifier : croissance, marges et perspectives annoncées.'
        elif re.search(r'acquis|fusion|merger|rachat|contrat|commande|contract|accord commercial', t):
            topic, note = 'OPÉRATION', 'À vérifier : montant, calendrier et impact potentiel.'
        elif re.search(r'enquete|amende|justice|antitrust|regulat|lawsuit|sanction', t):
            topic, note = 'RÉGLEMENTATION', 'À vérifier : nature de la procédure et conséquences documentées.'
        elif re.search(r'\b(lance|launch|partenariat|partnership|dividende|dividend|dilution|recall|rappel|retard|delay|livraison|shipment|production)\w*', t):
            topic, note = 'ENTREPRISE', 'À vérifier : impact sur les opérations ou les prévisions.'
        else:
            topic = None
        if topic:
            return dict(topic=topic, scope=' / '.join(matches), note=note, priority=1, kind='company')
    rate_context=re.search(r'\b(fed|bce|ecb|fomc)\b|banque centrale|central bank|monetary policy|politique monetaire',t)
    rate_event=re.search(r'taux|rates?|basis points|points de base|monetary policy decision',t)
    if rate_context and rate_event:
        from urllib.parse import urlsplit
        host = urlsplit(item.get('link', '')).hostname or ''
        official = host in {'ecb.europa.eu', 'www.ecb.europa.eu', 'federalreserve.gov', 'www.federalreserve.gov'}
        if official:
            return dict(topic='TAUX · SOURCE OFFICIELLE',scope='MACRO',note='Publication de la banque centrale : vérifier la décision, sa date et son calendrier d’application.',priority=1,kind='macro')
        return dict(topic='TAUX · ANALYSE / ANTICIPATIONS',scope='MACRO',note='Distinguer une décision officielle d’une prévision sur les prochains taux.',priority=1,kind='macro')
    energy = re.search(r'petrole|brent|crude|opec|opep|tanker|petrolier|hydrocarbur|gaz naturel|lng|gnl', t)
    supply = re.search(r'explo[sd]|avarie|incendie|attaque|interruption|rupture|embargo|production|quota|stock|inventor|transport|sanction|detroit|strait', t)
    if energy and supply:
        return dict(topic='ÉNERGIE', scope='MACRO', note='Vérifier si l’événement affecte les flux ou l’offre. Son effet sur le prix reste à établir.', priority=0, kind='macro')
    diplomacy = re.search(r'chine|china|pekin|beijing|russie|russia|moscou|washington|etats-unis|iran', t)
    policy = re.search(r'droits de douane|tariffs?|sanctions?|embargo|accord commercial|trade deal|trade talks|sommet|summit|rencontre|negociation', t)
    if diplomacy and policy:
        return dict(topic='GÉOPOLITIQUE', scope='MACRO', note='Vérifier les décisions annoncées, leur calendrier et les marchés exposés.', priority=0, kind='macro')
    indicator = re.search(r'inflation|\bcpi\b|\bpce\b|\bpib\b|\bgdp\b|payrolls|emploi americain', t)
    actual = re.search(r'ralent|acceler|augmente|recule|rebond|surpris|grimpe|baisse|hausse|inchang|stagn|rises?|falls?|cools?|eases?|report|publication', t)
    if indicator and actual:
        return dict(topic='ÉCONOMIE', scope='MACRO', note='Comparer le chiffre publié aux attentes et à la période précédente.', priority=0, kind='macro')
    market=re.search(r'bours|marche|market|stock|financ|bank|bancair|credit|dette|debt|nasdaq|wall street|\bia\b|\bai\b|technolog',t)
    stress=re.search(r'krach|crash|bulle|bubble|crise|crisis|systemic|systemique|recession|effondr|bank run|defaut souverain',t)
    if market and stress:
        return dict(topic='RISQUE ÉVOQUÉ',scope='MACRO',note='Un risque évoqué dans un article ne signifie pas qu’un krach ou une crise est confirmé.',priority=2,kind='macro')
    return None
