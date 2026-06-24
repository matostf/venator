import subprocess, json
VENV = "/home/thiago/Projetos/garimpo-imagens/.venv/bin/python"
CWD = "/home/thiago/Projetos/garimpo-imagens"

TESTS = [
    ("PINTURA — chegada da corte", "Desembarque da família real portuguesa no Rio de Janeiro 1808", []),
    ("CENA DEBRET (com hint-author)", "corte portuguesa no Rio de Janeiro", ["--hint-author", "Jean-Baptiste Debret"]),
    ("MAPA de período", "mapa do Reino Unido de Portugal Brasil e Algarves 1815", []),
    ("GLOBO/localizador", "Brazil orthographic projection", []),
]

def run(desc, extra):
    cmd = [VENV, "-m", "cli.reverse", "find", desc, *extra, "--max", "5", "--json"]
    try:
        out = subprocess.run(cmd, cwd=CWD, capture_output=True, text=True, timeout=90)
        d = json.loads(out.stdout)
        return d.get("candidates", []), d.get("strategies_used", [])
    except Exception as e:
        return None, str(e)

for label, desc, extra in TESTS:
    cands, strat = run(desc, extra)
    print(f"\n{'='*76}\n### {label}\n    busca='{desc}'  extra={extra}")
    if cands is None:
        print(f"  ERRO: {strat}"); continue
    print(f"  estratégias: {strat}")
    if not cands:
        print("  (0 candidatos)")
    for c in cands:
        sc = c.get("similarity_score", 0); w, h = c.get("width", 0), c.get("height", 0)
        print(f"  {sc:.2f} | {w}x{h} | {c.get('title','')[:74]}")
print("\n=== FIM ===")
