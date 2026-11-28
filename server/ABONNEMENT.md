# Activation du parcours adhérent

Lancer un seul processus `python server/instant_confirmation.py` avec Python 3.11+ et `discord.py>=2.4,<3`. Le processus doit rester connecté et redémarrer après interruption. Fournir les paramètres via le gestionnaire de secrets de l’hébergeur. La base SQLite doit rester sur un volume privé persistant sauvegardé, hors du dépôt. Elle associe le compte Discord au client Stripe et mémorise les droits déjà gérés par la facturation.

| Variable | Valeur attendue |
|---|---|
| BOT_TOKEN et GUILD | Jeton du bot existant et identifiant du serveur |
| STRIPE_SECRET_KEY | Clé serveur du bon environnement. Accès aux prix, factures et abonnements en lecture, aux clients, aux sessions Checkout et aux sessions de portail en écriture, aux configurations de portail en lecture |
| STRIPE_PRICE_ID | Identifiant du prix récurrent Cap Investissement de 39 EUR par mois |
| STRIPE_PORTAL_CONFIG_ID | Configuration active autorisant la résiliation en fin de période |
| BILLING_CHANNEL_ID | En test, salon privé pour testeurs invités individuellement. En production, identifiant d’Annonces |
| BILLING_DB_PATH | Chemin absolu vers la base sur le volume persistant |

En simulation, créer un rôle sans permissions nommé **Abonné test**, sous le rôle du bot. Le membre testeur doit avoir accepté le règlement. Tester le parcours depuis le bouton avec une carte de test Stripe, vérifier le rôle de test puis la résiliation sur le portail. En production, le rôle géré est **Abonné**. Vérifier le tarif et le portail dans le compte réel avant l’activation.

Le bot publie son annonce au démarrage après vérification du prix, du rôle et du portail. Chaque clic crée ou retrouve une session personnelle. La base associe le client Stripe à l’utilisateur qui a cliqué. Le bot consulte Stripe environ toutes les 30 secondes pendant son fonctionnement. Après un arrêt, la reprise utilise la même base. Une facture payée prolonge l’accès jusqu’à la fin de la période facturée. Le bot retire uniquement le rôle payant qu’il gère, laissant les rôles gratuits en place. Un rôle offert qui était déjà présent à la première synchronisation reste sous gestion manuelle.
