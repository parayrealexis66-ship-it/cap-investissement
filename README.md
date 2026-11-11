# Cap Investissement — actualités Discord

Ce dépôt recherche les nouveaux titres de la BCE et de la Federal Reserve et les publie dans le salon associé au webhook Discord. Il fonctionne sur les serveurs de GitHub, même lorsque l’ordinateur est éteint.

[Ouvrir le suivi des exécutions](https://github.com/parayrealexis66-ship-it/cap-investissement/actions/workflows/discord-rss.yml)

## Activation

Les fichiers et la planification sont installés. Si le secret n’est pas encore enregistré :

1. [Ouvrir la création d’un secret Actions](https://github.com/parayrealexis66-ship-it/cap-investissement/settings/secrets/actions/new).
2. Dans **Name**, saisir exactement `DISCORD_WEBHOOK_URL`.
3. Dans **Secret**, coller l’URL copiée dans les paramètres du webhook Discord, puis cliquer sur **Add secret**.

La prochaine exécution planifiée utilisera ce secret automatiquement. Pour démarrer immédiatement, ouvrir **Actions → Discord RSS → Run workflow** et sélectionner `main`.

L’URL reste dans les secrets GitHub et n’est pas inscrite dans les fichiers, les messages ou les journaux. Le connecteur ChatGPT n’a pas besoin de connaître sa valeur.

Au premier démarrage réussi, un message **« Cap Investissement — flux connecté »** apparaît dans le salon. Si le secret manque, GitHub affiche **« Installation prête — webhook à ajouter »** ; cela ne signifie pas que Discord est déjà connecté.

## Fonctionnement

- Recherche prévue deux fois par heure, aux minutes **15 et 45**.
- Jusqu’à **deux nouvelles actualités par source et par passage**. Le surplus attend le passage suivant.
- Premier passage : les articles de plus de six heures ou sans date sont enregistrés comme historique, sans être envoyés.
- Chaque publication contient la source, le titre, la date UTC lorsqu’elle est disponible et le lien original. Les titres restent dans la langue de la source.
- Un titre n’est enregistré comme envoyé qu’après confirmation de Discord. Les envois confirmés sont conservés même si une autre source ou un envoi ultérieur échoue.
- Aucun résumé automatique, aucune recommandation et aucune lecture des conversations Discord.

## Sources

Les flux se modifient dans `feeds.json` :

- [BCE : page RSS officielle](https://www.ecb.europa.eu/home/html/rss.fr.html) — communiqués, discours, interviews.
- [Federal Reserve : page RSS officielle](https://www.federalreserve.gov/feeds/feeds.htm) — politique monétaire.

Ce premier flux couvre surtout la macroéconomie et les banques centrales. Les actualités d’entreprises pourront être ajoutées par de nouvelles sources RSS.

## Suivi et limites

Le résultat détaillé est visible dans **Actions → une exécution → Summary**. Une source indisponible est signalée ; les autres continuent à publier. Un webhook absent ou invalide est signalé sans en afficher la valeur.

GitHub peut retarder ou omettre une exécution planifiée en période de forte charge. Les workflows planifiés d’un dépôt public peuvent être désactivés après **60 jours sans activité sur le dépôt** ; ils se réactivent dans Actions. Les runners standards sont gratuits pour un dépôt public, selon l’offre GitHub en vigueur.

Le suivi des titres utilise le cache GitHub Actions. Une suppression ou éviction du cache réinitialise ce suivi : le message de connexion et certains titres des six dernières heures peuvent alors être envoyés à nouveau. Une coupure après l’acceptation d’un message mais avant l’enregistrement de sa confirmation peut aussi provoquer un doublon ; l’envoi exactement une fois n’est pas garanti.

## Vérifications techniques

Aucune dépendance Python externe. Python 3.12 est utilisé dans GitHub Actions.

```sh
python -m unittest -v
python rss_to_discord.py --check
```

La seconde commande vérifie réellement les flux RSS sans envoyer de message ni modifier le suivi. Les tests couvrent RSS/Atom, doublons, files d’attente, première lecture de chaque source, échecs partiels et protection de l’URL du webhook.

## Améliorations du suivi

- Dates en heure de Paris, changement été/hiver inclus.
- Maximum 8 actualités par jour, toutes sources confondues, et 2 par source à chaque passage. Les éléments en attente restent éligibles pendant 48 heures.
- Déduplication par URL normalisée (paramètres de suivi ignorés), y compris entre sources. Deux articles différents sur le même événement peuvent encore apparaître.
- Chaque source peut recevoir `include_keywords` et `exclude_keywords` (listes facultatives, recherche dans le titre). Aucune traduction automatique ni interprétation financière générée.
- Suivi sauvegardé dans la branche `bot-state` en plus du cache. Elle contient uniquement des identifiants publics d’articles et les compteurs d’envoi, jamais les portefeuilles membres ou les secrets Discord.
- GitHub Actions a désormais `contents: write` pour cette sauvegarde. Un échec de restauration bloque la publication afin de limiter les doublons.
- Une coupure entre la confirmation Discord et la sauvegarde distante peut encore produire un doublon ; le stockage ne garantit pas une livraison exactement une fois.
- Les alertes privées de panne et les sources d’actualités d’entreprises ne sont pas encore configurées.

## Sources d’actualités actives

Le flux comprend la BCE, la Fed, CNBC (marchés et entreprises, titres en anglais filtrés par mots-clés) et Le Monde Économie (français). Les messages conservent le titre original, la source, la date et le lien ; certains articles peuvent nécessiter un abonnement sur le site éditeur. Aucun texte intégral n’est copié.

Le contrôle deux fois par heure n’implique pas deux publications par heure : seuls les éléments nouveaux et éligibles sont envoyés. Lors de l’ajout d’une source, seuls les articles des six dernières heures sont repris. Les logs indiquent désormais les volumes examinés et les identifiants des messages confirmés par Discord, sans révéler le webhook.
