import os
import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("TMDB_API_KEY")
BASE = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p/w500"

ISO_A_PAIS = {
    "US": "Estados Unidos", "GB": "Reino Unido", "FR": "Francia", "DE": "Alemania",
    "IT": "Italia", "ES": "España", "MX": "México", "AR": "Argentina",
    "BR": "Brasil", "CL": "Chile", "CO": "Colombia", "PE": "Perú",
    "VE": "Venezuela", "UY": "Uruguay", "PY": "Paraguay", "BO": "Bolivia",
    "EC": "Ecuador", "CA": "Canadá", "JP": "Japón", "CN": "China",
    "KR": "Corea del Sur", "IN": "India", "RU": "Rusia", "PL": "Polonia",
    "SE": "Suecia", "NO": "Noruega", "DK": "Dinamarca", "FI": "Finlandia",
    "NL": "Países Bajos", "BE": "Bélgica", "CH": "Suiza", "AT": "Austria",
    "PT": "Portugal", "IE": "Irlanda", "CZ": "República Checa", "HU": "Hungría",
    "RO": "Rumanía", "BG": "Bulgaria", "UA": "Ucrania", "RS": "Serbia",
    "HR": "Croacia", "GR": "Grecia", "TR": "Turquía", "IL": "Israel",
    "EG": "Egipto", "ZA": "Sudáfrica", "NG": "Nigeria", "MA": "Marruecos",
    "AU": "Australia", "NZ": "Nueva Zelanda", "TH": "Tailandia", "PH": "Filipinas",
    "ID": "Indonesia", "VN": "Vietnam", "TW": "Taiwán", "HK": "Hong Kong",
    "SG": "Singapur", "MY": "Malasia", "PK": "Pakistán", "BD": "Bangladesh",
    "AF": "Afganistán", "IQ": "Irak", "IR": "Irán", "SY": "Siria",
    "SA": "Arabia Saudita", "AE": "Emiratos Árabes Unidos", "QA": "Catar",
    "KW": "Kuwait", "JO": "Jordania", "LB": "Líbano", "PS": "Palestina",
    "IS": "Islandia", "LU": "Luxemburgo", "MC": "Mónaco", "MT": "Malta",
    "CY": "Chipre", "EE": "Estonia", "LV": "Letonia", "LT": "Lituania",
    "SK": "Eslovaquia", "SI": "Eslovenia", "BA": "Bosnia y Herzegovina",
    "AL": "Albania", "MK": "Macedonia del Norte", "ME": "Montenegro",
    "XK": "Kosovo", "GE": "Georgia", "AM": "Armenia", "AZ": "Azerbaiyán",
    "KZ": "Kazajistán", "UZ": "Uzbekistán", "MN": "Mongolia", "NP": "Nepal",
    "LK": "Sri Lanka", "MM": "Myanmar", "KH": "Camboya", "LA": "Laos",
    "BN": "Brunei", "TL": "Timor Oriental", "KG": "Kirguistán", "TJ": "Tayikistán",
    "TM": "Turkmenistán", "BT": "Bután", "MV": "Maldivas", "BH": "Baréin",
    "OM": "Omán", "YE": "Yemen", "DZ": "Argelia", "TN": "Túnez",
    "LY": "Libia", "SD": "Sudán", "ET": "Etiopía", "KE": "Kenia",
    "TZ": "Tanzania", "UG": "Uganda", "GH": "Ghana", "SN": "Senegal",
    "CM": "Camerún", "CI": "Costa de Marfil", "BF": "Burkina Faso",
    "ML": "Malí", "NE": "Níger", "TD": "Chad", "SO": "Somalia",
    "MZ": "Mozambique", "AO": "Angola", "ZM": "Zambia", "BW": "Botsuana",
    "NA": "Namibia", "GA": "Gabón", "GN": "Guinea", "BJ": "Benín",
    "BI": "Burundi", "TG": "Togo", "SL": "Sierra Leona", "LR": "Liberia",
    "CF": "República Centroafricana", "MR": "Mauritania", "ER": "Eritrea",
    "GM": "Gambia", "GQ": "Guinea Ecuatorial", "DJ": "Djibouti",
    "KM": "Comoras", "CV": "Cabo Verde", "ST": "Santo Tomé y Príncipe",
    "SC": "Seychelles", "MU": "Mauricio", "LS": "Lesoto", "SZ": "Esuatini",
    "CD": "República Democrática del Congo", "CG": "República del Congo",
    "SS": "Sudán del Sur", "EH": "Sahara Occidental", "RE": "Réunion",
    "YT": "Mayotte", "FJ": "Fiyi", "PG": "Papúa Nueva Guinea", "WS": "Samoa",
    "TO": "Tonga", "VU": "Vanuatu", "SB": "Islas Salomón", "KI": "Kiribati",
    "TV": "Tuvalu", "NR": "Nauru", "PW": "Palau", "FM": "Micronesia",
    "MH": "Islas Marshall", "AS": "Samoa Americana", "GU": "Guam",
    "NC": "Nueva Caledonia", "PF": "Polinesia Francesa", "WF": "Wallis y Futuna",
    "TK": "Tokelau", "NU": "Niue", "CK": "Islas Cook", "GL": "Groenlandia",
    "BM": "Bermudas", "PM": "Saint Pierre and Miquelon",
    "GT": "Guatemala", "BZ": "Belice", "HN": "Honduras", "SV": "El Salvador",
    "NI": "Nicaragua", "CR": "Costa Rica", "PA": "Panamá", "CU": "Cuba",
    "DO": "República Dominicana", "PR": "Puerto Rico", "JM": "Jamaica",
    "HT": "Haití", "BS": "Bahamas", "TT": "Trinidad y Tobago", "BB": "Barbados",
    "GD": "Granada", "AG": "Antigua y Barbuda", "DM": "Dominica",
    "VC": "San Vicente y las Granadinas", "LC": "Santa Lucía",
    "KN": "San Cristóbal y Nieves", "KY": "Islas Caimán", "VI": "Islas Vírgenes",
    "AW": "Aruba", "CW": "Curazao", "GP": "Guadalupe", "MQ": "Martinica",
    "GF": "Guyana Francesa", "FK": "Islas Malvinas", "GY": "Guyana",
    "SR": "Surinam", "GI": "Gibraltar", "JE": "Jersey", "GG": "Guernsey",
    "IM": "Isla de Man", "FO": "Islas Feroe", "AD": "Andorra",
    "SM": "San Marino", "VA": "Vaticano", "LI": "Liechtenstein",
    "BY": "Bielorrusia", "MD": "Moldavia", "SU": "Unión Soviética",
    "CS": "Serbia y Montenegro", "YU": "Yugoslavia",
    "AN": "Antillas Neerlandesas", "TP": "Timor Oriental",
    "XX": "Desconocido",
}

def get_country_spanish(iso_code):
    if not iso_code: return None
    return ISO_A_PAIS.get(iso_code.upper())

def get_continent_from_iso(iso_code):
    country = get_country_spanish(iso_code)
    if not country: return None
    from database import get_continent_by_country
    return get_continent_by_country(country)

async def search_movies(query: str, year: int = None, lang: str = "es-ES") -> list:
    params = {"api_key": API_KEY, "language": lang, "query": query, "include_adult": "false"}
    if year: params["year"] = year
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{BASE}/search/movie", params=params)
        r.raise_for_status()
        return r.json().get("results", [])[:20]

async def get_movie_collection_id(tmdb_id: int):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{BASE}/movie/{tmdb_id}", params={"api_key": API_KEY, "language": "es-ES"})
        if r.status_code != 200: return None
        bc = r.json().get("belongs_to_collection")
        return bc.get("id") if bc else None

async def list_collection_parts(collection_id: int) -> list:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{BASE}/collection/{collection_id}", params={"api_key": API_KEY, "language": "es-ES"})
        if r.status_code != 200: return []
        parts = []
        for m in r.json().get("parts", []) or []:
            rd = m.get("release_date") or ""
            parts.append({
                "id": m.get("id"), "title": m.get("title") or m.get("original_title") or "?",
                "original_title": m.get("original_title") or "",
                "year": int(rd[:4]) if len(rd) >= 4 and rd[:4].isdigit() else None,
                "poster_path": m.get("poster_path"),
            })
        return parts

async def get_movie_details(tmdb_id: int) -> dict:
    params_es = {"api_key": API_KEY, "language": "es-ES", "append_to_response": "credits"}
    synopsis_es = None
    title_es = None
    async with httpx.AsyncClient(timeout=10) as client:
        r_es = await client.get(f"{BASE}/movie/{tmdb_id}", params=params_es)
        if r_es.status_code == 200:
            data_es = r_es.json()
            synopsis_es = data_es.get("overview")
            title_es = data_es.get("title")
    if not title_es:
        async with httpx.AsyncClient(timeout=10) as client:
            tr = await client.get(f"{BASE}/movie/{tmdb_id}/translations", params={"api_key": API_KEY})
            if tr.status_code == 200:
                for t in tr.json().get("translations", []):
                    if t.get("iso_3166_1") == "ES" or t.get("iso_639_1") == "es":
                        tt = t.get("data", {}).get("title")
                        if tt: title_es = tt; break
    params_en = {"api_key": API_KEY, "language": "en-US", "append_to_response": "credits"}
    async with httpx.AsyncClient(timeout=10) as client:
        r_en = await client.get(f"{BASE}/movie/{tmdb_id}", params=params_en)
        r_en.raise_for_status()
        data_en = r_en.json()
    synopsis = synopsis_es if synopsis_es else data_en.get("overview")
    credits_data = data_en.get("credits", {})
    directors = [c["name"] for c in credits_data.get("crew", []) if c.get("job") == "Director"]
    cast = [{"id": c["id"], "name": c["name"], "profile_path": c.get("profile_path"), "character": c.get("character", "")} for c in credits_data.get("cast", [])[:15]]
    countries = data_en.get("production_countries", [])
    country_iso = countries[0].get("iso_3166_1") if countries else None
    country = get_country_spanish(country_iso)
    continent = get_continent_from_iso(country_iso)
    poster = f"{IMG}{data_en['poster_path']}" if data_en.get("poster_path") else None
    if not title_es: title_es = data_en.get("title") or data_en.get("original_title")
    return {
        "tmdb_id": data_en["id"], "title_es": title_es, "title_original": data_en.get("original_title"),
        "year": int(data_en["release_date"][:4]) if data_en.get("release_date") else None,
        "country": country, "continent": continent,
        "director": ", ".join(directors) or None, "cast": cast,
        "synopsis": synopsis, "poster_url": poster,
    }

async def search_series(query: str, year: int = None, lang: str = "es-ES") -> list:
    params = {"api_key": API_KEY, "language": lang, "query": query, "include_adult": "false"}
    if year: params["first_air_date_year"] = year
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{BASE}/search/tv", params=params)
        r.raise_for_status()
        return r.json().get("results", [])[:20]

async def get_series_details(tmdb_id: int) -> dict:
    params_es = {"api_key": API_KEY, "language": "es-ES", "append_to_response": "credits"}
    synopsis_es, name_es = None, None
    async with httpx.AsyncClient(timeout=10) as client:
        r_es = await client.get(f"{BASE}/tv/{tmdb_id}", params=params_es)
        if r_es.status_code == 200:
            data_es = r_es.json()
            synopsis_es = data_es.get("overview")
            name_es = data_es.get("name")
            
    if not name_es:
        async with httpx.AsyncClient(timeout=10) as client:
            tr = await client.get(f"{BASE}/tv/{tmdb_id}/translations", params={"api_key": API_KEY})
            if tr.status_code == 200:
                for t in tr.json().get("translations", []):
                    if t.get("iso_3166_1") == "ES" or t.get("iso_639_1") == "es":
                        tt = t.get("data", {}).get("name")
                        if tt: name_es = tt; break

    params_en = {"api_key": API_KEY, "language": "en-US", "append_to_response": "credits"}
    async with httpx.AsyncClient(timeout=10) as client:
        r_en = await client.get(f"{BASE}/tv/{tmdb_id}", params=params_en)
        r_en.raise_for_status()
        data_en = r_en.json()

    synopsis = synopsis_es if synopsis_es else data_en.get("overview")
    credits_data = data_en.get("credits", {})
    creators = [c["name"] for c in data_en.get("created_by", [])]
    directors = [c["name"] for c in credits_data.get("crew", []) if c.get("job") == "Director"]
    main_director = ", ".join(creators) if creators else (", ".join(directors) if directors else None)
    
    cast = [{"id": c["id"], "name": c["name"], "profile_path": c.get("profile_path"), "character": c.get("character", "")} for c in credits_data.get("cast", [])[:15]]
    countries = data_en.get("origin_country", [])
    country_iso = countries[0] if countries else None
    country = get_country_spanish(country_iso)
    poster = f"{IMG}{data_en['poster_path']}" if data_en.get("poster_path") else None
    if not name_es: name_es = data_en.get("name") or data_en.get("original_name")

    return {
        "tmdb_id": data_en["id"], "name": name_es, "name_original": data_en.get("original_name"),
        "first_air_date": data_en.get("first_air_date"), "country": country, "category": "",
        "creator": main_director,
        "cast": cast, "synopsis": synopsis, "poster_url": poster,
        "seasons": data_en.get("number_of_seasons", 0), "episodes": data_en.get("number_of_episodes", 0)
    }
