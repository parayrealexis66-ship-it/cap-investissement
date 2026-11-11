# Cap Investissement — flux RSS vers Discord

Ce petit projet publie automatiquement les nouveaux titres des flux RSS configurés dans le salon Discord associé à un webhook. Il ne lit pas les messages et ne nécessite ni bot Discord ni clé d’API de marché.

## Flux inclus

- Banque centrale européenne : communiqués, discours et interviews.
- Federal Reserve : annonces de politique monétaire.

Les URL proviennent des pages RSS officielles de la BCE et de la Fed. Tu peux ajouter ou retirer des sources dans `feeds.json`.

## Mise en route

1. Crée un dépôt GitHub **public** et importe le contenu de ce dossier. Le code sera visible publiquement ; n’y ajoute aucune donnée privée.
2. Dans le dépôt, ouvre **Settings → Secrets and variables → Actions → New repository secret**.
3. Nom du secret : `DISCORD_WEBHOOK_URL`. Valeur : l’URL du webhook que tu as créée dans Discord. Ne la mets jamais dans un fichier ni dans un message public.
4. Ouvre l’onglet **Actions**, active les workflows si GitHub le demande, puis lance **Discord RSS → Run workflow** une première fois.
5. Les vérifications suivantes sont planifiées deux fois par heure. GitHub peut décaler les tâches planifiées en période de forte charge.

Au premier lancement, le script publie au maximum les deux titres les plus récents par source, s’ils datent de moins de six heures. Les exécutions suivantes évitent les doublons grâce à un cache GitHub Actions.

## Modifier les sources

Dans `feeds.json`, ajoute un objet avec un nom et une URL RSS :

```json
{"name": "Nom de la source", "url": "https://exemple.org/rss.xml"}
```

Le script publie le titre, le nom de la source, la date lorsqu’elle est fournie et le lien vers l’article. Il ne génère pas de résumé ni de recommandation.

## Dépannage

- Si le workflow échoue avec `DISCORD_WEBHOOK_URL is missing`, vérifie le nom du secret et qu’il est enregistré dans **Actions secrets**.
- Si une source ne répond plus ou change son format, retire-la temporairement de `feeds.json` ou remplace son URL RSS.
- Une exécution manuelle est disponible via **Actions → Discord RSS → Run workflow**.
