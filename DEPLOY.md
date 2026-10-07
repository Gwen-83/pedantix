# Déployer Pédantix : Supabase + Render + Netlify

Architecture : **Netlify** (front statique) → **Render** (API FastAPI + WebSocket) → **Supabase** (PostgreSQL).

## 1. Supabase (base de données)
1. Créez un projet, région **EU (Frankfurt)**.
2. SQL Editor → collez `supabase_schema.sql` → Run.
3. Project Settings → Database → **Connection string → Session pooler** (port 5432).
   > Ne prenez PAS la « Direct connection » : elle est IPv6 uniquement et Render (gratuit) est IPv4 → « Network is unreachable ».
4. Remplacez `[YOUR-PASSWORD]` dans l'URI. C'est votre `DATABASE_URL`.

## 2. Render (backend)
1. Poussez le dépôt sur GitHub (racine = ce dossier, avec `app/`, `requirements.txt`, `render.yaml`).
2. Render → New → **Blueprint** → choisissez le dépôt.
3. Renseignez les variables demandées :
   - `DATABASE_URL` = URI Supabase (étape 1)
   - `PEDANTIX_ALLOWED_ORIGINS` = `https://VOTRE-SITE.netlify.app`
4. **Un seul worker** (déjà configuré) : les salons vivent en mémoire, plusieurs workers casseraient le multijoueur.
5. Plan gratuit : le service s'endort après ~15 min d'inactivité (premier chargement ≈ 30-60 s). Un ping régulier sur `/health` (UptimeRobot) évite cela.
6. Disque éphémère : `api_synonyms_cache.json` et le SQLite de repli sont perdus à chaque déploiement (sans gravité, Supabase garde les données importantes).

## 3. Netlify (front)
1. New site from Git → même dépôt. Publish directory : `static` (lu depuis `netlify.toml`).
2. Dans `static/js/config.js`, mettez l'URL de l'API Render (`https://pedantix-api.onrender.com`) et l'URL WebSocket (`wss://pedantix-api.onrender.com`).
3. Remettez le nom du site Netlify dans `PEDANTIX_ALLOWED_ORIGINS` côté Render.

## Fichiers de données à committer
`nlp.py` lit `app/data/` : `french_words.txt.gz`, `proper_nouns.txt.gz`, `synonyms.json.gz`, `verb_lemmas.json.gz`, ainsi que `app/curated_articles.json` (repli hors-ligne). Ils ne faisaient pas partie de vos envois : vérifiez qu'ils sont bien dans le dépôt, sinon le dictionnaire de mots sera vide.

## Test local
```bash
pip install -r requirements.txt
python3 main.py            # ajoutez --tunnel pour un lien public
```
