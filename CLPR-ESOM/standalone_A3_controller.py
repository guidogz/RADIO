from __future__ import annotations
import argparse, csv
from pathlib import Path
from typing import Dict, List, Optional
from standalone_A2_sequential import find_csv, hnorm, norm

def read_initial_policy_value(policy_path: Path, emission: str) -> Optional[float]:
    for line in Path(policy_path).read_text(encoding="utf-8", errors="ignore").splitlines():
        s=line.strip()
        if not s or s.startswith("#"): continue
        tok=s.split()
        if tok and tok[0].upper()==emission.upper():
            for x in tok[1:]:
                try: return float(x)
                except ValueError: pass
    return None

def read_emission_at_year(workdir: Path, emission: str, year: int, region: Optional[str]=None) -> float:
    p=find_csv(workdir,"AnnualEmissions.csv")
    if p is None: raise FileNotFoundError("AnnualEmissions.csv not found.")
    rows=list(csv.reader(p.open("r",encoding="utf-8",newline="")))
    hdr=[hnorm(h) for h in rows[0]]
    def idx(*names):
        for n in names:
            if n in hdr: return hdr.index(n)
        return None
    iR,iE,iY,iV=idx("r","region"),idx("e","emission","emis","pollutant"),idx("y","year","yr"),idx("annualemissions","value","val","amount","total")
    if None in (iE,iY,iV): raise ValueError("Unexpected AnnualEmissions.csv columns.")
    total=0.0
    for r in rows[1:]:
        try:
            yy=int(float(norm(r[iY]))); ee=norm(r[iE]); rr=norm(r[iR]) if iR is not None else ""
            if yy==year and ee.upper()==emission.upper() and (region is None or rr==region):
                total += float(norm(r[iV]))
        except Exception: pass
    return total

def compute_error(target: float, performance: float) -> float:
    return target-performance

def proportional_update(current_policy: float, error: float, kp: float,
                        lower_bound: float=0.0, upper_bound: float=500.0) -> float:
    updated=current_policy-kp*error
    return max(lower_bound,min(updated,upper_bound))

def update_future_policy_curve(curve: Dict[int,float], years: List[int],
                               after_year: int, new_value: float) -> Dict[int,float]:
    out=dict(curve)
    for y in years:
        if y>after_year: out[y]=new_value
    return out

def write_active_policy(path: Path, region: str, emission: str,
                        years: List[int], curve: Dict[int,float]) -> Path:
    lines=["data;","param EmissionsPenalty default 0 :=",f"[{region},*,*]:",
           " ".join(map(str,years))+":=",
           emission+" "+" ".join(f"{curve[y]:.10g}" for y in years),";","end;"]
    Path(path).write_text("\n".join(lines)+"\n",encoding="utf-8")
    return Path(path)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--lambda-current",type=float,default=20.0)
    ap.add_argument("--performance",type=float,required=True)
    ap.add_argument("--target",type=float,default=0.0)
    ap.add_argument("--kp",type=float,default=250.0)
    ap.add_argument("--lambda-min",type=float,default=0.0)
    ap.add_argument("--lambda-max",type=float,default=500.0)
    a=ap.parse_args()
    e=compute_error(a.target,a.performance)
    nxt=proportional_update(a.lambda_current,e,a.kp,a.lambda_min,a.lambda_max)
    print(f">> performance={a.performance} | target={a.target} | error={e} | lambda_next={nxt}")

if __name__=="__main__":
    main()
