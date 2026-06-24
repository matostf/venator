# Spec — Garimpo Rota 1: descoberta via Commons direto + aposentadoria do app web

*(design doc · 2026-06-24)*

## Contexto e problema

O `garimpo-imagens` tem **personalidade dupla**: (a) um **app web/galeria no Fly** (login, contas, SMTP, biblioteca pessoal) que está **ocioso** (3 imagens, 0 usuários, máquina parada) e duplica o `banco-imagens`; e (b) uma **biblioteca/CLI de descoberta** (`cli.reverse find` + conectores de acervo + hash/dedup) que é o que **de fato** é usado (pelo pipeline do `decks-historia` e pela skill `reverse-search`).

O motor de descoberta atual (`app/reverse/triangulate.py`) é uma **heurística caseira** — MediaSearch direto + multilíngue + BFS de subcategorias por autor + score por sobreposição de palavras. Diagnóstico empírico (2026-06-24, bateria de testes):

- **Score achatado e não-discriminante:** quase tudo empata em `0.55`/`0.63`; obra relevante e ruído ficam lado a lado.
- **Cego a frases em PT:** descrição em português com data → **0 candidatos** (ex.: "Desembarque da família real… no Rio… 1808" → 0; "Reforma Protestante século XVI" → puxa livro aleatório).
- **`--hint-period` é inerte:** só dá bônus se a string ("século XVI") aparecer *literalmente no título* da imagem — o que nunca acontece. Não traduz período em data nem filtra por categoria. Resultado idêntico com e sem a flag em 4/4 temas testados.
- **Fraco para conceito abstrato** (Hebreus → 0/4: bandeira, igreja "Jewry", meme) e **para mapas** (mapa de 1815 → "South America 1700").
- **Forte com "alça":** com `--hint-author "Debret"` o score salta para **0.98** (caminha pelas subcategorias do autor); com termo canônico em inglês (`Brazil orthographic projection`) acha o SVG exato (0.79). Ou seja: o garimpo acerta quando recebe uma alça que o Commons entende (autor ou termo canônico EN); erra com frase descritiva em PT.

**Decisão (Thiago, 2026-06-24):** adotar a **Rota 1** — substituir a triangulação heurística por **busca direta no Wikimedia Commons + filtro de período real**, mantendo a interface do CLI, e **aposentar o app web/Fly**. O `banco-imagens` segue como cofre/galeria (navegar); o garimpo vira o **motor de descoberta enxuto** + utilitários + coletor em lote.

## Objetivos

1. **Trocar o motor de `find`** de heurística própria para **busca direta no Commons** (a fonte que tem as imagens e as etiqueta), **preservando a interface `cli.reverse find`** (mesmos flags, mesmo JSON de saída) para **não quebrar** o pipeline do `decks-historia` nem a skill `reverse-search`.
2. **Tornar `--hint-period` real:** mapear "século XVI"/"1815"/"Antiguidade" → categorias/intervalos de data do Commons (`Category:16th-century paintings`, `Category:1815 maps`, etc.) que **filtram de verdade**. (É o pedido central do Thiago: desambiguar por período.)
3. **Ranqueamento que discrimina:** priorizar obra histórica (pintura/gravura/mapa/foto-de-artefato, PD/CC, ≥1500px, data dentro do período) e penalizar ruído (SVG de bandeira/logo, diagrama, foto moderna quando a intenção é histórica).
4. **Escada de fallback** para nunca devolver 0 sem tentar: query estruturada → afrouxar período → re-traduzir PT→EN → sinalizar "vá ao WebSearch".
5. **Preservar o que funciona:** o `--hint-author` (caminhada de subcategorias, o caminho mais forte), `hash`/`dedup`/`normalize`, os conectores multi-acervo (`scripts/acervos.py`) e o **coletor em lote** (`cli/coletar.py`, hoje na branch `coleta-lote` — promover a oficial).
6. **Aposentar:** o app web (`app/main.py` rotas web/auth/biblioteca), SMTP, o deploy no Fly, e os internos da triangulação de score achatado.

## Não-objetivos

- Não construir nova galeria de navegação — isso é o `banco-imagens`.
- O `find` **não baixa** imagem (continua devolvendo URLs/metadados); quem baixa é o `render_themed.py`/`banco-imagens`.
- O CLI **não** chama WebSearch sozinho — o agente (pesquisador do decks) orquestra o fallback, como hoje.
- Não resolver, nesta v1, o caso "conceito abstrato sem objeto" (Hebreus) — fica anotado como trabalho futuro (expansão por objetos associados).

## Design

### A. Construtor de query (brief PT → query Commons) — o conserto central
Entrada: `description` (PT) + hints. Saída: uma query estruturada para o Commons.
- **Extrair e traduzir** os termos-chave PT→EN (reaproveitar a parte multilíngue, mas como termos da query, não como "estratégia" separada).
- **Separar a data/período da frase:** "Desembarque da família real… 1808" → termos {família real, Rio de Janeiro} + período {1808 → século XIX}. (Hoje a data crua na frase zera a busca.)
- **Se `--hint-author`:** manter a caminhada de subcategorias (`Category:<autor>`) — comprovadamente o caminho de maior precisão (0.98).
- **Se `--hint-period`:** anexar filtro de categoria/data (ver módulo E).
- **Se `--hint-region`:** anexar como termo/categoria.

### B. Backend de busca no Commons
Substituir a triangulação por chamada direta à API do Commons:
- **MediaSearch** (o mesmo motor da caixa de busca do Commons — melhor relevância) e/ou **Action API** `list=search` com `srnamespace=6` (File) + `incategory:`.
- Para período/data, usar **interseção de categoria** (`incategory:"16th-century paintings"`) e/ou **structured data** (`haswbstatement:P571` = data de criação).
- Puxar metadados por candidato: título, autor e licença (via `extmetadata`), dimensões, **data**.

### C. Ranqueamento (substitui o score achatado)
Sinais que importam:
- **+** licença PD/CC; tipo pintura/gravura/mapa/foto-de-artefato; dimensões ≥1500px; **data dentro do período** pedido; presença em categoria relevante; casamento autor (se hint).
- **−** SVG de bandeira/logo/diagrama; foto moderna (data recente) quando a intenção é histórica; "exterior de museu".
- Resultado: score com **espalhamento real** (não mais tudo em 0.55), para o top-1/top-3 ser confiável.

### D. Escada de fallback (contrato com o chamador)
`find` → se 0/fraco: **afrouxar período** → se 0: **re-traduzir PT→EN** e reconsultar → se 0: devolver vazio com um campo `next: "websearch"` no JSON, para o agente assumir. Nunca um 0 silencioso sem ter tentado afrouxar.

### E. Mapeador de período (a feature que realiza a desambiguação)
Módulo pequeno `app/reverse/periodo.py`: string de período → `{categoria_commons, intervalo_de_data}`.
- "século XVI" → `{cat: "16th-century …", anos: 1500–1599}`
- "1815"/"período joanino" → `{anos: 1808–1821 / séc. XIX, cat: "19th-century …"}`
- "Antiguidade" → categorias/anos antigos
- Tabela inicial cobrindo séculos (a.C./d.C.) + eras nomeadas comuns do currículo do EM (Antiguidade, Idade Média, etc.). Extensível.

### F. Preservar (sem mudança ou com promoção)
- `--hint-author` subcategory walk; `app/reverse/hasher.py` (pHash/dHash); `app/reverse/dedup.py` (vs MANIFESTO — usado também pelo `acervo-didatico`); `normalize`; `scripts/acervos.py` (BnF/LoC/Walters/DPLA/Rijks/Harvard…).
- **Promover `coleta-lote`:** mesclar `cli/coletar.py` na `master` como feature oficial do broker (é o modo "em lote" que o Thiago usa para alimentar o `banco-imagens`); idealmente dar a ele o mesmo filtro de período.

### G. Remover (aposentadoria)
- `app/main.py`: rotas web/auth/biblioteca/coleções, sessão/PBKDF2, SMTP/recuperação de senha. Manter só (se útil) um endpoint fino de busca? **Não** — o uso é por CLI/import; o servidor HTTP é supérfluo. Avaliar reduzir `app/main.py` a nada ou a um import-only.
- Config do Fly (`fly.toml`), deploy. **Destruir o app no Fly é passo manual do Thiago:** `fly apps destroy acervo-historia-matostf` (e o volume `acervo_data`).
- Internos da triangulação de score achatado (`triangulate.py` `_score` flat) — reescritos pelo ranqueamento (C).
- **Consequência:** a PR `design-herodoto` (#3) do garimpo restyla o app web que será aposentado → **fica moot; fechar sem merge.**

## Contratos (o que NÃO muda)

- CLI: `cli.reverse find <desc> [--hint-author] [--hint-period] [--hint-region] [--max] [--json]` — **interface idêntica**.
- JSON de saída: `candidates[]` com `file_url, thumbnail_url, upload_url, title, author, license, width, height, source_strategy, similarity_score` — **mantido** (o `wave_workflow_so_pesquisador.js` continua parseando igual). *Acréscimos* compatíveis: `date`, `period_match` (bool), e no envelope `next: "websearch"` quando vazio.
- O `decks-historia/pipeline/scripts/wave_workflow_so_pesquisador.js` e a skill `reverse-search` **não precisam de mudança** (chamam o mesmo comando).

## Casos de borda

- **Frase PT + data** → não pode dar 0: o construtor de query tira a data para o filtro de período e traduz o resto. (Hoje é a falha nº 1.)
- **Mapa/globo** → caminho de termo canônico EN; documentar na skill que mapas/globos devem usar o termo canônico (`<País> orthographic projection`, `<tema> map`). O construtor também tenta auto-traduzir.
- **0 resultados** → escada de fallback (D), nunca 0 silencioso.
- **Conceito abstrato** (Hebreus) → fora do escopo v1; anotar futuro (expandir por objetos: "Menorá", "rolo da Torá", "Reino de Israel mapa").
- **Rate limit / user-agent** do Commons: respeitar (já há rate-limit no fetcher).

## Verificação (definição de pronto)

Re-rodar a **mesma bateria** de hoje (`teste_garimpo.py` + `teste_joanino.py`) e provar a melhora, item a item:
- Pintura joanina (frase PT) **0 → ≥1 relevante** no top-3.
- Mapa de período (1815) **errado → mapa correto** (via filtro de período).
- Debret (autor) e globo (termo canônico) **continuam 0.9+/0.79+**.
- `--hint-period` passa a **mudar o resultado** (ao contrário de hoje).
- Reforma e Fenícios: top-3 com ≥2 relevantes; score com espalhamento (não mais tudo 0.55).
Meta: cada tema retorna ≥3 candidatos relevantes no top-5; a pintura e o mapa do deck joanino saem de **falha → sucesso**.

## Sequenciamento (vira o plano)

1. **Mapeador de período** (`periodo.py`) — prioridade do Thiago; é o que torna a desambiguação real. (TDD: tabela séculos/eras → categoria+intervalo.)
2. **Construtor de query** (brief PT → query Commons: termos EN + autor + período + região).
3. **Backend Commons** (MediaSearch/Action API) + **ranqueamento** (C).
4. **Escada de fallback** (D).
5. **Aposentar app web + Fly** (remover rotas/auth/biblioteca/SMTP; `fly apps destroy` é do Thiago); **promover `coleta-lote`**.
6. **Re-rodar a bateria** de testes e verificar (seção acima).

## Questões em aberto

- MediaSearch vs Action API `list=search`: decidir no build (MediaSearch tende a relevância melhor; Action API dá `incategory` mais previsível). Talvez combinar.
- Cobertura inicial do mapeador de período (quais eras nomeadas pré-mapear além dos séculos).
- O `coletar.py` (lote) ganha o mesmo filtro de período agora ou depois?
- Reduzir `app/main.py` a import-only ou remover de vez? (sem consumidor HTTP, tende a remover.)
