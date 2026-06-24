import subprocess, json, sys

VENV = "/home/thiago/Projetos/garimpo-imagens/.venv/bin/python"
CWD = "/home/thiago/Projetos/garimpo-imagens"

# (rótulo, descrição, args-extra)
TESTS = [
    # Hebreus
    ("HEBREUS — sem período", "Hebreus", []),
    ("HEBREUS — período na descrição", "Hebreus na Antiguidade", []),
    ("HEBREUS — período na flag", "Hebreus", ["--hint-period", "Antiguidade"]),
    # Fenícios
    ("FENÍCIOS — sem período", "Fenícios", []),
    ("FENÍCIOS — período na descrição", "Fenícios Antiguidade", []),
    ("FENÍCIOS — período na flag", "Fenícios", ["--hint-period", "Antiguidade"]),
    # Reforma Protestante
    ("REFORMA — sem período", "Reforma Protestante", []),
    ("REFORMA — período na descrição", "Reforma Protestante século XVI", []),
    ("REFORMA — período na flag", "Reforma Protestante", ["--hint-period", "século XVI"]),
    # Período Joanino
    ("JOANINO — sem período", "Período Joanino", []),
    ("JOANINO — período na descrição", "Brasil Joanino corte portuguesa 1808", []),
    ("JOANINO — período na flag", "Período Joanino", ["--hint-period", "século XIX"]),
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
    print(f"\n{'='*78}\n### {label}   →   busca='{desc}'  extra={extra}")
    if cands is None:
        print(f"  ERRO: {strat}")
        continue
    print(f"  estratégias: {strat}")
    if not cands:
        print("  (0 candidatos)")
    for c in cands:
        sc = c.get("similarity_score", 0)
        w, h = c.get("width", 0), c.get("height", 0)
        lic = (c.get("license") or "")[:14]
        title = c.get("title", "")[:78]
        print(f"  {sc:.2f} | {w}x{h} | {lic:14} | {title}")
    sys.stdout.flush()
print("\n=== FIM ===")
