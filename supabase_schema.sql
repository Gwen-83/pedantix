-- À exécuter une fois dans Supabase > SQL Editor (l'app le fait aussi via init_db()).
CREATE TABLE IF NOT EXISTS article_cache (
  title TEXT PRIMARY KEY, url TEXT, image TEXT, paragraphs_json TEXT, category TEXT,
  cached_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS games (
  session_id TEXT PRIMARY KEY, seed TEXT, title TEXT, url TEXT, image TEXT, mode TEXT, category TEXT,
  won INTEGER DEFAULT 0, surrendered INTEGER DEFAULT 0, attempts_count INTEGER DEFAULT 0,
  revealed_words INTEGER DEFAULT 0, total_words INTEGER DEFAULT 0, time_seconds INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, finished_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS guesses (
  id BIGSERIAL PRIMARY KEY,
  session_id TEXT REFERENCES games(session_id) ON DELETE CASCADE,
  attempt_num INTEGER, word TEXT, status TEXT, matches_count INTEGER,
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS player_scores (
  player_name TEXT PRIMARY KEY, score INTEGER DEFAULT 0, wins INTEGER DEFAULT 0,
  games_played INTEGER DEFAULT 0, last_played TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_guesses_session ON guesses(session_id);
CREATE INDEX IF NOT EXISTS idx_games_finished ON games(finished_at DESC);
CREATE INDEX IF NOT EXISTS idx_article_category ON article_cache(category);

-- Sécurité : Supabase expose les tables via l'API REST publique (clé anon).
-- Le backend se connecte avec le rôle postgres (qui contourne RLS), donc on
-- active RLS SANS politique : l'API publique ne peut plus rien lire/écrire.
ALTER TABLE article_cache  ENABLE ROW LEVEL SECURITY;
ALTER TABLE games          ENABLE ROW LEVEL SECURITY;
ALTER TABLE guesses        ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_scores  ENABLE ROW LEVEL SECURITY;
