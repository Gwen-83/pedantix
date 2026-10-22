# Consignes de développement

Ces consignes s'appliquent à toute intervention de l'IA dans ce dépôt.

## Façon de travailler

- Commencer par examiner la structure du projet, les fichiers concernés, les conventions existantes et l'état Git avant de modifier quoi que ce soit.
- Si la demande est claire, réaliser directement le changement demandé. Poser une question avant de trancher lorsqu'une ambiguïté ou un choix important peut modifier le comportement, l'architecture ou l'expérience utilisateur.
- Faire des changements ciblés et complets. Préserver les modifications déjà présentes dans le dépôt et ne pas toucher aux éléments hors sujet.
- Ne pas créer de commit ni effectuer d'opération destructive sans demande explicite.
- Répondre en français, de façon concise, en résumant le changement et les vérifications effectuées ou restant à faire.

## Code et conception

- Suivre les pratiques professionnelles du langage et des outils utilisés, en particulier pour Python, HTML et JavaScript, tout en détectant et respectant les technologies et conventions réellement présentes dans le projet.
- Privilégier un code simple, lisible, fiable et cohérent avec l'existant. Éviter les abstractions, dépendances et changements d'architecture qui ne sont pas nécessaires.
- Ne pas ajouter de commentaires au code, sauf si une explication est réellement nécessaire pour rendre compréhensible une logique non évidente.
- Préserver les comportements attendus et vérifier les conséquences fonctionnelles, logiques et de sécurité de chaque changement. Ne pas introduire de régression.
- Valider et traiter les entrées aux frontières appropriées, protéger les données et secrets, et ne pas masquer les erreurs avec des valeurs de repli silencieuses.
- Mettre à jour la documentation directement liée lorsque le changement la rend inexacte ou incomplète.

## Vérification

- Repérer les commandes et outils déjà prévus par le projet avant de choisir comment valider le changement.
- Ajouter ou adapter des tests pertinents pour les comportements modifiés, puis exécuter les tests ciblés et les vérifications adaptées (formatage, lint, types ou build) lorsque disponibles.
- Ne pas déclarer une vérification réussie si elle n'a pas été exécutée. Signaler clairement les échecs, les limites et les vérifications impossibles.
