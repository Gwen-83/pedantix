# Plan d'action — Chat vocal dans les salons

## Objectif

Permettre à l'hôte d'un salon d'activer ou de désactiver le chat vocal, puis permettre aux joueurs présents de rejoindre le salon vocal, de parler et de couper leur micro.

## 1. Cible fonctionnelle

### Cas d'usage

1. L'hôte crée un salon.
2. L'hôte active le chat vocal depuis l'interface du salon.
3. Les joueurs peuvent rejoindre le salon vocal.
4. Les joueurs peuvent :
   - se connecter au micro,
   - parler,
   - couper leur micro,
   - quitter le salon vocal.
5. L'hôte peut désactiver entièrement le chat vocal.
6. Quand le chat vocal est désactivé :
   - les flux audio sont coupés,
   - les participants sont déconnectés du salon vocal,
   - l'UI reflète l'état désactivé.

---

## 2. Architecture proposée

### 2.1. Backend

Le backend garde la logique de salon et de permissions.

À ajouter :

- un état `voice_chat_enabled` par room
- un état `voice_chat_members` (liste des joueurs connectés au salon vocal)
- un flag `voice_chat_host_only` ou une règle de permissions selon le besoin
- une commande pour activer/désactiver le salon vocal
- une commande pour joindre/quitter le salon vocal
- une commande pour changer l'état micro : `mute` / `unmute`

### 2.2. Frontend

Le frontend gère :

- l'UI du bouton “Activé / Désactivé” pour l'hôte
- l'UI “Rejoindre le chat vocal”
- l'UI micro : “Parler / Muet”
- l'affichage de qui est connecté au salon vocal

### 2.3. WebRTC

Le flux audio réel est géré côté navigateur via WebRTC.

Les points clés :

- `getUserMedia()` pour accéder au micro
- `RTCPeerConnection` pour les connexions audio entre participants
- signalisation via WebSocket pour échanger les offres / réponses / ICE candidates
- STUN/TURN pour permettre les connexions derrière NAT / routeurs

---

## 3. Modèle de donnée du salon

Ajouter dans la structure du salon, côté backend :

```python
voice_chat = {
  "enabled": False,
  "members": ["player_id_1", "player_id_2"],
  "muted": {
    "player_id_1": False,
    "player_id_2": True,
  },
  "host_id": "host_player_id",
}
```

### Règles

- seul l'hôte peut activer / désactiver le chat vocal
- tout joueur du salon peut rejoindre ou quitter le salon vocal si `enabled == True`
- un joueur peut toujours couper son propre micro
- lorsqu'un joueur quitte le salon, il est retiré des participants audio

---

## 4. API / événements WebSocket à prévoir

### 4.1. Activation / désactivation

Messages côté serveur :

- `voice_chat_toggle`
- `voice_chat_state`

Exemple :

```json
{
  "type": "voice_chat_toggle",
  "enabled": true
}
```

Réponse :

```json
{
  "type": "voice_chat_state",
  "room_id": "abc123",
  "enabled": true,
  "members": ["p1", "p2"],
  "muted": { "p1": false, "p2": true }
}
```

### 4.2. Rejoindre le salon vocal

```json
{
  "type": "voice_chat_join"
}
```

### 4.3. Quitter le salon vocal

```json
{
  "type": "voice_chat_leave"
}
```

### 4.4. Muet / micro actif

```json
{
  "type": "voice_chat_mute_toggle",
  "muted": true
}
```

---

## 5. Flux de signalisation WebRTC

> **Implémentation actuelle** : la logique WebRTC est centralisée dans
> `static/shared/voice-chat.js` (utilisé par Pédantix, Scribbl, Tarot africain et
> Bataille navale) et l'état du salon vocal dans `app/voice_chat.py`
> (`VoiceChatMixin`). Pour chaque paire de participants, seul le joueur dont
> l'identifiant est le plus petit envoie l'offre : l'autre lui envoie d'abord un
> signal `ready`. Les descriptions SDP sont envoyées complètes (candidats ICE
> inclus), sans échange séparé de candidats. Le serveur n'accepte que les signaux
> `ready` / `offer` / `answer` entre deux membres du salon vocal et impose
> l'expéditeur (`from_player_id`). La Bataille navale relaie les signaux par
> HTTP (`POST /api/battleship/room/voice/signal`, puis `voice_signals` dans
> l'état interrogé).


### 5.1. Quand un joueur rejoint le salon vocal

1. navigateur demande l'accès micro
2. navigateur crée un flux média local
3. navigateur envoie une `offer` via WebSocket au serveur
4. serveur redistribue l'offre aux autres joueurs du salon
5. les autres joueurs répondent avec `answer`
6. ICE candidates sont échangés jusqu'à établissement de la connexion

### 5.2. Quand un joueur quitte

- fermeture de la connexion RTCPeerConnection
- suppression du participant de la liste du salon vocal
- broadcast à tout le monde pour arrêter le flux audio

---

## 6. Règles de permissions

### Hôte

- peut activer / désactiver le chat vocal
- peut voir l'état global du salon vocal
- peut décider de couper le salon vocal pour tout le monde si besoin

### Joueurs

- peuvent rejoindre le salon vocal si activé
- peuvent couper leur micro
- peuvent quitter le salon vocal à tout moment
- ne peuvent pas activer/désactiver le salon vocal pour tout le monde

---

## 7. UI côté frontend

### Boutons à ajouter

- Bouton hôte : “Activer le chat vocal” / “Désactiver le chat vocal”
- Bouton joueur : “Rejoindre le chat vocal” / “Quitter le chat vocal”
- Bouton micro : “Parler” / “Muet”

### États visuels

- `disabled` : salon vocal fermé
- `enabled` : salon vocal ouvert
- `joined` : le joueur est dans le salon vocal
- `muted` : le joueur a le micro coupé

### Exemple de logique UI

```js
if (!room.voiceChat.enabled) {
  showDisabledState();
}

if (room.voiceChat.enabled && userJoinedVoiceChat) {
  showConnectedState();
}

if (userMuted) {
  showMutedLabel();
}
```

---

## 8. Implémentation fonctionnelle par étape

### Étape 1 — Backend

- ajouter `voice_chat_enabled`
- ajouter `voice_chat_members`
- ajouter les handlers WebSocket pour :
  - toggle
  - join
  - leave
  - mute/unmute

### Étape 2 — Frontend UI

- bouton pour l'hôte
- bouton pour le joueur
- bouton micro
- afficher liste des participants audio

### Étape 3 — WebRTC

- initialiser `getUserMedia()`
- créer `RTCPeerConnection`
- gérer offers / answers / ICE candidates
- connecter les participants du salon

### Étape 4 — Tests

- test du toggle par l'hôte
- test du join vocal par un joueur
- test du mute/unmute
- test du leave vocal
- test de fermeture globale du salon vocal

### Étape 5 — Polissage

- gérer erreurs permission micro
- gérer reconnexion
- gérer cas de perte de connexion
- ajouter indikator “micro activé / muet”

---

## 9. Cas limites à anticiper

- l'hôte active le salon vocal alors qu'aucun joueur n'est prêt
- un joueur accepte le navigateur, mais pas de micro
- un joueur se déconnecte pendant une session audio
- un joueur revient après avoir quitté le salon
- plusieurs participants parlent en même temps
- l'hôte désactive le salon alors que des flux sont en cours

---

## 10. Recommandation de mise en œuvre

Pour cette app, je recommande :

1. garder la logique par room déjà existante
2. ajouter le salon vocal sous l’état du salon
3. utiliser WebRTC + WebSocket uniquement
4. laisser l'hôte contrôler le toggle global
5. permettre aux joueurs de self-control avec mute/unmute

C’est le bon équilibre entre simplicité, fiabilité et compatibilité avec le code actuel.

---

## 11. Prochaine étape concrète

La prochaine étape serait de faire la feuille de route côté code :

- ajout du state `voice_chat` dans les rooms backend
- ajout des messages WebSocket de gestion du salon vocal
- création d’un petit module JS `voice-chat.js`
- intégration dans le frontend du salon Tarot / jeux multi-joueurs

Si tu veux, je peux maintenant te préparer un deuxième fichier plus technique, avec un plan de code exact : handlers WebSocket, structure JS, et pseudo-code des fonctions WebRTC.
