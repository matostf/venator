# Venator

Ferramenta de **linha de comando (CLI)** para **descobrir imagens de licença aberta**
(domínio público / Creative Commons) em acervos de museus e arquivos de acesso aberto —
para montar slides de aula de História. Devolve URLs e metadados (**não** baixa imagem nem
guarda biblioteca); quem guarda e exibe é o projeto-irmão `thesaurus`.

Dois comandos:

- **`cli.reverse`** — busca por descrição em linguagem natural (PT) no Wikimedia Commons →
  candidatos ranqueados com URL, licença e metadados. Usado pelo pipeline do `decks-historia`
  e pela skill `reverse-search`.
- **`cli.coletar`** — coletor em lote: roda um plano de buscas em várias fontes, filtra por
  licença e grava o resultado para alimentar o `thesaurus`.

> **Rota 1 (2026-06):** este repo já teve também um app web (FastAPI na Fly.io, com login e
> biblioteca pessoal), agora **aposentado** — estava ocioso e redundante com o `thesaurus`.
> Restaram só o motor de descoberta + o coletor. O rebuild do motor de busca está pausado na
> branch `rota1-descoberta-commons`. Branch padrão: `master`.

## Rodar localmente

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env   # opcional: chaves de API de fontes extras (Smithsonian, Europeana)
```

Buscar uma imagem:

```bash
./.venv/bin/python -m cli.reverse find "família real chegando ao Brasil" \
    --hint-author "Debret" --hint-period "século XIX" --hint-region "Brasil" --max 10 --json
```

Outros subcomandos: `normalize` (canoniza URL do Commons), `hash` (pHash/dHash de uma
imagem), `dedup` (checa duplicata contra um manifesto).

Coletar em lote (alimenta o `thesaurus`):

```bash
./.venv/bin/python -m cli.coletar --plano <plano.json> --out <dir>
```

## Testes

```bash
./.venv/bin/python -m pytest -q
```

Mais detalhes de arquitetura em [CLAUDE.md](CLAUDE.md).
