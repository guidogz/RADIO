#REVELATION
from __future__ import annotations
import argparse, re, subprocess
from pathlib import Path
from typing import Iterable, Optional, Tuple

OBJ_LINE_RE = re.compile(r"Objective:\s*[^=]*=\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")
ALT_OBJ_RE = re.compile(r"Objective value\s*[:=]\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)", re.IGNORECASE)

def parse_objective(text: str) -> Optional[float]:
    m = OBJ_LINE_RE.search(text) or ALT_OBJ_RE.search(text)
    return float(m.group(1)) if m else None

def detect_solver_status(text: str, returncode: int) -> str:
    u = text.upper()
    if "OPTIMAL LP SOLUTION FOUND" in u or "INTEGER OPTIMAL SOLUTION FOUND" in u:
        return "OPTIMAL"
    if "NO PRIMAL FEASIBLE SOLUTION" in u or "NO FEASIBLE SOLUTION" in u:
        return "INFEASIBLE"
    return "ERROR" if returncode != 0 else "COMPLETED"

def run_glpsol(model: Path, data_files: Iterable[Path], workdir: Path,
               tag: str = "run", debug: bool = False) -> Tuple[Optional[float], str]:
    model = Path(model).resolve()
    data_files = [Path(p).resolve() for p in data_files]
    workdir = Path(workdir).resolve()

    if not model.exists():
        raise FileNotFoundError(model)
    for p in data_files:
        if not p.exists():
            raise FileNotFoundError(p)

    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "res").mkdir(parents=True, exist_ok=True)

    cmd = ["glpsol", "--math", str(model)]
    for p in data_files:
        cmd += ["--data", str(p)]

    if debug:
        d = workdir / "debug"
        d.mkdir(parents=True, exist_ok=True)
        cmd += ["-o", str(d / f"solution_{tag}.sol"),
                "--log", str(d / f"glpsol_{tag}.log")]

    print(f">> GLPK [{tag}]")
    proc = subprocess.run(cmd, cwd=str(workdir), capture_output=True, text=True, check=False)
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")

    if debug:
        (workdir / "debug" / f"stdout_{tag}.txt").write_text(proc.stdout or "", encoding="utf-8")
        (workdir / "debug" / f"stderr_{tag}.txt").write_text(proc.stderr or "", encoding="utf-8")

    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "")[-1200:])

    return parse_objective(text), detect_solver_status(text, proc.returncode)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="osemosys_model.txt")
    ap.add_argument("--data", default="atlantis_data.txt")
    ap.add_argument("--workdir", default="standalone_A1_output")
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()
    obj, status = run_glpsol(Path(a.model), [Path(a.data)], Path(a.workdir), "A1_BASE", a.debug)
    print(f">> Completed | status={status} | objective={obj}")

if __name__ == "__main__":
    main()
