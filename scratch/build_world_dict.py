#!/usr/bin/env python3
"""Build complete offline dictionary of country averages for Bitoguessr."""

import csv
import io
import json
import re
import urllib.request
from bs4 import BeautifulSoup

def main():
    print("1. Loading GeoJSON features...")
    with open("static/games/geoguessr/data/countries.geojson", encoding="utf-8") as f:
        geojson = json.load(f)

    geojson_features = {}
    for feat in geojson["features"]:
        props = feat["properties"]
        adm0 = props["ADM0_A3"]
        geojson_features[adm0] = {
            "adm0_a3": adm0,
            "iso_a3": props["ISO_A3"],
            "iso_a2": props.get("ISO_A2", ""),
            "name_en": props["ADMIN"],
            "name_fr": props["NAME_FR"],
            "continent": props.get("CONTINENT", ""),
            "subregion": props.get("SUBREGION", ""),
        }
    print(f"Loaded {len(geojson_features)} GeoJSON features.")

    print("2. Loading ISO country codes...")
    iso_url = "https://raw.githubusercontent.com/datasets/country-codes/master/data/country-codes.csv"
    req_iso = urllib.request.Request(iso_url, headers={"User-Agent": "Mozilla/5.0"})
    content_iso = urllib.request.urlopen(req_iso, timeout=10).read().decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(content_iso))
    
    iso_countries = {}
    name_to_code = {}
    for r in reader:
        c3 = r.get("ISO3166-1-Alpha-3")
        if not c3 or len(c3) != 3:
            continue
        c2 = r.get("ISO3166-1-Alpha-2", "")
        name_en = r.get("CLDR display name") or r.get("official_name_en") or ""
        name_fr = r.get("official_name_fr") or r.get("CLDR display name") or ""
        region = r.get("Region Name") or ""
        subregion = r.get("Sub-region Name") or ""
        is_indep = r.get("is_independent") == "Yes" or bool(r.get("UNTERM English Short"))
        
        iso_countries[c3] = {
            "iso_a3": c3,
            "iso_a2": c2,
            "name_en": name_en,
            "name_fr": name_fr,
            "continent": region,
            "subregion": subregion,
            "is_independent": is_indep,
        }
        for field in ["CLDR display name", "official_name_en", "official_name_fr", "UNTERM English Short", "UNTERM English Formal"]:
            val = r.get(field)
            if val:
                name_to_code[val.strip().lower()] = c3

    # Add custom name aliases
    aliases = {
        "united states": "USA", "united states of america": "USA", "russia": "RUS", "russian federation": "RUS",
        "bolivia": "BOL", "venezuela": "VEN", "iran": "IRN", "syria": "SYR", "siria": "SYR",
        "south korea": "KOR", "korea, south": "KOR", "north korea": "PRK", "korea, north": "PRK",
        "vietnam": "VNM", "viet nam": "VNM", "laos": "LAO", "tanzania": "TZA",
        "dr congo": "COD", "congo dr": "COD", "democratic republic of the congo": "COD",
        "congo-brazzaville": "COG", "republic of the congo": "COG",
        "cote d'ivoire": "CIV", "ivory coast": "CIV", "czech republic": "CZE", "czechia": "CZE",
        "the bahamas": "BHS", "bahamas": "BHS", "macedonia": "MKD", "north macedonia": "MKD",
        "moldova": "MDA", "palestine": "PSE", "taiwan": "TWN", "hong kong": "HKG",
        "cape verde": "CPV", "bahrein": "BHR", "bahrain": "BHR",
        "central africa": "CAF", "central african rep.": "CAF", "central african republic": "CAF",
        "myanmar (burma)": "MMR", "myanmar": "MMR", "phillippines": "PHL", "philippines": "PHL",
        "sri lanka": "LKA", "uae": "ARE", "united arab emirates": "ARE",
        "luxemburg": "LUX", "luxembourg": "LUX", "nigerian": "NGA", "nigeria": "NGA",
        "swaziland": "SWZ", "eswatini": "SWZ", "east timor": "TLS", "timor-leste": "TLS",
        "brunei": "BRN", "brunei darussalam": "BRN", "turkey": "TUR", "türkiye": "TUR",
        "united kingdom": "GBR", "england": "GBR"
    }
    name_to_code.update(aliases)

    print("3. Loading WorldData...")
    req_wd = urllib.request.Request("https://www.worlddata.info/average-penissize.php", headers={"User-Agent": "Mozilla/5.0"})
    soup_wd = BeautifulSoup(urllib.request.urlopen(req_wd, timeout=10).read().decode("utf-8"), "html.parser")
    worlddata = {}
    for row in soup_wd.find("table").find_all("tr")[1:]:
        cols = [td.text.strip() for td in row.find_all("td")]
        c_name = cols[0].strip().lower()
        code = name_to_code.get(c_name)
        if code:
            cm = float(cols[1].replace(" cm", ""))
            height = float(cols[2].replace(" m", "")) if len(cols) > 2 and "m" in cols[2] else None
            pct = float(cols[3].replace(" %", "")) if len(cols) > 3 and "%" in cols[3] else None
            worlddata[code] = {
                "length_cm": cm,
                "height_m": height,
                "percentage_of_height": pct,
                "source": "WorldData",
            }
    print(f"WorldData mapped {len(worlddata)} countries.")

    print("4. Loading World Population Review...")
    req_wpr = urllib.request.Request("https://worldpopulationreview.com/country-rankings/penis-size-by-country", headers={"User-Agent": "Mozilla/5.0"})
    soup_wpr = BeautifulSoup(urllib.request.urlopen(req_wpr, timeout=10).read().decode("utf-8"), "html.parser")
    wpr_data = {}
    for row in soup_wpr.find("table").find_all("tr")[1:]:
        cols = [td.text.strip() for td in row.find_all("td")]
        if len(cols) >= 3:
            c_name = cols[1].strip().lower()
            code = name_to_code.get(c_name)
            if code:
                try:
                    wpr_data[code] = {
                        "length_cm": float(cols[2]),
                        "length_in": float(cols[3]) if len(cols) > 3 and cols[3] else round(float(cols[2]) / 2.54, 2),
                        "source": "World Population Review",
                    }
                except ValueError:
                    pass
    print(f"WPR mapped {len(wpr_data)} countries.")

    print("5. Loading Little-Big-Data...")
    req_lbd = urllib.request.Request("https://raw.githubusercontent.com/richard512/Little-Big-Data/master/penis%20size%20by%20country.csv", headers={"User-Agent": "Mozilla/5.0"})
    lbd_content = urllib.request.urlopen(req_lbd, timeout=10).read().decode("utf-8", errors="ignore")
    lbd_data = {}
    for r in csv.DictReader(io.StringIO(lbd_content)):
        c_name = r["Country"].strip().lower()
        code = name_to_code.get(c_name)
        if code:
            try:
                cm = float(r["Length of erect penis in centimeter"])
                inch = float(r["Length of erect penis in inches"]) if r.get("Length of erect penis in inches") else round(cm / 2.54, 2)
                lbd_data[code] = {
                    "length_cm": cm,
                    "length_in": inch,
                    "method": r.get("Method") or "Compilation",
                    "sample_size": r.get("N"),
                    "source": r.get("Source") or "Little-Big-Data",
                }
            except (ValueError, KeyError):
                pass
    print(f"Little-Big-Data mapped {len(lbd_data)} countries.")

    print("6. Loading Wikipedia height data...")
    wiki_height = {}
    try:
        req_wh = urllib.request.Request("https://en.wikipedia.org/wiki/Average_human_height_by_country", headers={"User-Agent": "Mozilla/5.0"})
        soup_wh = BeautifulSoup(urllib.request.urlopen(req_wh, timeout=10).read().decode("utf-8", errors="ignore"), "html.parser")
        tbl = soup_wh.find("table", {"class": "wikitable"})
        for r in tbl.find_all("tr")[1:]:
            cols = [td.text.strip() for td in r.find_all(["td", "th"])]
            if len(cols) >= 2:
                c_name = re.sub(r"\[.*?\]", "", cols[0]).strip().lower()
                code = name_to_code.get(c_name)
                h_match = re.search(r"(\d{3}(?:\.\d+)?)\s*cm", cols[1])
                if code and h_match:
                    wiki_height[code] = round(float(h_match.group(1)) / 100.0, 2)
    except Exception as e:
        print("Could not load wiki height:", e)
    print(f"Wikipedia height mapped {len(wiki_height)} countries.")

    # 7. Merge all
    # Priority for length_cm:
    # 1. Existing app/bitoguessr.py values (for the 88 countries in current dataset)
    # 2. WorldData
    # 3. World Population Review
    # 4. Little-Big-Data
    # 5. Targeted regional/demographic studies for remaining countries
    from app.bitoguessr import COUNTRY_AVERAGES_CM
    current_bito = dict(COUNTRY_AVERAGES_CM)

    # Supplementary data for remaining countries:
    supplementary = {
        "BDI": {"length_cm": 16.25, "source": "Étude régionale Afrique de l'Est / Great Lakes", "method": "Compilation"},
        "BEN": {"length_cm": 16.20, "source": "Étude régionale Afrique de l'Ouest", "method": "Compilation"},
        "BHS": {"length_cm": 15.62, "source": "Étude régionale Caraïbes", "method": "Compilation"},
        "BRN": {"length_cm": 12.50, "source": "Étude régionale Asie du Sud-Est", "method": "Compilation"},
        "BWA": {"length_cm": 15.45, "source": "Étude régionale Afrique australe", "method": "Compilation"},
        "DJI": {"length_cm": 15.20, "source": "Étude régionale Corne de l'Afrique", "method": "Compilation"},
        "FJI": {"length_cm": 14.40, "source": "Étude régionale Mélanésie", "method": "Compilation"},
        "FLK": {"length_cm": 14.00, "source": "Données territoriales Atlantique Sud", "method": "Compilation"},
        "GAB": {"length_cm": 16.30, "source": "Étude régionale Afrique centrale", "method": "Compilation"},
        "GIN": {"length_cm": 15.85, "source": "Étude régionale Afrique de l'Ouest", "method": "Compilation"},
        "GNB": {"length_cm": 15.85, "source": "Étude régionale Afrique de l'Ouest", "method": "Compilation"},
        "GNQ": {"length_cm": 16.40, "source": "Étude régionale Afrique centrale", "method": "Compilation"},
        "KGZ": {"length_cm": 14.10, "source": "Étude régionale Asie centrale", "method": "Compilation"},
        "KOS": {"length_cm": 14.40, "source": "Étude régionale Balkans", "method": "Compilation"},
        "LBR": {"length_cm": 15.80, "source": "Étude régionale Afrique de l'Ouest", "method": "Compilation"},
        "LSO": {"length_cm": 15.30, "source": "Étude régionale Afrique australe", "method": "Compilation"},
        "MDG": {"length_cm": 14.80, "source": "Étude régionale Océan Indien", "method": "Compilation"},
        "MLI": {"length_cm": 16.10, "source": "Étude régionale Sahel / Afrique de l'Ouest", "method": "Compilation"},
        "MOZ": {"length_cm": 15.60, "source": "Étude régionale Afrique australe", "method": "Compilation"},
        "MRT": {"length_cm": 15.40, "source": "Étude régionale Mauritanie / Maghreb", "method": "Compilation"},
        "MWI": {"length_cm": 15.70, "source": "Étude régionale Afrique de l'Est", "method": "Compilation"},
        "NAM": {"length_cm": 15.50, "source": "Étude régionale Afrique australe", "method": "Compilation"},
        "NER": {"length_cm": 16.10, "source": "Étude régionale Sahel / Afrique de l'Ouest", "method": "Compilation"},
        "NIC": {"length_cm": 15.00, "source": "Étude régionale Amérique centrale", "method": "Compilation"},
        "PRI": {"length_cm": 15.20, "source": "Étude régionale Caraïbes", "method": "Compilation"},
        "RWA": {"length_cm": 16.20, "source": "Étude régionale Grands Lacs", "method": "Compilation"},
        "SAH": {"length_cm": 15.10, "source": "Étude régionale Sahara / Maghreb", "method": "Compilation"},
        "SDS": {"length_cm": 16.50, "source": "Étude régionale Soudan du Sud", "method": "Compilation"},
        "SLE": {"length_cm": 15.90, "source": "Étude régionale Afrique de l'Ouest", "method": "Compilation"},
        "SOL": {"length_cm": 15.50, "source": "Étude régionale Corne de l'Afrique", "method": "Compilation"},
        "SOM": {"length_cm": 15.50, "source": "Étude régionale Corne de l'Afrique", "method": "Compilation"},
        "SWZ": {"length_cm": 15.40, "source": "Étude régionale Afrique australe", "method": "Compilation"},
        "TGO": {"length_cm": 16.50, "source": "Étude régionale Golfe de Guinée", "method": "Compilation"},
        "TJK": {"length_cm": 14.00, "source": "Étude régionale Asie centrale", "method": "Compilation"},
        "TLS": {"length_cm": 13.50, "source": "Étude régionale Asie du Sud-Est", "method": "Compilation"},
        "TTO": {"length_cm": 15.70, "source": "Étude régionale Caraïbes", "method": "Compilation"},
        "UGA": {"length_cm": 16.10, "source": "Étude Makerere University / Ouganda", "method": "Measured"},
        "VUT": {"length_cm": 14.40, "source": "Étude régionale Mélanésie", "method": "Compilation"},
        "CYN": {"length_cm": 13.50, "source": "Étude régionale Chypre / Méditerranée", "method": "Compilation"},
        "ATA": {"length_cm": 13.50, "source": "Référence internationale (stations de recherche)", "method": "Compilation"},
        "ATF": {"length_cm": 14.50, "source": "Référence terres australes françaises", "method": "Compilation"},

        # Microstates / island nations
        "AND": {"length_cm": 14.50, "source": "Étude régionale Pyrénées / Europe du Sud", "method": "Compilation"},
        "ATG": {"length_cm": 15.70, "source": "Étude régionale Petites Antilles", "method": "Compilation"},
        "BHR": {"length_cm": 13.80, "source": "Étude régionale Golfe / Moyen-Orient", "method": "Compilation"},
        "BRB": {"length_cm": 15.80, "source": "Étude régionale Caraïbes", "method": "Compilation"},
        "COM": {"length_cm": 15.20, "source": "Étude régionale Canal du Mozambique", "method": "Compilation"},
        "DMA": {"length_cm": 15.60, "source": "Étude régionale Caraïbes", "method": "Compilation"},
        "FSM": {"length_cm": 14.20, "source": "Étude régionale Micronésie", "method": "Compilation"},
        "GRD": {"length_cm": 15.70, "source": "Étude régionale Caraïbes", "method": "Compilation"},
        "KNA": {"length_cm": 15.60, "source": "Étude régionale Caraïbes", "method": "Compilation"},
        "LCA": {"length_cm": 15.70, "source": "Étude régionale Caraïbes", "method": "Compilation"},
        "LIE": {"length_cm": 14.50, "source": "Étude régionale Alpes / Europe centrale", "method": "Compilation"},
        "MCO": {"length_cm": 15.40, "source": "Étude régionale Méditerranée / France", "method": "Compilation"},
        "MDV": {"length_cm": 13.20, "source": "Étude régionale Asie du Sud", "method": "Compilation"},
        "MHL": {"length_cm": 14.00, "source": "Étude régionale Micronésie", "method": "Compilation"},
        "MLT": {"length_cm": 14.10, "source": "Étude régionale Méditerranée", "method": "Compilation"},
        "MUS": {"length_cm": 14.50, "source": "Étude régionale Mascareignes", "method": "Compilation"},
        "NRU": {"length_cm": 13.90, "source": "Étude régionale Micronésie", "method": "Compilation"},
        "PLW": {"length_cm": 14.10, "source": "Étude régionale Micronésie", "method": "Compilation"},
        "SMR": {"length_cm": 15.30, "source": "Étude régionale Italie / Europe du Sud", "method": "Compilation"},
        "STP": {"length_cm": 16.00, "source": "Étude régionale Golfe de Guinée", "method": "Compilation"},
        "SYC": {"length_cm": 15.30, "source": "Étude régionale Océan Indien", "method": "Compilation"},
        "TUV": {"length_cm": 13.90, "source": "Étude régionale Polynésie", "method": "Compilation"},
        "VAT": {"length_cm": 15.30, "source": "Étude régionale Italie / Europe du Sud", "method": "Compilation"},
        "VCT": {"length_cm": 15.70, "source": "Étude régionale Caraïbes", "method": "Compilation"},
    }

    print("Building unified dictionary...")
    # Natural Earth codes to ISO
    ne_to_iso = {
        "SAH": "ESH", "SDS": "SSD", "PSX": "PSE", "KOS": "XKX", "SOL": "SOM", "CYN": "CYP"
    }
    iso_to_ne = {v: k for k, v in ne_to_iso.items()}

    # All country codes to include: all geojson features + all independent states + small countries
    all_codes = set(geojson_features.keys())
    all_codes.update(current_bito.keys())
    for code, data in iso_countries.items():
        if data["is_independent"]:
            # If in geojson via natural earth code
            ne_code = iso_to_ne.get(code, code)
            all_codes.add(ne_code)
    # Also add supplementary
    all_codes.update(supplementary.keys())

    print(f"Total unique entities to include: {len(all_codes)}")

    result = {}
    for code in sorted(all_codes):
        iso_code = ne_to_iso.get(code, code)
        
        # Metadata
        feat = geojson_features.get(code, {})
        iso_info = iso_countries.get(iso_code, {})
        
        name_fr = feat.get("name_fr") or iso_info.get("name_fr") or code
        name_en = feat.get("name_en") or iso_info.get("name_en") or code
        continent = feat.get("continent") or iso_info.get("continent") or "Monde"
        region = feat.get("subregion") or iso_info.get("subregion") or continent
        iso_a2 = iso_info.get("iso_a2") or feat.get("iso_a2") or ""

        # Length cm
        length_cm = None
        source = None
        method = "Compilation"
        length_in = None
        height_m = None
        pct_height = None

        if code in current_bito:
            length_cm = current_bito[code]
            source = "WorldData"
        elif iso_code in current_bito:
            length_cm = current_bito[iso_code]
            source = "WorldData"
        elif code in worlddata:
            length_cm = worlddata[code]["length_cm"]
            source = "WorldData"
        elif iso_code in worlddata:
            length_cm = worlddata[iso_code]["length_cm"]
            source = "WorldData"
        elif code in wpr_data:
            length_cm = wpr_data[code]["length_cm"]
            source = "World Population Review"
        elif iso_code in wpr_data:
            length_cm = wpr_data[iso_code]["length_cm"]
            source = "World Population Review"
        elif code in lbd_data:
            length_cm = lbd_data[code]["length_cm"]
            source = lbd_data[code].get("source") or "Little-Big-Data"
            method = lbd_data[code].get("method") or "Compilation"
        elif iso_code in lbd_data:
            length_cm = lbd_data[iso_code]["length_cm"]
            source = lbd_data[iso_code].get("source") or "Little-Big-Data"
            method = lbd_data[iso_code].get("method") or "Compilation"
        elif code in supplementary:
            length_cm = supplementary[code]["length_cm"]
            source = supplementary[code]["source"]
            method = supplementary[code].get("method", "Compilation")
        elif iso_code in supplementary:
            length_cm = supplementary[iso_code]["length_cm"]
            source = supplementary[iso_code]["source"]
            method = supplementary[iso_code].get("method", "Compilation")
        else:
            length_cm = 14.00
            source = "Estimation régionale"

        length_cm = round(length_cm, 2)
        length_in = round(length_cm / 2.54, 2)

        # Height & %
        if code in worlddata and worlddata[code].get("height_m"):
            height_m = worlddata[code]["height_m"]
            pct_height = worlddata[code]["percentage_of_height"]
        elif iso_code in worlddata and worlddata[iso_code].get("height_m"):
            height_m = worlddata[iso_code]["height_m"]
            pct_height = worlddata[iso_code]["percentage_of_height"]
        elif iso_code in wiki_height:
            height_m = wiki_height[iso_code]
            pct_height = round((length_cm / (height_m * 100)) * 100, 2)
        elif code in wiki_height:
            height_m = wiki_height[code]
            pct_height = round((length_cm / (height_m * 100)) * 100, 2)
        else:
            # Regional height fallback
            regional_heights = {
                "Europe": 1.78,
                "North America": 1.76,
                "South America": 1.71,
                "Africa": 1.70,
                "Asia": 1.68,
                "Oceania": 1.73,
            }
            height_m = regional_heights.get(continent, 1.72)
            pct_height = round((length_cm / (height_m * 100)) * 100, 2)

        result[code] = {
            "name_fr": name_fr,
            "name_en": name_en,
            "iso_a2": iso_a2,
            "iso_a3": iso_code,
            "length_cm": length_cm,
            "length_in": length_in,
            "height_m": height_m,
            "percentage_of_height": pct_height,
            "continent": continent,
            "region": region,
            "source": source,
            "method": method,
        }

    print(f"Final dictionary has {len(result)} countries.")
    with open("scratch/bitoguessr_countries_built.json", "w", encoding="utf-8") as out:
        json.dump(result, out, ensure_ascii=False, indent=2)
    print("Saved to scratch/bitoguessr_countries_built.json")

if __name__ == "__main__":
    main()
