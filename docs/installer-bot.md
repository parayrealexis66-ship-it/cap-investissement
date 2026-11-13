# Activer CAP · Assistant

Le code est prêt. Il ne s’exécute sur Discord qu’après installation du bot, ajout des secrets et lancement manuel du workflow. Aucun jeton de compte personnel.

## 1. Créer le bot

Ouvrir https://discord.com/developers/applications dans votre navigateur habituel connecté à Discord.
Créer une application « CAP Assistant ». Sur sa page Bot, générer/copier le jeton et le conserver uniquement dans un gestionnaire de mots de passe ou le secret GitHub ci-dessous. Ne pas le coller dans un chat, un fichier du dépôt ou une capture.
Ne pas activer les intents privilégiés : cette installation n’en a pas besoin.

## 2. Ajouter le bot au serveur

Dans Installation, choisir Guild Install (installation sur un serveur), scope bot. Sélectionner :
- View Channels (Voir les salons)
- Manage Channels (Gérer les salons)
- Send Messages (Envoyer des messages)
- Embed Links (Intégrer des liens)
- Read Message History (Voir les anciens messages)
- Pin Messages (Épingler des messages)

Ne pas sélectionner Administrator, Manage Roles, Kick Members ou Ban Members. Utiliser le lien d’installation fourni par Discord et sélectionner le serveur CAP Investissement. Valider personnellement les permissions demandées.
Si un salon refuse l’accès au bot, ajuster uniquement l’accès à ce salon. Le script ne change aucune permission existante et ne synchronise pas les permissions des anciens salons avec celles des nouvelles catégories.

## 3. Enregistrer les deux secrets GitHub

https://github.com/parayrealexis66-ship-it/cap-investissement/settings/secrets/actions

Créer :
- DISCORD_BOT_TOKEN : le jeton de la page Bot.
- DISCORD_GUILD_ID : l’identifiant du serveur CAP Investissement. Pour le copier : Discord → Paramètres utilisateur → Avancés → Mode développeur ; clic droit sur le serveur → Copier l’identifiant du serveur.

Le script vérifie que le serveur porte le nom CAP Investissement (majuscules/espaces tolérés).
Conserver DISCORD_WEBHOOK_URL : le flux d’actualités actuel reste indépendant.

## 4. Aperçu puis installation

GitHub → Actions → Installer le serveur Discord → Run workflow sur main.
Premier lancement : laisser apply décoché pour obtenir un aperçu sans modification.
Après lecture du bilan : relancer avec apply coché.

Le script installe 3 catégories, 5 salons textuels et 1 vocal. Il réutilise les salons général, actualités-marchés et Général vocal s’ils existent, conserve leurs identifiants et leurs permissions, et ne supprime rien. Une correspondance ambiguë provoque un arrêt explicite.
Les cinq messages d’introduction sont publiés par le bot, avec un marqueur visible CAP SETUP, puis épinglés. Les relances retrouvent ses propres messages ; elles ne modifient pas les messages d’un membre ou d’un autre bot. Un échec au milieu peut laisser une installation partielle : relancer reprend à partir de l’état présent. Une interruption réseau au moment précis d’une création reste un résultat incertain ; vérifier le bilan avant de relancer.

## Limites de cette version

C’est un installateur ponctuel. Il n’apparaît pas en ligne en permanence et n’accueille pas encore chaque nouvel arrivant. Les commandes interactives, abonnements Stripe et synchronisation des portefeuilles ne sont pas activés. Il ne lit les historiques que pour retrouver ses messages d’installation ; il ne les journalise pas.
Le compte du bot ne doit pas être utilisé pour publier ailleurs des messages ayant les marqueurs CAP SETUP.
Les catégories nouvelles suivent les permissions par défaut du serveur. Aucune donnée financière individuelle n’est publiée.
Le test automatique sur un push vérifie le code et n’utilise pas les secrets Discord.
