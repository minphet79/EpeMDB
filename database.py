import json
import sqlite3
import os
import unicodedata
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "movies.db")

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tmdb_id INTEGER UNIQUE, title_es TEXT,
            title_original TEXT, year INTEGER, country TEXT, continent TEXT, director TEXT,
            "cast" TEXT DEFAULT '[]', synopsis TEXT, poster_url TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS failed_movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, year TEXT, error TEXT,
            summary TEXT, directors TEXT, countries TEXT, genres TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS ignored_movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT UNIQUE, year TEXT,
            ignored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS import_dudas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT, titulo_original TEXT,
            year TEXT, pais TEXT, continente TEXT, director TEXT, candidatos TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        conn.commit()

def normalize_title(t):
    if not t: return ""
    t = unicodedata.normalize('NFD', str(t))
    t = ''.join(c for c in t if not unicodedata.combining(c))
    t = t.lower().strip().replace("'", "").replace('"', '').replace('.', '').replace(',', '').replace(':', '')
    t = t.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n')
    t = t.replace('ü', 'u').replace('¿', '').replace('?', '').replace('!', '').replace('¡', '').replace('  ', ' ')
    return t

CONTINENTES_VALIDOS = ["América del Norte", "América Central", "América del Sur", "África", "Asia", "Oceanía", "Europa Oriental", "Europa Occidental"]

PAIS_A_CONTINENTE = {
    "Estados Unidos": "América del Norte", "USA": "América del Norte", "United States": "América del Norte",
    "Canadá": "América del Norte", "Canada": "América del Norte", "México": "América del Norte", "Mexico": "América del Norte",
    "Argentina": "América del Sur", "Brasil": "América del Sur", "Brazil": "América del Sur", "Chile": "América del Sur", "Colombia": "América del Sur", "Perú": "América del Sur", "Peru": "América del Sur",
    "España": "Europa Occidental", "Espana": "Europa Occidental", "Spain": "Europa Occidental", "Francia": "Europa Occidental", "France": "Europa Occidental",
    "Italia": "Europa Occidental", "Italy": "Europa Occidental", "Alemania": "Europa Occidental", "Germany": "Europa Occidental",
    "Reino Unido": "Europa Occidental", "United Kingdom": "Europa Occidental", "UK": "Europa Occidental", "Inglaterra": "Europa Occidental", "England": "Europa Occidental",
    "Escocia": "Europa Occidental", "Scotland": "Europa Occidental", "Gales": "Europa Occidental", "Wales": "Europa Occidental", "Irlanda del Norte": "Europa Occidental", "Northern Ireland": "Europa Occidental",
    "Irlanda": "Europa Occidental", "Ireland": "Europa Occidental", "Países Bajos": "Europa Occidental", "Netherlands": "Europa Occidental",
    "Suecia": "Europa Occidental", "Noruega": "Europa Occidental", "Norway": "Europa Occidental", "Dinamarca": "Europa Occidental", "Denmark": "Europa Occidental",
    "Rusia": "Europa Oriental", "Russia": "Europa Oriental", "Polonia": "Europa Oriental", "Poland": "Europa Oriental",
    "China": "Asia", "Japón": "Asia", "Japon": "Asia", "Japan": "Asia", "Corea del Sur": "Asia", "South Korea": "Asia", "India": "Asia",
    "Sudáfrica": "África", "South Africa": "África", "Nigeria": "África", "Egipto": "África", "Egypt": "África",
    "Australia": "Oceanía", "Nueva Zelanda": "Oceanía", "New Zealand": "Oceanía"
}

def get_continent_by_country(country):
    if not country: return None
    return PAIS_A_CONTINENTE.get(country.strip())

def get_continents_list(): return CONTINENTES_VALIDOS

def list_movies(q="", sort="added_desc", continent="", country="", director="", offset=0, limit=20):
    with db() as conn:
        query = "SELECT * FROM movies WHERE 1=1"
        params = []
        if continent: query += " AND continent = ?"; params.append(continent)
        if country: query += " AND country = ?"; params.append(country)
        if director: query += " AND director = ?"; params.append(director)

        if q:
            rows = conn.execute(query, params).fetchall()
            movies = [dict(r) for r in rows]
            q_norm = normalize_title(q)
            def matches(m):
                text = f"{m.get('title_es', '')} {m.get('title_original', '')} {m.get('director', '')} {m.get('cast', '')}"
                return q_norm in normalize_title(text)
            movies = [m for m in movies if matches(m)]
        else:
            if sort == "year_asc":
                query += " ORDER BY year ASC, title_original ASC"
            elif sort == "year_desc":
                query += " ORDER BY year DESC, title_original ASC"
            elif sort == "title_es":
                query += " ORDER BY title_es COLLATE NOCASE ASC"
            elif sort == "title_original":
                query += " ORDER BY title_original COLLATE NOCASE ASC"
            else:
                query += " ORDER BY id DESC"

            query += f" LIMIT {limit} OFFSET {offset}"
            rows = conn.execute(query, params).fetchall()
            movies = [dict(r) for r in rows]

    return movies

def count_movies(q="", continent="", country="", director=""):
    with db() as conn:
        query = "SELECT * FROM movies WHERE 1=1"
        params = []
        if continent: query += " AND continent = ?"; params.append(continent)
        if country: query += " AND country = ?"; params.append(country)
        if director: query += " AND director = ?"; params.append(director)

        if q:
            rows = conn.execute(query, params).fetchall()
            q_norm = normalize_title(q)
            count = 0
            for r in rows:
                text = f"{r['title_es'] or ''} {r['title_original'] or ''} {r['director'] or ''} {r['cast'] or ''}"
                if q_norm in normalize_title(text):
                    count += 1
            return count
        else:
            count_query = "SELECT COUNT(*) FROM movies WHERE 1=1"
            count_params = []
            if continent: count_query += " AND continent = ?"; count_params.append(continent)
            if country: count_query += " AND country = ?"; count_params.append(country)
            if director: count_query += " AND director = ?"; count_params.append(director)
            return conn.execute(count_query, count_params).fetchone()[0]

def get_movie(movie_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM movies WHERE id = ?", (movie_id,)).fetchone()
        return dict(row) if row else None

def get_movie_by_tmdb(tmdb_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM movies WHERE tmdb_id = ?", (tmdb_id,)).fetchone()
        return dict(row) if row else None

def get_distinct_values(field):
    if field == "continent": return get_continents_list()
    with db() as conn:
        rows = conn.execute(f"SELECT DISTINCT {field} FROM movies WHERE {field} IS NOT NULL AND {field} != '' ORDER BY {field}").fetchall()
        return [r[0] for r in rows]

def get_countries_by_continent(continent):
    if not continent: return get_distinct_values("country")
    with db() as conn:
        rows = conn.execute("SELECT DISTINCT country FROM movies WHERE continent = ? AND country IS NOT NULL AND country != '' ORDER BY country", (continent,)).fetchall()
        return [r[0] for r in rows]

def get_movies_without_poster():
    with db() as conn:
        rows = conn.execute("SELECT * FROM movies WHERE poster_url IS NULL OR poster_url = '' ORDER BY title_es").fetchall()
        return [dict(r) for r in rows]

def get_uk_related_movies():
    uk_countries = ('Reino Unido', 'United Kingdom', 'UK', 'Inglaterra', 'England', 'Escocia', 'Scotland', 'Gales', 'Wales', 'Irlanda del Norte', 'Northern Ireland')
    placeholders = ','.join(['?'] * len(uk_countries))
    with db() as conn:
        rows = conn.execute(f"SELECT id, title_es, title_original, year, country FROM movies WHERE country IN ({placeholders}) ORDER BY year ASC, title_es ASC", uk_countries).fetchall()
        return [dict(r) for r in rows]

def merge_cast(old_cast, new_cast):
    if not old_cast: return new_cast or []
    if not new_cast: return old_cast
    seen_ids = set()
    merged = []
    for c in old_cast + new_cast:
        if isinstance(c, dict) and c.get("id") and c["id"] not in seen_ids:
            seen_ids.add(c["id"]); merged.append(c)
        elif isinstance(c, str) and c not in seen_ids:
            seen_ids.add(c); merged.append(c)
    return merged

def insert_movie(m):
    if not m.get("continent") and m.get("country"):
        auto_continent = get_continent_by_country(m["country"])
        if auto_continent: m["continent"] = auto_continent
    with db() as conn:
        existing = conn.execute('SELECT "cast" FROM movies WHERE tmdb_id = ?', (m.get("tmdb_id"),)).fetchone()
        if existing: m["cast"] = merge_cast(json.loads(existing["cast"]) if existing["cast"] else [], m.get("cast") or [])
        cur = conn.execute("""INSERT INTO movies (tmdb_id, title_es, title_original, year, country, continent, director, "cast", synopsis, poster_url)
            VALUES (:tmdb_id, :title_es, :title_original, :year, :country, :continent, :director, :cast, :synopsis, :poster_url)
            ON CONFLICT(tmdb_id) DO UPDATE SET title_es=excluded.title_es, year=excluded.year, director=excluded.director,
            "cast"=excluded."cast", synopsis=excluded.synopsis, country=excluded.country, continent=excluded.continent,
            poster_url = CASE WHEN excluded.poster_url IS NOT NULL AND excluded.poster_url != '' THEN excluded.poster_url ELSE movies.poster_url END""",
            {**m, "cast": json.dumps(m.get("cast") or [])})
        return cur.lastrowid

def delete_movie(movie_id):
    with db() as conn: conn.execute("DELETE FROM movies WHERE id = ?", (movie_id,))

def update_poster(movie_id, poster_url):
    with db() as conn: conn.execute("UPDATE movies SET poster_url = ? WHERE id = ?", (poster_url, movie_id))

def update_actor_photo(actor_id, actor_name, photo_url):
    with db() as conn:
        for r in conn.execute('SELECT id, "cast" FROM movies').fetchall():
            try:
                cast = json.loads(r["cast"]) if r["cast"] else []
                changed = False
                for c in cast:
                    if isinstance(c, dict) and ((actor_id and str(c.get("id")) == str(actor_id)) or (not actor_id and c.get("name") == actor_name)):
                        c["profile_path"] = photo_url.strip() if photo_url else None; changed = True
                if changed: conn.execute('UPDATE movies SET "cast" = ? WHERE id = ?', (json.dumps(cast, ensure_ascii=False), r["id"]))
            except Exception as e: print(f"[Error] {e}")

def remove_actor_photo(actor_id, actor_name):
    with db() as conn:
        for r in conn.execute('SELECT id, "cast" FROM movies').fetchall():
            try:
                cast = json.loads(r["cast"]) if r["cast"] else []
                changed = False
                for c in cast:
                    if isinstance(c, dict) and ((actor_id and str(c.get("id")) == str(actor_id)) or (not actor_id and c.get("name") == actor_name)):
                        c["profile_path"] = None; changed = True
                if changed: conn.execute('UPDATE movies SET "cast" = ? WHERE id = ?', (json.dumps(cast, ensure_ascii=False), r["id"]))
            except Exception as e: print(f"[Error] {e}")

def add_failed_movie(title, year, error, summary="", directors="", countries="", genres=""):
    with db() as conn: conn.execute("INSERT INTO failed_movies (title, year, error, summary, directors, countries, genres) VALUES (?, ?, ?, ?, ?, ?, ?)", (title, year, error, summary, directors, countries, genres))

def list_failed_movies():
    with db() as conn: return [dict(r) for r in conn.execute("SELECT * FROM failed_movies ORDER BY title").fetchall()]

def delete_failed_movie(failed_id):
    with db() as conn: conn.execute("DELETE FROM failed_movies WHERE id = ?", (failed_id,))

def delete_all_failed_movies():
    with db() as conn: conn.execute("DELETE FROM failed_movies")

def add_ignored_movie(title, year):
    with db() as conn: conn.execute("INSERT OR IGNORE INTO ignored_movies (title, year) VALUES (?, ?)", (title, year))

def list_ignored_movies():
    with db() as conn: return [dict(r) for r in conn.execute("SELECT * FROM ignored_movies").fetchall()]

def is_movie_ignored(title):
    norm = normalize_title(title)
    with db() as conn:
        for r in conn.execute("SELECT title FROM ignored_movies").fetchall():
            if normalize_title(r[0]) == norm: return True
    return False

def list_import_dudas():
    with db() as conn: return [dict(r) for r in conn.execute("SELECT * FROM import_dudas ORDER BY titulo").fetchall()]

def get_import_duda(duda_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM import_dudas WHERE id = ?", (duda_id,)).fetchone()
        return dict(row) if row else None

def delete_import_duda(duda_id):
    with db() as conn: conn.execute("DELETE FROM import_dudas WHERE id = ?", (duda_id,))

init_db()
