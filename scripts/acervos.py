#!/usr/bin/env python3
"""
Wrapper único para buscas em acervos sem MCP pronto.

Cobre 5 acervos via REST direta — todos retornam lista normalizada de dicts
no formato: {title, creator, year, url, license, source, raw}.

Uso (CLI):
    python3 scripts/acervos.py <source> "<query>" [--max N]

Sources: bnf | loc | walters | dpla | openlib

Variáveis de ambiente esperadas:
    DPLA_API_KEY      — obrigatória para DPLA (obter via curl POST a
                         https://api.dp.la/v2/api_key/SEU_EMAIL)
    WALTERS_API_KEY   — obrigatória para Walters (cadastro pendente)

Acervos SEM chave (funcionam direto): BnF, LoC, Open Library.

Migração futura: este arquivo é um starter; quando ganhar 200+ linhas ou
mais de 5 fontes, migrar para módulo dedicado no projeto `garimpo-imagens`
(que já tem CLI estruturado `cli.reverse` para Wikimedia Commons).
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UA = "garimpo-imagens/0.1 (matostf@gmail.com)"


def _fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def _fetch_xml(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/xml"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return ET.fromstring(r.read())


def bnf_search(query, maxn=10):
    """BnF Gallica via SRU (Search/Retrieve via URL). Retorna XML Dublin Core."""
    q = f'dc.title all "{query}"'
    url = (
        "https://gallica.bnf.fr/SRU"
        f"?operation=searchRetrieve&version=1.2&query={urllib.parse.quote(q)}"
        f"&maximumRecords={maxn}&recordSchema=dc"
    )
    root = _fetch_xml(url)
    ns = {
        "srw": "http://www.loc.gov/zing/srw/",
        "dc": "http://purl.org/dc/elements/1.1/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
    }
    out = []
    for rec in root.findall(".//srw:record", ns):
        data = rec.find(".//oai_dc:dc", ns)
        if data is None:
            data = rec
        title = (data.findtext("dc:title", default="", namespaces=ns) or "").strip()
        creator = (data.findtext("dc:creator", default="", namespaces=ns) or "").strip()
        date = (data.findtext("dc:date", default="", namespaces=ns) or "").strip()
        identifier = (data.findtext("dc:identifier", default="", namespaces=ns) or "").strip()
        rights = (data.findtext("dc:rights", default="", namespaces=ns) or "").strip()
        out.append({
            "title": title,
            "creator": creator,
            "year": date,
            "url": identifier,
            "license": rights or "BnF — verificar caso a caso",
            "source": "bnf-gallica",
        })
    return out


def loc_search(query, maxn=10):
    """Library of Congress JSON API. Sem chave.

    Atenção: WAF (Akamai) bloqueia User-Agents simples com 403. Usar
    headers browser-like. Rate limit: 20 req/min; excesso → bloqueio 1h.
    """
    url = (
        "https://www.loc.gov/search/?fo=json"
        f"&q={urllib.parse.quote(query)}"
        f"&c={maxn}"
    )
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "application/json,text/html;q=0.9",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Referer": "https://www.loc.gov/",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8", errors="replace"))
    out = []
    for item in data.get("results", [])[:maxn]:
        out.append({
            "title": item.get("title", ""),
            "creator": (item.get("contributor") or [""])[0] if isinstance(item.get("contributor"), list) else item.get("contributor", ""),
            "year": item.get("date", "") or item.get("dates", [""])[0] if isinstance(item.get("dates"), list) else "",
            "url": item.get("id", "") or item.get("url", ""),
            "license": "LoC — sem restrições conhecidas (verificar campo rights)",
            "source": "library-of-congress",
        })
    return out


_WALTERS_DUMP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "external", "walters-api")
_WALTERS_CACHE = None
_WALTERS_CREATORS = None


def _walters_load():
    """Carrega art.csv do dump GitHub do Walters (21878 obras) em memória."""
    global _WALTERS_CACHE
    if _WALTERS_CACHE is not None:
        return _WALTERS_CACHE
    import csv
    rows = []
    with open(f"{_WALTERS_DUMP_DIR}/art.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    _WALTERS_CACHE = rows
    return rows


def _walters_load_creators():
    """Carrega creators.csv como dict {id: name}."""
    global _WALTERS_CREATORS
    if _WALTERS_CREATORS is not None:
        return _WALTERS_CREATORS
    import csv
    creators = {}
    with open(f"{_WALTERS_DUMP_DIR}/creators.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cid = row.get("id", "")
            name = row.get("name", "") or row.get("sort_name", "")
            date = row.get("date", "").strip()
            creators[cid] = f"{name}{' ' + date if date else ''}"
    _WALTERS_CREATORS = creators
    return creators


def _walters_resolve_creators(creators_field):
    """Resolve 'id1|id2|id3' → 'Nome 1; Nome 2; Nome 3' (sem duplicatas)."""
    if not creators_field:
        return ""
    creators_map = _walters_load_creators()
    ids = [i.strip() for i in creators_field.split("|") if i.strip()]
    seen = set()
    names = []
    for cid in ids:
        name = creators_map.get(cid, f"(unknown id {cid})")
        if name not in seen:
            seen.add(name)
            names.append(name)
    return "; ".join(names)


def walters_search(query, maxn=10):
    """Walters Art Museum via dump CSV local (API v1 descontinuada em 2023).

    Busca string-match (case-insensitive) em Title + Classification +
    Description + Keywords. Carrega 21878 obras na primeira chamada e
    mantém em memória.
    """
    art_csv = f"{_WALTERS_DUMP_DIR}/art.csv"
    if not os.path.exists(art_csv):
        raise RuntimeError(
            f"Walters CSV não encontrado em {art_csv}. "
            "Rodar: git clone --depth 1 https://github.com/WaltersArtMuseum/walters-api.git "
            "em external/ (ou: git submodule update --init)"
        )
    rows = _walters_load()
    q = query.lower()
    matches = []
    for row in rows:
        haystack = " ".join([
            row.get("Title", ""),
            row.get("Classification", ""),
            row.get("Description", ""),
            row.get("Keywords", ""),
            row.get("Culture", ""),
            row.get("Period", ""),
        ]).lower()
        if q in haystack:
            matches.append(row)
            if len(matches) >= maxn:
                break
    out = []
    for row in matches:
        out.append({
            "title": row.get("Title", ""),
            "creator": _walters_resolve_creators(row.get("Creators", "")),
            "year": row.get("DateText", ""),
            "url": row.get("ResourceURL", ""),
            "license": "Walters Art Museum — verificar caso a caso (em geral CC-BY-SA ou PD)",
            "source": "walters-art-museum",
            "classification": row.get("Classification", ""),
            "culture": row.get("Culture", ""),
        })
    return out


def dpla_search(query, maxn=10):
    """DPLA API. Requer DPLA_API_KEY env var."""
    key = os.environ.get("DPLA_API_KEY")
    if not key:
        raise RuntimeError("DPLA_API_KEY não configurada. Obter via: curl -X POST https://api.dp.la/v2/api_key/SEU_EMAIL")
    url = (
        "https://api.dp.la/v2/items"
        f"?q={urllib.parse.quote(query)}&page_size={maxn}&api_key={key}"
    )
    data = _fetch_json(url)
    out = []
    for item in data.get("docs", [])[:maxn]:
        src = item.get("sourceResource", {})
        out.append({
            "title": src.get("title", [""])[0] if isinstance(src.get("title"), list) else src.get("title", ""),
            "creator": src.get("creator", [""])[0] if isinstance(src.get("creator"), list) else src.get("creator", ""),
            "year": src.get("date", {}).get("displayDate", "") if isinstance(src.get("date"), dict) else "",
            "url": item.get("isShownAt", ""),
            "license": src.get("rights", "DPLA — verificar institução de origem"),
            "source": "dpla",
        })
    return out


def _rijks_extract_title(item):
    """Extrai um título 'human-readable' de um Linked Art item."""
    for ib in item.get("identified_by", []) or []:
        if ib.get("type") == "Name":
            content = ib.get("content")
            if content:
                return content
    return ""


def _rijks_extract_creator(item):
    prod = item.get("produced_by") or {}
    actors = []
    for ag in prod.get("carried_out_by", []) or []:
        for ib in ag.get("identified_by", []) or []:
            if ib.get("type") == "Name":
                actors.append(ib.get("content") or "")
    return "; ".join(filter(None, actors))


def _rijks_extract_year(item):
    prod = item.get("produced_by") or {}
    ts = prod.get("timespan") or {}
    for ib in ts.get("identified_by", []) or []:
        if ib.get("type") == "Name":
            return ib.get("content") or ""
    begin = (ts.get("begin_of_the_begin") or "")[:4]
    end = (ts.get("end_of_the_end") or "")[:4]
    return f"{begin}–{end}".strip("–") or ""


def _rijks_extract_image(item):
    for r in item.get("representation", []) or []:
        rid = r.get("id")
        if rid:
            return rid
    return ""


def rijks_search(query, maxn=10):
    """Rijksmuseum Search API (Linked Art). SEM chave.

    Faz 1 chamada à Search API + N chamadas ao Persistent ID Resolver para
    enriquecer cada resultado com título/criador/data/imagem.

    Aceita query no formato 'creator=Rembrandt&type=painting' OU query livre
    (vira parâmetro 'title=').
    """
    base = "https://data.rijksmuseum.nl/search/collection"
    if "=" in query:
        url = f"{base}?{query}"
    else:
        url = f"{base}?title={urllib.parse.quote(query)}"
    data = _fetch_json(url)
    ids = [it.get("id") for it in data.get("orderedItems", []) if it.get("id")][:maxn]
    out = []
    for lod_id in ids:
        try:
            item = _fetch_json(lod_id)
        except Exception as e:
            out.append({
                "title": "(falha ao resolver)",
                "creator": "",
                "year": "",
                "url": lod_id,
                "license": "Rijksmuseum — CC0 (verificar caso a caso)",
                "source": "rijksmuseum",
                "error": str(e),
            })
            continue
        out.append({
            "title": _rijks_extract_title(item),
            "creator": _rijks_extract_creator(item),
            "year": _rijks_extract_year(item),
            "url": lod_id,
            "image": _rijks_extract_image(item),
            "license": "Rijksmuseum — CC0 (verificar campo subject_to)",
            "source": "rijksmuseum",
        })
    return out


def harvard_search(query, maxn=10):
    """Harvard Art Museums API. Requer HARVARD_API_KEY env var.

    Atribuição obrigatória 'Harvard Art Museums' em cada uso.
    """
    key = os.environ.get("HARVARD_API_KEY")
    if not key:
        raise RuntimeError("HARVARD_API_KEY não configurada. Cadastrar em harvardartmuseums.org/collections/api")
    url = (
        "https://api.harvardartmuseums.org/object"
        f"?apikey={key}&q={urllib.parse.quote(query)}&size={maxn}&hasimage=1"
    )
    data = _fetch_json(url)
    out = []
    for rec in data.get("records", [])[:maxn]:
        people = rec.get("people") or []
        creator = people[0].get("name", "") if people else ""
        images = rec.get("images") or []
        image_url = images[0].get("baseimageurl", "") if images else ""
        out.append({
            "title": rec.get("title", ""),
            "creator": creator,
            "year": rec.get("dated", ""),
            "url": rec.get("url", ""),
            "image": image_url,
            "license": "Harvard Art Museums — atribuição obrigatória; verificar imagepermissionlevel",
            "source": "harvard-art-museums",
            "classification": rec.get("classification", ""),
            "culture": rec.get("culture", ""),
        })
    return out


def smithsonian_search(query, maxn=10):
    """Smithsonian Open Access API. Requer DATA_GOV_API_KEY env var."""
    key = os.environ.get("DATA_GOV_API_KEY")
    if not key:
        raise RuntimeError("DATA_GOV_API_KEY não configurada. Cadastrar em api.data.gov/signup")
    url = (
        "https://api.si.edu/openaccess/api/v1.0/search"
        f"?q={urllib.parse.quote(query)}&rows={maxn}&api_key={key}"
    )
    data = _fetch_json(url)
    out = []
    for row in (data.get("response") or {}).get("rows", [])[:maxn]:
        content = row.get("content", {})
        freetext = content.get("freetext", {})
        notes = freetext.get("notes", [])
        summary = next((n.get("content", "") for n in notes if n.get("label") == "Summary"), "")
        cite = next((n.get("content", "") for n in notes if n.get("label") == "Cite as"), "")
        date = next((d.get("content", "") for d in freetext.get("date", [])), "")
        creator = next((n.get("content", "") for n in freetext.get("name", []) if n.get("label") == "Creator"), "")
        out.append({
            "title": row.get("title", ""),
            "creator": creator,
            "year": date,
            "url": (content.get("descriptiveNonRepeating") or {}).get("record_link", ""),
            "license": "Smithsonian Open Access — CC0 quando metadata.usage_flags indica",
            "source": "smithsonian",
            "summary": summary,
            "citation": cite,
        })
    return out


def openlib_search(query, maxn=10):
    """Open Library REST. Sem chave."""
    url = (
        "https://openlibrary.org/search.json"
        f"?q={urllib.parse.quote(query)}&limit={maxn}"
    )
    data = _fetch_json(url)
    out = []
    for item in data.get("docs", [])[:maxn]:
        authors = item.get("author_name", [])
        out.append({
            "title": item.get("title", ""),
            "creator": ", ".join(authors[:3]) if authors else "",
            "year": str(item.get("first_publish_year", "")),
            "url": f"https://openlibrary.org{item.get('key', '')}",
            "license": "Open Library — metadados livres; texto integral varia",
            "source": "open-library",
        })
    return out


SOURCES = {
    "bnf": bnf_search,
    "loc": loc_search,
    "walters": walters_search,
    "dpla": dpla_search,
    "openlib": openlib_search,
    "rijks": rijks_search,
    "si": smithsonian_search,
    "harvard": harvard_search,
}


def main():
    ap = argparse.ArgumentParser(description="Busca multi-acervo (BnF, LoC, Walters, DPLA, Open Library)")
    ap.add_argument("source", choices=list(SOURCES.keys()))
    ap.add_argument("query")
    ap.add_argument("--max", type=int, default=10)
    args = ap.parse_args()
    try:
        results = SOURCES[args.source](args.query, args.max)
    except Exception as e:
        print(json.dumps({"error": str(e), "source": args.source}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"source": args.source, "query": args.query, "count": len(results), "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
