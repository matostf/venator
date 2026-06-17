# IDEIAS — garimpo-imagens

Backlog de ideias antes de virarem PRs/issues. Cada item tem **status**, **why** e
**escopo grosso**. Refinar quando for puxar pra implementação.

---

## 🆕 [proposto] Pivotar: de buscador de museus → banco de imagens próprio

**Origem:** sessão de 2026-06-15, ~03h — Thiago.

**O que muda:**
- **Hoje:** o app é um *broker* — faz requests em tempo real às APIs de museus abertos (Smarthistory, Wikimedia, etc) e devolve resultados.
- **Vira:** um *repositório próprio* com imagens já curadas e catalogadas pelo Thiago em outros projetos, com busca local rápida. (As APIs externas podem continuar como *fallback* opcional.)

**Sementes pra ingestão imediata (já catalogadas hoje, dois projetos):**

| Origem | Onde | Formato | Volume hoje |
|---|---|---|---|
| `acervo-didatico-historia` | `~/Projetos/acervo-didatico-historia/*.jpg` + manifesto | arquivos `.jpg` locais + JSON de metadados | **143 imagens** |
| `decks-historia` (pipeline) | `~/Projetos/decks-historia/pipeline/data/wave-1.json` (campo `resolucoes[].resolucao`) | URL canônica + autor + licença + nota | **103 URLs verificadas** |

Total potencial bruto: ~246 imagens (alguma sobreposição esperada — dedup por URL do Commons ou hash do arquivo).

**✅ Decisões fechadas (2026-06-15, ~03h)**

- **Modelo de uso**: 100% pessoal, local, sem audiência externa. Sem preocupação com licenciamento, escala, multi-tenant, auth. Se um dia for distribuir/vender, Thiago pede as adaptações.
- **Storage**: imagens **completas** baixadas no HD do Thiago (não URL, não thumbnail, não cloud). Junto com **todos os metadados** que o app já mostra hoje (autor, data, museu, técnica, descrição etc).
- **Implicação arquitetural**: app provavelmente **deixa de ser Fly.io público** e vira **local-first** (FastAPI em `localhost` + SQLite + imagens em pasta no HD). Confirmar.
- **Pré-requisito implícito**: plano de **backup** do diretório de imagens (rsync pro NAS, HD externo, BackBlaze etc) — sem isso, o "local" vira ponto único de falha.

**Decisões pendentes:**

1. **Schema unificado** — vai precisar abrigar:
   - Campos do manifesto do `acervo-didatico-historia` (provavelmente: id, era, slide-slot, autor, licença, fonte, caminho_local)
   - Campos do `wave-1.json` (aulaId, slideN, obraConfirmada, autor, licenca, acervo, url, dominioPublico, status, nota)
   - Campos novos: hashtags livres, era/período (BNCC), tipo (pintura/foto/mapa/etc), thumbnail_url

2. **Modelo de ingestão**:
   - (a) One-shot: importa tudo, fim
   - (b) Sync contínuo: cada `git push` nos projetos-fonte dispara webhook → reingere
   - (c) CLI `python ingest.py --from ~/Projetos/acervo-didatico-historia` rodada manualmente
   - Recomendado: **(c)** pra começar; promover pra (b) quando estabilizar.

3. **Busca**:
   - Full-text por título/descrição (SQLite FTS5 é suficiente — banco local não pede Postgres)
   - Filtros: era, hashtag, licença (DP-only vs CC OK), tipo
   - Ordenação por relevância vs. resolução vs. data

4. **Identidade do projeto após o pivô**:
   - Mantém o nome `garimpo-imagens`?
   - O atual broker de museus (Smarthistory etc) vira **feature secundária** ou **deprecado**?
   - Atenção: nos seus deploys, `garimpo-imagens` está em `versao-galeria-noturna` (branch design não mesclado) — a mudança de paradigma é boa hora pra fechar essa decisão de UI também.

5. **Plano de backup do diretório** (consequência do storage local):
   - rsync semanal pro NAS / HD externo / cloud privada
   - Snapshot do SQLite + arquivos junto (consistência)
   - Quem dispara: cron `~/dotfiles/`? script manual? hook do app?

**Pré-requisitos pra implementação:**
- Fechar a [[paleta-uis-internas-terminal-like]]? Não — esse projeto é cliente-facing (Fly.io público), não vale a paleta interna.
- Decidir antes: pivô vs. broker + agregação. Talvez fique mais limpo iniciar um repo novo `banco-imagens` e manter o atual como broker, ou aposentar o broker. Conversar.
