from __future__ import annotations
import argparse, csv, re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from standalone_A1_base import run_glpsol

NewCapacityRow = Tuple[str, str, int, float]
YEAR_SET_RE = re.compile(r"set\s+YEAR\s*:=\s*(.*?)\s*;", re.IGNORECASE | re.DOTALL)

def norm(s: str) -> str:
    return (s or "").strip().strip('"').strip("'").replace("\ufeff", "")

def hnorm(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "").replace("_", "")

def find_csv(workdir: Path, name: str) -> Optional[Path]:
    for p in [Path(workdir)/name, Path(workdir)/"res"/name]:
        if p.exists():
            return p
    return None

def detect_years_from_data(data_path: Path) -> Tuple[int,int]:
    txt = Path(data_path).read_text(encoding="utf-8", errors="ignore")
    m = YEAR_SET_RE.search(txt)
    if not m:
        raise ValueError("Could not detect set YEAR.")
    years = [int(t) for t in m.group(1).replace("\n"," ").split() if t.strip().isdigit()]
    if not years:
        raise ValueError("YEAR set has no numeric years.")
    return min(years), max(years)

def split_years_into_n_blocks(years_all: List[int], n_blocks: int) -> List[Tuple[int,int]]:
    if n_blocks < 1 or n_blocks > len(years_all):
        raise ValueError("Invalid number of blocks.")
    n, base, rem, idx = len(years_all), len(years_all)//n_blocks, len(years_all)%n_blocks, 0
    blocks = []
    for b in range(n_blocks):
        size = base + (1 if b < rem else 0)
        blocks.append((years_all[idx], years_all[idx+size-1]))
        idx += size
    return blocks

def comment_param_blocks(src: Path, dst: Path, names: List[str]) -> Path:
    lines = Path(src).read_text(encoding="utf-8", errors="ignore").splitlines()
    pat = re.compile(r"^\s*param\s+(%s)\b" % "|".join(re.escape(n) for n in names), re.IGNORECASE)
    out, commenting = [], False
    for line in lines:
        if not commenting and pat.match(line):
            commenting = True
            out.append("# " + line)
            if ";" in line: commenting = False
        elif commenting:
            out.append("# " + line)
            if ";" in line: commenting = False
        else:
            out.append(line)
    Path(dst).write_text("\n".join(out) + "\n", encoding="utf-8")
    return Path(dst)

def load_newcapacity(workdir: Path) -> List[NewCapacityRow]:
    p = find_csv(workdir, "NewCapacity.csv")
    if p is None:
        raise FileNotFoundError("NewCapacity.csv not found.")
    rows = list(csv.reader(p.open("r", encoding="utf-8", newline="")))
    hdr = [hnorm(h) for h in rows[0]]
    def idx(*names):
        for n in names:
            if n in hdr: return hdr.index(n)
        return None
    iR, iT, iY, iV = idx("r","region"), idx("t","tech","technology"), idx("y","year","yr"), idx("newcapacity","value","val","amount","activity")
    if None in (iR,iT,iY,iV):
        raise ValueError("Unexpected NewCapacity.csv columns.")
    out = []
    for r in rows[1:]:
        try:
            out.append((norm(r[iR]), norm(r[iT]), int(float(norm(r[iY]))), float(norm(r[iV]))))
        except Exception:
            pass
    return out


PARAM_BLOCK_RE_TEMPLATE = r"param\s+{name}\b(.*?);"

def extract_capacity_investment_parameter(
    data_path: Path,
    param_name: str,
) -> Tuple[Dict[Tuple[str, str, int], float], float]:
    """
    Read an OSeMOSYS investment parameter and its default value.

    Supports empty/default-only declarations such as:

        param TotalAnnualMinCapacityInvestment default 0 :=
        ;

        param TotalAnnualMaxCapacityInvestment default 99999 :=
        ;

    Returns:
        (explicit_values, default_value)
    """
    txt = Path(data_path).read_text(encoding="utf-8", errors="ignore")

    pattern = re.compile(
        rf"param\s+{re.escape(param_name)}\b.*?;",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(txt)

    if not match:
        raise ValueError(
            f"Parameter '{param_name}' was not found in {data_path.name}."
        )

    block_text = match.group(0)
    block = block_text.splitlines()

    default_match = re.search(
        r"\bdefault\s+([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)",
        block_text,
        re.IGNORECASE,
    )
    default_value = float(default_match.group(1)) if default_match else 0.0

    values: Dict[Tuple[str, str, int], float] = {}

    # Long-format entries: REGION TECHNOLOGY YEAR VALUE
    for raw in block:
        line = raw.strip()
        if (
            not line
            or line.startswith("#")
            or line.lower().startswith("param ")
            or line == ";"
        ):
            continue

        line = line.rstrip(";").strip()
        parts = line.split()

        if len(parts) >= 4:
            try:
                year = int(float(parts[-2]))
                value = float(parts[-1])
            except ValueError:
                continue

            region = parts[-4].strip("'\"")
            technology = parts[-3].strip("'\"")

            if not region.startswith("[") and ":=" not in line:
                values[(region, technology, year)] = value

    if values:
        return values, default_value

    # Matrix-format entries
    region = None
    years: List[int] = []

    region_re = re.compile(
        r"\[\s*['\"]?([^,'\"\]]+)['\"]?\s*,\s*\*\s*,\s*\*\s*\]\s*:"
    )

    for raw in block:
        line = raw.strip()

        if not line or line.startswith("#"):
            continue

        m_region = region_re.search(line)
        if m_region:
            region = m_region.group(1).strip()
            after = line[m_region.end():].strip()
            if after:
                candidate_years = []
                for token in after.replace(":=", " ").split():
                    try:
                        candidate_years.append(int(float(token)))
                    except ValueError:
                        pass
                if candidate_years:
                    years = candidate_years
            continue

        if region and not years and ":=" in line:
            candidate_years = []
            for token in line.replace(":=", " ").split():
                try:
                    candidate_years.append(int(float(token)))
                except ValueError:
                    pass
            if candidate_years:
                years = candidate_years
                continue

        if region and years:
            parts = line.rstrip(";").split()
            if len(parts) == len(years) + 1:
                technology = parts[0].strip("'\"")
                try:
                    nums = [float(x) for x in parts[1:]]
                except ValueError:
                    continue

                for year, value in zip(years, nums):
                    values[(region, technology, year)] = value

    # Empty parameter blocks are valid; the default defines all values.
    return values, default_value


def write_active_block_minmax(
    committed_years: List[int],
    new_capacity: List[NewCapacityRow],
    base_data: Path,
    workdir: Path,
    filename: str = "Block_current.txt",
) -> Tuple[Path, int]:
    """
    Fix committed investments with Min = Max = committed NewCapacity.

    Uncommitted years preserve the original OSeMOSYS defaults:
      - Min: original default (Atlantis = 0)
      - Max: original default (Atlantis = 99999)

    Any explicit original parameter values are also preserved outside
    the committed years.
    """
    if not committed_years:
        raise ValueError("committed_years cannot be empty.")

    original_min, min_default = extract_capacity_investment_parameter(
        base_data,
        "TotalAnnualMinCapacityInvestment",
    )
    original_max, max_default = extract_capacity_investment_parameter(
        base_data,
        "TotalAnnualMaxCapacityInvestment",
    )

    regions = sorted({r for r, _, _, _ in new_capacity if r})
    region = regions[0] if regions else "Atlantis_00A"

    # Use modeled years from the base data so future years remain available.
    y0, yN = detect_years_from_data(base_data)
    all_years = list(range(y0, yN + 1))
    committed = set(committed_years)

    committed_map: Dict[Tuple[str, str, int], float] = {}
    technologies = set()

    for r, t, y, value in new_capacity:
        if r != region:
            continue

        technologies.add(t)

        if y in committed:
            key = (r, t, y)
            committed_map[key] = committed_map.get(key, 0.0) + max(0.0, value)

    technologies |= {
        t for (r, t, _) in set(original_min) | set(original_max)
        if r == region
    }
    technologies = sorted(technologies)

    def value_for(
        original: Dict[Tuple[str, str, int], float],
        default_value: float,
        tech: str,
        year: int,
    ) -> float:
        key = (region, tech, year)

        if year in committed:
            return committed_map.get(key, 0.0)

        return original.get(key, default_value)

    lines = ["data;"]

    # MIN
    lines += [
        f"param TotalAnnualMinCapacityInvestment default {min_default:.10g} :=",
        f"[{region},*,*]:",
        " ".join(str(y) for y in all_years) + ":=",
    ]

    for tech in technologies:
        vals = [
            value_for(original_min, min_default, tech, year)
            for year in all_years
        ]
        lines.append(
            tech + " " + " ".join(f"{v:.10g}" for v in vals)
        )

    lines.append(";")

    # MAX
    lines += [
        f"param TotalAnnualMaxCapacityInvestment default {max_default:.10g} :=",
        f"[{region},*,*]:",
        " ".join(str(y) for y in all_years) + ":=",
    ]

    for tech in technologies:
        vals = [
            value_for(original_max, max_default, tech, year)
            for year in all_years
        ]
        lines.append(
            tech + " " + " ".join(f"{v:.10g}" for v in vals)
        )

    lines += [";", "end;"]

    path = Path(workdir) / filename
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    n_locks = sum(
        1 for _, value in committed_map.items()
        if value > 0
    )

    return path, n_locks


def write_active_block(committed_years: List[int], nc: List[NewCapacityRow],
                       workdir: Path, filename: str = "Block_current.txt") -> Tuple[Path,int]:
    region = sorted({r for r,_,_,_ in nc if r})
    region = region[0] if region else "Atlantis_00A"
    ys = sorted(committed_years)
    yset = set(ys)
    tech_years: Dict[str, Dict[int,float]] = {}
    for _,t,y,v in nc:
        if y in yset:
            d = tech_years.setdefault(t or "", {})
            d[y] = d.get(y,0.0) + max(0.0,v)

    p = Path(workdir)/filename
    lines = ["data;", "param TotalAnnualMinCapacityInvestment default 0 :=",
             f"[{region},*,*]:", " ".join(map(str,ys)) + ":="]
    if not tech_years:
        lines.append("DUMMY_TECH " + " ".join("0" for _ in ys))
    else:
        for t in sorted(tech_years):
            lines.append(t + " " + " ".join(f"{tech_years[t].get(y,0.0):.10g}" for y in ys))
    lines += [";","end;"]
    p.write_text("\n".join(lines)+"\n", encoding="utf-8")
    nlocks = sum(1 for t in tech_years for y in ys if tech_years[t].get(y,0.0)>0)
    return p, nlocks

def _map(rows: List[NewCapacityRow]) -> Dict[Tuple[str,str,int],float]:
    d={}
    for r,t,y,v in rows:
        d[(r,t,y)] = d.get((r,t,y),0.0)+v
    return d

def validate_min_locks(prev: List[NewCapacityRow], cur: List[NewCapacityRow],
                       committed_years: List[int], tolerance: float=1e-9) -> Tuple[int,float]:
    a,b,ys = _map(prev),_map(cur),set(committed_years)
    n,mx=0,0.0
    for k,pv in a.items():
        if k[2] not in ys: continue
        deficit=max(0.0,pv-tolerance)-b.get(k,0.0)
        if deficit>tolerance:
            n+=1; mx=max(mx,deficit)
    return n,mx

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--model",default="osemosys_model.txt")
    ap.add_argument("--data",default="atlantis_data.txt")
    ap.add_argument("--blocks",type=int,default=5)
    ap.add_argument("--workdir",default="standalone_A2_output")
    ap.add_argument("--tol",type=float,default=1e-6)
    ap.add_argument("--debug",action="store_true")
    a=ap.parse_args()
    model,data,workdir=Path(a.model).resolve(),Path(a.data).resolve(),Path(a.workdir).resolve()
    workdir.mkdir(parents=True,exist_ok=True)
    y0,yN=detect_years_from_data(data); years=list(range(y0,yN+1))
    br=split_years_into_n_blocks(years,a.blocks)
    obj,status=run_glpsol(model,[data],workdir,"A2_START",a.debug)
    prev=load_newcapacity(workdir)
    data_seq=comment_param_blocks(
        data,
        workdir/"data_sequential.txt",
        ["TotalAnnualMinCapacityInvestment", "TotalAnnualMaxCapacityInvestment"]
    )
    print(f">> Baseline | status={status} | objective={obj}")
    for j in range(1,len(br)+1):
        committed=list(range(br[0][0],br[j-1][1]+1))
        block,_=write_active_block_minmax(
            committed,
            prev,
            data,
            workdir
        )
        obj,status=run_glpsol(model,[data_seq,block],workdir,f"A2_B{j}",a.debug)
        cur=load_newcapacity(workdir)
        n,mx=validate_min_locks(prev,cur,committed,a.tol)
        print(f">> Block {j} | {committed[0]}-{committed[-1]} | status={status} | violations={n} | max={mx:.3g}")
        prev=cur

if __name__=="__main__":
    main()

