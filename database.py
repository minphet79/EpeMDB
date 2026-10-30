import json
import os
import unicodedata
import sqlite3
import psycopg
from psycopg.rows import dict_row
from contextlib import contextmanager

DATABASE_URL = os.environ.get("DATABASE_URL")

@contextmanager
def db():
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def migrate_sqlite_to_postgres():
    sqlite_path = os.path.join(os.path.dirname(__file__), "data", "movies.db")
    if not os.path.exists(sqlite_path):
        return

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM movies")
            if cur.fetchone()['count'] > 0:
                print("La base de datos en la nube ya tiene datos, omitiendo migración.")
                return

    print("Iniciando migración de películas desde el archivo local...")
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()
    sqlite_cur.execute("SELECT * FROM movies")
    rows = sqlite_cur.fetchall()

    with db() as conn:
        with conn.cursor() as cur:
            for row in rows:
                try:
                    cur.execute("""
                        INSERT INTO movies (tmdb_id, title_es, title_original, year, country, continent, director, "cast", synopsis, poster_url)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (tmdb_id) DO NOTHING
                    """, (
                        row['tmdb_id'], row['title_es'], row['title_original'], row['year'],
                        row['country'], row['continent'], row['director'], row['cast'],
                        row['synopsis'], row['poster_url']
                    ))
                except Exception as e:
                    print(f"Error migrando fila {row['id']}: {e}")
    sqlite_conn.close()
    print("¡Migración terminada!")

def init_db():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS movies (
                id SERIAL PRIMARY KEY, tmdb_id INTEGER UNIQUE, title_es TEXT,
                title_original TEXT, year INTEGER, country TEXT, continent TEXT, director TEXT,
                "cast" TEXT DEFAULT '[]', synopsis TEXT, poster_url TEXT)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS failed_movies (
                id SERIAL PRIMARY KEY, title TEXT, year TEXT, error TEXT,
                summary TEXT, directors TEXT, countries TEXT, genres TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS ignored_movies (
                id SERIAL PRIMARY KEY, title TEXT UNIQUE, year TEXT,
                ignored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS import_dudas (
                id SERIAL PRIMARY KEY, titulo TEXT, titulo_original TEXT,
                year TEXT, pais TEXT, continente TEXT, director TEXT, candidatos TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS series (
                id SERIAL PRIMARY KEY, tmdb_id INTEGER UNIQUE, name TEXT,
                name_original TEXT, first_air_date TEXT, country TEXT, 
                category TEXT, creator TEXT, "cast" TEXT DEFAULT '[]', synopsis TEXT, 
                poster_url TEXT, seasons INTEGER DEFAULT 0, episodes INTEGER DEFAULT 0)""")
            cur.execute("ALTER TABLE series ADD COLUMN IF NOT EXISTS creator TEXT")
    migrate_sqlite_to_postgres()

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
        with conn.cursor() as cur:
            query = "SELECT * FROM movies WHERE 1=1"
            params = []
            if continent: query += " AND continent = %s"; params.append(continent)
            if country: query += " AND country = %s"; params.append(country)
            if director: query += " AND director = %s"; params.append(director)

            if q:
                cur.execute(query, params)
                movies = [dict(r) for r in cur.fetchall()]
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
                    query += " ORDER BY LOWER(title_es) ASC"
                elif sort == "title_original":
                    query += " ORDER BY LOWER(title_original) ASC"
                else:
                    query += " ORDER BY id DESC"

                query += f" LIMIT {limit} OFFSET {offset}"
                cur.execute(query, params)
                movies = [dict(r) for r in cur.fetchall()]

    return movies

def count_movies(q="", continent="", country="", director=""):
    with db() as conn:
        with conn.cursor() as cur:
            query = "SELECT * FROM movies WHERE 1=1"
            params = []
            if continent: query += " AND continent = %s"; params.append(continent)
            if country: query += " AND country = %s"; params.append(country)
            if director: query += " AND director = %s"; params.append(director)

            if q:
                cur.execute(query, params)
                rows = cur.fetchall()
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
                if continent: count_query += " AND continent = %s"; count_params.append(continent)
                if country: count_query += " AND country = %s"; count_params.append(country)
                if director: count_query += " AND director = %s"; count_params.append(director)
                cur.execute(count_query, count_params)
                return cur.fetchone()['count']

def get_movie(movie_id):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM movies WHERE id = %s", (movie_id,))
            row = cur.fetchone()
            return dict(row) if row else None

def get_movie_by_tmdb(tmdb_id):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM movies WHERE tmdb_id = %s", (tmdb_id,))
            row = cur.fetchone()
            return dict(row) if row else None

def get_distinct_values(field):
    if field == "continent": return get_continents_list()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT DISTINCT {field} FROM movies WHERE {field} IS NOT NULL AND {field} != '' ORDER BY {field}")
            return [r[field] for r in cur.fetchall()]

def get_countries_by_continent(continent):
    if not continent: return get_distinct_values("country")
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT country FROM movies WHERE continent = %s AND country IS NOT NULL AND country != '' ORDER BY country", (continent,))
            return [r['country'] for r in cur.fetchall()]

def get_movies_without_poster():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM movies WHERE poster_url IS NULL OR poster_url = '' ORDER BY title_es")
            return [dict(r) for r in cur.fetchall()]

def get_uk_related_movies():
    uk_countries = ('Reino Unido', 'United Kingdom', 'UK', 'Inglaterra', 'England', 'Escocia', 'Scotland', 'Gales', 'Wales', 'Irlanda del Norte', 'Northern Ireland')
    placeholders = ','.join(['%s'] * len(uk_countries))
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT id, title_es, title_original, year, country FROM movies WHERE country IN ({placeholders}) ORDER BY year ASC, title_es ASC", uk_countries)
            return [dict(r) for r in cur.fetchall()]

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
        with conn.cursor() as cur:
            cur.execute('SELECT "cast" FROM movies WHERE tmdb_id = %s', (m.get("tmdb_id"),))
            existing = cur.fetchone()
            if existing: m["cast"] = merge_cast(json.loads(existing["cast"]) if existing["cast"] else [], m.get("cast") or [])
            
            cur.execute("""INSERT INTO movies (tmdb_id, title_es, title_original, year, country, continent, director, "cast", synopsis, poster_url)
                VALUES (%(tmdb_id)s, %(title_es)s, %(title_original)s, %(year)s, %(country)s, %(continent)s, %(director)s, %(cast)s, %(synopsis)s, %(poster_url)s)
                ON CONFLICT(tmdb_id) DO UPDATE SET title_es=EXCLUDED.title_es, year=EXCLUDED.year, director=EXCLUDED.director,
                "cast"=EXCLUDED."cast", synopsis=EXCLUDED.synopsis, country=EXCLUDED.country, continent=EXCLUDED.continent,
                poster_url = CASE WHEN EXCLUDED.poster_url IS NOT NULL AND EXCLUDED.poster_url != '' THEN EXCLUDED.poster_url ELSE movies.poster_url END
                RETURNING id""",
                {**m, "cast": json.dumps(m.get("cast") or [])})
            return cur.fetchone()['id']

def delete_movie(movie_id):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM movies WHERE id = %s", (movie_id,))

def update_poster(movie_id, poster_url):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE movies SET poster_url = %s WHERE id = %s", (poster_url, movie_id))

def update_actor_photo(actor_id, actor_name, photo_url):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT id, "cast" FROM movies')
            for r in cur.fetchall():
                try:
                    cast = json.loads(r["cast"]) if r["cast"] else []
                    changed = False
                    for c in cast:
                        if isinstance(c, dict) and ((actor_id and str(c.get("id")) == str(actor_id)) or (not actor_id and c.get("name") == actor_name)):
                            c["profile_path"] = photo_url.strip() if photo_url else None; changed = True
                    if changed:
                        cur.execute('UPDATE movies SET "cast" = %s WHERE id = %s', (json.dumps(cast, ensure_ascii=False), r["id"]))
                except Exception as e: print(f"[Error] {e}")

def remove_actor_photo(actor_id, actor_name):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT id, "cast" FROM movies')
            for r in cur.fetchall():
                try:
                    cast = json.loads(r["cast"]) if r["cast"] else []
                    changed = False
                    for c in cast:
                        if isinstance(c, dict) and ((actor_id and str(c.get("id")) == str(actor_id)) or (not actor_id and c.get("name") == actor_name)):
                            c["profile_path"] = None; changed = True
                    if changed:
                        cur.execute('UPDATE movies SET "cast" = %s WHERE id = %s', (json.dumps(cast, ensure_ascii=False), r["id"]))
                except Exception as e: print(f"[Error] {e}")

def add_failed_movie(title, year, error, summary="", directors="", countries="", genres=""):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO failed_movies (title, year, error, summary, directors, countries, genres) VALUES (%s, %s, %s, %s, %s, %s, %s)", (title, year, error, summary, directors, countries, genres))

def list_failed_movies():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM failed_movies ORDER BY title")
            return [dict(r) for r in cur.fetchall()]

def delete_failed_movie(failed_id):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM failed_movies WHERE id = %s", (failed_id,))

def delete_all_failed_movies():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM failed_movies")

def add_ignored_movie(title, year):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO ignored_movies (title, year) VALUES (%s, %s) ON CONFLICT (title) DO NOTHING", (title, year))

def list_ignored_movies():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM ignored_movies")
            return [dict(r) for r in cur.fetchall()]

def is_movie_ignored(title):
    norm = normalize_title(title)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT title FROM ignored_movies")
            for r in cur.fetchall():
                if normalize_title(r['title']) == norm: return True
    return False

def list_import_dudas():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM import_dudas ORDER BY titulo")
            return [dict(r) for r in cur.fetchall()]

def get_import_duda(duda_id):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM import_dudas WHERE id = %s", (duda_id,))
            row = cur.fetchone()
            return dict(row) if row else None

def delete_import_duda(duda_id):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM import_dudas WHERE id = %s", (duda_id,))

# === FUNCIONES PARA SERIES ===

def list_series(q="", sort="added_desc", category="", country="", continent="", offset=0, limit=20):
    with db() as conn:
        with conn.cursor() as cur:
            query = "SELECT * FROM series WHERE 1=1"
            params = []
            
            if category: 
                query += " AND category = %s"
                params.append(category)
                
            if continent:
                continent_countries = get_countries_by_continent(continent)
                if continent_countries:
                    placeholders = ','.join(['%s'] * len(continent_countries))
                    query += f" AND country IN ({placeholders})"
                    params.extend(continent_countries)
                    
            if country: 
                query += " AND country = %s"
                params.append(country)

            if q:
                cur.execute(query, params)
                series = [dict(r) for r in cur.fetchall()]
                q_norm = normalize_title(q)
                def matches(s):
                    text = f"{s.get('name', '')} {s.get('name_original', '')} {s.get('creator', '')} {s.get('cast', '')}"
                    return q_norm in normalize_title(text)
                series = [s for s in series if matches(s)]
            else:
                if sort == "year_asc":
                    query += " ORDER BY first_air_date ASC, name ASC"
                elif sort == "year_desc":
                    query += " ORDER BY first_air_date DESC, name ASC"
                elif sort == "name":
                    query += " ORDER BY LOWER(COALESCE(name_original, name)) ASC"
                else:
                    query += " ORDER BY id DESC"
                
                query += f" LIMIT {limit} OFFSET {offset}"
                cur.execute(query, params)
                series = [dict(r) for r in cur.fetchall()]

    return series
    
def count_series(q="", category="", country="", continent=""):
    with db() as conn:
        with conn.cursor() as cur:
            query = "SELECT * FROM series WHERE 1=1"
            params = []
            
            if category: 
                query += " AND category = %s"
                params.append(category)
                
            if continent:
                continent_countries = get_countries_by_continent(continent)
                if continent_countries:
                    placeholders = ','.join(['%s'] * len(continent_countries))
                    query += f" AND country IN ({placeholders})"
                    params.extend(continent_countries)
                    
            if country: 
                query += " AND country = %s"
                params.append(country)

            if q:
                cur.execute(query, params)
                rows = cur.fetchall()
                q_norm = normalize_title(q)
                count = 0
                for r in rows:
                    text = f"{r['name'] or ''} {r['name_original'] or ''} {r['creator'] or ''} {r['cast'] or ''}"
                    if q_norm in normalize_title(text):
                        count += 1
                return count
            else:
                count_query = "SELECT COUNT(*) FROM series WHERE 1=1"
                count_params = []
                if category: 
                    count_query += " AND category = %s"
                    count_params.append(category)
                if continent:
                    continent_countries = get_countries_by_continent(continent)
                    if continent_countries:
                        placeholders = ','.join(['%s'] * len(continent_countries))
                        count_query += f" AND country IN ({placeholders})"
                        count_params.extend(continent_countries)
                if country: 
                    count_query += " AND country = %s"
                    count_params.append(country)
                    
                cur.execute(count_query, count_params)
                return cur.fetchone()['count']

def get_series(series_id):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM series WHERE id = %s", (series_id,))
            row = cur.fetchone()
            return dict(row) if row else None

def get_series_by_tmdb(tmdb_id):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM series WHERE tmdb_id = %s", (tmdb_id,))
            row = cur.fetchone()
            return dict(row) if row else None

def get_series_categories():
    return ["Dibujos Animados", "Sagas", "Documentales", "Musicales"]

def get_series_countries():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT country FROM series WHERE country IS NOT NULL AND country != '' ORDER BY country")
            raw_countries = [r['country'] for r in cur.fetchall()]
    
    # Traducir códigos ISO a nombres en español
    from tmdb import get_country_spanish
    translated = []
    for c in raw_countries:
        name = get_country_spanish(c)
        if name:
            translated.append(name)
        elif c not in translated:
            translated.append(c)
    
    return sorted(set(translated))

def get_series_continents():
    countries = get_series_countries()
    continents = set()
    for c in countries:
        cont = get_continent_by_country(c)
        if cont:
            continents.add(cont)
    return sorted(continents)

def get_series_creators():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT creator FROM series WHERE creator IS NOT NULL AND creator != '' ORDER BY creator")
            return [r['creator'] for r in cur.fetchall()]

def insert_series(s):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO series (tmdb_id, name, name_original, first_air_date, country, category, creator, "cast", synopsis, poster_url, seasons, episodes)
                VALUES (%(tmdb_id)s, %(name)s, %(name_original)s, %(first_air_date)s, %(country)s, %(category)s, %(creator)s, %(cast)s, %(synopsis)s, %(poster_url)s, %(seasons)s, %(episodes)s)
                ON CONFLICT(tmdb_id) DO UPDATE SET name=EXCLUDED.name, first_air_date=EXCLUDED.first_air_date, 
                "cast"=EXCLUDED."cast", synopsis=EXCLUDED.synopsis, country=EXCLUDED.country, category=EXCLUDED.category,
                creator=EXCLUDED.creator,
                poster_url = CASE WHEN EXCLUDED.poster_url IS NOT NULL AND EXCLUDED.poster_url != '' THEN EXCLUDED.poster_url ELSE series.poster_url END,
                seasons=EXCLUDED.seasons, episodes=EXCLUDED.episodes
                RETURNING id""",
                {**s, "cast": json.dumps(s.get("cast") or [])})
            return cur.fetchone()['id']

def delete_series(series_id):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM series WHERE id = %s", (series_id,))
        conn.commit()

def update_series_poster(series_id, poster_url):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE series SET poster_url = %s WHERE id = %s", (poster_url, series_id))
        conn.commit()
        
init_db()
