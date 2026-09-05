"""
CLPR_ESOM Stand-alone A.5
Experimental Runner

Purpose
-------
Generate demand futures and execute:

1) No-policy benchmark:
       Future
   using the same sequential information revelation and investment
   commitments, with EmissionsPenalty = 0 throughout the horizon.

2) Prescribed policy comparator:
       Future x lambda0 x prescribed-policy trajectory
   using the same sequential information revelation and investment
   commitments as CLPR, while keeping the carbon-price trajectory fixed
   ex ante (linear-down, flat, linear-up).

3) Closed-loop policy representation (CLPR):
       Future x lambda0 x Kp
   by calling standalone_A4_CLPR.py.

Demand futures
--------------
- Base
- Linear-up
- Linear-down
- Step-up
- Step-down

The number and range of demand samples are configurable.

Policy sampling
---------------
lambda0 is sampled from [LAMBDA_MIN, LAMBDA_MAX].

Kp is NOT sampled independently in arbitrary units. It is defined as
a multiple of the lambda sampling step:

    delta_lambda = (lambda_max - lambda_min) / (n_lambda - 1)
    Kp = alpha * delta_lambda

where alpha is sampled from [KP_MULT_MIN, KP_MULT_MAX].

Normal outputs
--------------
- Experiment_Index.csv
- Experiment_Results.csv

Individual run folders are retained under Experiment_A5/runs/
for full traceability of each OSeMOSYS execution.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from standalone_A1_base import run_glpsol
from standalone_A2_sequential import (
    comment_param_blocks,
    detect_years_from_data,
    find_csv,
    split_years_into_n_blocks,
    load_newcapacity,
    validate_min_locks,
    write_active_block_minmax,
)
from standalone_A3_controller import (
    read_emission_at_year,
    write_active_policy,
)


# ============================================================
# Generic helpers
# ============================================================

def linspace(start: float, stop: float, n: int) -> List[float]:
    if n < 1:
        return []
    if n == 1:
        return [float(start)]
    step = (stop - start) / (n - 1)
    return [start + i * step for i in range(n)]


def positive_levels(max_value: float, n: int) -> List[float]:
    """Generate n positive non-zero levels from max/n to max."""
    if n <= 0:
        return []
    if max_value < 0:
        raise ValueError("Maximum magnitude must be non-negative.")
    return [max_value * i / n for i in range(1, n + 1)]


def safe_tag(value: float) -> str:
    sign = "P" if value >= 0 else "M"
    return f"{sign}{abs(value)*100:05.1f}".replace(".", "p")


def lambda_tag(value: float) -> str:
    return f"L{value:07.2f}".replace(".", "p")


def kp_tag(value: float) -> str:
    return f"KP{value:08.3f}".replace(".", "p")


def policy_delta_tag(value: float) -> str:
    sign = "UP" if value > 0 else "DN" if value < 0 else "FL"
    return f"{sign}{abs(value)*100:05.1f}".replace(".", "p")


def build_prescribed_policy_family(args) -> List[Dict[str, object]]:
    """
    Prescribed ex-ante carbon-price trajectories.

    Every trajectory starts at lambda0 in the first model year.
    Linear-down/up trajectories reach lambda0 * (1 + delta_final)
    in the final model year. Flat has delta_final = 0.
    """
    family: List[Dict[str, object]] = []

    down_levels = positive_levels(
        args.policy_down_max,
        args.n_policy_down,
    )
    # Order from strongest decrease toward flat.
    for i, magnitude in enumerate(reversed(down_levels), start=1):
        family.append({
            "policy_id": f"PD{i:02d}",
            "policy_trajectory": "linear",
            "policy_direction": "down",
            "policy_delta_final": -magnitude,
        })

    family.append({
        "policy_id": "PF00",
        "policy_trajectory": "flat",
        "policy_direction": "flat",
        "policy_delta_final": 0.0,
    })

    for i, magnitude in enumerate(
        positive_levels(args.policy_up_max, args.n_policy_up),
        start=1,
    ):
        family.append({
            "policy_id": f"PU{i:02d}",
            "policy_trajectory": "linear",
            "policy_direction": "up",
            "policy_delta_final": magnitude,
        })

    return family


def prescribed_policy_curve(
    years: List[int],
    lambda0: float,
    policy: Dict[str, object],
) -> Tuple[Dict[int, float], float]:
    y0 = min(years)
    yN = max(years)
    delta_final = float(policy["policy_delta_final"])
    lambda_final = lambda0 * (1.0 + delta_final)

    if lambda_final < 0:
        raise ValueError(
            f"Prescribed policy produces negative final lambda: {lambda_final}"
        )

    if policy["policy_trajectory"] == "flat":
        curve = {y: lambda0 for y in years}
    else:
        curve = {
            y: lambda0 + (lambda_final - lambda0) * (y - y0) / (yN - y0)
            for y in years
        }

    return curve, lambda_final


# ============================================================
# Demand block parser / writer
# ============================================================

DEMAND_BLOCK_RE = re.compile(
    r"param\s+SpecifiedAnnualDemand\b.*?;",
    re.IGNORECASE | re.DOTALL,
)

REGION_RE = re.compile(
    r"\[\s*([^,\]]+)\s*,\s*\*\s*,\s*\*\s*\]\s*:"
)


def parse_specified_annual_demand(
    data_path: Path,
) -> Tuple[str, List[int], Dict[str, List[float]], str]:
    """
    Parse the matrix form used by Atlantis:

        param SpecifiedAnnualDemand default 0 :=
        [Atlantis_00A,*,*]:
        2014 ... 2040:=
        EL_Industry ...
        ...
        ;

    Returns:
        region, years, sector_values, original_block_text
    """
    text = Path(data_path).read_text(encoding="utf-8", errors="ignore")
    match = DEMAND_BLOCK_RE.search(text)

    if not match:
        raise ValueError("SpecifiedAnnualDemand block not found.")

    block_text = match.group(0)
    lines = block_text.splitlines()

    region: Optional[str] = None
    years: List[int] = []
    sectors: Dict[str, List[float]] = {}

    for raw in lines:
        line = raw.strip()

        if not line or line.startswith("#"):
            continue

        region_match = REGION_RE.search(line)
        if region_match:
            region = region_match.group(1).strip()
            continue

        if region is not None and not years and ":=" in line:
            candidate = []
            for token in line.replace(":=", " ").split():
                try:
                    candidate.append(int(float(token)))
                except ValueError:
                    pass

            if candidate:
                years = candidate
                continue

        if region is not None and years:
            if line == ";":
                continue

            parts = line.rstrip(";").split()

            if len(parts) == len(years) + 1:
                sector = parts[0]
                try:
                    values = [float(x) for x in parts[1:]]
                except ValueError:
                    continue

                sectors[sector] = values

    if region is None or not years or not sectors:
        raise ValueError(
            "SpecifiedAnnualDemand was found but could not be parsed "
            "using the Atlantis matrix format."
        )

    return region, years, sectors, block_text


def demand_multiplier(
    years: List[int],
    trajectory: str,
    delta: float,
    step_year: Optional[int],
    reveal_year: Optional[int],
) -> Dict[int, float]:
    """
    delta:
      positive for upward futures
      negative for downward futures
    """
    y0 = min(years)
    yN = max(years)

    if trajectory == "base":
        return {y: 1.0 for y in years}

    if trajectory == "linear":
        if reveal_year is None:
            raise ValueError("reveal_year is required for linear futures.")
        if reveal_year < y0 or reveal_year >= yN:
            raise ValueError(
                f"reveal_year={reveal_year} must satisfy "
                f"{y0} <= reveal_year < {yN} for linear futures."
            )

        # No retrospective modification of demand. The revised trend is
        # identical to baseline through reveal_year, then diverges linearly
        # and reaches the requested delta at the final model year.
        return {
            y: (
                1.0
                if y <= reveal_year
                else 1.0 + delta * (y - reveal_year) / (yN - reveal_year)
            )
            for y in years
        }

    if trajectory == "step":
        if step_year is None:
            raise ValueError("step_year is required for step futures.")

        return {
            y: 1.0 if y < step_year else 1.0 + delta
            for y in years
        }

    raise ValueError(f"Unknown trajectory: {trajectory}")

def write_future_data(
    base_data: Path,
    output_path: Path,
    trajectory: str,
    delta: float,
    step_year: Optional[int],
    reveal_year: Optional[int],
) -> Path:
    """
    Copy base data and replace only SpecifiedAnnualDemand.

    The same yearly multiplier is applied to Industry, Residential,
    Services and Transport, preserving their relative composition.
    """
    text = Path(base_data).read_text(encoding="utf-8", errors="ignore")

    region, years, sectors, original_block = parse_specified_annual_demand(
        base_data
    )

    multipliers = demand_multiplier(
        years,
        trajectory,
        delta,
        step_year,
        reveal_year,
    )

    lines = [
        "param SpecifiedAnnualDemand default 0 :=",
        f"[{region},*,*]:",
        " ".join(str(y) for y in years) + ":=",
    ]

    for sector, values in sectors.items():
        modified = [
            value * multipliers[year]
            for year, value in zip(years, values)
        ]

        lines.append(
            sector + " " + " ".join(f"{v:.10g}" for v in modified)
        )

    lines.append(";")
    new_block = "\n".join(lines)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        text.replace(original_block, new_block),
        encoding="utf-8",
    )

    return output_path


# ============================================================
# Experiment design
# ============================================================

def build_futures(args) -> List[Dict[str, object]]:
    futures: List[Dict[str, object]] = [
        {
            "future_id": "BASE",
            "trajectory": "base",
            "direction": "base",
            "delta": 0.0,
            "step_year": "",
        }
    ]

    for i, delta in enumerate(
        positive_levels(args.linear_up_max, args.n_linear_up),
        start=1,
    ):
        futures.append({
            "future_id": f"LU{i:02d}",
            "trajectory": "linear",
            "direction": "up",
            "delta": delta,
            "step_year": "",
        })

    for i, magnitude in enumerate(
        positive_levels(args.linear_down_max, args.n_linear_down),
        start=1,
    ):
        futures.append({
            "future_id": f"LD{i:02d}",
            "trajectory": "linear",
            "direction": "down",
            "delta": -magnitude,
            "step_year": "",
        })

    for i, delta in enumerate(
        positive_levels(args.step_up_max, args.n_step_up),
        start=1,
    ):
        futures.append({
            "future_id": f"SU{i:02d}",
            "trajectory": "step",
            "direction": "up",
            "delta": delta,
            "step_year": args.step_year,
        })

    for i, magnitude in enumerate(
        positive_levels(args.step_down_max, args.n_step_down),
        start=1,
    ):
        futures.append({
            "future_id": f"SD{i:02d}",
            "trajectory": "step",
            "direction": "down",
            "delta": -magnitude,
            "step_year": args.step_year,
        })

    return futures


def build_policy_sampling(args) -> Tuple[List[float], List[float], float]:
    if args.n_lambda < 1:
        raise ValueError("n_lambda must be >= 1.")

    lambda_values = linspace(
        args.lambda_min,
        args.lambda_max,
        args.n_lambda,
    )

    if args.n_kp <= 0:
        return lambda_values, [], 0.0

    if args.n_lambda < 2:
        raise ValueError(
            "At least two lambda samples are required to derive "
            "Kp from the lambda sampling step."
        )

    delta_lambda = (
        args.lambda_max - args.lambda_min
    ) / (args.n_lambda - 1)

    if delta_lambda <= 0:
        raise ValueError(
            "lambda_max must be greater than lambda_min "
            "when Kp is derived from lambda steps."
        )

    multipliers = linspace(
        args.kp_mult_min,
        args.kp_mult_max,
        args.n_kp,
    )

    kp_values = [
        alpha * delta_lambda
        for alpha in multipliers
    ]

    return lambda_values, kp_values, delta_lambda


# ============================================================
# Result readers
# ============================================================

def run_prescribed_sequential(
    model: Path,
    base_data: Path,
    revealed_data: Path,
    workdir: Path,
    run_id: str,
    future: Dict[str, object],
    lambda0: float,
    policy: Dict[str, object],
    lambda_final: float,
    curve: Dict[int, float],
    block_ranges: List[Tuple[int, int]],
    reveal_year: int,
    emission: str,
    region: str,
    target: float,
    tol: float,
) -> List[Dict[str, object]]:
    """
    Sequential prescribed comparator.

    It uses the same information revelation and investment-locking logic as
    CLPR, but the complete carbon-price trajectory is fixed ex ante and is
    never updated from the performance error.
    """
    years_all = list(range(block_ranges[0][0], block_ranges[-1][1] + 1))

    def prepare_data_state(source: Path, tag: str):
        policy_data = comment_param_blocks(
            source,
            workdir / f"data_policy_{tag}.txt",
            ["EmissionsPenalty"],
        )
        block_data = comment_param_blocks(
            policy_data,
            workdir / f"data_prescribed_blocks_{tag}.txt",
            [
                "TotalAnnualMinCapacityInvestment",
                "TotalAnnualMaxCapacityInvestment",
            ],
        )
        return policy_data, block_data

    data_policy_initial, data_blocks_initial = prepare_data_state(
        base_data, "initial"
    )
    data_policy_revealed, data_blocks_revealed = prepare_data_state(
        revealed_data, "revealed"
    )

    policy_file = workdir / "policy_current.txt"
    block_file = workdir / "Block_current.txt"
    write_active_policy(
        policy_file,
        region,
        emission,
        years_all,
        curve,
    )

    setup_obj, setup_status = run_glpsol(
        model,
        [data_policy_initial, policy_file],
        workdir,
        tag="A5_PRES_SETUP",
        debug=False,
    )
    if setup_status != "OPTIMAL":
        raise RuntimeError(
            f"Prescribed SETUP failed with solver_status={setup_status}."
        )

    prev_nc = load_newcapacity(workdir)
    rows: List[Dict[str, object]] = []
    performance_year = block_ranges[-1][1]

    for j, (block_start, block_end) in enumerate(block_ranges, start=1):
        revealed_now = block_start >= reveal_year

        if revealed_now:
            active_source_data = revealed_data
            active_block_data = data_blocks_revealed
            information_state = "revealed"
        else:
            active_source_data = base_data
            active_block_data = data_blocks_initial
            information_state = "initial"

        if j == 1:
            committed_end = block_end
        else:
            committed_end = block_ranges[j - 2][1]

        committed = list(
            range(block_ranges[0][0], committed_end + 1)
        )

        block_file, nlocks = write_active_block_minmax(
            committed,
            prev_nc,
            active_source_data,
            workdir,
            block_file.name,
        )

        objective, solver_status = run_glpsol(
            model,
            [active_block_data, policy_file, block_file],
            workdir,
            tag=f"A5_PRES_B{j}",
            debug=False,
        )

        if solver_status != "OPTIMAL":
            raise RuntimeError(
                f"Prescribed block {j} ({block_start}-{block_end}) failed "
                f"with solver_status={solver_status}."
            )

        cur_nc = load_newcapacity(workdir)
        nviol, maxviol = validate_min_locks(
            prev_nc,
            cur_nc,
            committed,
            tol,
        )

        performance = read_emission_at_year(
            workdir,
            emission,
            performance_year,
            region,
        )

        rows.append({
            "run_id": run_id,
            "representation": "prescribed",
            "future_id": future["future_id"],
            "trajectory": future["trajectory"],
            "direction": future["direction"],
            "demand_delta": future["delta"],
            "step_year": future["step_year"],
            "lambda0": lambda0,
            "kp": "",
            "policy_id": policy["policy_id"],
            "policy_trajectory": policy["policy_trajectory"],
            "policy_direction": policy["policy_direction"],
            "policy_delta_final": policy["policy_delta_final"],
            "lambda_final": lambda_final,
            "block": j,
            "block_start_year": block_start,
            "block_end_year": block_end,
            "information_state": information_state,
            "active_data": active_source_data.name,
            "reveal_year": reveal_year,
            "performance_year": performance_year,
            "performance": performance,
            "target": target,
            "error": target - performance,
            # Policy is fixed ex ante. These fields report the prescribed
            # trajectory at the start of the current and next decision stage.
            "lambda_applied": curve[block_start],
            "lambda_next": (
                curve[block_ranges[j][0]]
                if j < len(block_ranges)
                else curve[block_end]
            ),
            "n_locks": nlocks,
            "lock_violations": nviol,
            "max_lock_violation": maxviol,
            "objective": objective if objective is not None else "",
            "total_newcapacity": sum(v for _, _, _, v in cur_nc),
            "solver_status": solver_status,
        })

        prev_nc = cur_nc

    return rows

def read_clpr_report(
    report_path: Path,
    run_id: str,
    future: Dict[str, object],
    lambda0: float,
    kp: float,
    reveal_year: int,
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []

    with Path(report_path).open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)

        for rec in reader:
            rows.append({
                "run_id": run_id,
                "representation": "closed_loop",
                "future_id": future["future_id"],
                "trajectory": future["trajectory"],
                "direction": future["direction"],
                "demand_delta": future["delta"],
                "step_year": future["step_year"],
                "lambda0": lambda0,
                "kp": kp,
                "policy_id": "",
                "policy_trajectory": "",
                "policy_direction": "",
                "policy_delta_final": "",
                "lambda_final": "",
                "block": rec.get("block", ""),
                "block_start_year": rec.get("block_start_year", ""),
                "block_end_year": rec.get("block_end_year", ""),
                "information_state": rec.get("information_state", ""),
                "active_data": rec.get("active_data", ""),
                "reveal_year": reveal_year,
                "performance_year": rec.get("performance_year", ""),
                "performance": rec.get("performance", ""),
                "target": rec.get("target", ""),
                "error": rec.get("error", ""),
                "lambda_applied": rec.get("lambda_applied", ""),
                "lambda_next": rec.get("lambda_next", ""),
                "n_locks": rec.get("n_locks", ""),
                "lock_violations": rec.get("lock_violations", ""),
                "max_lock_violation": rec.get("max_lock_violation", ""),
                "objective": rec.get("objective", ""),
                "total_newcapacity": rec.get("total_newcapacity", ""),
                "solver_status": rec.get("solver_status", ""),
            })

    return rows


# ============================================================
# Output writers
# ============================================================

INDEX_FIELDS = [
    "run_id",
    "representation",
    "future_id",
    "trajectory",
    "direction",
    "demand_delta",
    "step_year",
    "reveal_year",
    "lambda0",
    "kp",
    "policy_id",
    "policy_trajectory",
    "policy_direction",
    "policy_delta_final",
    "lambda_final",
    "status",
    "run_folder",
    "message",
]

RESULT_FIELDS = [
    "run_id",
    "representation",
    "future_id",
    "trajectory",
    "direction",
    "demand_delta",
    "step_year",
    "lambda0",
    "kp",
    "policy_id",
    "policy_trajectory",
    "policy_direction",
    "policy_delta_final",
    "lambda_final",
    "block",
    "block_start_year",
    "block_end_year",
    "information_state",
    "active_data",
    "reveal_year",
    "performance_year",
    "performance",
    "target",
    "error",
    "lambda_applied",
    "lambda_next",
    "n_locks",
    "lock_violations",
    "max_lock_violation",
    "objective",
    "total_newcapacity",
    "solver_status",
]


def write_csv(path: Path, rows: List[Dict[str, object]], fields: List[str]):
    with Path(path).open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


# ============================================================
# Main experiment
# ============================================================

def build_cli():
    ap = argparse.ArgumentParser(
        description="CLPR_ESOM A.5 - Experimental Runner"
    )

    # Core files
    ap.add_argument("--model", default="osemosys_model.txt")
    ap.add_argument("--data", default="atlantis_data.txt")
    ap.add_argument("--a4", default="standalone_A4_CLPR.py")
    ap.add_argument("--outdir", default="Experiment_A5")

    # ========================================================
    # Demand futures - MINIMUM EXPERIMENT
    # ========================================================

    # Linear-up: 1 future, ending +50% in 2040
    ap.add_argument("--n-linear-up", type=int, default=3)
    ap.add_argument("--linear-up-max", type=float, default=0.50)

    # Linear-down: 1 future, ending -20% in 2040
    ap.add_argument("--n-linear-down", type=int, default=3)
    ap.add_argument("--linear-down-max", type=float, default=0.50)

    # Step-up: 1 future, persistent +20% shift from baseline from 2025
    ap.add_argument("--n-step-up", type=int, default=3)
    ap.add_argument("--step-up-max", type=float, default=0.50)

    # Step-down: 1 future, persistent -20% shift from baseline from 2025
    ap.add_argument("--n-step-down", type=int, default=3)
    ap.add_argument("--step-down-max", type=float, default=0.50)

    ap.add_argument("--step-year", type=int, default=2021)
    ap.add_argument("--reveal-year", type=int, default=2020)

    # ========================================================
    # Initial carbon-price sampling
    # ========================================================

    ap.add_argument("--lambda-min", type=float, default=50.0)
    ap.add_argument("--lambda-max", type=float, default=400.0)
    ap.add_argument("--n-lambda", type=int, default=8)

    # ========================================================
    # Kp sampling
    # Kp = multiplier × delta_lambda
    # delta_lambda = 20 in this experiment
    # ========================================================

    ap.add_argument("--kp-mult-min", type=float, default=0.5)
    ap.add_argument("--kp-mult-max", type=float, default=5)
    ap.add_argument("--n-kp", type=int, default=5)

    # ========================================================
    # Prescribed policy family
    # lambda_final = lambda0 * (1 + policy_delta_final)
    # Default: -50%, -25%, flat, +25%, +50%
    # ========================================================

    ap.add_argument("--policy-down-max", type=float, default=0.50)
    ap.add_argument("--policy-up-max", type=float, default=0.50)
    ap.add_argument("--n-policy-down", type=int, default=2)
    ap.add_argument("--n-policy-up", type=int, default=2)

    # CLPR settings
    ap.add_argument("--blocks", type=int, default=5)
    ap.add_argument("--target", type=float, default=0.0)
    ap.add_argument("--emission", default="CO2")
    ap.add_argument("--region", default="Atlantis_00A")
    ap.add_argument("--policy-lower-bound", type=float, default=0.0)
    ap.add_argument("--policy-upper-bound", type=float, default=1000.0)
    ap.add_argument("--tol", type=float, default=1e-6)

    # Execution
    ap.add_argument("--skip-no-policy", action="store_true")
    ap.add_argument("--skip-prescribed", action="store_true")
    ap.add_argument("--skip-clpr", action="store_true")
    ap.add_argument("--dry-run", action="store_true")

    return ap


def main():
    args, _unknown = build_cli().parse_known_args()

    here = Path(".").resolve()

    model = (here / args.model).resolve()
    base_data = (here / args.data).resolve()
    a4_script = (here / args.a4).resolve()

    outdir = Path(args.outdir)
    if not outdir.is_absolute():
        outdir = (here / outdir).resolve()

    outdir.mkdir(parents=True, exist_ok=True)

    if not model.exists():
        raise FileNotFoundError(model)

    if not base_data.exists():
        raise FileNotFoundError(base_data)

    if not args.skip_clpr and not a4_script.exists():
        raise FileNotFoundError(a4_script)

    futures = build_futures(args)
    lambda_values, kp_values, delta_lambda = build_policy_sampling(args)
    prescribed_policies = build_prescribed_policy_family(args)

    if not args.skip_prescribed and not args.skip_clpr:
        if len(prescribed_policies) != len(kp_values):
            raise ValueError(
                "For a balanced comparison, the number of prescribed policy "
                f"trajectories ({len(prescribed_policies)}) must equal the "
                f"number of Kp alternatives ({len(kp_values)})."
            )

    y0, yN = detect_years_from_data(base_data)
    years_all = list(range(y0, yN + 1))
    block_ranges = split_years_into_n_blocks(
        years_all,
        args.blocks,
    )

    valid_reveal_years = [start for start, _ in block_ranges]
    if args.reveal_year not in valid_reveal_years:
        raise ValueError(
            f"reveal_year={args.reveal_year} must match a block start year: "
            f"{valid_reveal_years}"
        )

    n_no_policy = (
        0 if args.skip_no_policy
        else len(futures)
    )

    n_prescribed = (
        0 if args.skip_prescribed
        else len(futures) * len(lambda_values) * len(prescribed_policies)
    )

    n_clpr = (
        0 if args.skip_clpr
        else len(futures) * len(lambda_values) * len(kp_values)
    )

    print(">> A.5 Experimental design")
    print(f">> Futures: {len(futures)}")
    print(f">> Lambda samples: {len(lambda_values)} -> {lambda_values}")
    print(f">> Lambda step: {delta_lambda:.6g}")
    print(f">> Kp samples: {len(kp_values)} -> {kp_values}")
    print(f">> Reveal year: {args.reveal_year}")
    print(
        ">> Prescribed policy family: "
        + ", ".join(
            f"{p['policy_id']}={float(p['policy_delta_final']):+.1%}"
            for p in prescribed_policies
        )
    )
    print(f">> No-policy runs: {n_no_policy}")
    print(f">> Prescribed runs: {n_prescribed}")
    print(f">> CLPR runs: {n_clpr}")
    print(f">> Total runs: {n_no_policy + n_prescribed + n_clpr}")

    if args.dry_run:
        print(">> DRY RUN: no OSeMOSYS cases executed.")
        return

    index_rows: List[Dict[str, object]] = []
    result_rows: List[Dict[str, object]] = []

    runs_dir = outdir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    # One temporary future-data file is kept at experiment level and overwritten
    # for each future. Individual OSeMOSYS outputs are preserved per run.
    future_data = outdir / "atlantis_data_future.txt"

    run_counter = 0
    total_runs = n_no_policy + n_prescribed + n_clpr

    for future in futures:
        trajectory = str(future["trajectory"])
        delta = float(future["delta"])
        step_year = (
            int(future["step_year"])
            if future["step_year"] != ""
            else None
        )

        # Generate the future once and reuse it across lambda/Kp combinations.
        write_future_data(
            base_data,
            future_data,
            trajectory,
            delta,
            step_year,
            args.reveal_year,
        )

        # ----------------------------------------------------
        # No-policy benchmark: one sequential run per future
        # ----------------------------------------------------
        if not args.skip_no_policy:
            run_counter += 1

            run_id = f"NOPOL_{future['future_id']}"
            run_folder = runs_dir / run_id
            run_folder.mkdir(parents=True, exist_ok=True)

            status = "OK"
            message = ""

            try:
                no_policy = {
                    "policy_id": "NP00",
                    "policy_trajectory": "none",
                    "policy_direction": "none",
                    "policy_delta_final": 0.0,
                }
                no_policy_curve = {y: 0.0 for y in years_all}

                no_policy_rows = run_prescribed_sequential(
                    model=model,
                    base_data=base_data,
                    revealed_data=future_data,
                    workdir=run_folder,
                    run_id=run_id,
                    future=future,
                    lambda0=0.0,
                    policy=no_policy,
                    lambda_final=0.0,
                    curve=no_policy_curve,
                    block_ranges=block_ranges,
                    reveal_year=args.reveal_year,
                    emission=args.emission,
                    region=args.region,
                    target=args.target,
                    tol=args.tol,
                )

                for row in no_policy_rows:
                    row["representation"] = "no_policy"

                result_rows.extend(no_policy_rows)

            except Exception as exc:
                status = "FAILED"
                message = str(exc)

            index_rows.append({
                "run_id": run_id,
                "representation": "no_policy",
                "future_id": future["future_id"],
                "trajectory": future["trajectory"],
                "direction": future["direction"],
                "demand_delta": future["delta"],
                "step_year": future["step_year"],
                "reveal_year": args.reveal_year,
                "lambda0": 0.0,
                "kp": "",
                "policy_id": "NP00",
                "policy_trajectory": "none",
                "policy_direction": "none",
                "policy_delta_final": 0.0,
                "lambda_final": 0.0,
                "status": status,
                "run_folder": str(run_folder),
                "message": message,
            })

            print(
                f">> [{run_counter}/{total_runs}] "
                f"{run_id} -> {status}"
            )

        # ----------------------------------------------------
        # Prescribed policy comparator: Future x lambda0
        # ----------------------------------------------------
        if not args.skip_prescribed:
            for lambda0 in lambda_values:
                for policy in prescribed_policies:
                    run_counter += 1

                    run_id = (
                        f"PRES_{future['future_id']}_"
                        f"{lambda_tag(lambda0)}_"
                        f"{policy['policy_id']}_"
                        f"{policy_delta_tag(float(policy['policy_delta_final']))}"
                    )

                    run_folder = runs_dir / run_id
                    run_folder.mkdir(parents=True, exist_ok=True)

                    status = "OK"
                    message = ""

                    try:
                        curve, lambda_final = prescribed_policy_curve(
                            years_all,
                            lambda0,
                            policy,
                        )

                        pres_rows = run_prescribed_sequential(
                            model=model,
                            base_data=base_data,
                            revealed_data=future_data,
                            workdir=run_folder,
                            run_id=run_id,
                            future=future,
                            lambda0=lambda0,
                            policy=policy,
                            lambda_final=lambda_final,
                            curve=curve,
                            block_ranges=block_ranges,
                            reveal_year=args.reveal_year,
                            emission=args.emission,
                            region=args.region,
                            target=args.target,
                            tol=args.tol,
                        )
                        result_rows.extend(pres_rows)

                    except Exception as exc:
                        status = "FAILED"
                        message = str(exc)

                    index_rows.append({
                        "run_id": run_id,
                        "representation": "prescribed",
                        "future_id": future["future_id"],
                        "trajectory": future["trajectory"],
                        "direction": future["direction"],
                        "demand_delta": future["delta"],
                        "step_year": future["step_year"],
                        "reveal_year": args.reveal_year,
                        "lambda0": lambda0,
                        "kp": "",
                        "policy_id": policy["policy_id"],
                        "policy_trajectory": policy["policy_trajectory"],
                        "policy_direction": policy["policy_direction"],
                        "policy_delta_final": policy["policy_delta_final"],
                        "lambda_final": (
                            lambda0 * (1.0 + float(policy["policy_delta_final"]))
                        ),
                        "status": status,
                        "run_folder": str(run_folder),
                        "message": message,
                    })

                    print(
                        f">> [{run_counter}/{total_runs}] "
                        f"{run_id} -> {status}"
                    )

        # ----------------------------------------------------
        # CLPR: Future x lambda0 x Kp
        # ----------------------------------------------------
        if not args.skip_clpr:
            for lambda0 in lambda_values:
                for kp in kp_values:
                    run_counter += 1

                    run_id = (
                        f"CLPR_{future['future_id']}_"
                        f"{lambda_tag(lambda0)}_"
                        f"{kp_tag(kp)}"
                    )

                    run_folder = runs_dir / run_id
                    run_folder.mkdir(parents=True, exist_ok=True)

                    cmd = [
                        sys.executable,
                        str(a4_script),
                        "--model", str(model),
                        "--data", str(base_data),
                        "--revealed-data", str(future_data),
                        "--reveal-year", str(args.reveal_year),
                        "--workdir", str(run_folder),
                        "--blocks", str(args.blocks),
                        "--kp", str(kp),
                        "--emission", str(args.emission),
                        "--region", str(args.region),
                        "--target", str(args.target),
                        "--lambda0", str(lambda0),
                        "--lambda-min", str(args.policy_lower_bound),
                        "--lambda-max", str(args.policy_upper_bound),
                        "--tol", str(args.tol),
                    ]

                    status = "OK"
                    message = ""

                    try:
                        proc = subprocess.run(
                            cmd,
                            cwd=str(a4_script.parent),
                            capture_output=True,
                            text=True,
                            check=False,
                        )

                        if proc.returncode != 0:
                            raise RuntimeError(
                                (proc.stderr or proc.stdout or "")[-1500:]
                            )

                        report_path = run_folder / "CLPR_Run_Report.csv"

                        if not report_path.exists():
                            raise FileNotFoundError(
                                f"CLPR report not found: {report_path}"
                            )

                        result_rows.extend(
                            read_clpr_report(
                                report_path,
                                run_id,
                                future,
                                lambda0,
                                kp,
                                args.reveal_year,
                            )
                        )

                    except Exception as exc:
                        status = "FAILED"
                        message = str(exc)

                    index_rows.append({
                        "run_id": run_id,
                        "representation": "closed_loop",
                        "future_id": future["future_id"],
                        "trajectory": future["trajectory"],
                        "direction": future["direction"],
                        "demand_delta": future["delta"],
                        "step_year": future["step_year"],
                        "lambda0": lambda0,
                        "kp": kp,
                        "policy_id": "",
                        "policy_trajectory": "",
                        "policy_direction": "",
                        "policy_delta_final": "",
                        "lambda_final": "",
                        "status": status,
                        "run_folder": str(run_folder),
                        "message": message,
                    })

                    print(
                        f">> [{run_counter}/{total_runs}] "
                        f"{run_id} -> {status}"
                    )

    index_path = outdir / "Experiment_Index.csv"
    results_path = outdir / "Experiment_Results.csv"

    write_csv(index_path, index_rows, INDEX_FIELDS)
    write_csv(results_path, result_rows, RESULT_FIELDS)


    successful = sum(
        1 for row in index_rows
        if row["status"] == "OK"
    )

    failed = len(index_rows) - successful

    print(">> Experiment completed.")
    print(f">> Successful runs: {successful}")
    print(f">> Failed runs: {failed}")
    print(f">> Index: {index_path}")
    print(f">> Results: {results_path}")


if __name__ == "__main__":
    main()


