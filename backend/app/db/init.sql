-- Tipos / utilidades
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
    CREATE TYPE user_role AS ENUM ('user', 'admin');
  END IF;
END$$;

-- Usuarios de la app
CREATE TABLE IF NOT EXISTS app_user (
  id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  display_name TEXT,
  role user_role NOT NULL DEFAULT 'user',
  preferred_lang TEXT DEFAULT 'es',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Cuenta Spotify conectada al usuario
CREATE TABLE IF NOT EXISTS spotify_account (
  user_id TEXT PRIMARY KEY REFERENCES app_user(id) ON DELETE CASCADE,
  spotify_user_id TEXT UNIQUE NOT NULL,
  access_token TEXT NOT NULL,
  refresh_token TEXT NOT NULL,
  scope TEXT,
  token_type TEXT,
  expires_at TIMESTAMPTZ NOT NULL
);

-- Eventos de comportamiento (JSONB)
CREATE TABLE IF NOT EXISTS analytics_event (
  id SERIAL PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  type VARCHAR(64) NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_event_user_type ON analytics_event (user_id, type);

-- Recomendaciones calculadas para respuesta rápida
CREATE TABLE IF NOT EXISTS ml_models (
  user_id TEXT PRIMARY KEY REFERENCES app_user(id) ON DELETE CASCADE,
  recommendations JSONB DEFAULT '[]'::jsonb
);

-- (Opcional) Cache de idioma por track
CREATE TABLE IF NOT EXISTS track_language (
  track_id TEXT PRIMARY KEY,
  lang TEXT,
  detected_at TIMESTAMPTZ DEFAULT NOW()
);
