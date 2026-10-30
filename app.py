import json
import os
import re
import unicodedata
from urllib.parse import quote, unquote
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import database as db
import tmdb

app = FastAPI(title="EpeMDB")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
db.init_db()

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

@app.get("/api/search-live")
async def api_search_live(q: str = ""):
    q_clean = normalize_search(q)
    if len(q_clean) < 1: return JSONResponse([])
    results, seen_ids = [], set()
    all_movies = db.list_movies()
    for m in all_movies:
        if m["id"] in seen_ids: continue
        title_es_norm = normalize_search(m.get("title_es", ""))
        title_orig_norm = normalize_search(m.get("title_original", ""))
        if q_clean in title_es_norm or q_clean in title_orig_norm:
            priority = 3 if title_es_norm == q_clean else (4 if title_orig_norm == q_clean else (2.5 if title_es_norm.startswith(q_clean) or title_orig_norm.startswith(q_clean) else 2))
            results.append({"type": "película", "label": f"{m['title_es']} ({m['year'] or '?'})", "sub": f"Título: {m.get('title_original') or '-'}", "url": f"/movie/{m['id']}", "icon": ""})
            seen_ids.add(m["id"])
    director_stats = {}
    for m in all_movies:
        for dir_name in _split_directors(m.get("director", "")):
            if q_clean in normalize_search(dir_name):
                director_stats.setdefault(normalize_search(dir_name), {"name": dir_name, "count": 0})["count"] += 1
    for d in sorted(director_stats.values(), key=lambda x: -x["count"])[:3]:
        results.append({"type": "director", "label": d["name"], "sub": f"{d['count']} película{'s' if d['count'] != 1 else ''}", "url": f"/director?name={quote(d['name'])}", "icon": "🎥"})
    return JSONResponse(results[:15])

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, q: str = "", sort: str = "added_desc", continent: str = "", country: str = "", director: str = "", page: int = 1, per_page: int = 100):
    offset = (page - 1) * per_page
    movies = db.list_movies(q, sort, continent, country, director, offset=offset, limit=per_page)
    total = db.count_movies(q, continent, country, director)
    total_pages = (total + per_page - 1) // per_page
    return templates.TemplateResponse("index.html", {
        "request": request, "movies": movies, "q": q, "sort": sort, "continent": continent, "country": country, "director": director,
        "continents": db.get_continents_list(), "countries": db.get_countries_by_continent(continent),
        "all_countries": db.get_distinct_values("country"), "directors": db.get_distinct_values("director"),
        "no_poster_count": len(db.get_movies_without_poster()), "pending_count": len(db.list_failed_movies()),
        "page": page, "total_pages": total_pages, "total_movies": total, "per_page": per_page
    })

@app.get("/add", response_class=HTMLResponse)
async def add_form(request: Request):
    return templates.TemplateResponse("add.html", {"request": request})

@app.post("/search", response_class=HTMLResponse)
async def search_tmdb(request: Request, query: str = Form(...), year: str = Form("")):
    results = await tmdb.search_movies(query, int(year) if year.isdigit() else None)
    return templates.TemplateResponse("search.html", {"request": request, "results": results, "query": query})

@app.get("/import/{tmdb_id}", response_class=HTMLResponse)
async def import_movie(request: Request, tmdb_id: int):
    movie_id = db.insert_movie(await tmdb.get_movie_details(tmdb_id))
    return RedirectResponse(f"/movie/{movie_id}", status_code=303)

@app.get("/movie/{movie_id}", response_class=HTMLResponse)
async def movie_detail(request: Request, movie_id: int):
    m = db.get_movie(movie_id)
    if not m: return HTMLResponse("No encontrada", status_code=404)
    m["cast"] = json.loads(m["cast"]) if m["cast"] else []
    return templates.TemplateResponse("movie.html", {"request": request, "movie": m, "no_poster_count": len(db.get_movies_without_poster()), "pending_count": len(db.list_failed_movies())})

@app.post("/delete/{movie_id}")
async def delete(movie_id: int):
    db.delete_movie(movie_id)
    return RedirectResponse("/", status_code=303)

@app.post("/edit-title/{movie_id}")
async def edit_title(movie_id: int, title_es: str = Form(...), title_original: str = Form("")):
    with db.db() as conn: conn.execute("UPDATE movies SET title_es = ?, title_original = ? WHERE id = ?", (title_es.strip(), title_original.strip() or None, movie_id))
    return RedirectResponse(f"/movie/{movie_id}", status_code=303)

@app.post("/set-poster/{movie_id}")
async def set_poster(movie_id: int, poster_url: str = Form(...)):
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
    director_movies = [m for m in db.list_movies() if m.get("director") and all(dn in normalize_search(m["director"]) for dn in director_norms)]
    return templates.TemplateResponse("director.html", {"request": request, "director_name": director_name, "movies": director_movies, "no_poster_count": len(db.get_movies_without_poster()), "pending_count": len(db.list_failed_movies())})

@app.get("/failed", response_class=HTMLResponse)
async def failed_movies(request: Request):
    failed = db.list_failed_movies()
    return templates.TemplateResponse("failed.html", {"request": request, "failed": failed, "no_poster_count": len(db.get_movies_without_poster()), "pending_count": len(failed)})

@app.post("/delete-failed/{failed_id}")
async def delete_failed(failed_id: int):
    f = next((x for x in db.list_failed_movies() if x["id"] == failed_id), None)
    if f: db.add_ignored_movie(f["title"], f.get("year")); db.delete_failed_movie(failed_id)
    return RedirectResponse("/failed", status_code=303)

@app.post("/delete-all-failed")
async def delete_all_failed():
    for f in db.list_failed_movies(): db.add_ignored_movie(f["title"], f.get("year"))
    db.delete_all_failed_movies()
    return RedirectResponse("/failed", status_code=303)

@app.get("/no-poster", response_class=HTMLResponse)
async def no_poster(request: Request):
    movies = db.get_movies_without_poster()
    return templates.TemplateResponse("no_poster.html", {"request": request, "movies": movies, "no_poster_count": len(movies), "pending_count": len(db.list_failed_movies())})

@app.post("/update-poster/{movie_id}")
async def update_poster(request: Request, movie_id: int, poster_url: str = Form(...)):
    db.update_poster(movie_id, poster_url)
    return RedirectResponse("/no-poster", status_code=303)

@app.get("/import-dudas", response_class=HTMLResponse)
async def import_dudas_view(request: Request):
    dudas = db.list_import_dudas()
    for d in dudas: d["candidatos"] = json.loads(d["candidatos"]) if d["candidatos"] else []
    return templates.TemplateResponse("import_dudas.html", {"request": request, "dudas": dudas, "no_poster_count": len(db.get_movies_without_poster()), "pending_count": len(db.list_failed_movies())})

@app.get("/edit-movie/{movie_id}", response_class=HTMLResponse)
async def edit_movie_page(request: Request, movie_id: int):
    m = db.get_movie(movie_id)
    if not m: return HTMLResponse("No encontrada", status_code=404)
    cast_list = [c.get("name", "") if isinstance(c, dict) else c for c in (json.loads(m.get("cast") or "[]") or [])]
    return templates.TemplateResponse("edit_movie.html", {"request": request, "movie": m, "cast_text": "\n".join(cast_list)})

@app.post("/save-movie/{movie_id}")
async def save_movie(movie_id: int, title_es: str = Form(""), title_original: str = Form(""), year: str = Form(""), country: str = Form(""), continent: str = Form(""), director: str = Form(""), synopsis: str = Form(""), cast_text: str = Form(""), poster_url: str = Form(""), tmdb_id: str = Form("")):
    tmdb_id_int = int(tmdb_id) if tmdb_id and tmdb_id.isdigit() else None
    cast_list = []
    if tmdb_id_int:
        try:
            tmdb_data = await tmdb.get_movie_details(tmdb_id_int)
            if tmdb_data and tmdb_data.get("cast"):
                cast_list = [{"name": c.get("name", ""), "id": c.get("id"), "profile_path": c.get("profile_path"), "character": c.get("character", "")} for c in tmdb_data["cast"][:15]]
                synopsis = synopsis or tmdb_data.get("synopsis"); poster_url = poster_url or tmdb_data.get("poster_url")
        except: pass
    if not cast_list and cast_text.strip():
        cast_list = [{"name": line.strip(), "id": None, "profile_path": None, "character": ""} for line in cast_text.strip().split("\n") if line.strip()]
    if country:
        auto_continent = db.get_continent_by_country(country)
        if auto_continent: continent = auto_continent
    with db.db() as conn:
        conn.execute("UPDATE movies SET tmdb_id = ?, title_es = ?, title_original = ?, year = ?, country = ?, continent = ?, director = ?, synopsis = ?, poster_url = ?, cast = ? WHERE id = ?",
            (tmdb_id_int, title_es.strip() or None, title_original.strip() or None, int(year) if year.isdigit() else None, country.strip() or None, continent.strip() or None, director.strip() or None, synopsis.strip() or None, poster_url.strip() or None, json.dumps(cast_list, ensure_ascii=False), movie_id))
    return RedirectResponse(f"/movie/{movie_id}", status_code=303)

@app.get("/actor/{actor_id}", response_class=HTMLResponse)
async def actor_detail(request: Request, actor_id: int):
    actor_movies, actor_name, actor_photo = [], "Desconocido", None
    for m in db.list_movies():
        for c in (json.loads(m["cast"]) if m["cast"] else []):
            if isinstance(c, dict) and c.get("id") == actor_id:
                actor_movies.append(m); actor_name = c.get("name", "Desconocido")
                if c.get("profile_path"): actor_photo = f"https://image.tmdb.org/t/p/w300{c['profile_path']}" if not c['profile_path'].startswith('http') else c['profile_path']
                break
    return templates.TemplateResponse("actor.html", {"request": request, "actor_name": actor_name, "actor_photo": actor_photo, "actor_movies": actor_movies, "no_poster_count": len(db.get_movies_without_poster()), "pending_count": len(db.list_failed_movies())})

@app.post("/update-actor-photo")
async def update_actor_photo(request: Request, actor_id: str = Form(""), actor_name: str = Form(""), photo_url: str = Form(...), movie_id: int = Form(...)):
    try: db.update_actor_photo(actor_id or None, actor_name, photo_url)
    except Exception as e: print(f"Error: {e}")
    return RedirectResponse(f"/movie/{movie_id}#cast", status_code=303)

@app.post("/remove-actor-photo")
async def remove_actor_photo(request: Request, actor_id: str = Form(""), actor_name: str = Form(""), movie_id: int = Form(...)):
    try: db.remove_actor_photo(actor_id or None, actor_name)
    except Exception as e: print(f"Error: {e}")
    return RedirectResponse(f"/movie/{movie_id}#cast", status_code=303)

@app.get("/review-uk", response_class=HTMLResponse)
async def review_uk_movies(request: Request):
    movies = db.get_uk_related_movies()
    return templates.TemplateResponse("review_uk.html", {"request": request, "movies": movies, "total": len(movies), "no_poster_count": len(db.get_movies_without_poster()), "pending_count": len(db.list_failed_movies())})

@app.get("/show-english-synopsis", response_class=HTMLResponse)
async def show_english_synopsis(request: Request):
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
async def apply_translations(request: Request, translations_text: str = Form(...)):
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
