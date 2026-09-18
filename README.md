# venator

Command-line tool for **finding openly licensed images in museum and archive
open-access collections**, and for **recording, for every candidate, who made
it, where it lives and under which licence it may be reused**.

Built to source imagery for history lessons and for teaching material that is
sold, which is why the licence check is strict: anything that is not public
domain, CC0, CC BY or CC BY-SA is rejected, and every accepted image comes
with a ready-to-paste credit line.

*Venator* is Latin for "hunter". Portuguese documentation: [README.pt-BR.md](README.pt-BR.md).

## What it does

- **`cli.reverse find`** — describe an image in natural language (Portuguese
  or English), optionally hint author, period or region, and get a ranked
  list of Wikimedia Commons candidates with **author, licence, dimensions,
  date and canonical file URL**. Search triangulates three strategies:
  direct text search, multilingual expansion (PT → EN/FR/DE) and a walk of
  the author's Commons category tree.
- **`cli.reverse normalize`** — canonicalise any Commons URL (thumbnail,
  upload, redirect) to the `File:` page, so provenance is recorded once and
  unambiguously.
- **`cli.reverse hash` / `dedup`** — perceptual hashes (pHash + dHash) of an
  image and duplicate check against a manifest, so the same picture is not
  sourced twice under two names.
- **`cli.coletar`** — batch collector: runs a search plan across several
  sources, classifies each licence, and writes a normalised record per image
  for a downstream library ([`thesaurus`](https://github.com/matostf/thesaurus)).
- **`scripts/acervos.py`** — thin REST wrapper for archives without a
  dedicated adapter (Gallica/BnF, Library of Congress, Walters, DPLA, Open
  Library).

## Open-access sources

| Source | Adapter | Key needed | Notes |
|---|---|---|---|
| Wikimedia Commons | `venator/app/sources/wikimedia.py`, `venator/app/reverse/` | no | licence and artist read from `extmetadata`; complies with the Wikimedia User-Agent policy |
| Smithsonian Open Access (EDAN) | `venator/app/sources/smithsonian.py` | free, api.data.gov | CC0 records only |
| Europeana | `venator/app/sources/europeana.py` | free | queried with `reusability=open` |
| The Met Collection API | `venator/app/sources/met.py` | no | open-access (CC0) objects |
| Art Institute of Chicago + IIIF | `venator/app/sources/artic.py` | no | public-domain flag respected |
| Gallica / BnF (SRU) | `scripts/acervos.py` | no | |
| Library of Congress | `scripts/acervos.py` | no | |
| Rijksmuseum (linked data) | `scripts/acervos.py` | no | |
| Walters Art Museum | `external/walters-api` (git submodule, CC0 data dump) | no | |
| DPLA | `scripts/acervos.py` | free | |

Every adapter normalises its output to one record
(`venator/app/sources/base.py`): `id, source, title, thumbnail, full_image,
source_url, license, creator, width, height`, plus an `attribution` property
that renders the credit line.

## Licence policy (the part that matters)

`venator/app/licenca.py` classifies each licence string into three states,
**fail-closed**: an empty or unrecognised licence is rejected, and the
non-commercial / no-derivatives markers are tested *before* the "BY" match,
because otherwise `CC BY-NC` would pass as `CC BY`.

| input licence string | state | category | generated credit |
|---|---|---|---|
| `Public domain` | free | Public domain | (none required) |
| `CC0` | free | CC0 | (none required) |
| `CC BY-SA 4.0` | attribution | CC BY-SA | `Carole Raddato, CC BY-SA, via Wikimedia Commons` |
| `CC BY 2.0` | attribution | CC BY | `Carole Raddato, CC BY, via Wikimedia Commons` |
| `CC BY-NC 2.0` | **rejected** | | |
| `CC BY-ND` | **rejected** | | |
| `All rights reserved` | **rejected** | | |
| *(empty / unknown)* | **rejected** | | |

The table above is the actual output of `classificar()` for those inputs; the
behaviour is pinned by `tests/test_licenca.py`.

## Worked example

```bash
python -m cli.reverse find "Debret desembarque" --hint-author "Debret" --max 3 --json
```

```json
{
  "candidates": [
    {
      "file_url": "https://commons.wikimedia.org/wiki/File:Debret_-_Estudo_para_o_desembarque_de_D._Leopoldina_no_Brasil.jpg",
      "title": "Debret - Estudo para o desembarque de D. Leopoldina no Brasil.jpg",
      "author": "Jean-Baptiste Debret",
      "license": "Public domain",
      "width": 4799,
      "height": 2888,
      "date": "1818",
      "source_strategy": "direct",
      "similarity_score": 1.0
    }
  ],
  "strategies_used": ["direct"]
}
```

(Output trimmed to one candidate and to the fields that matter for
provenance; the full JSON also carries thumbnail and upload URLs.) Note the
search vocabulary: MediaWiki search requires every word to match, so a short
description with an author hint beats a long sentence.

## Install and run

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # optional keys: Smithsonian, Europeana, DPLA
git submodule update --init     # Walters CC0 data dump (optional)

cd venator
python -m cli.reverse find "Roman aqueduct Segovia" --max 5
python -m cli.reverse normalize "https://upload.wikimedia.org/wikipedia/commons/thumb/..."
python -m cli.reverse hash picture.jpg
python -m cli.reverse dedup picture.jpg --manifest manifest.json
python -m cli.coletar --plano plan.json --out ./out --dry
```

Tests (19, offline, no network):

```bash
python -m pytest -q
```

Requires Python 3.12+. Dependencies: httpx, Pillow, imagehash, pydantic,
python-dotenv.

## Design notes

- **Discovery only.** This tool returns URLs and metadata; it does not
  download or store images. Storage, deduplication at scale and the gallery
  live in the sister project `thesaurus`; the curated public-domain
  collection built with these tools is
  [`armarium`](https://github.com/matostf/armarium).
- **Commons first.** Wikimedia Commons carries machine-readable licence and
  artist fields for every file, which makes provenance capture reliable. The
  other sources are fallbacks when Commons has nothing usable.
- **History.** Started as a web app (FastAPI on Fly.io) with a personal
  library; that layer was retired in June 2026 as redundant, and the
  discovery engine and collector remained. Default branch: `master`.

## Author

Thiago F. Matos — historian and teacher (UDESC), author of history teaching
material, currently working in AI data annotation and training in Machine
Learning & Computer Vision (Carreira Tech, Santa Catarina). Code under the
MIT licence; every image found with this tool keeps the licence recorded by
its holding institution.
