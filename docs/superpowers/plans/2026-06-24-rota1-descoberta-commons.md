# Garimpo Rota 1 — Descoberta via Commons direto — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir a triangulação heurística do `reverse-search` por busca no Commons com **filtro de período real** e **ranqueamento que discrimina**, mantendo a interface do CLI, e aposentar o app web/Fly.

**Architecture:** O motor já busca no Commons (`commons_search.search_direct`, `commons_categories.bfs_files`) mas (1) joga a frase PT crua na API — frase PT+data → 0 resultados — e (2) ranqueia com score achatado (tudo nasce `0.5`). Esta mudança insere três peças puras e testáveis — um **mapeador de período**, um **construtor de query** (tira a data da frase e adiciona o termo em inglês) e um **ranqueador** (licença/dimensão/tipo/data-no-período) — e as costura em `triangulate.run`, com escada de fallback. A interface `cli.reverse find` e o JSON de saída não mudam (só ganham campos).

**Tech Stack:** Python 3.12, pydantic v2, httpx (async), pytest. API: MediaWiki Action API do Wikimedia Commons (`commons.wikimedia.org/w/api.php`).

## Global Constraints

- **Interface do CLI imutável:** `cli.reverse find <desc> [--hint-author] [--hint-period] [--hint-region] [--max] [--json]`. Nada de novo flag obrigatório.
- **JSON de saída retrocompatível:** os campos atuais de `ReverseCandidate`/`ReverseResponse` permanecem; só **acrescentar** campos opcionais (`date`, `next`). O `decks-historia/pipeline/scripts/wave_workflow_so_pesquisador.js` parseia esse JSON e **não pode quebrar**.
- **Sem servidor HTTP no caminho de descoberta:** tudo via import/CLI (como hoje).
- **Qualidade/licença:** preferir ≥1500px e licença PD/CC no ranqueamento (não filtrar fora, só ranquear).
- **Rodar testes:** `cd ~/Projetos/garimpo-imagens && .venv/bin/python -m pytest <arquivo> -v`. Testes ficam em `tests/` (layout plano, como `tests/test_smoke.py`).
- **User-Agent** do Commons já vem de `app.sources.base.USER_AGENT` — reusar.

---

### Task 1: Mapeador de período (`periodo.py`)

Converte "século XVI" / "1815" / "Antiguidade" em `{ano_inicio, ano_fim, termo_en}`. Função pura — base da desambiguação.

**Files:**
- Create: `app/reverse/periodo.py`
- Test: `tests/test_periodo.py`

**Interfaces:**
- Consumes: nada.
- Produces: `@dataclass(frozen=True) class Periodo: rotulo: str; ano_inicio: int; ano_fim: int; termo_en: str` e `def mapear_periodo(texto: str | None) -> Optional[Periodo]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_periodo.py
from app.reverse.periodo import mapear_periodo, Periodo


def test_seculo_romano():
    p = mapear_periodo("século XVI")
    assert p == Periodo(rotulo="século XVI", ano_inicio=1500, ano_fim=1599, termo_en="16th-century")


def test_ano_vira_seculo():
    p = mapear_periodo("1815")
    assert p.ano_inicio == 1800 and p.ano_fim == 1899 and p.termo_en == "19th-century"


def test_ano_dentro_de_frase():
    p = mapear_periodo("Desembarque da família real em 1808")
    assert p.termo_en == "19th-century"


def test_antiguidade():
    p = mapear_periodo("Antiguidade")
    assert p.termo_en == "ancient" and p.ano_inicio < 0


def test_vazio_ou_desconhecido():
    assert mapear_periodo("") is None
    assert mapear_periodo(None) is None
    assert mapear_periodo("coisa sem período") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_periodo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.reverse.periodo'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/reverse/periodo.py
"""Mapeia uma expressão de período histórico (PT) para século/intervalo + termo EN
usável na busca do Commons. Função pura, sem rede."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_ROMANOS = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8,
    "ix": 9, "x": 10, "xi": 11, "xii": 12, "xiii": 13, "xiv": 14, "xv": 15,
    "xvi": 16, "xvii": 17, "xviii": 18, "xix": 19, "xx": 20, "xxi": 21,
}
_ERAS_NOMEADAS = {
    "antiguidade": ("ancient", -3000, 476),
    "idade média": ("medieval", 476, 1453),
    "idade media": ("medieval", 476, 1453),
}
_ORDINAL_EN = {
    1: "1st", 2: "2nd", 3: "3rd", 21: "21st",
}


@dataclass(frozen=True)
class Periodo:
    rotulo: str
    ano_inicio: int
    ano_fim: int
    termo_en: str


def _ordinal(n: int) -> str:
    return _ORDINAL_EN.get(n, f"{n}th")


def _seculo_para_periodo(rotulo: str, seculo: int) -> Periodo:
    inicio = (seculo - 1) * 100
    return Periodo(rotulo=rotulo, ano_inicio=inicio, ano_fim=inicio + 99,
                   termo_en=f"{_ordinal(seculo)}-century")


def mapear_periodo(texto: Optional[str]) -> Optional[Periodo]:
    if not texto:
        return None
    low = texto.lower().strip()

    for nome, (termo, ini, fim) in _ERAS_NOMEADAS.items():
        if nome in low:
            return Periodo(rotulo=nome, ano_inicio=ini, ano_fim=fim, termo_en=termo)

    m = re.search(r"s[ée]culo\s+([ivxl]+)", low)
    if m and m.group(1) in _ROMANOS:
        sec = _ROMANOS[m.group(1)]
        return _seculo_para_periodo(f"século {m.group(1).upper()}", sec)

    m = re.search(r"\b(\d{3,4})\b", low)
    if m:
        ano = int(m.group(1))
        sec = ano // 100 + 1
        return _seculo_para_periodo(texto.strip(), sec)

    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_periodo.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add app/reverse/periodo.py tests/test_periodo.py
git commit -m "feat(reverse): mapeador de período (século/ano → intervalo + termo EN)"
```

---

### Task 2: Capturar a data da obra no candidato (`models.py` + `commons_search.py`)

O ranqueamento por período (Task 4) precisa da **data** de cada imagem; hoje `_candidates_from_pages` só extrai licença e autor. Adiciona o campo `date` e o popula do `extmetadata`.

**Files:**
- Modify: `app/reverse/models.py` (classe `ReverseCandidate`)
- Modify: `app/reverse/commons_search.py:_candidates_from_pages`
- Test: `tests/test_candidate_date.py`

**Interfaces:**
- Consumes: nada novo.
- Produces: `ReverseCandidate.date: Optional[str]` populado de `extmetadata.DateTimeOriginal` (fallback `DateTime`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_candidate_date.py
from app.reverse.commons_search import _candidates_from_pages


def _page(extmeta):
    return {
        "title": "File:Exemplo.jpg",
        "imageinfo": [{
            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Exemplo.jpg",
            "url": "https://upload.wikimedia.org/x/Exemplo.jpg",
            "thumburl": "https://upload.wikimedia.org/thumb/Exemplo.jpg",
            "mime": "image/jpeg", "width": 2000, "height": 1500,
            "extmetadata": extmeta,
        }],
    }


def test_extrai_date_time_original():
    pages = [_page({"DateTimeOriginal": {"value": "1808"}})]
    c = _candidates_from_pages(pages, strategy="direct")[0]
    assert c.date == "1808"


def test_fallback_para_datetime():
    pages = [_page({"DateTime": {"value": "1839-01-01"}})]
    c = _candidates_from_pages(pages, strategy="direct")[0]
    assert c.date == "1839-01-01"


def test_sem_data_fica_none():
    pages = [_page({})]
    c = _candidates_from_pages(pages, strategy="direct")[0]
    assert c.date is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_candidate_date.py -v`
Expected: FAIL — `AttributeError: 'ReverseCandidate' object has no attribute 'date'`

- [ ] **Step 3: Write minimal implementation**

In `app/reverse/models.py`, add the field to `ReverseCandidate` (right after `height`):

```python
    width: Optional[int] = None
    height: Optional[int] = None
    date: Optional[str] = None
    source_strategy: str
```

In `app/reverse/commons_search.py`, inside `_candidates_from_pages`, after the `author = ...` line, add:

```python
        raw_date = (meta.get("DateTimeOriginal") or {}).get("value", "") or \
                   (meta.get("DateTime") or {}).get("value", "")
        date = _strip_html(raw_date) or None
```

and pass `date=date,` into the `ReverseCandidate(...)` constructor (right after `height=info.get("height"),`).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_candidate_date.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/reverse/models.py app/reverse/commons_search.py tests/test_candidate_date.py
git commit -m "feat(reverse): capturar data da obra (extmetadata) no candidato"
```

---

### Task 3: Construtor de query (tira a data da frase, adiciona termo EN)

A falha nº 1 ("frase PT + data → 0 resultados") nasce de jogar a frase crua no `gsrsearch`. Esta função limpa a frase e injeta o termo de período em inglês.

**Files:**
- Modify: `app/reverse/commons_search.py` (nova função `construir_busca`)
- Test: `tests/test_construir_busca.py`

**Interfaces:**
- Consumes: `app.reverse.periodo.Periodo` (Task 1).
- Produces: `def construir_busca(description: str, periodo: Optional["Periodo"]) -> str` — string para `gsrsearch`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_construir_busca.py
from app.reverse.commons_search import construir_busca
from app.reverse.periodo import mapear_periodo


def test_remove_ano_e_adiciona_termo_en():
    q = construir_busca("Desembarque da família real no Rio de Janeiro 1808",
                        mapear_periodo("1808"))
    assert "1808" not in q              # número cru sai (zera a busca)
    assert "19th-century" in q          # termo de período entra
    assert "família real" in q.lower()  # o miolo permanece


def test_sem_periodo_passa_frase():
    q = construir_busca("Fenícios", None)
    assert q.strip() == "Fenícios"


def test_remove_palavra_seculo():
    q = construir_busca("Reforma Protestante século XVI", mapear_periodo("século XVI"))
    assert "século" not in q.lower()
    assert "16th-century" in q
    assert "reforma protestante" in q.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_construir_busca.py -v`
Expected: FAIL — `ImportError: cannot import name 'construir_busca'`

- [ ] **Step 3: Write minimal implementation**

Add to `app/reverse/commons_search.py` (top: `from typing import Optional` já existe via `List`; add `from .periodo import Periodo`):

```python
import re as _re  # (já há `import re` no topo; reuse o existente em vez deste alias)

def construir_busca(description: str, periodo: Optional[Periodo]) -> str:
    """Limpa a descrição (remove anos crus e a palavra 'século XX') e injeta o
    termo de período em inglês, para o gsrsearch do Commons não zerar com frase PT."""
    texto = description
    if periodo is not None:
        # remove "século XVI" e anos de 3-4 dígitos da frase
        texto = re.sub(r"s[ée]culo\s+[ivxl]+", " ", texto, flags=re.IGNORECASE)
        texto = re.sub(r"\b\d{3,4}\b", " ", texto)
        texto = re.sub(r"\s+", " ", texto).strip()
        return f"{texto} {periodo.termo_en}".strip()
    return texto.strip()
```

(Use o `import re` já presente no módulo — não adicione um segundo.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_construir_busca.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/reverse/commons_search.py tests/test_construir_busca.py
git commit -m "feat(reverse): construir_busca tira data da frase e injeta termo EN de período"
```

---

### Task 4: Ranqueador que discrimina (`ranking.py`)

Substitui o score achatado por sinais reais: licença PD/CC, dimensão ≥1500px, tipo de obra (penaliza SVG de bandeira/diagrama), data dentro do período, palavra-chave no título, autor.

**Files:**
- Create: `app/reverse/ranking.py`
- Test: `tests/test_ranking.py`

**Interfaces:**
- Consumes: `ReverseCandidate` (com `date`, Task 2), `ReverseQuery`, `Periodo` (Task 1).
- Produces: `def ano_da_data(date: Optional[str]) -> Optional[int]` e `def ranquear(c: ReverseCandidate, query: ReverseQuery, periodo: Optional[Periodo]) -> float`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ranking.py
from app.reverse.models import ReverseCandidate, ReverseQuery, ReverseHint
from app.reverse.periodo import mapear_periodo
from app.reverse.ranking import ano_da_data, ranquear


def _cand(**kw):
    base = dict(file_url="u", thumbnail_url="t", upload_url="up", title="x",
                source_strategy="direct", similarity_score=0.0,
                license="Public domain", width=2000, height=1500, date=None)
    base.update(kw)
    return ReverseCandidate(**base)


def test_ano_da_data():
    assert ano_da_data("1808") == 1808
    assert ano_da_data("circa 1839-01") == 1839
    assert ano_da_data(None) is None


def test_pd_e_alta_res_pontuam_mais_que_svg_bandeira():
    q = ReverseQuery(description="Fenícios")
    bom = _cand(title="Phoenician patera Idalium", license="Public domain", width=3000, height=2000)
    ruim = _cand(title="Phoenician Language Flag.svg", license="CC0", width=300, height=200)
    assert ranquear(bom, q, None) > ranquear(ruim, q, None)


def test_data_no_periodo_pontua_mais():
    q = ReverseQuery(description="família real Rio de Janeiro",
                     hints=ReverseHint(period="1808"))
    per = mapear_periodo("1808")
    dentro = _cand(title="Chegada da corte", date="1816")
    fora = _cand(title="Chegada da corte", date="2010")
    assert ranquear(dentro, q, per) > ranquear(fora, q, per)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_ranking.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.reverse.ranking'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/reverse/ranking.py
"""Ranqueia um ReverseCandidate por sinais que importam para slide de História:
licença, resolução, tipo de obra, data dentro do período, palavra-chave, autor."""
from __future__ import annotations

import re
from typing import Optional

from .models import ReverseCandidate, ReverseQuery
from .periodo import Periodo

_STOP = {"de", "da", "do", "das", "dos", "e", "a", "o", "os", "as", "no", "na", "em"}
_RUIDO = (".svg", "flag", "logo", "icon", "diagram", "map of the world")


def ano_da_data(date: Optional[str]) -> Optional[int]:
    if not date:
        return None
    m = re.search(r"\b(\d{3,4})\b", date)
    return int(m.group(1)) if m else None


def _keywords(text: str) -> list[str]:
    return [w for w in re.findall(r"\w+", (text or "").lower()) if len(w) >= 4 and w not in _STOP]


def ranquear(c: ReverseCandidate, query: ReverseQuery, periodo: Optional[Periodo]) -> float:
    score = 0.4
    title_l = c.title.lower()
    lic = (c.license or "").lower()

    # licença
    if "public domain" in lic or "pd" in lic or "cc0" in lic:
        score += 0.15
    elif "cc by" in lic:
        score += 0.10

    # resolução
    if (c.width or 0) >= 1500 and (c.height or 0) >= 1500:
        score += 0.15
    elif (c.width or 0) >= 1000:
        score += 0.05

    # ruído (bandeira/logo/diagrama/svg)
    if any(tok in title_l for tok in _RUIDO):
        score -= 0.30

    # palavra-chave no título
    for kw in _keywords(query.description):
        if kw in title_l:
            score += 0.06

    # autor
    if query.hints.author:
        ah = query.hints.author.lower()
        surname = ah.split()[-1] if ah else ""
        if ah in (c.author or "").lower() or (surname and surname in title_l):
            score += 0.25

    # data dentro do período
    if periodo is not None:
        ano = ano_da_data(c.date)
        if ano is not None:
            if periodo.ano_inicio <= ano <= periodo.ano_fim:
                score += 0.15
            else:
                score -= 0.15

    return min(1.0, max(0.0, score))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_ranking.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/reverse/ranking.py tests/test_ranking.py
git commit -m "feat(reverse): ranqueador por licença/resolução/tipo/data-no-período"
```

---

### Task 5: Costurar em `triangulate.run` + escada de fallback

Usar `construir_busca` na busca direta, `ranquear` no lugar de `_score_candidate`, e afrouxar o período se vier vazio; expor `next="websearch"` quando ainda assim 0.

**Files:**
- Modify: `app/reverse/models.py` (`ReverseResponse`: campo `next`)
- Modify: `app/reverse/triangulate.py` (`run`)
- Modify: `app/reverse/commons_search.py` (`search_direct` aceita query já construída)
- Test: `tests/test_run_fallback.py`

**Interfaces:**
- Consumes: `construir_busca`, `mapear_periodo`, `ranquear`.
- Produces: `ReverseResponse.next: Optional[str]`; `run` usa as novas peças. `search_direct(client, description, *, limit, busca=None)` — se `busca` for dado, usa-o como gsrsearch.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_fallback.py
import asyncio
import app.reverse.triangulate as tri
from app.reverse.models import ReverseQuery, ReverseHint, ReverseCandidate


def _fake_cand(title):
    return ReverseCandidate(file_url="u", thumbnail_url="t", upload_url="up",
                            title=title, source_strategy="direct",
                            license="Public domain", width=2000, height=1600)


def test_fallback_marca_websearch_quando_vazio(monkeypatch):
    async def vazio(client, description, *, limit=10, busca=None):
        return []
    async def vazio_multi(client, description, *, limit=10):
        return []
    monkeypatch.setattr(tri, "search_direct", vazio)
    monkeypatch.setattr(tri, "search_multilingual", vazio_multi)

    q = ReverseQuery(description="tema inexistente", hints=ReverseHint(period="1808"))
    resp = asyncio.run(tri.run(q, client=object()))
    assert resp.candidates == []
    assert resp.next == "websearch"


def test_resultado_ordenado_por_ranqueador(monkeypatch):
    async def achou(client, description, *, limit=10, busca=None):
        return [_fake_cand("Phoenician Flag.svg"), _fake_cand("Phoenician patera Idalium")]
    async def vazio_multi(client, description, *, limit=10):
        return []
    monkeypatch.setattr(tri, "search_direct", achou)
    monkeypatch.setattr(tri, "search_multilingual", vazio_multi)

    q = ReverseQuery(description="Fenícios patera")
    resp = asyncio.run(tri.run(q, client=object()))
    assert resp.candidates[0].title == "Phoenician patera Idalium"  # ruído .svg/flag perde
    assert resp.next is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_run_fallback.py -v`
Expected: FAIL — `search_direct` não aceita `busca=`, e `ReverseResponse` não tem `next`.

- [ ] **Step 3: Write minimal implementation**

In `app/reverse/models.py`, add to `ReverseResponse`:

```python
    strategies_used: List[str] = Field(default_factory=list)
    next: Optional[str] = None
```

In `app/reverse/commons_search.py`, change `search_direct` signature/body:

```python
async def search_direct(client, description, *, limit=10, busca=None):
    """Single direct MediaSearch query. `busca` overrides the gsrsearch string."""
    pages = await _search_single(client, busca or description, limit=limit)
    return _candidates_from_pages(pages, strategy="direct")
```

In `app/reverse/triangulate.py`: add imports

```python
from .commons_search import TERM_TRANSLATIONS, search_direct, search_multilingual, construir_busca
from .periodo import mapear_periodo
from .ranking import ranquear
```

Replace the direct-task line and the scoring/fallback. The direct task becomes:

```python
        periodo = mapear_periodo(query.hints.period) or mapear_periodo(query.description)
        busca = construir_busca(query.description, periodo)
        direct_task = search_direct(client, query.description, limit=query.max_results, busca=busca)
```

Replace the dedup/score block's `c.similarity_score = _score_candidate(c, query)` with:

```python
            c.similarity_score = ranquear(c, query, periodo)
```

After `unique = unique[: query.max_results]`, before the `return`, add the fallback flag:

```python
        nxt = "websearch" if not unique else None
```

and pass `next=nxt` into `ReverseResponse(...)`. (Deixe `_score_candidate` no arquivo por ora — será removido na Task 7; ele deixa de ser chamado.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_run_fallback.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/reverse/models.py app/reverse/commons_search.py app/reverse/triangulate.py tests/test_run_fallback.py
git commit -m "feat(reverse): run usa período+construir_busca+ranqueador e marca next=websearch"
```

---

### Task 6: Verificação contra a bateria (a/b vs baseline)

Provar a melhora rodando a mesma bateria do diagnóstico contra o baseline versionado.

**Files:**
- Use: `docs/superpowers/baterias/teste_garimpo.py`, `docs/superpowers/baterias/teste_joanino.py`
- Compare: `docs/superpowers/baterias/baseline-2026-06-24-*.out`

- [ ] **Step 1: Rodar a suíte de testes unitários inteira**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: PASS — todos os testes das Tasks 1–5 verdes + a suíte pré-existente intacta.

- [ ] **Step 2: Rodar a bateria de descoberta (rede)**

Run: `.venv/bin/python docs/superpowers/baterias/teste_garimpo.py | tee /tmp/rota1_garimpo.out`
Expected vs baseline (`baseline-2026-06-24-teste_garimpo.out`): Reforma e Fenícios com score **espalhado** (não mais tudo 0.55) e top-3 com ≥2 relevantes; `--hint-period` muda o resultado (antes era idêntico).

- [ ] **Step 3: Rodar a bateria do deck joanino (rede)**

Run: `.venv/bin/python docs/superpowers/baterias/teste_joanino.py | tee /tmp/rota1_joanino.out`
Expected vs baseline (`baseline-2026-06-24-teste_joanino.out`): a **PINTURA** (frase PT) sai de **0 candidatos → ≥1 relevante**; o **MAPA** de período sai de "South America 1700" → mapa do séc. XIX; Debret e globo continuam ≥0.79.

- [ ] **Step 4: Registrar o resultado**

```bash
cp /tmp/rota1_garimpo.out docs/superpowers/baterias/depois-rota1-teste_garimpo.out
cp /tmp/rota1_joanino.out docs/superpowers/baterias/depois-rota1-teste_joanino.out
git add docs/superpowers/baterias/depois-rota1-*.out
git commit -m "test(reverse): bateria pós-Rota 1 (antes×depois) — pintura 0→achada, mapa corrigido"
```

> Se a pintura ainda vier 0 ou o mapa não melhorar, **não declarar pronto**: voltar à Task 3 (termos da query) ou Task 4 (sinais do ranqueador) e iterar antes de seguir.

---

### Task 7: Aposentar o app web/Fly + limpar a triangulação morta

Remover o app web ocioso e o código de score achatado que deixou de ser chamado.

**Files:**
- Remove/reduce: `app/main.py` (rotas web/auth/biblioteca/SMTP), `fly.toml`
- Modify: `app/reverse/triangulate.py` (remover `_score_candidate` e helpers órfãos)
- Test: a suíte inteira (`tests/`) deve continuar verde após a remoção.

- [ ] **Step 1: Remover `_score_candidate` (e `_keywords`/`_expand_for_category_match` se ficarem órfãos) de `triangulate.py`**

Conferir com `grep -rn "_score_candidate\|_expand_for_category_match" app/ cli/ tests/` que não há mais uso, então apagar as funções.

- [ ] **Step 2: Rodar os testes**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: PASS (nada quebrou — a função removida não era mais chamada).

- [ ] **Step 3: Reduzir/remover o app web**

`grep -rn "from app.main\|app.main" .` para confirmar que nada de descoberta importa o app web. Remover de `app/main.py` as rotas web/auth/biblioteca/coleções/SMTP (manter apenas o que `cli`/`reverse`/`sources` importam, se algo). Remover `fly.toml` e referências de deploy no README.

- [ ] **Step 4: Rodar a suíte de novo + smoke do CLI**

Run: `.venv/bin/python -m pytest tests/ -v && .venv/bin/python -m cli.reverse find "Fenícios" --max 3`
Expected: testes verdes + o CLI ainda lista candidatos.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(reverse): aposentar app web/Fly e remover triangulação de score achatado"
```

> **Passo manual do Thiago (fora do repo):** destruir o app no Fly — `fly apps destroy acervo-historia-matostf` (e o volume `acervo_data`). O Claude entrega o comando; o login Fly é seu.

---

## Self-Review

**1. Spec coverage:**
- Objetivo 1 (Commons direto, interface mantida) → Tasks 3, 5 (busca via `construir_busca`; CLI/JSON intactos). ✓
- Objetivo 2 (`--hint-period` real) → Tasks 1, 3, 4 (mapeador + termo na query + data-no-período no rank). ✓
- Objetivo 3 (ranqueamento que discrimina) → Task 4. ✓
- Objetivo 4 (escada de fallback) → Task 5 (`next=websearch`; afrouxar período via `mapear_periodo` separado da descrição). ✓
- Objetivo 5 (preservar hint-author/hash/dedup/conectores/coletor) → intocados (subcategory_walk permanece em `run`; hasher/dedup/acervos não tocados). Promover `coleta-lote`: ação de merge de branch, registrada na spec §F (fora deste plano de código; é um `git merge`). ✓
- Objetivo 6 (aposentar web/Fly) → Task 7. ✓
- Verificação (bateria + baseline) → Task 6. ✓

**2. Placeholder scan:** sem "TODO"/"etc."; todo step de código tem o código. ✓

**3. Type consistency:** `Periodo(rotulo, ano_inicio, ano_fim, termo_en)` usado igual em Tasks 1/3/4; `mapear_periodo`, `construir_busca`, `ranquear`, `ano_da_data` com as mesmas assinaturas onde citadas; `ReverseCandidate.date` (Task 2) consumido por `ranquear`/`ano_da_data` (Task 4); `search_direct(..., busca=None)` definido na Task 5 e usado em `run`. ✓

> **Nota de escopo:** "promover `coleta-lote` a oficial" (spec §F) é um merge de branch, não código novo — fazer com `git checkout master && git merge coleta-lote` quando o Thiago aprovar, fora deste plano. O conserto do filtro de período no `coletar.py` (se desejado) seria um plano seguinte.
