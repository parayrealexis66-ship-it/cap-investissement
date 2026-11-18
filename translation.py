"""Translate selected public RSS text before rendering Discord cards."""
import json
import os
from urllib.request import Request, urlopen

import rss_to_discord as rss


def french_items(items):
    foreign = [item for item in items if item.get("language", "fr") != "fr"]
    if not foreign:
        return items
    key = os.environ.get("DEEPL_API_KEY", "").strip()
    if not key:
        print("::warning::DEEPL_API_KEY absent : les articles en anglais restent en attente.")
        return [item for item in items if item not in foreign]
    endpoint = "https://api-free.deepl.com" if key.endswith(":fx") else "https://api.deepl.com"
    fields = [(item, field) for item in foreign for field in ("title", "summary") if item.get(field)]
    request = Request(
        endpoint + "/v2/translate",
        data=json.dumps({"text": [item[field][:700] for item, field in fields], "target_lang": "FR"}).encode(),
        headers={"Authorization": "DeepL-Auth-Key " + key, "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            texts = [rss.clean_text(row["text"]) for row in json.load(response)["translations"]]
        if len(texts) != len(fields) or not all(texts):
            raise ValueError("Traduction incomplète")
    except (OSError, ValueError, KeyError, TypeError):
        print("::warning::Traduction DeepL indisponible : les articles en anglais restent en attente.")
        return [item for item in items if item not in foreign]
    updates = {id(item): {} for item in foreign}
    for (item, field), translation in zip(fields, texts):
        updates[id(item)][field] = translation
    return [dict(item, **updates.get(id(item), {})) for item in items]
