import json
import os
import re
import unicodedata
import csv
import io
import difflib
from urllib.parse import quote, unquote
from fastapi import FastAPI, Request, Form, Cookie, Depends, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import database as db
import tmdb

app = FastAPI(title="EpeMDB")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

db.init_db()

# === CONFIGURACIÓN DE SEGURIDAD ===
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")

@app.exception_handler(401)
async def unauthorized_handler(request: Request, exc: HTTPException):
    redirect_url = str(request.url)
    return RedirectResponse(url=f"/login?redirect_url={redirect_url}", status_code=303)

async def check_admin(admin_token: str = Cookie(None)):
    if admin_token != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="No autorizado")
    return True

# === FUNCIONES AUXILIARES ===
def normalize_search(text):
    if not text: return ""
    text = unicodedata.normalize('NFD', str(text))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return text.lower().strip()

def _split_directors(dir_field):
    if not dir_field: return []
    separators = [',', '&', ' y ', ' Y ', ' - ', '-', ' and ', ' AND ']
    directors = [dir_field]
    for sep in separators:
        new_directors = []
        for d in directors:
            parts = d.split(sep)
            new_directors.extend([p.strip() for p in parts if p.strip()])
        directors = new_directors
    return directors

def _find_actor_id_by_name(actor_name):
    if not actor_name: return None, None
    name_norm = normalize_search(actor_name)
    try:
        for m in db.list_movies(limit=10000):
            cast_list = json.loads(m["cast"]) if m["cast"] else []
            for c in cast_list:
                if isinstance(c, dict) and c.get("name"):
                    if normalize_search(c["name"]) == name_norm:
                        return c.get("id"), c.get("profile_path")
    except Exception:
        pass
    return None, None

# === RUTAS PÚBLICAS Y DE BÚSQUEDA ===
@app.get("/api/search-live")
async def api_search_live(q: str = ""):
    q_clean = normalize_search(q)
    if len(q_clean) < 1: return JSONResponse([])
    results, seen_ids = [], set()
    
    all_movies = db.list_movies(q=q, limit=10000)
    for m in all_movies:
        if m["id"] in seen_ids: continue
        title_es_norm = normalize_search(m.get("title_es", ""))
        title_orig_norm = normalize_search(m.get("title_original", ""))
        if q_clean in title_es_norm or q_clean in title_orig_norm:
            results.append({"type": "película", "label": f"{m['title_es']} ({m['year'] or '?'})", "sub": f"Título: {m.get('title_original') or '-'}", "url": f"/movie/{m['id']}", "icon": "🎬"})
            seen_ids.add(m["id"])
            
    director_stats = {}
    for m in all_movies:
        for dir_name in _split_directors(m.get("director", "")):
            if q_clean in normalize_search(dir_name):
                director_stats.setdefault(normalize_search(dir_name), {"name": dir_name, "count": 0})["count"] += 1
    for d in sorted(director_stats.values(), key=lambda x: -x["count"])[:3]:
        results.append({"type": "director", "label": d["name"], "sub": f"{d['count']} película{'s' if d['count'] != 1 else ''}", "url": f"/director?name={quote(d['name'])}", "icon": "🎥"})
    
    actor_stats = {}
    for m in all_movies:
        cast_list = json.loads(m["cast"]) if m["cast"] else []
        for c in cast_list:
            if isinstance(c, dict):
                actor_name = c.get("name", "")
                actor_id = c.get("id", 0)
                if q_clean in normalize_search(actor_name):
                    key = normalize_search(actor_name)
                    if key not in actor_stats:
                        actor_stats[key] = {"name": actor_name, "count": 0, "actor_id": actor_id}
                    actor_stats[key]["count"] += 1
    for a in sorted(actor_stats.values(), key=lambda x: -x["count"])[:3]:
        results.append({"type": "actor", "label": a["name"], "sub": f"{a['count']} película{'s' if a['count'] != 1 else ''}", "url": f"/actor/{a['actor_id']}", "icon": "🎬"})

    all_series = db.list_series(q=q, limit=10000)
    for s in all_series:
        if s["id"] in seen_ids: continue
        name_norm = normalize_search(s.get("name", ""))
        name_orig_norm = normalize_search(s.get("name_original", ""))
        if q_clean in name_norm or q_clean in name_orig_norm:
            year = s.get("first_air_date", "")[:4] if s.get("first_air_date") else "?"
            results.append({"type": "serie", "label": f"{s['name']} ({year})", "sub": f"Temporadas: {s.get('seasons', '?')} | {s.get('country', '?')}", "url": f"/serie/{s['id']}", "icon": "📺"})
            seen_ids.add(s["id"])
            continue
        cast_list = json.loads(s["cast"]) if s["cast"] else []
        for c in cast_list:
            if isinstance(c, dict):
                actor_name = c.get("name", "")
                if q_clean in normalize_search(actor_name):
                    year = s.get("first_air_date", "")[:4] if s.get("first_air_date") else "?"
                    results.append({"type": "serie", "label": f"{s['name']} ({year})", "sub": f"Actúa: {actor_name}", "url": f"/serie/{s['id']}", "icon": "📺"})
                    seen_ids.add(s["id"])
                    break
    return JSONResponse(results[:15])

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, q: str = "", sort: str = "", continent: str = "", country: str = "", director: str = "", tag: str = "", page: int = 1, per_page: int = 24):
    # REGLA ESTRICTA: Si hay algún filtro activo, ordenar de más antiguo a más reciente
    if continent or country or director or tag:
        sort = "year_asc"
    elif not sort:
        sort = "name" # Orden por defecto si no hay filtros
        
    offset = (page - 1) * per_page
    movies = db.list_movies(q, sort, continent, country, director, tag, offset=offset, limit=per_page)
    
    # Parsear las etiquetas para el template
    for m in movies:
        if m.get("tags"):
            try:
                m["tags"] = json.loads(m["tags"]) if isinstance(m["tags"], str) else m["tags"]
            except Exception:
                m["tags"] = []
        else:
            m["tags"] = []
            
    total = db.count_movies(q, continent, country, director, tag)
    total_pages = (total + per_page - 1) // per_page
    return templates.TemplateResponse("index.html", {
        "request": request, "movies": movies, "q": q, "sort": sort, "continent": continent, "country": country, "director": director, "tag": tag,
        "continents": db.get_continents_list(), "countries": db.get_countries_by_continent(continent),
        "all_countries": db.get_distinct_values("country"), "directors": db.get_distinct_values("director"),
        "no_poster_count": len(db.get_movies_without_poster()), "pending_count": len(db.list_failed_movies()),
        "page": page, "total_pages": total_pages, "total_movies": total, "per_page": per_page
    })
    
@app.get("/add", response_class=HTMLResponse)
async def add_form(request: Request):
    return templates.TemplateResponse("add.html", {"request": request})

@app.post("/search", response_class=HTMLResponse)
async def search_tmdb(request: Request, type: str = Form("movie"), query: str = Form(...), year: str = Form(""), admin: bool = Depends(check_admin)):
    if type == "tv":
        results = await tmdb.search_series(query, int(year) if year.isdigit() else None)
    else:
        results = await tmdb.search_movies(query, int(year) if year.isdigit() else None)
    return templates.TemplateResponse("add.html", {"request": request, "results": results, "query": query, "year": year, "type": type})

@app.get("/import/{tmdb_id}", response_class=HTMLResponse)
async def import_item(request: Request, tmdb_id: int, type: str = "movie", admin: bool = Depends(check_admin)):
    if type == "tv":
        item_id = db.insert_series(await tmdb.get_series_details(tmdb_id))
        return RedirectResponse(f"/serie/{item_id}", status_code=303)
    else:
        item_id = db.insert_movie(await tmdb.get_movie_details(tmdb_id))
        return RedirectResponse(f"/movie/{item_id}", status_code=303)

@app.get("/movie/{movie_id}", response_class=HTMLResponse)
async def movie_detail(request: Request, movie_id: int):
    m = db.get_movie(movie_id)
    if not m: return HTMLResponse("No encontrada", status_code=404)
    m["cast"] = json.loads(m["cast"]) if m["cast"] else []
    return templates.TemplateResponse("movie.html", {"request": request, "movie": m})

@app.post("/delete/{movie_id}")
async def delete(movie_id: int, admin: bool = Depends(check_admin)):
    db.delete_movie(movie_id)
    return RedirectResponse("/", status_code=303)

@app.post("/edit-title/{movie_id}")
async def edit_title(movie_id: int, title_es: str = Form(...), title_original: str = Form(""), admin: bool = Depends(check_admin)):
    with db.db() as conn: 
        conn.execute("UPDATE movies SET title_es = ?, title_original = ? WHERE id = ?", (title_es.strip(), title_original.strip() or None, movie_id))
    return RedirectResponse(f"/movie/{movie_id}", status_code=303)

@app.post("/set-poster/{movie_id}")
async def set_poster(movie_id: int, poster_url: str = Form(...), admin: bool = Depends(check_admin)):
    db.update_poster(movie_id, poster_url)
    import html as html_module
    m = db.get_movie(movie_id)
    url = (m.get("poster_url") if m else None) or poster_url
    return HTMLResponse(f'<img id="poster-img" src="{html_module.escape(url)}" class="w-full aspect-[2/3] object-cover rounded shadow-lg">')

@app.get("/director", response_class=HTMLResponse)
async def director_page(request: Request, name: str = ""):
    if not name: return HTMLResponse("<h1>Director no especificado</h1>", status_code=400)
    director_name = unquote(name)
    directors_list = _split_directors(director_name)
    director_norms = [normalize_search(d) for d in directors_list]
    director_movies = [m for m in db.list_movies(limit=10000) if m.get("director") and all(dn in normalize_search(m["director"]) for dn in director_norms)]
    return templates.TemplateResponse("director.html", {"request": request, "director": director_name, "movies": director_movies})

@app.get("/failed", response_class=HTMLResponse)
async def failed_movies(request: Request):
    failed = db.list_failed_movies()
    return templates.TemplateResponse("failed.html", {"request": request, "failed": failed})

@app.post("/delete-failed/{failed_id}")
async def delete_failed(failed_id: int, admin: bool = Depends(check_admin)):
    f = next((x for x in db.list_failed_movies() if x["id"] == failed_id), None)
    if f: db.add_ignored_movie(f["title"], f.get("year")); db.delete_failed_movie(failed_id)
    return RedirectResponse("/failed", status_code=303)

@app.post("/delete-all-failed")
async def delete_all_failed(admin: bool = Depends(check_admin)):
    for f in db.list_failed_movies(): db.add_ignored_movie(f["title"], f.get("year"))
    db.delete_all_failed_movies()
    return RedirectResponse("/failed", status_code=303)

@app.get("/no-poster", response_class=HTMLResponse)
async def no_poster(request: Request):
    movies = db.get_movies_without_poster()
    return templates.TemplateResponse("no_poster.html", {"request": request, "movies": movies})

@app.post("/update-poster/{movie_id}")
async def update_poster(request: Request, movie_id: int, poster_url: str = Form(...), admin: bool = Depends(check_admin)):
    db.update_poster(movie_id, poster_url)
    return RedirectResponse("/no-poster", status_code=303)

@app.get("/import-dudas", response_class=HTMLResponse)
async def import_dudas_view(request: Request, admin: bool = Depends(check_admin)):
    dudas = db.list_import_dudas()
    for d in dudas: d["candidatos"] = json.loads(d["candidatos"]) if d["candidatos"] else []
    return templates.TemplateResponse("import_dudas.html", {"request": request, "dudas": dudas})

@app.get("/edit-movie/{movie_id}", response_class=HTMLResponse)
async def edit_movie_page(request: Request, movie_id: int, admin: bool = Depends(check_admin)):
    m = db.get_movie(movie_id)
    if not m: return HTMLResponse("No encontrada", status_code=404)
    cast_list = [c.get("name", "") if isinstance(c, dict) else c for c in (json.loads(m.get("cast") or "[]") or [])]
    return templates.TemplateResponse("edit_movie.html", {"request": request, "movie": m, "cast_text": "\n".join(cast_list)})

@app.get("/reidentify-movie/{movie_id}", response_class=HTMLResponse)
async def reidentify_movie_form(request: Request, movie_id: int, admin: bool = Depends(check_admin)):
    try:
        print(f"🔍 DEBUG: Intentando obtener película con ID {movie_id}")
        m = db.get_movie(movie_id)
        print(f"🔍 DEBUG: Película obtenida: {m}")
        if not m: 
            return HTMLResponse("Película no encontrada", status_code=404)
        return templates.TemplateResponse("reidentify_movie.html", {
            "request": request, "movie": m, "results": None, "query": ""
        })
    except Exception as e:
        print(f"🚨 ERROR CRÍTICO en reidentify_movie_form: {e}")
        return HTMLResponse(f"<h1>Error interno</h1><p>{str(e)}</p>", status_code=500)

@app.post("/reidentify-movie/{movie_id}", response_class=HTMLResponse)
async def reidentify_movie_search(request: Request, movie_id: int, query: str = Form(...), year: str = Form(""), admin: bool = Depends(check_admin)):
    m = db.get_movie(movie_id)
    if not m: return HTMLResponse("Película no encontrada", status_code=404)
    results = await tmdb.search_movies(query, int(year) if year.isdigit() else None)
    return templates.TemplateResponse("reidentify_movie.html", {
        "request": request, "movie": m, "results": results, "query": query
    })

@app.get("/confirm-reidentify/{movie_id}/{new_tmdb_id}", response_class=HTMLResponse)
async def confirm_reidentify_movie(request: Request, movie_id: int, new_tmdb_id: int, admin: bool = Depends(check_admin)):
    m = db.get_movie(movie_id)
    if not m: return HTMLResponse("Película no encontrada", status_code=404)
    
    # Obtener datos frescos de TMDB
    new_data = await tmdb.get_movie_details(new_tmdb_id)
    if not new_data:
        return HTMLResponse("No se pudo obtener la película de TMDB", status_code=500)
    
    # Solo actualizar sinopsis, reparto y póster (respetar título, año, país, director)
    new_synopsis = new_data.get('synopsis') or m.get('synopsis') or ''
    new_poster = new_data.get('poster_url') or m.get('poster_url') or ''
    new_cast = new_data.get('cast') or []
    
    with db.db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE movies SET 
                    synopsis = %s, 
                    poster_url = %s, 
                    "cast" = %s 
                WHERE id = %s
            """, (
                new_synopsis.strip() or None,
                new_poster.strip() or None,
                json.dumps(new_cast, ensure_ascii=False),
                movie_id
            ))
        conn.commit()
    
    return RedirectResponse(f"/movie/{movie_id}", status_code=303)

@app.post("/save-movie/{movie_id}")
async def save_movie(
    movie_id: int, title_es: str = Form(""), title_original: str = Form(""), 
    year: str = Form(""), country: str = Form(""), continent: str = Form(""), 
    director: str = Form(""), synopsis: str = Form(""), cast_text: str = Form(""), 
    poster_url: str = Form(""), tmdb_id: str = Form(""), 
    tags: list[str] = Form(default=[]), admin: bool = Depends(check_admin)
):
    tmdb_id_int = int(tmdb_id) if tmdb_id and tmdb_id.isdigit() else None
    cast_list = []
    if tmdb_id_int:
        try:
            tmdb_data = await tmdb.get_movie_details(tmdb_id_int)
            if tmdb_data and tmdb_data.get("cast"):
                cast_list = [{"name": c.get("name", ""), "id": c.get("id"), "profile_path": c.get("profile_path"), "character": c.get("character", "")} for c in tmdb_data["cast"][:15]]
                synopsis = synopsis or tmdb_data.get("synopsis")
                poster_url = poster_url or tmdb_data.get("poster_url")
        except: pass
    if not cast_list and cast_text.strip():
        cast_list = [{"name": line.strip(), "id": None, "profile_path": None, "character": ""} for line in cast_text.strip().split("\n") if line.strip()]
    if country:
        auto_continent = db.get_continent_by_country(country)
        if auto_continent: continent = auto_continent
    
    # Convertir lista de tags a JSON
    tags_json = json.dumps(tags, ensure_ascii=False)
    
    with db.db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE movies SET 
                    tmdb_id = %s, title_es = %s, title_original = %s, year = %s, 
                    country = %s, continent = %s, director = %s, synopsis = %s, 
                    poster_url = %s, "cast" = %s, tags = %s
                WHERE id = %s
            """, (
                tmdb_id_int, title_es.strip() or None, title_original.strip() or None, 
                int(year) if year.isdigit() else None, country.strip() or None, 
                continent.strip() or None, director.strip() or None, synopsis.strip() or None, 
                poster_url.strip() or None, json.dumps(cast_list, ensure_ascii=False), 
                tags_json, movie_id
            ))
        conn.commit()
    return RedirectResponse(f"/movie/{movie_id}", status_code=303)

@app.get("/actor/{actor_id}", response_class=HTMLResponse)
async def actor_detail(request: Request, actor_id: int):
    actor_movies, actor_series, actor_name, actor_photo = [], [], "Desconocido", None
    for m in db.list_movies(limit=10000):
        for c in (json.loads(m["cast"]) if m["cast"] else []):
            if isinstance(c, dict) and c.get("id") == actor_id:
                actor_movies.append(m)
                if not actor_name or actor_name == "Desconocido":
                    actor_name = c.get("name", "Desconocido")
                if c.get("profile_path") and not actor_photo:
                    actor_photo = f"https://image.tmdb.org/t/p/w300{c['profile_path']}" if not c['profile_path'].startswith('http') else c['profile_path']
                break
    for s in db.list_series(limit=10000):
        for c in (json.loads(s["cast"]) if s["cast"] else []):
            if isinstance(c, dict) and c.get("id") == actor_id:
                actor_series.append(s)
                if not actor_name or actor_name == "Desconocido":
                    actor_name = c.get("name", "Desconocido")
                if c.get("profile_path") and not actor_photo:
                    actor_photo = f"https://image.tmdb.org/t/p/w300{c['profile_path']}" if not c['profile_path'].startswith('http') else c['profile_path']
                break
    return templates.TemplateResponse("actor.html", {
        "request": request, "actor_name": actor_name, "actor_photo": actor_photo, 
        "movies": actor_movies, "series": actor_series
    })

@app.post("/update-actor-photo")
async def update_actor_photo(request: Request, actor_id: str = Form(""), actor_name: str = Form(""), photo_url: str = Form(...), movie_id: int = Form(...), admin: bool = Depends(check_admin)):
    try: db.update_actor_photo(actor_id or None, actor_name, photo_url)
    except Exception as e: print(f"Error: {e}")
    return RedirectResponse(f"/movie/{movie_id}#cast", status_code=303)

@app.post("/remove-actor-photo")
async def remove_actor_photo(request: Request, actor_id: str = Form(""), actor_name: str = Form(""), movie_id: int = Form(...), admin: bool = Depends(check_admin)):
    try: db.remove_actor_photo(actor_id or None, actor_name)
    except Exception as e: print(f"Error: {e}")
    return RedirectResponse(f"/movie/{movie_id}#cast", status_code=303)

@app.get("/review-uk", response_class=HTMLResponse)
async def review_uk_movies(request: Request, admin: bool = Depends(check_admin)):
    movies = db.get_uk_related_movies()
    return templates.TemplateResponse("review_uk.html", {"request": request, "movies": movies})

@app.get("/show-english-synopsis", response_class=HTMLResponse)
async def show_english_synopsis(request: Request, admin: bool = Depends(check_admin)):
    from langdetect import detect, LangDetectException
    to_translate = []
    for m in db.list_movies():
        synopsis = m.get("synopsis") or ""
        if len(synopsis) >= 20:
            try:
                if detect(synopsis) == 'en': to_translate.append({"id": m["id"], "title_es": m.get("title_es", ""), "year": m.get("year"), "synopsis_en": synopsis})
            except LangDetectException: pass
    return templates.TemplateResponse("show_english_synopsis.html", {"request": request, "to_translate": to_translate, "total": len(to_translate)})

@app.get("/apply-translations-form", response_class=HTMLResponse)
async def apply_translations_form(request: Request):
    return templates.TemplateResponse("apply_translations.html", {"request": request})

@app.post("/apply-translations", response_class=HTMLResponse)
async def apply_translations(request: Request, translations_text: str = Form(...), admin: bool = Depends(check_admin)):
    updated, current_id = 0, None
    for line in translations_text.strip().split('\n'):
        line = line.strip()
        if line.startswith('ID:'):
            try: current_id = int(line.replace('ID:', '').strip())
            except: current_id = None
        elif line.startswith('Sinopsis ES:') and current_id:
            synopsis_es = line.replace('Sinopsis ES:', '').strip()
            if synopsis_es:
                with db.db() as conn: conn.execute("UPDATE movies SET synopsis = ? WHERE id = ?", (synopsis_es, current_id))
                updated += 1; current_id = None
    return HTMLResponse(f'<div class="bg-green-900 border border-green-600 p-6 rounded text-center max-w-2xl mx-auto mt-10"><p class="text-green-300 font-semibold text-lg">✅ Traducciones aplicadas</p><p class="text-green-200 text-sm mt-2">{updated} sinopsis actualizadas.</p><a href="/" class="inline-block mt-4 bg-gray-600 hover:bg-gray-700 px-4 py-2 rounded">Volver al Inicio</a></div>')

# === RUTAS DE LOGIN Y LOGOUT ===
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, redirect_url: str = "/", error: str = ""):
    return templates.TemplateResponse("login.html", {"request": request, "redirect_url": redirect_url, "error": error})

@app.post("/login")
async def login_submit(password: str = Form(...), redirect_url: str = Form("/")):
    if password == ADMIN_PASSWORD:
        response = RedirectResponse(url=redirect_url, status_code=303)
        response.set_cookie(key="admin_token", value=ADMIN_PASSWORD, httponly=True, samesite="lax")
        return response
    return RedirectResponse(url=f"/login?redirect_url={redirect_url}&error=Contrase%C3%B1a%20incorrecta", status_code=303)

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("admin_token")
    return response

# === RUTAS DE SERIES ===
@app.get("/series", response_class=HTMLResponse)
async def series_index(request: Request, q: str = "", sort: str = "name", category: str = "", country: str = "", continent: str = "", page: int = 1, per_page: int = 20):
    offset = (page - 1) * per_page
    series_list = db.list_series(q=q, sort=sort, category=category, country=country, continent=continent, offset=offset, limit=per_page)
    total = db.count_series(q=q, category=category, country=country, continent=continent)
    total_pages = (total + per_page - 1) // per_page
    return templates.TemplateResponse("series_index.html", {
        "request": request, "series": series_list, "q": q, "sort": sort, "category": category, "country": country, "continent": continent,
        "categories": db.get_series_categories(), "continents": db.get_series_continents(), "countries": db.get_series_countries(),
        "page": page, "total_pages": total_pages, "total_series": total, "per_page": per_page
    })

@app.get("/serie/{series_id}", response_class=HTMLResponse)
async def serie_detail(request: Request, series_id: int):
    s = db.get_series(series_id)
    if not s: return HTMLResponse("Serie no encontrada", status_code=404)
    s["cast"] = json.loads(s["cast"]) if s["cast"] else []
    return templates.TemplateResponse("serie.html", {"request": request, "serie": s})

@app.get("/edit-serie/{series_id}", response_class=HTMLResponse)
async def edit_serie_page(request: Request, series_id: int, admin: bool = Depends(check_admin)):
    s = db.get_series(series_id)
    if not s: return HTMLResponse("No encontrada", status_code=404)
    cast_list = [c.get("name", "") if isinstance(c, dict) else c for c in (json.loads(s.get("cast") or "[]") or [])]
    return templates.TemplateResponse("edit_serie.html", {"request": request, "serie": s, "cast_text": "\n".join(cast_list), "categories": db.get_series_categories()})

@app.post("/save-serie/{series_id}")
async def save_serie(
    series_id: int, name: str = Form(""), name_original: str = Form(""), 
    first_air_date: str = Form(""), country: str = Form(""), category: str = Form(""), 
    creator: str = Form(""), synopsis: str = Form(""), cast_text: str = Form(""), 
    poster_url: str = Form(""), tmdb_id: str = Form(""), seasons: str = Form(""), 
    episodes: str = Form(""), admin: bool = Depends(check_admin)
):
    tmdb_id_int = int(tmdb_id) if tmdb_id and tmdb_id.isdigit() else None
    current_serie = db.get_series(series_id) or {}
    current_cast_raw = current_serie.get("cast") or "[]"
    try:
        current_cast = json.loads(current_cast_raw) if isinstance(current_cast_raw, str) else (current_cast_raw or [])
    except Exception:
        current_cast = []

    tmdb_cast_list = []
    if tmdb_id_int:
        try:
            tmdb_data = await tmdb.get_series_details(tmdb_id_int)
            if tmdb_data:
                if tmdb_data.get("cast"):
                    tmdb_cast_list = [{"name": c.get("name", ""), "id": c.get("id"), "profile_path": c.get("profile_path"), "character": c.get("character", "")} for c in tmdb_data["cast"][:15] if c.get("name")]
                synopsis = synopsis or tmdb_data.get("synopsis") or ""
                poster_url = poster_url or tmdb_data.get("poster_url") or ""
                creator = creator or tmdb_data.get("creator") or ""
        except Exception:
            pass

    cast_list = []
    if cast_text.strip():
        known_cast = {}
        for c in current_cast + tmdb_cast_list:
            if isinstance(c, dict) and c.get("name"):
                known_cast[normalize_search(c["name"])] = c

        for line in cast_text.strip().split("\n"):
            actor_name = line.strip()
            if not actor_name: continue
            old = known_cast.get(normalize_search(actor_name), {})
            actor_id = old.get("id")
            profile_path = old.get("profile_path")
            character = old.get("character", "")
            if not actor_id:
                found_id, found_photo = _find_actor_id_by_name(actor_name)
                if found_id: actor_id = found_id
                if found_photo and not profile_path: profile_path = found_photo
            cast_list.append({"name": actor_name, "id": actor_id, "profile_path": profile_path, "character": character})
    else:
        cast_list = tmdb_cast_list or current_cast

    with db.db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE series SET 
                    tmdb_id = %(tmdb_id)s, name = %(name)s, name_original = %(name_original)s, 
                    first_air_date = %(first_air_date)s, country = %(country)s, category = %(category)s, 
                    creator = %(creator)s, synopsis = %(synopsis)s, poster_url = %(poster_url)s, 
                    "cast" = %(cast)s, seasons = %(seasons)s, episodes = %(episodes)s 
                WHERE id = %(series_id)s
            """, {
                "tmdb_id": tmdb_id_int, "name": name.strip() or None, "name_original": name_original.strip() or None,
                "first_air_date": first_air_date.strip() or None, "country": country.strip() or None,
                "category": category.strip() or None, "creator": creator.strip() or None,
                "synopsis": synopsis.strip() or None, "poster_url": poster_url.strip() or None,
                "cast": json.dumps(cast_list, ensure_ascii=False),
                "seasons": int(seasons) if seasons.isdigit() else 0,
                "episodes": int(episodes) if episodes.isdigit() else 0,
                "series_id": series_id
            })
        conn.commit()
    return RedirectResponse(f"/serie/{series_id}", status_code=303)

@app.get("/reidentify-serie/{series_id}", response_class=HTMLResponse)
async def reidentify_serie_form(request: Request, series_id: int, admin: bool = Depends(check_admin)):
    s = db.get_series(series_id)
    if not s: return HTMLResponse("Serie no encontrada", status_code=404)
    return templates.TemplateResponse("reidentify_serie.html", {"request": request, "serie": s, "results": None, "query": ""})

@app.post("/reidentify-serie/{series_id}", response_class=HTMLResponse)
async def reidentify_serie_search(request: Request, series_id: int, query: str = Form(...), year: str = Form(""), admin: bool = Depends(check_admin)):
    s = db.get_series(series_id)
    if not s: return HTMLResponse("Serie no encontrada", status_code=404)
    results = await tmdb.search_series(query, int(year) if year.isdigit() else None)
    return templates.TemplateResponse("reidentify_serie.html", {"request": request, "serie": s, "results": results, "query": query})

@app.get("/confirm-reidentify/{series_id}/{new_tmdb_id}", response_class=HTMLResponse)
async def confirm_reidentify(request: Request, series_id: int, new_tmdb_id: int, admin: bool = Depends(check_admin)):
    s = db.get_series(series_id)
    if not s: return HTMLResponse("Serie no encontrada", status_code=404)
    with db.db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM series WHERE tmdb_id = %s", (new_tmdb_id,))
            existing_row = cur.fetchone()
            if existing_row:
                cur.execute("DELETE FROM series WHERE id = %s", (series_id,))
                conn.commit()
                return RedirectResponse("/series", status_code=303)
            new_data = await tmdb.get_series_details(new_tmdb_id)
            if not new_data: return HTMLResponse("No se pudo obtener la nueva serie de TMDB", status_code=500)
            new_data["category"] = s.get("category", "")
            cur.execute("""
                UPDATE series SET 
                    tmdb_id = %(tmdb_id)s, name = %(name)s, name_original = %(name_original)s,
                    first_air_date = %(first_air_date)s, country = %(country)s, synopsis = %(synopsis)s,
                    poster_url = %(poster_url)s, seasons = %(seasons)s, episodes = %(episodes)s,
                    "cast" = %(cast)s, creator = %(creator)s, category = %(category)s
                WHERE id = %(series_id)s
            """, {
                **new_data,
                "cast": json.dumps(new_data.get("cast") or [], ensure_ascii=False),
                "series_id": series_id
            })
            conn.commit()
    return RedirectResponse(f"/serie/{series_id}", status_code=303)

@app.post("/delete-serie/{series_id}")
async def delete_serie(series_id: int, admin: bool = Depends(check_admin)):
    db.delete_series(series_id)
    return RedirectResponse("/series", status_code=303)

@app.post("/update-serie-poster/{series_id}")
async def update_serie_poster(request: Request, series_id: int, poster_url: str = Form(...), admin: bool = Depends(check_admin)):
    db.update_series_poster(series_id, poster_url)
    return RedirectResponse(f"/serie/{series_id}", status_code=303)

# === RUTA DE COMPARACIÓN CON EXCEL/CSV ===
@app.get("/comparar-excel", response_class=HTMLResponse)
async def comparar_excel_form(request: Request, admin: bool = Depends(check_admin)):
    return templates.TemplateResponse("comparar_excel.html", {
        "request": request, 
        "resultados": None, 
        "total_rows": 0, 
        "total_faltantes": 0, 
        "total_posibles": 0, 
        "total_encontradas": 0
    })

@app.post("/comparar-excel", response_class=HTMLResponse)
async def comparar_excel_submit(request: Request, archivo: UploadFile = Form(...), admin: bool = Depends(check_admin)):
    contents = await archivo.read()
    try:
        text = contents.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = contents.decode('latin-1')
    
    # Detectar delimitador automáticamente (coma o punto y coma)
    first_line = text.split('\n')[0]
    delimiter = ';' if ';' in first_line else ','
    print(f"📊 Delimitador detectado: '{delimiter}'")
    
    csv_file = io.StringIO(text)
    reader = csv.DictReader(csv_file, delimiter=delimiter)
    
    db_movies = db.list_movies(limit=10000)
    
    # Construir índice de búsqueda por título original normalizado
    db_origins = {}
    for m in db_movies:
        orig = m.get('title_original', '')
        if orig:
            db_origins[normalize_search(orig)] = m
            
    db_origins_keys = list(db_origins.keys())
    resultados = []
    total_rows = 0
    
    # Nombres posibles para columnas
    possible_orig_cols = ['Título Original', 'titulo_original', 'Original', 'original', 'Title Original', 'Titulo Original']
    possible_title_cols = ['Título', 'titulo', 'Titulo', 'Title', 'title', 'Nombre', 'nombre', 'Name', 'name']
    possible_year_cols = ['Año', 'anio', 'año', 'Year', 'year', 'Anio']
    
    orig_col = None
    title_col = None
    year_col = None
    
    if reader.fieldnames:
        print(f"📊 COLUMNAS DETECTADAS: {reader.fieldnames}")
        for col in reader.fieldnames:
            col_clean = col.strip()
            col_lower = col_clean.lower()
            for possible in possible_orig_cols:
                if possible.lower() == col_lower:
                    orig_col = col_clean
                    break
            for possible in possible_title_cols:
                if possible.lower() == col_lower:
                    title_col = col_clean
                    break
            for possible in possible_year_cols:
                if possible.lower() == col_lower:
                    year_col = col_clean
                    break
    
    print(f"✅ Columna título original usada: {orig_col}")
    print(f"✅ Columna título usada: {title_col}")
    print(f"✅ Columna año usada: {year_col}")
    
    # Artículos a ignorar al inicio para comparación
    articulos = ['the ', 'el ', 'la ', 'los ', 'las ', 'un ', 'una ', 'unos ', 'unas ', 'a ', 'an ']
    
    def quitar_articulos(texto):
        t = texto.lower().strip()
        for art in articulos:
            if t.startswith(art):
                return t[len(art):].strip()
        return t
    
    for row in reader:
        total_rows += 1
        if not orig_col or not title_col:
            continue
            
        excel_orig = row.get(orig_col, '').strip()
        excel_title = row.get(title_col, '').strip()
        excel_year = row.get(year_col, '').strip() if year_col else ''
        
        if not excel_orig: 
            continue
            
        norm_excel = normalize_search(excel_orig)
        excel_year_int = int(excel_year) if excel_year.isdigit() else None
        
        # 1. Búsqueda exacta por título original
        if norm_excel in db_origins:
            db_movie = db_origins[norm_excel]
            if excel_year_int and db_movie.get('year'):
                if abs(db_movie['year'] - excel_year_int) <= 1:
                    status = "✅ Encontrada"
                else:
                    status = "⚠️ Título coincide pero año difiere"
            else:
                status = "✅ Encontrada"
            match_title = db_movie.get('title_es', '')
            match_orig = db_movie.get('title_original', '')
            match_year = db_movie.get('year', '')
        else:
            # 2. Búsqueda ignorando artículos al inicio
            excel_sin_art = quitar_articulos(norm_excel)
            found = False
            for db_norm, db_movie in db_origins.items():
                db_sin_art = quitar_articulos(db_norm)
                if excel_sin_art == db_sin_art:
                    status = "✅ Encontrada (ignorando artículo)"
                    match_title = db_movie.get('title_es', '')
                    match_orig = db_movie.get('title_original', '')
                    match_year = db_movie.get('year', '')
                    found = True
                    break
            
            if not found:
                # 3. Búsqueda difusa (fuzzy matching) con umbral 0.85
                matches = difflib.get_close_matches(norm_excel, db_origins_keys, n=1, cutoff=0.85)
                if matches:
                    matched_movie = db_origins[matches[0]]
                    if excel_year_int and matched_movie.get('year'):
                        if abs(matched_movie['year'] - excel_year_int) <= 2:
                            status = "⚠️ Posible coincidencia"
                        else:
                            status = "⚠️ Título similar pero año muy distinto"
                    else:
                        status = "⚠️ Posible coincidencia"
                    match_title = matched_movie.get('title_es', '')
                    match_orig = matched_movie.get('title_original', '')
                    match_year = matched_movie.get('year', '')
                else:
                    status = "❌ Faltante"
                    match_title = "-"
                    match_orig = "-"
                    match_year = "-"
                    
        resultados.append({
            "excel_title": excel_title, 
            "excel_orig": excel_orig, 
            "excel_year": excel_year,
            "status": status,
            "db_title": match_title, 
            "db_orig": match_orig,
            "db_year": match_year
        })
        
    orden = {"❌ Faltante": 0, "⚠️ Posible coincidencia": 1, "⚠️ Título similar pero año muy distinto": 2, "⚠️ Título coincide pero año difiere": 3, "✅ Encontrada": 4, "✅ Encontrada (ignorando artículo)": 5}
    resultados.sort(key=lambda x: orden.get(x["status"], 6))
    
    print(f"📊 Total filas procesadas: {total_rows}")
    print(f"📊 Resultados encontrados: {len(resultados)}")
    
    return templates.TemplateResponse("comparar_excel.html", {
        "request": request, 
        "resultados": resultados,
        "total_faltantes": sum(1 for r in resultados if r["status"] == "❌ Faltante"),
        "total_posibles": sum(1 for r in resultados if "⚠️" in r["status"]),
        "total_encontradas": sum(1 for r in resultados if "✅" in r["status"]),
        "total_rows": total_rows
    })
