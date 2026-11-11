"""Local editorial rules. Private watchlist is read only from an Actions secret."""
import os
import re
import unicodedata


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))


def watchlist_from_env():
    # One company per line; aliases on the same line separated by |.
    return [tuple(x.strip() for x in line.split('|') if x.strip()) for line in os.environ.get('WATCHLIST', '').splitlines() if line.strip()]


def contains(text, alias):
    return bool(re.search(r'(?<!\w)'+re.escape(normalized(alias))+r'(?!\w)',text))


def classify(item, watchlist):
    t=normalized(item['title'])
    matches=[names[0] for names in watchlist if any(contains(t,name) for name in names)]
    if matches:
        if re.search(r'resultat|earnings|guidance|prevision|benefice|revenue|chiffre d.affaires',t):
            topic='RÉSULTATS'; note='À vérifier dans la publication : croissance, marges et perspectives annoncées.'
        elif re.search(r'acquis|fusion|merger|rachat',t):
            topic='OPÉRATION'; note='À vérifier : montant, financement et calendrier de l’opération.'
        elif re.search(r'enquete|amende|justice|antitrust|regulat|lawsuit',t):
            topic='RÉGLEMENTATION'; note='À vérifier : nature de la procédure et conséquences effectivement documentées.'
        else:
            topic='ENTREPRISE'; note='À vérifier : événement ponctuel ou changement durable pour l’entreprise ?'
        return dict(topic=topic,scope=' / '.join(matches),note=note,priority=0,kind='company')
    rate_context=re.search(r'\b(fed|bce|ecb|fomc)\b|banque centrale|central bank|monetary policy|politique monetaire',t)
    rate_event=re.search(r'taux|rates?|basis points|points de base|monetary policy decision',t)
    if rate_context and rate_event:
        return dict(topic='TAUX DIRECTEURS',scope='MACRO',note='Distinguer une décision officielle d’une prévision sur les prochains taux.',priority=1,kind='macro')
    market=re.search(r'bours|marche|market|stock|financ|bank|bancair|credit|dette|debt|nasdaq|wall street|\bia\b|\bai\b|technolog',t)
    stress=re.search(r'krach|crash|bulle|bubble|crise|crisis|systemic|systemique|recession|effondr|bank run|defaut souverain',t)
    if market and stress:
        return dict(topic='RISQUE ÉVOQUÉ',scope='MACRO',note='Un risque évoqué dans un article ne signifie pas qu’un krach ou une crise est confirmé.',priority=2,kind='macro')
    return None
