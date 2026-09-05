"""
CLPR_ESOM Stand-alone A.6
Results Analysis & Plotting

Version: A6.49 (label connectors + rightmost label fix; paper directory removed; Block 2 data folder added)

Purpose
-------
A.6 is the main post-processing module for the CLPR_ESOM experiment.
It reads A.5 outputs, validates the experiment, builds one scientific
summary row per run, and generates a first plots plot.

This module DOES NOT rerun or modify OSeMOSYS.

Pipeline
--------
A.5 outputs -> validation -> run metrics -> plots -> later extensions
(comparisons, Pareto, robustness, sensitivity).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

EXPECTED_REPRESENTATIONS = {"no_policy", "prescribed", "closed_loop"}

INDEX_REQUIRED = {"run_id", "representation", "future_id", "status", "run_folder"}
RESULT_REQUIRED = {
    "run_id", "representation", "future_id", "lambda0", "block",
    "performance_year", "performance", "target", "lambda_applied",
    "lambda_next", "lock_violations", "max_lock_violation", "solver_status",
}

NUMERIC_RESULTS = [
    "demand_delta", "step_year", "reveal_year", "lambda0", "kp",
    "policy_delta_final", "lambda_final", "block", "block_start_year",
    "block_end_year", "performance_year", "performance", "target", "error",
    "lambda_applied", "lambda_next", "n_locks", "lock_violations",
    "max_lock_violation", "objective", "total_newcapacity",
]
NUMERIC_INDEX = [
    "demand_delta", "step_year", "reveal_year", "lambda0", "kp",
    "policy_delta_final", "lambda_final",
]


def numericize(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def read_csv_required(path: Path, required: set[str]) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    df = pd.read_csv(path)
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"{path.name} is missing required columns: "
            + ", ".join(sorted(missing))
        )
    return df


def locate_res_folder(run_folder: Path) -> Optional[Path]:
    for folder in (run_folder / "res", run_folder):
        if folder.exists():
            return folder
    return None


def resolve_run_folder(experiment_dir: Path, raw: object, run_id: str) -> Path:
    text = str(raw).strip()
    if text and text.lower() != "nan":
        p = Path(text)
        if p.is_absolute():
            return p
        if p.exists():
            return p.resolve()
        return (experiment_dir / p).resolve()
    return (experiment_dir / "runs" / run_id).resolve()


def read_optional_csv(folder: Optional[Path], filename: str) -> Optional[pd.DataFrame]:
    if folder is None:
        return None
    path = folder / filename
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except Exception:
        return None

def read_first_available_csv(
    folder: Optional[Path], filenames: Iterable[str]
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    if folder is None:
        return None, None
    for filename in filenames:
        path = folder / filename
        if path.exists():
            try:
                return pd.read_csv(path), filename
            except Exception:
                pass
    return None, None



def named_column(df: pd.DataFrame, names: Iterable[str]) -> Optional[str]:
    mapping = {str(c).lower(): c for c in df.columns}
    for name in names:
        if name.lower() in mapping:
            return mapping[name.lower()]
    return None


def value_column(df: pd.DataFrame, preferred: Iterable[str]) -> Optional[str]:
    found = named_column(df, preferred)
    if found is not None:
        return found
    for col in reversed(df.columns):
        if pd.to_numeric(df[col], errors="coerce").notna().any():
            return col
    return None


def sum_value(df: Optional[pd.DataFrame], preferred: Iterable[str]) -> float:
    if df is None or df.empty:
        return np.nan
    col = value_column(df, preferred)
    if col is None:
        return np.nan
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())


def annual_emission_metrics(
    df: Optional[pd.DataFrame],
    start_year: int,
    target_year: int,
    emission_selector: str = "CO2",
) -> Tuple[float, float]:
    """Return cumulative and terminal emissions for one selected gas."""
    if df is None or df.empty:
        return np.nan, np.nan

    ycol = named_column(df, ["y", "year"])
    ecol = named_column(df, ["e", "emission", "emissions", "emission_type"])
    vcol = value_column(
        df, ["AnnualEmissions", "annual_emissions", "annualemissions", "value"]
    )
    if ycol is None or ecol is None or vcol is None:
        return np.nan, np.nan

    tmp = df[[ycol, ecol, vcol]].copy()
    tmp[ycol] = pd.to_numeric(tmp[ycol], errors="coerce")
    tmp[vcol] = pd.to_numeric(tmp[vcol], errors="coerce")

    selector = str(emission_selector).strip().upper()
    labels = tmp[ecol].astype(str).str.strip().str.upper()

    exact = labels.eq(selector)
    if exact.any():
        tmp = tmp.loc[exact].copy()
    else:
        tmp = tmp.loc[labels.str.contains(selector, regex=False)].copy()

    tmp = tmp.dropna(subset=[ycol, vcol])
    tmp = tmp[(tmp[ycol] >= start_year) & (tmp[ycol] <= target_year)]
    if tmp.empty:
        return np.nan, np.nan

    yearly = tmp.groupby(ycol)[vcol].sum().sort_index()
    cumulative = float(yearly.sum())
    final = float(yearly.loc[target_year]) if target_year in yearly.index else np.nan
    return cumulative, final


def parse_discount_rate_from_text(path: Path) -> Optional[float]:
    """Parse OSeMOSYS DiscountRate from a .dat/.txt file."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    for pattern in (
        r"param\s+DiscountRate\s+default\s+([0-9eE+\-.]+)",
        r"param\s+DiscountRate\s*:=\s*([0-9eE+\-.]+)\s*;",
    ):
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass

    block = re.search(
        r"param\s+DiscountRate\s*:=([\s\S]*?);",
        text,
        flags=re.IGNORECASE,
    )
    if block:
        vals = []
        for token in re.findall(
            r"([0-9]+\.[0-9]+(?:[eE][+\-]?\d+)?)",
            block.group(1),
        ):
            try:
                vals.append(float(token))
            except ValueError:
                pass
        if vals and max(vals) - min(vals) < 1e-12:
            return vals[0]

    return None


def discover_discount_rate(
    experiment_dir: Path,
    index_df: pd.DataFrame,
    override: Optional[float],
) -> Tuple[Optional[float], str]:
    """Prefer CLI override; otherwise inspect A.5 data files."""
    if override is not None:
        return float(override), "cli"

    candidates = []
    for pattern in ("*.dat", "*.txt"):
        candidates.extend(experiment_dir.glob(pattern))

    for _, row in index_df.head(10).iterrows():
        run_id = str(row["run_id"])
        run_folder = resolve_run_folder(
            experiment_dir, row.get("run_folder", ""), run_id
        )
        if run_folder.exists():
            for pattern in ("data_policy_*.txt", "*.dat", "*.txt"):
                candidates.extend(run_folder.glob(pattern))

    seen = set()
    for path in candidates:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        rate = parse_discount_rate_from_text(path)
        if rate is not None:
            return rate, str(path)

    return None, ""


def discount_annual_cost_file(
    df: Optional[pd.DataFrame],
    value_names: Iterable[str],
    start_year: int,
    target_year: int,
    discount_rate: Optional[float],
    timing: str,
) -> float:
    """
    Discount annual OSeMOSYS cost outputs.

    timing='start': exponent y-start_year (CAPEX)
    timing='mid': exponent y-start_year+0.5 (FOM/VOM)
    """
    if df is None or df.empty or discount_rate is None:
        return np.nan

    ycol = named_column(df, ["y", "year"])
    vcol = value_column(df, value_names)
    if ycol is None or vcol is None:
        return np.nan

    tmp = df[[ycol, vcol]].copy()
    tmp[ycol] = pd.to_numeric(tmp[ycol], errors="coerce")
    tmp[vcol] = pd.to_numeric(tmp[vcol], errors="coerce")
    tmp = tmp.dropna(subset=[ycol, vcol])
    tmp = tmp[(tmp[ycol] >= start_year) & (tmp[ycol] <= target_year)]
    if tmp.empty:
        return np.nan

    exponent = (
        tmp[ycol] - start_year
        if timing == "start"
        else tmp[ycol] - start_year + 0.5
    )
    factor = (1.0 + float(discount_rate)) ** exponent
    return float((tmp[vcol] / factor).sum())


def discounted_salvage_value(
    df: Optional[pd.DataFrame],
    value_names: Iterable[str],
    start_year: int,
    target_year: int,
    discount_rate: Optional[float],
) -> float:
    """
    Discount OSeMOSYS salvage value exactly as in OFS_Cost / SV4:

        PV(SV) = SalvageValue / (1+r)^(target_year-start_year+1)

    This applies to both technology and storage salvage in the supplied model.
    """
    if df is None or df.empty or discount_rate is None:
        return np.nan

    vcol = value_column(df, value_names)
    if vcol is None:
        return np.nan

    values = pd.to_numeric(df[vcol], errors="coerce")
    if values.notna().sum() == 0:
        return np.nan

    exponent = target_year - start_year + 1
    return float(values.sum() / ((1.0 + float(discount_rate)) ** exponent))


def load_experiment(experiment_dir: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    index_df = read_csv_required(experiment_dir / "Experiment_Index.csv", INDEX_REQUIRED)
    results_df = read_csv_required(experiment_dir / "Experiment_Results.csv", RESULT_REQUIRED)
    index_df = numericize(index_df, NUMERIC_INDEX)
    results_df = numericize(results_df, NUMERIC_RESULTS)
    index_df["run_id"] = index_df["run_id"].astype(str)
    results_df["run_id"] = results_df["run_id"].astype(str)
    return index_df, results_df


def build_validation_report(
    experiment_dir: Path, index_df: pd.DataFrame, results_df: pd.DataFrame
) -> pd.DataFrame:
    groups = {rid: g.copy() for rid, g in results_df.groupby("run_id", sort=False)}
    rows = []

    for _, idx in index_df.iterrows():
        run_id = str(idx["run_id"])
        rep = str(idx["representation"])
        future = str(idx["future_id"])
        status = str(idx["status"])
        grp = groups.get(run_id)
        results_found = grp is not None and not grp.empty

        if results_found:
            n_blocks = int(grp["block"].dropna().nunique())
            solver_ok = grp["solver_status"].astype(str).str.upper().eq("OPTIMAL").all()
            lock_total = float(pd.to_numeric(grp["lock_violations"], errors="coerce").fillna(0).sum())
            max_lock = float(pd.to_numeric(grp["max_lock_violation"], errors="coerce").fillna(0).max())
            rep_ok = grp["representation"].astype(str).eq(rep).all()
            future_ok = grp["future_id"].astype(str).eq(future).all()
        else:
            n_blocks, solver_ok, lock_total, max_lock = 0, False, np.nan, np.nan
            rep_ok, future_ok = False, False

        run_folder = resolve_run_folder(experiment_dir, idx.get("run_folder", ""), run_id)
        res = locate_res_folder(run_folder)
        emissions_found = bool(res and (res / "AnnualEmissions.csv").exists())
        annual_capital_found = bool(res and (res / "CapitalInvestment.csv").exists())
        annual_fixed_found = bool(res and (res / "AnnualFixedOperatingCost.csv").exists())
        annual_variable_found = bool(res and (res / "AnnualVariableOperatingCost.csv").exists())
        penalty_found = bool(res and (res / "DiscountedTechnologyEmissionsPenalty.csv").exists())
        salvage_technology_found = bool(res and (res / "SalvageValue.csv").exists())
        salvage_storage_found = bool(res and (res / "SalvageValueStorage.csv").exists())
        annual_resource_cost_found = (
            annual_capital_found
            and annual_fixed_found
            and annual_variable_found
            and salvage_technology_found
            and salvage_storage_found
        )

        index_ok = status.upper() == "OK"
        known_rep = rep in EXPECTED_REPRESENTATIONS
        locks_ok = results_found and lock_total == 0
        valid = all([index_ok, results_found, solver_ok, locks_ok, rep_ok, future_ok, known_rep])

        msg = []
        if not index_ok: msg.append(f"index_status={status}")
        if not results_found: msg.append("missing Experiment_Results rows")
        if results_found and not solver_ok: msg.append("non-OPTIMAL block")
        if results_found and not locks_ok: msg.append(f"lock_violations={lock_total:g}")
        if results_found and not rep_ok: msg.append("representation mismatch")
        if results_found and not future_ok: msg.append("future_id mismatch")
        if not known_rep: msg.append(f"unknown representation={rep}")
        if res is None: msg.append("raw run folder unavailable")
        elif not emissions_found: msg.append("AnnualEmissions.csv unavailable")
        if res is not None and not annual_resource_cost_found:
            msg.append("annual resource-cost outputs unavailable/incomplete")

        rows.append({
            "run_id": run_id,
            "representation": rep,
            "future_id": future,
            "lambda0": idx.get("lambda0", np.nan),
            "kp": idx.get("kp", np.nan),
            "policy_id": idx.get("policy_id", ""),
            "index_status": status,
            "n_blocks": n_blocks,
            "solver_ok": bool(solver_ok),
            "locks_ok": bool(locks_ok),
            "lock_violations_total": lock_total,
            "max_lock_violation": max_lock,
            "results_found": bool(results_found),
            "results_representation_ok": bool(rep_ok),
            "results_future_ok": bool(future_ok),
            "raw_run_folder_found": res is not None,
            "emissions_found": emissions_found,
            "annual_capital_found": annual_capital_found,
            "annual_fixed_found": annual_fixed_found,
            "annual_variable_found": annual_variable_found,
            "salvage_technology_found": salvage_technology_found,
            "salvage_storage_found": salvage_storage_found,
            "annual_resource_cost_found": annual_resource_cost_found,
            "emissions_penalty_found": penalty_found,
            "valid_run": bool(valid),
            "validation_message": "; ".join(msg) if msg else "OK",
        })

    return pd.DataFrame(rows)


def build_run_metrics(
    experiment_dir: Path,
    index_df: pd.DataFrame,
    results_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    start_year: int,
    target_year: int,
    discount_rate: Optional[float],
    discount_rate_source: str,
) -> pd.DataFrame:
    groups = {rid: g.sort_values("block").copy() for rid, g in results_df.groupby("run_id", sort=False)}
    val = validation_df.set_index("run_id")
    rows = []

    meta_cols = [
        "run_id", "representation", "future_id", "trajectory", "direction",
        "demand_delta", "step_year", "reveal_year", "lambda0", "kp",
        "policy_id", "policy_trajectory", "policy_direction",
        "policy_delta_final", "lambda_final", "status",
    ]

    for _, idx in index_df.iterrows():
        run_id = str(idx["run_id"])
        grp = groups.get(run_id)
        if grp is None or grp.empty:
            continue

        final = grp.iloc[-1]
        terminal = float(final["performance"])
        target = float(final["target"])
        deviation = terminal - target

        lapplied = pd.to_numeric(grp["lambda_applied"], errors="coerce")
        lnext = pd.to_numeric(grp["lambda_next"], errors="coerce")
        lambdas = pd.concat([lapplied, lnext], ignore_index=True).dropna()
        lambda_max = float(lambdas.max()) if not lambdas.empty else np.nan
        lambda_final_actual = (
            float(lnext.dropna().iloc[-1]) if lnext.notna().any()
            else float(lapplied.dropna().iloc[-1]) if lapplied.notna().any()
            else np.nan
        )
        paired = pd.DataFrame({"applied": lapplied, "next": lnext}).dropna()
        policy_adjustment = (
            float((paired["next"] - paired["applied"]).abs().sum())
            if not paired.empty else np.nan
        )

        run_folder = resolve_run_folder(experiment_dir, idx.get("run_folder", ""), run_id)
        res = locate_res_folder(run_folder)
        cumulative, raw_final = annual_emission_metrics(
            read_optional_csv(res, "AnnualEmissions.csv"),
            start_year=start_year,
            target_year=target_year,
            emission_selector="CO2",
        )

        capital_annual_df = read_optional_csv(res, "CapitalInvestment.csv")
        fixed_annual_df = read_optional_csv(res, "AnnualFixedOperatingCost.csv")
        variable_annual_df = read_optional_csv(res, "AnnualVariableOperatingCost.csv")
        penalty_df = read_optional_csv(res, "DiscountedTechnologyEmissionsPenalty.csv")
        salvage_tech_df = read_optional_csv(res, "SalvageValue.csv")
        salvage_storage_df = read_optional_csv(res, "SalvageValueStorage.csv")

        discounted_capital = discount_annual_cost_file(
            capital_annual_df,
            ["CapitalInvestment", "capital_investment", "capitalinvestment", "value"],
            start_year, target_year, discount_rate, timing="start",
        )
        discounted_fixed = discount_annual_cost_file(
            fixed_annual_df,
            ["AnnualFixedOperatingCost", "annual_fixed_operating_cost",
             "annualfixedoperatingcost", "value"],
            start_year, target_year, discount_rate, timing="mid",
        )
        discounted_variable = discount_annual_cost_file(
            variable_annual_df,
            ["AnnualVariableOperatingCost", "annual_variable_operating_cost",
             "annualvariableoperatingcost", "value"],
            start_year, target_year, discount_rate, timing="mid",
        )
        penalty = sum_value(
            penalty_df,
            ["DiscountedTechnologyEmissionsPenalty",
             "discounted_technology_emissions_penalty",
             "discountedtechnologyemissionspenalty", "value"],
        )

        discounted_salvage_technology = discounted_salvage_value(
            salvage_tech_df,
            ["SalvageValue", "salvage_value", "salvagevalue", "value"],
            start_year,
            target_year,
            discount_rate,
        )
        discounted_salvage_storage = discounted_salvage_value(
            salvage_storage_df,
            ["SalvageValueStorage", "salvage_value_storage",
             "salvagevaluestorage", "value"],
            start_year,
            target_year,
            discount_rate,
        )

        positive_components = [
            discounted_capital,
            discounted_fixed,
            discounted_variable,
        ]
        salvage_components = [
            discounted_salvage_technology,
            discounted_salvage_storage,
        ]

        resource_cost = (
            float(
                np.nansum(positive_components)
                - np.nansum(salvage_components)
            )
            if not all(np.isnan(v) for v in positive_components)
            else np.nan
        )
        cost_with_penalty = (
            resource_cost + penalty
            if not np.isnan(resource_cost) and not np.isnan(penalty)
            else np.nan
        )

        objective_final = pd.to_numeric(
            pd.Series([final.get("objective", np.nan)]),
            errors="coerce",
        ).iloc[0]
        objective_residual = (
            float(objective_final - cost_with_penalty)
            if not np.isnan(objective_final) and not np.isnan(cost_with_penalty)
            else np.nan
        )
        objective_relative_error = (
            abs(objective_residual) / max(abs(float(objective_final)), 1e-12)
            if not np.isnan(objective_residual)
            else np.nan
        )

        v = val.loc[run_id]
        row = {col: idx.get(col, "") for col in meta_cols}
        row.update({
            "n_blocks": int(grp["block"].dropna().nunique()),
            "target_year": target_year,
            "terminal_emissions": terminal,
            "target": target,
            "target_deviation": deviation,
            "absolute_target_deviation": abs(deviation),
            "cumulative_emissions_CO2": cumulative,
            "annual_emissions_final_raw_CO2": raw_final,
            "lambda_final_actual": lambda_final_actual,
            "lambda_max_run": lambda_max,
            "total_policy_adjustment": policy_adjustment,
            "discount_rate": discount_rate,
            "discount_rate_source": discount_rate_source,
            "discounted_capital_investment": discounted_capital,
            "discounted_fixed_operating_cost": discounted_fixed,
            "discounted_variable_operating_cost": discounted_variable,
            "discounted_salvage_value_technology": discounted_salvage_technology,
            "discounted_salvage_value_storage": discounted_salvage_storage,
            "discounted_salvage_value_total": (
                np.nansum([
                    discounted_salvage_technology,
                    discounted_salvage_storage,
                ])
                if not (
                    np.isnan(discounted_salvage_technology)
                    and np.isnan(discounted_salvage_storage)
                )
                else np.nan
            ),
            "discounted_resource_cost": resource_cost,
            "discounted_emissions_penalty": penalty,
            "discounted_total_cost_with_penalty": cost_with_penalty,
            "objective_final": objective_final,
            "objective_reconciliation_residual": objective_residual,
            "objective_reconciliation_relative_error": objective_relative_error,
            "solver_ok": bool(v["solver_ok"]),
            "lock_violations_total": v["lock_violations_total"],
            "max_lock_violation": v["max_lock_violation"],
            "valid_run": bool(v["valid_run"]),
        })
        rows.append(row)

    return pd.DataFrame(rows)




def canonical_representation(value) -> str:
    """Normalize A5 representation labels without changing the source CSV."""
    x = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "no_policy": "no_policy",
        "nopolicy": "no_policy",
        "np": "no_policy",
        "prescribed": "prescribed",
        "prescribed_policy": "prescribed",
        "clpr": "closed_loop",
        "closed_loop": "closed_loop",
        "closedloop": "closed_loop",
        "closed_loop_policy": "closed_loop",
    }
    return aliases.get(x, x)


def add_target_tracking_metrics(
    metrics: pd.DataFrame,
    target_tolerance: float = 1e-6,
) -> pd.DataFrame:
    """
    A6.5 first analytical layer.

    Adds target-tracking and No-Policy-relative metrics while preserving
    one row per experimental configuration.

    Comparisons are always made within the same demand future so that:
      No Policy -> Prescribed measures the effect of introducing policy.
      No Policy -> Closed Loop measures the full policy response.
    """
    out = metrics.copy()
    out["representation_canonical"] = out["representation"].map(
        canonical_representation
    )

    numeric_cols = [
        "terminal_emissions",
        "target_deviation",
        "absolute_target_deviation",
        "cumulative_emissions_CO2",
        "discounted_resource_cost",
        "discounted_total_cost_with_penalty",
    ]
    for col in numeric_cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    out["target_tolerance"] = float(target_tolerance)
    out["target_met"] = (
        out["absolute_target_deviation"].le(float(target_tolerance))
        & out["absolute_target_deviation"].notna()
    )

    # One No-Policy reference per future is expected by A5.
    np_rows = out[
        out["representation_canonical"].eq("no_policy")
    ].copy()

    # Keep the first only if a future unexpectedly contains duplicates.
    np_rows = np_rows.sort_values("run_id").drop_duplicates("future_id", keep="first")

    ref_cols = {
        "terminal_emissions": "np_terminal_emissions",
        "target_deviation": "np_target_deviation",
        "absolute_target_deviation": "np_absolute_target_deviation",
        "cumulative_emissions_CO2": "np_cumulative_emissions_CO2",
        "discounted_resource_cost": "np_discounted_resource_cost",
        "discounted_total_cost_with_penalty": "np_discounted_total_cost_with_penalty",
    }

    ref = np_rows[["future_id", *ref_cols.keys()]].rename(columns=ref_cols)
    out = out.merge(ref, on="future_id", how="left", validate="many_to_one")

    out["target_improvement_vs_no_policy"] = (
        out["np_absolute_target_deviation"] - out["absolute_target_deviation"]
    )

    denom = out["np_absolute_target_deviation"].abs()
    out["target_improvement_fraction_vs_no_policy"] = np.where(
        denom > 1e-12,
        out["target_improvement_vs_no_policy"] / denom,
        np.nan,
    )

    np_terminal_denom = out["np_terminal_emissions"].abs()
    out["terminal_emissions_reduction_vs_no_policy_pct"] = np.where(
        np_terminal_denom > 1e-12,
        100.0
        * (out["np_terminal_emissions"] - out["terminal_emissions"])
        / np_terminal_denom,
        np.nan,
    )

    np_cum_denom = out["np_cumulative_emissions_CO2"].abs()
    out["cumulative_emissions_reduction_vs_no_policy_pct"] = np.where(
        np_cum_denom > 1e-12,
        100.0
        * (out["np_cumulative_emissions_CO2"] - out["cumulative_emissions_CO2"])
        / np_cum_denom,
        np.nan,
    )

    out["resource_cost_change_vs_no_policy"] = (
        out["discounted_resource_cost"] - out["np_discounted_resource_cost"]
    )
    np_cost_denom = out["np_discounted_resource_cost"].abs()
    out["resource_cost_premium_vs_no_policy_pct"] = np.where(
        np_cost_denom > 1e-12,
        100.0
        * out["resource_cost_change_vs_no_policy"]
        / np_cost_denom,
        np.nan,
    )

    return out


def build_representation_summary(metrics: pd.DataFrame) -> pd.DataFrame:
    """
    Summarize target tracking by future and representation.
    No weighting or composite score is introduced.
    """
    data = metrics.copy()
    if data.empty:
        return pd.DataFrame()

    rows = []
    for (future_id, rep), grp in data.groupby(
        ["future_id", "representation_canonical"], sort=True
    ):
        absdev = pd.to_numeric(
            grp["absolute_target_deviation"], errors="coerce"
        )
        terminal = pd.to_numeric(grp["terminal_emissions"], errors="coerce")
        improvement = pd.to_numeric(
            grp["target_improvement_fraction_vs_no_policy"], errors="coerce"
        )
        cost_premium = pd.to_numeric(
            grp["resource_cost_premium_vs_no_policy_pct"], errors="coerce"
        )

        rows.append({
            "future_id": future_id,
            "representation": rep,
            "n_runs": len(grp),
            "n_valid_runs": int(grp["valid_run"].fillna(False).astype(bool).sum()),
            "target_success_fraction": float(grp["target_met"].mean()),
            "terminal_emissions_mean": terminal.mean(),
            "terminal_emissions_median": terminal.median(),
            "terminal_emissions_min": terminal.min(),
            "terminal_emissions_max": terminal.max(),
            "absolute_target_deviation_mean": absdev.mean(),
            "absolute_target_deviation_median": absdev.median(),
            "absolute_target_deviation_min": absdev.min(),
            "absolute_target_deviation_max": absdev.max(),
            "target_improvement_fraction_vs_no_policy_mean": improvement.mean(),
            "target_improvement_fraction_vs_no_policy_median": improvement.median(),
            "resource_cost_premium_vs_no_policy_pct_mean": cost_premium.mean(),
            "resource_cost_premium_vs_no_policy_pct_median": cost_premium.median(),
        })

    return pd.DataFrame(rows)


def build_overall_representation_summary(metrics: pd.DataFrame) -> pd.DataFrame:
    """
    Overall descriptive summary across all futures/configurations.
    This is descriptive only: representations contain different numbers of
    configurations, so future-level tables remain the primary comparison.
    """
    data = metrics.copy()
    if data.empty:
        return pd.DataFrame()

    rows = []
    for rep, grp in data.groupby("representation_canonical", sort=True):
        absdev = pd.to_numeric(grp["absolute_target_deviation"], errors="coerce")
        improvement = pd.to_numeric(
            grp["target_improvement_fraction_vs_no_policy"], errors="coerce"
        )
        cost_premium = pd.to_numeric(
            grp["resource_cost_premium_vs_no_policy_pct"], errors="coerce"
        )
        rows.append({
            "representation": rep,
            "n_runs": len(grp),
            "n_valid_runs": int(grp["valid_run"].fillna(False).astype(bool).sum()),
            "n_futures": grp["future_id"].nunique(),
            "target_success_fraction": float(grp["target_met"].mean()),
            "absolute_target_deviation_mean": absdev.mean(),
            "absolute_target_deviation_median": absdev.median(),
            "absolute_target_deviation_worst": absdev.max(),
            "target_improvement_fraction_vs_no_policy_mean": improvement.mean(),
            "target_improvement_fraction_vs_no_policy_median": improvement.median(),
            "resource_cost_premium_vs_no_policy_pct_mean": cost_premium.mean(),
            "resource_cost_premium_vs_no_policy_pct_median": cost_premium.median(),
        })

    return pd.DataFrame(rows)



def build_clpr_heatmap_table(metrics: pd.DataFrame) -> pd.DataFrame:
    """One row per CLPR configuration for controller-response analysis."""
    data = metrics[
        metrics["representation_canonical"].eq("closed_loop")
    ].copy()

    keep = [
        "run_id", "future_id", "lambda0", "kp",
        "terminal_emissions", "target_deviation",
        "absolute_target_deviation", "target_met",
        "discounted_resource_cost",
    ]
    keep = [c for c in keep if c in data.columns]
    out = data[keep].copy()

    for c in ["lambda0", "kp", "terminal_emissions",
              "target_deviation", "absolute_target_deviation",
              "discounted_resource_cost"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")

    return out.sort_values(["future_id", "lambda0", "kp"])


def plot_clpr_heatmaps(metrics: pd.DataFrame, outdir: Path) -> list:
    """
    One heatmap per future:
      x = lambda0
      y = Kp
      cell = absolute deviation from the 2040 target.
    A common scale is used across futures.
    """
    data = metrics[
        metrics["representation_canonical"].eq("closed_loop")
    ].copy()

    if data.empty:
        print(">> CLPR heatmaps skipped: no closed-loop runs found.")
        return []

    data["lambda0"] = pd.to_numeric(data["lambda0"], errors="coerce")
    data["kp"] = pd.to_numeric(data["kp"], errors="coerce")
    data["absolute_target_deviation"] = pd.to_numeric(
        data["absolute_target_deviation"], errors="coerce"
    )
    data = data.dropna(
        subset=["future_id", "lambda0", "kp", "absolute_target_deviation"]
    )
    if data.empty:
        return []

    vmax = float(data["absolute_target_deviation"].max())
    outdir.mkdir(parents=True, exist_ok=True)
    paths = []

    for future_id, grp in data.groupby("future_id", sort=True):
        pivot = grp.pivot_table(
            index="kp",
            columns="lambda0",
            values="absolute_target_deviation",
            aggfunc="mean",
        ).sort_index(ascending=False)

        fig, ax = plt.subplots(figsize=(8.2, 5.4))
        im = ax.imshow(
            pivot.to_numpy(),
            aspect="auto",
            interpolation="nearest",
            vmin=0.0,
            vmax=vmax,
        )

        ax.set_xticks(range(len(pivot.columns)))
        ax.set_xticklabels([f"{x:g}" for x in pivot.columns])
        ax.set_yticks(range(len(pivot.index)))
        ax.set_yticklabels([f"{y:g}" for y in pivot.index])

        ax.set_xlabel("Initial carbon price, λ₀ (USD/tCO$_2$)")
        ax.set_ylabel("Proportional gain, Kₚ")
        ax.set_title(f"CLPR target deviation — future {future_id}")

        for i in range(len(pivot.index)):
            for j in range(len(pivot.columns)):
                val = pivot.iloc[i, j]
                if pd.notna(val):
                    ax.text(j, i, f"{val:.3f}",
                            ha="center", va="center", fontsize=8)

        cbar = fig.colorbar(im, ax=ax)
        cbar.set_label("Absolute deviation from 2040 target")
        fig.tight_layout()

        path = outdir / f"A6_CLPR_heatmap_{future_id}.png"
        fig.savefig(path, dpi=220)
        plt.close(fig)
        paths.append(path)

    return paths


def build_clpr_robustness_table(metrics: pd.DataFrame) -> pd.DataFrame:
    """Aggregate each (lambda0, Kp) pair across all demand futures."""
    data = metrics[
        metrics["representation_canonical"].eq("closed_loop")
    ].copy()
    if data.empty:
        return pd.DataFrame()

    for c in ["lambda0", "kp", "absolute_target_deviation",
              "discounted_resource_cost"]:
        data[c] = pd.to_numeric(data[c], errors="coerce")

    rows = []
    for (lambda0, kp), grp in data.groupby(["lambda0", "kp"], sort=True):
        dev = grp["absolute_target_deviation"].dropna()
        cost = grp["discounted_resource_cost"].dropna()
        rows.append({
            "lambda0": lambda0,
            "kp": kp,
            "n_futures": grp["future_id"].nunique(),
            "target_success_fraction": float(grp["target_met"].mean()),
            "target_deviation_mean": dev.mean(),
            "target_deviation_median": dev.median(),
            "target_deviation_worst": dev.max(),
            "target_deviation_best": dev.min(),
            "discounted_resource_cost_mean": cost.mean(),
            "discounted_resource_cost_worst": cost.max(),
        })

    return pd.DataFrame(rows)



def _future_signed_level(future_id: str, family: str):
    fid = str(future_id).strip().upper()
    if fid == "BASE":
        return 0.0
    prefixes = {"linear": ("LU", "LD"), "step": ("SU", "SD")}
    if family not in prefixes:
        return np.nan
    up, down = prefixes[family]
    if fid.startswith(up):
        try:
            return float(int(fid[2:]))
        except Exception:
            return np.nan
    if fid.startswith(down):
        try:
            return -float(int(fid[2:]))
        except Exception:
            return np.nan
    return np.nan



def build_cost_surface_data(
    metrics,
    value_column,
    value_label,
    family="linear",
    max_deviation=0.50,
):
    """
    Build the same (future deviation, lambda0) median surface used for emissions,
    but for a selected discounted cost metric.

    No Policy is replicated across the lambda0 grid only to preserve comparable
    geometry with Prescribed and Closed Loop.
    """
    data = metrics.copy()
    data["lambda0"] = pd.to_numeric(data["lambda0"], errors="coerce")
    data[value_column] = pd.to_numeric(data[value_column], errors="coerce")
    data["_level"] = data["future_id"].map(
        lambda x: _future_signed_level(x, family)
    )
    data = data[data["_level"].notna()].copy()

    max_level = data["_level"].abs().max()
    if pd.isna(max_level) or max_level == 0:
        max_level = 1.0
    data["future_deviation"] = (
        data["_level"] / max_level * float(max_deviation)
    )

    lambda_grid = sorted(
        data.loc[
            data["representation_canonical"].isin(
                ["prescribed", "closed_loop"]
            ),
            "lambda0",
        ].dropna().unique()
    )

    median_col = f"{value_label}_median"
    rows = []

    for rep in ["no_policy", "prescribed", "closed_loop"]:
        grp = data[data["representation_canonical"].eq(rep)].copy()

        if rep == "no_policy":
            base = (
                grp.groupby(
                    ["future_id", "future_deviation"], as_index=False
                )[value_column]
                .median()
            )
            for _, r in base.iterrows():
                for lam in lambda_grid:
                    rows.append({
                        "representation": rep,
                        "future_id": r["future_id"],
                        "future_deviation": r["future_deviation"],
                        "lambda0": lam,
                        median_col: r[value_column],
                    })
        else:
            agg = (
                grp.groupby(
                    ["future_id", "future_deviation", "lambda0"],
                    as_index=False,
                )[value_column]
                .median()
                .rename(columns={value_column: median_col})
            )
            agg["representation"] = rep
            rows.extend(agg.to_dict("records"))

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    return out.sort_values(
        ["representation", "future_deviation", "lambda0"]
    )


def plot_cost_surface_3d(
    surface_data,
    representation,
    family,
    outdir,
    value_column,
    zmin,
    zmax,
    title_suffix,
    zlabel,
    filename_tag,
):
    grp = surface_data[
        surface_data["representation"].eq(representation)
    ].copy()
    if grp.empty:
        return None

    pivot = grp.pivot_table(
        index="lambda0",
        columns="future_deviation",
        values=value_column,
        aggfunc="median",
    ).sort_index()

    X, Y = np.meshgrid(
        pivot.columns.to_numpy(dtype=float) * 100.0,
        pivot.index.to_numpy(dtype=float),
    )
    Z = pivot.to_numpy(dtype=float)

    fig = plt.figure(figsize=(7.4, 5.8))
    ax = fig.add_subplot(111, projection="3d")
    ax.plot_surface(
        X, Y, Z,
        linewidth=0.3,
        antialiased=True,
        alpha=0.9,
        cmap="viridis",
        vmin=zmin,
        vmax=zmax,
    )
    ax.scatter(X.ravel(), Y.ravel(), Z.ravel(), s=12, depthshade=False)
    ax.set_xlabel("Demand deviation (%)")
    ax.set_ylabel("Initial carbon price, λ₀ (USD/tCO$_2$)")
    ax.set_zlabel(zlabel)
    ax.set_zlim(zmin, zmax)
    ax.set_title(
        f"{representation.replace('_',' ').title()} — "
        f"{family.title()} futures\n{title_suffix}"
    )
    ax.view_init(elev=25, azim=-55)
    fig.tight_layout()

    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / (
        f"A6_{filename_tag}_surface_{family}_{representation}.png"
    )
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_cost_contour_2d(
    surface_data,
    representation,
    family,
    outdir,
    value_column,
    vmin,
    vmax,
    colorbar_label,
    filename_tag,
):
    grp = surface_data[
        surface_data["representation"].eq(representation)
    ].copy()
    if grp.empty:
        return None

    pivot = grp.pivot_table(
        index="lambda0",
        columns="future_deviation",
        values=value_column,
        aggfunc="median",
    ).sort_index()

    X, Y = np.meshgrid(
        pivot.columns.to_numpy(dtype=float) * 100.0,
        pivot.index.to_numpy(dtype=float),
    )
    Z = pivot.to_numpy(dtype=float)

    levels = np.linspace(vmin, vmax, 12)

    fig, ax = plt.subplots(figsize=(7.4, 5.4))
    cf = ax.contourf(
        X, Y, Z,
        levels=levels,
        cmap="viridis",
        vmin=vmin,
        vmax=vmax,
    )
    cs = ax.contour(
        X, Y, Z,
        levels=levels,
        linewidths=0.7,
        cmap="viridis",
        vmin=vmin,
        vmax=vmax,
    )
    ax.clabel(cs, inline=True, fontsize=7, fmt="%.0f")

    ax.set_xlabel("Demand deviation (%)")
    ax.set_ylabel("Initial carbon price, λ₀ (USD/tCO$_2$)")
    ax.set_title(
        f"{representation.replace('_',' ').title()} — {family.title()} futures"
    )

    cbar_ticks = np.linspace(vmin, vmax, 5)
    cbar = fig.colorbar(cf, ax=ax, ticks=cbar_ticks)
    cbar.ax.set_yticklabels([f"{v:.0f}" for v in cbar_ticks])
    cbar.set_label(colorbar_label)

    fig.tight_layout()
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / (
        f"A6_{filename_tag}_contour_{family}_{representation}.png"
    )
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_cost_contour_comparison(
    surface_data,
    family,
    outdir,
    value_column,
    vmin,
    vmax,
    colorbar_label,
    filename_tag,
    figure_title,
):
    """Three policy representations using one common colorbar."""
    reps = [
        ("no_policy", "(a) No Policy"),
        ("prescribed", "(b) Prescribed"),
        ("closed_loop", "(c) Closed Loop"),
    ]

    fig, axes = plt.subplots(
        1, 3,
        figsize=(15.2, 4.8),
        sharex=True,
        sharey=True,
        constrained_layout=True,
    )

    levels = np.linspace(vmin, vmax, 12)
    contour_ref = None

    for ax, (rep, title) in zip(axes, reps):
        grp = surface_data[
            surface_data["representation"].eq(rep)
        ].copy()

        pivot = grp.pivot_table(
            index="lambda0",
            columns="future_deviation",
            values=value_column,
            aggfunc="median",
        ).sort_index()

        X, Y = np.meshgrid(
            pivot.columns.to_numpy(dtype=float) * 100.0,
            pivot.index.to_numpy(dtype=float),
        )
        Z = pivot.to_numpy(dtype=float)

        contour_ref = ax.contourf(
            X, Y, Z,
            levels=levels,
            cmap="viridis",
            vmin=vmin,
            vmax=vmax,
        )
        cs = ax.contour(
            X, Y, Z,
            levels=levels,
            linewidths=0.55,
            cmap="viridis",
            vmin=vmin,
            vmax=vmax,
        )
        ax.clabel(cs, inline=True, fontsize=6.5, fmt="%.0f")
        ax.set_title(title)
        ax.set_xlabel("Demand deviation (%)")

    axes[0].set_ylabel("Initial carbon price, λ₀ (USD/tCO$_2$)")

    cbar_ticks = np.linspace(vmin, vmax, 5)
    cbar = fig.colorbar(
        contour_ref,
        ax=axes,
        ticks=cbar_ticks,
        shrink=0.95,
        pad=0.02,
    )
    cbar.ax.set_yticklabels([f"{v:.0f}" for v in cbar_ticks])
    cbar.set_label(colorbar_label)

    fig.suptitle(
        f"{figure_title} — {family.title()} demand futures",
        fontsize=13,
    )

    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / (
        f"A6_{filename_tag}_contour_{family}_comparison.png"
    )
    fig.savefig(path, dpi=240, bbox_inches="tight")
    plt.close(fig)
    return path



def build_aggregation_diagnostics(metrics, family="linear", max_deviation=0.50, target_tolerance=1e-6):
    """H2: quantify dispersion behind each median surface cell."""
    data=metrics[metrics["representation_canonical"].isin(["prescribed","closed_loop"])].copy()
    data["lambda0"]=pd.to_numeric(data["lambda0"],errors="coerce")
    metrics_cols=["terminal_emissions","discounted_resource_cost","discounted_total_cost_with_penalty"]
    for c in metrics_cols:
        data[c]=pd.to_numeric(data[c],errors="coerce")
    data["_level"]=data["future_id"].map(lambda x:_future_signed_level(x,family))
    data=data[data["_level"].notna()].copy()
    mx=data["_level"].abs().max()
    if pd.isna(mx) or mx==0: mx=1.0
    data["future_deviation_pct"]=data["_level"]/mx*float(max_deviation)*100.0
    rows=[]
    keys=["representation_canonical","future_id","future_deviation_pct","lambda0"]
    for key,g in data.groupby(keys,dropna=False,sort=True):
        rep,fid,dev,lam=key
        row={"representation":rep,"family":family,"future_id":fid,
             "future_deviation_pct":dev,"lambda0":lam,"n_configurations":len(g)}
        for col,prefix in [
            ("terminal_emissions","emissions"),
            ("discounted_resource_cost","resource_cost"),
            ("discounted_total_cost_with_penalty","total_cost_with_penalty")]:
            v=pd.to_numeric(g[col],errors="coerce").dropna()
            if v.empty:
                vals=[np.nan]*7
            else:
                q25=float(v.quantile(.25)); q75=float(v.quantile(.75))
                vals=[float(v.min()),q25,float(v.median()),q75,float(v.max()),
                      q75-q25,float(v.max()-v.min())]
            for n,x in zip(["min","q25","median","q75","max","iqr","range"],vals):
                row[f"{prefix}_{n}"]=x
        e=pd.to_numeric(g["terminal_emissions"],errors="coerce").dropna()
        row["target_success_fraction"]=float((e.abs()<=target_tolerance).mean()) if not e.empty else np.nan
        for prefix in ["resource_cost","total_cost_with_penalty"]:
            med=row[f"{prefix}_median"]; iqr=row[f"{prefix}_iqr"]
            row[f"{prefix}_iqr_pct_of_median"]=100*iqr/abs(med) if pd.notna(med) and abs(med)>1e-12 else np.nan
        rows.append(row)
    return pd.DataFrame(rows)

def build_aggregation_diagnostic_summary(d):
    if d.empty: return pd.DataFrame()
    rows=[]
    for (family,rep),g in d.groupby(["family","representation"],sort=True):
        ei=pd.to_numeric(g["emissions_iqr"],errors="coerce")
        er=pd.to_numeric(g["emissions_range"],errors="coerce")
        ri=pd.to_numeric(g["resource_cost_iqr_pct_of_median"],errors="coerce")
        ti=pd.to_numeric(g["total_cost_with_penalty_iqr_pct_of_median"],errors="coerce")
        sf=pd.to_numeric(g["target_success_fraction"],errors="coerce")
        rows.append({
            "family":family,"representation":rep,"n_cells":len(g),
            "cells_with_5_configurations":int((g["n_configurations"]==5).sum()),
            "emissions_iqr_median":ei.median(),"emissions_iqr_p90":ei.quantile(.9),
            "emissions_iqr_max":ei.max(),"emissions_range_median":er.median(),
            "emissions_range_max":er.max(),
            "resource_cost_iqr_pct_median":ri.median(),"resource_cost_iqr_pct_p90":ri.quantile(.9),
            "resource_cost_iqr_pct_max":ri.max(),
            "total_cost_with_penalty_iqr_pct_median":ti.median(),
            "total_cost_with_penalty_iqr_pct_p90":ti.quantile(.9),
            "total_cost_with_penalty_iqr_pct_max":ti.max(),
            "target_success_fraction_cell_median":sf.median(),
            "cells_all_5_meet_target":int((sf==1).sum()),
            "cells_mixed_target_outcome":int(((sf>0)&(sf<1)).sum()),
            "cells_no_configuration_meets_target":int((sf==0).sum())})
    return pd.DataFrame(rows)



def build_cost_performance_cell_comparison(
    metrics,
    family="linear",
    max_deviation=0.50,
):
    """
    H5 primary matched comparison.

    For every (future, lambda0) cell, compare the median Prescribed outcome
    with the median Closed-Loop outcome.

    Positive target_tracking_improvement_CLPR means CLPR is closer to target.
    Positive resource_cost_premium_CLPR_pct means CLPR is more expensive.
    """
    data = metrics[
        metrics["representation_canonical"].isin(["prescribed", "closed_loop"])
    ].copy()

    data["lambda0"] = pd.to_numeric(data["lambda0"], errors="coerce")
    for c in [
        "absolute_target_deviation",
        "terminal_emissions",
        "discounted_resource_cost",
        "discounted_total_cost_with_penalty",
    ]:
        data[c] = pd.to_numeric(data[c], errors="coerce")

    data["_level"] = data["future_id"].map(
        lambda x: _future_signed_level(x, family)
    )
    data = data[data["_level"].notna()].copy()

    max_level = data["_level"].abs().max()
    if pd.isna(max_level) or max_level == 0:
        max_level = 1.0
    data["future_deviation_pct"] = (
        data["_level"] / max_level * float(max_deviation) * 100.0
    )

    med = (
        data.groupby(
            [
                "future_id",
                "future_deviation_pct",
                "lambda0",
                "representation_canonical",
            ],
            as_index=False,
        )[
            [
                "absolute_target_deviation",
                "terminal_emissions",
                "discounted_resource_cost",
                "discounted_total_cost_with_penalty",
            ]
        ]
        .median()
    )

    pr = med[
        med["representation_canonical"].eq("prescribed")
    ].drop(columns="representation_canonical")
    cl = med[
        med["representation_canonical"].eq("closed_loop")
    ].drop(columns="representation_canonical")

    keys = ["future_id", "future_deviation_pct", "lambda0"]
    pr = pr.rename(columns={
        "absolute_target_deviation": "pr_target_deviation",
        "terminal_emissions": "pr_terminal_emissions",
        "discounted_resource_cost": "pr_resource_cost",
        "discounted_total_cost_with_penalty": "pr_total_cost_with_penalty",
    })
    cl = cl.rename(columns={
        "absolute_target_deviation": "clpr_target_deviation",
        "terminal_emissions": "clpr_terminal_emissions",
        "discounted_resource_cost": "clpr_resource_cost",
        "discounted_total_cost_with_penalty": "clpr_total_cost_with_penalty",
    })

    out = pr.merge(cl, on=keys, how="inner", validate="one_to_one")
    out["family"] = family

    # Positive = CLPR improves target tracking.
    out["target_tracking_improvement_CLPR"] = (
        out["pr_target_deviation"] - out["clpr_target_deviation"]
    )
    denom_d = out["pr_target_deviation"].abs()
    out["target_tracking_improvement_CLPR_pct"] = np.where(
        denom_d > 1e-12,
        100.0 * out["target_tracking_improvement_CLPR"] / denom_d,
        np.nan,
    )

    # Positive = CLPR has higher cost.
    out["resource_cost_difference_CLPR"] = (
        out["clpr_resource_cost"] - out["pr_resource_cost"]
    )
    out["resource_cost_premium_CLPR_pct"] = np.where(
        out["pr_resource_cost"].abs() > 1e-12,
        100.0 * out["resource_cost_difference_CLPR"]
        / out["pr_resource_cost"].abs(),
        np.nan,
    )

    out["total_cost_difference_CLPR"] = (
        out["clpr_total_cost_with_penalty"]
        - out["pr_total_cost_with_penalty"]
    )
    out["total_cost_premium_CLPR_pct"] = np.where(
        out["pr_total_cost_with_penalty"].abs() > 1e-12,
        100.0 * out["total_cost_difference_CLPR"]
        / out["pr_total_cost_with_penalty"].abs(),
        np.nan,
    )

    # Quadrant classification based on resource cost + target deviation.
    eps = 1e-12
    better = out["target_tracking_improvement_CLPR"] > eps
    worse = out["target_tracking_improvement_CLPR"] < -eps
    cheaper = out["resource_cost_difference_CLPR"] < -eps
    costlier = out["resource_cost_difference_CLPR"] > eps

    out["cost_performance_class"] = "approximately_equal"
    out.loc[better & cheaper, "cost_performance_class"] = "CLPR_better_and_cheaper"
    out.loc[better & costlier, "cost_performance_class"] = "CLPR_better_with_cost_premium"
    out.loc[worse & cheaper, "cost_performance_class"] = "CLPR_worse_but_cheaper"
    out.loc[worse & costlier, "cost_performance_class"] = "CLPR_worse_and_costlier"

    # Dominance of median cell outcome.
    out["CLPR_dominates_PR_resource_cost"] = (
        (out["clpr_resource_cost"] <= out["pr_resource_cost"] + eps)
        & (out["clpr_target_deviation"] <= out["pr_target_deviation"] + eps)
        & (
            (out["clpr_resource_cost"] < out["pr_resource_cost"] - eps)
            | (out["clpr_target_deviation"] < out["pr_target_deviation"] - eps)
        )
    )
    out["PR_dominates_CLPR_resource_cost"] = (
        (out["pr_resource_cost"] <= out["clpr_resource_cost"] + eps)
        & (out["pr_target_deviation"] <= out["clpr_target_deviation"] + eps)
        & (
            (out["pr_resource_cost"] < out["clpr_resource_cost"] - eps)
            | (out["pr_target_deviation"] < out["clpr_target_deviation"] - eps)
        )
    )

    return out.sort_values(["future_deviation_pct", "lambda0"]).reset_index(drop=True)


def build_cost_performance_summary(cell_comparison):
    """Compact H5 summary by Linear/Step family."""
    if cell_comparison.empty:
        return pd.DataFrame()

    rows = []
    for family, g in cell_comparison.groupby("family", sort=True):
        dc = pd.to_numeric(g["resource_cost_premium_CLPR_pct"], errors="coerce")
        dt = pd.to_numeric(g["total_cost_premium_CLPR_pct"], errors="coerce")
        imp = pd.to_numeric(g["target_tracking_improvement_CLPR"], errors="coerce")
        imp_pct = pd.to_numeric(
            g["target_tracking_improvement_CLPR_pct"], errors="coerce"
        )
        cls = g["cost_performance_class"].value_counts()

        rows.append({
            "family": family,
            "n_matched_cells": len(g),
            "target_improvement_median": imp.median(),
            "target_improvement_mean": imp.mean(),
            "target_improvement_pct_median": imp_pct.median(),
            "resource_cost_premium_pct_median": dc.median(),
            "resource_cost_premium_pct_mean": dc.mean(),
            "resource_cost_premium_pct_p90": dc.quantile(0.90),
            "resource_cost_premium_pct_min": dc.min(),
            "resource_cost_premium_pct_max": dc.max(),
            "total_cost_premium_pct_median": dt.median(),
            "total_cost_premium_pct_mean": dt.mean(),
            "cells_CLPR_better_and_cheaper": int(
                cls.get("CLPR_better_and_cheaper", 0)
            ),
            "cells_CLPR_better_with_cost_premium": int(
                cls.get("CLPR_better_with_cost_premium", 0)
            ),
            "cells_CLPR_worse_but_cheaper": int(
                cls.get("CLPR_worse_but_cheaper", 0)
            ),
            "cells_CLPR_worse_and_costlier": int(
                cls.get("CLPR_worse_and_costlier", 0)
            ),
            "cells_approximately_equal": int(
                cls.get("approximately_equal", 0)
            ),
            "cells_CLPR_dominates_PR": int(
                g["CLPR_dominates_PR_resource_cost"].sum()
            ),
            "cells_PR_dominates_CLPR": int(
                g["PR_dominates_CLPR_resource_cost"].sum()
            ),
        })

    return pd.DataFrame(rows)


def _pareto_efficient_mask(cost, deviation):
    """Minimize both cost and target deviation."""
    cost = np.asarray(cost, dtype=float)
    deviation = np.asarray(deviation, dtype=float)
    valid = np.isfinite(cost) & np.isfinite(deviation)
    efficient = np.zeros(len(cost), dtype=bool)

    ids = np.where(valid)[0]
    for i in ids:
        dominated = (
            (cost[ids] <= cost[i])
            & (deviation[ids] <= deviation[i])
            & ((cost[ids] < cost[i]) | (deviation[ids] < deviation[i]))
        )
        if not dominated.any():
            efficient[i] = True

    return efficient


def build_pareto_run_table(metrics, cost_column="discounted_resource_cost"):
    """
    Pareto analysis over all Prescribed + CLPR runs within each future.
    Both dimensions are minimized: cost and absolute target deviation.
    """
    data = metrics[
        metrics["representation_canonical"].isin(["prescribed", "closed_loop"])
    ].copy()

    data[cost_column] = pd.to_numeric(data[cost_column], errors="coerce")
    data["absolute_target_deviation"] = pd.to_numeric(
        data["absolute_target_deviation"], errors="coerce"
    )

    frames = []
    for future_id, g in data.groupby("future_id", sort=True):
        g = g.copy()
        g["pareto_efficient"] = _pareto_efficient_mask(
            g[cost_column].to_numpy(),
            g["absolute_target_deviation"].to_numpy(),
        )
        g["pareto_cost_metric"] = cost_column
        frames.append(g)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def build_pareto_dominance_summary(
    metrics,
    cost_column="discounted_resource_cost",
    matched_lambda0=False,
):
    """
    Cross-representation dominance by future.

    fraction_PR_dominated_by_any_CLPR answers:
      What fraction of Prescribed alternatives are dominated by at least
      one CLPR alternative?

    matched_lambda0=True restricts dominance comparisons to the same lambda0,
    giving a stricter representation-level comparison.
    """
    data = metrics[
        metrics["representation_canonical"].isin(["prescribed", "closed_loop"])
    ].copy()

    data["lambda0"] = pd.to_numeric(data["lambda0"], errors="coerce")
    data[cost_column] = pd.to_numeric(data[cost_column], errors="coerce")
    data["absolute_target_deviation"] = pd.to_numeric(
        data["absolute_target_deviation"], errors="coerce"
    )

    rows = []
    eps = 1e-12

    for future_id, g in data.groupby("future_id", sort=True):
        pr = g[g["representation_canonical"].eq("prescribed")].copy()
        cl = g[g["representation_canonical"].eq("closed_loop")].copy()

        pr_dominated = []
        for _, r in pr.iterrows():
            candidates = cl
            if matched_lambda0:
                candidates = candidates[
                    np.isclose(
                        candidates["lambda0"].astype(float),
                        float(r["lambda0"]),
                        rtol=0,
                        atol=1e-9,
                    )
                ]
            dom = (
                (candidates[cost_column] <= r[cost_column] + eps)
                & (
                    candidates["absolute_target_deviation"]
                    <= r["absolute_target_deviation"] + eps
                )
                & (
                    (candidates[cost_column] < r[cost_column] - eps)
                    | (
                        candidates["absolute_target_deviation"]
                        < r["absolute_target_deviation"] - eps
                    )
                )
            )
            pr_dominated.append(bool(dom.any()))

        cl_dominated = []
        for _, r in cl.iterrows():
            candidates = pr
            if matched_lambda0:
                candidates = candidates[
                    np.isclose(
                        candidates["lambda0"].astype(float),
                        float(r["lambda0"]),
                        rtol=0,
                        atol=1e-9,
                    )
                ]
            dom = (
                (candidates[cost_column] <= r[cost_column] + eps)
                & (
                    candidates["absolute_target_deviation"]
                    <= r["absolute_target_deviation"] + eps
                )
                & (
                    (candidates[cost_column] < r[cost_column] - eps)
                    | (
                        candidates["absolute_target_deviation"]
                        < r["absolute_target_deviation"] - eps
                    )
                )
            )
            cl_dominated.append(bool(dom.any()))

        rows.append({
            "future_id": future_id,
            "cost_metric": cost_column,
            "matched_lambda0": bool(matched_lambda0),
            "n_prescribed": len(pr),
            "n_clpr": len(cl),
            "fraction_PR_dominated_by_any_CLPR": (
                float(np.mean(pr_dominated)) if pr_dominated else np.nan
            ),
            "fraction_CLPR_dominated_by_any_PR": (
                float(np.mean(cl_dominated)) if cl_dominated else np.nan
            ),
            "n_PR_dominated_by_any_CLPR": int(np.sum(pr_dominated)),
            "n_CLPR_dominated_by_any_PR": int(np.sum(cl_dominated)),
        })

    return pd.DataFrame(rows)


def build_pareto_frontier_summary(pareto_runs):
    if pareto_runs.empty:
        return pd.DataFrame()

    rows = []
    for (future_id, cost_metric), g in pareto_runs.groupby(
        ["future_id", "pareto_cost_metric"], sort=True
    ):
        frontier = g[g["pareto_efficient"]]
        counts = frontier["representation_canonical"].value_counts()
        rows.append({
            "future_id": future_id,
            "cost_metric": cost_metric,
            "n_frontier_total": len(frontier),
            "n_frontier_prescribed": int(counts.get("prescribed", 0)),
            "n_frontier_clpr": int(counts.get("closed_loop", 0)),
            "fraction_frontier_CLPR": (
                float(counts.get("closed_loop", 0) / len(frontier))
                if len(frontier) else np.nan
            ),
        })
    return pd.DataFrame(rows)


def plot_cost_performance_delta(cell_comparison, family, outdir):
    """
    Primary H5 figure.
    x > 0: CLPR costs more than Prescribed.
    y > 0: CLPR improves target tracking relative to Prescribed.
    Each point is one matched (future, lambda0) median comparison.
    """
    data = cell_comparison[
        cell_comparison["family"].eq(family)
    ].copy()
    data = data.dropna(
        subset=[
            "resource_cost_premium_CLPR_pct",
            "target_tracking_improvement_CLPR",
        ]
    )
    if data.empty:
        return None

    outdir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.2, 5.6))

    ax.scatter(
        data["resource_cost_premium_CLPR_pct"],
        data["target_tracking_improvement_CLPR"],
        alpha=0.75,
    )
    ax.axvline(0.0, linewidth=1.0)
    ax.axhline(0.0, linewidth=1.0)

    ax.set_xlabel("CLPR resource-cost premium vs Prescribed (%)")
    ax.set_ylabel("Target-tracking improvement of CLPR")
    ax.set_title(
        f"Cost–performance comparison — {family.title()} demand futures"
    )

    fig.tight_layout()
    path = outdir / f"A6_cost_performance_delta_{family}.png"
    fig.savefig(path, dpi=220)
    plt.close(fig)
    return path



def _demand_direction_from_future(future_id, family):
    level = _future_signed_level(future_id, family)
    if level is None or pd.isna(level):
        return None
    if level < 0:
        return "Decrease"
    if level > 0:
        return "Increase"
    return None


def _prepare_direction_box_data(metrics, family, value_col):
    data=metrics[
        metrics["representation_canonical"].isin(["prescribed","closed_loop"])
    ].copy()
    data["lambda0"]=pd.to_numeric(data["lambda0"],errors="coerce")
    data[value_col]=pd.to_numeric(data[value_col],errors="coerce")
    data["demand_direction"]=data["future_id"].map(
        lambda x:_demand_direction_from_future(x,family)
    )
    return data[
        data["demand_direction"].isin(["Decrease","Increase"])
        & data["lambda0"].notna()
        & data[value_col].notna()
    ].copy()


def plot_direction_box_metric(metrics,value_col,ylabel,title,outpath):
    families=["linear","step"]
    fig,axes=plt.subplots(1,2,figsize=(14.5,5.8),sharey=True,constrained_layout=True)
    rep_order=["prescribed","closed_loop"]
    direction_order=["Decrease","Increase"]
    offsets={
        ("Decrease","prescribed"):-0.27,
        ("Decrease","closed_loop"):-0.09,
        ("Increase","prescribed"):0.09,
        ("Increase","closed_loop"):0.27,
    }
    all_data={f:_prepare_direction_box_data(metrics,f,value_col) for f in families}
    lambda_values=sorted(set().union(*[
        set(d["lambda0"].dropna().unique()) for d in all_data.values() if not d.empty
    ]))
    base_positions=np.arange(len(lambda_values),dtype=float)

    default_colors=plt.rcParams["axes.prop_cycle"].by_key()["color"]
    rep_colors={"prescribed":default_colors[1 % len(default_colors)],
                "closed_loop":default_colors[0]}
    direction_hatch={"Decrease":"//","Increase":""}

    for ax,family in zip(axes,families):
        data=all_data[family]
        for direction in direction_order:
            for rep in rep_order:
                positions=[]
                values=[]
                for i,lam in enumerate(lambda_values):
                    vals=data[
                        np.isclose(data["lambda0"],lam)
                        & data["demand_direction"].eq(direction)
                        & data["representation_canonical"].eq(rep)
                    ][value_col].dropna().to_numpy()
                    if len(vals):
                        positions.append(base_positions[i]+offsets[(direction,rep)])
                        values.append(vals)
                if values:
                    bp=ax.boxplot(values,positions=positions,widths=0.16,
                                  patch_artist=True,showfliers=True,manage_ticks=False,
                                  medianprops={"linewidth":1.2})
                    for box in bp["boxes"]:
                        box.set_facecolor(rep_colors[rep])
                        box.set_alpha(0.70)
                        box.set_hatch(direction_hatch[direction])
        ax.set_title(f"{family.title()} demand")
        ax.set_xlabel(r"Initial carbon price, $\lambda_0$ (USD/tCO$_2$)")
        ax.set_xticks(base_positions)
        ax.set_xticklabels([f"{x:g}" for x in lambda_values])
        ax.grid(axis="y",alpha=0.25)

    axes[0].set_ylabel(ylabel)
    fig.suptitle(title,fontsize=13)

    from matplotlib.patches import Patch
    handles=[
        Patch(facecolor=rep_colors["closed_loop"],alpha=0.70,label="CLPR"),
        Patch(facecolor=rep_colors["prescribed"],alpha=0.70,label="Prescribed"),
        Patch(facecolor="white",edgecolor="black",hatch="//",label="Demand decrease"),
        Patch(facecolor="white",edgecolor="black",label="Demand increase"),
    ]
    fig.legend(handles=handles,loc="upper center",bbox_to_anchor=(0.5,0.93),
               ncol=4,frameon=False)

    outpath.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(outpath,dpi=240,bbox_inches="tight")
    plt.close(fig)
    return outpath


def plot_all_combinations_scatter(metrics,x_col,xlabel,y_col,ylabel,title,outpath):
    data=metrics[
        metrics["representation_canonical"].isin(["prescribed","closed_loop"])
    ].copy()
    data[x_col]=pd.to_numeric(data[x_col],errors="coerce")
    data[y_col]=pd.to_numeric(data[y_col],errors="coerce")
    data=data.dropna(subset=[x_col,y_col])

    fig,ax=plt.subplots(figsize=(8.2,6.2))
    for rep,label in [("prescribed","Prescribed"),("closed_loop","CLPR")]:
        d=data[data["representation_canonical"].eq(rep)]
        ax.scatter(d[x_col],d[y_col],s=22,alpha=0.62,label=label)

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(alpha=0.25)
    ax.legend()
    outpath.parent.mkdir(parents=True,exist_ok=True)
    fig.tight_layout()
    fig.savefig(outpath,dpi=240,bbox_inches="tight")
    plt.close(fig)
    return outpath



def _trajectory_family(future_id):
    """Return linear/step for non-BASE futures; BASE is excluded."""
    fid = str(future_id).strip().upper()
    if fid.startswith(("LU", "LD")):
        return "linear"
    if fid.startswith(("SU", "SD")):
        return "step"
    return None


def build_carbon_price_trajectory_table(
    index_df,
    results_df,
    start_year,
    target_year,
):
    """
    Reconstruct annual carbon-price trajectories for Prescribed and CLPR.

    Prescribed:
        exact ex-ante annual linear/flat curve from lambda0 and
        policy_delta_final.

    CLPR:
        piecewise-constant annual trajectory reconstructed from the
        stage/block lambda_applied values stored by A5.

    BASE futures are excluded so the two panels summarize perturbed futures.
    """
    result_groups = {
        str(rid): g.sort_values("block").copy()
        for rid, g in results_df.groupby("run_id", sort=False)
    }

    rows = []
    years = list(range(int(start_year), int(target_year) + 1))

    for _, r in index_df.iterrows():
        rep = str(r.get("representation", "")).strip().lower()
        if rep not in {"prescribed", "closed_loop"}:
            continue

        family = _trajectory_family(r.get("future_id", ""))
        if family is None:
            continue

        run_id = str(r["run_id"])
        lambda0 = pd.to_numeric(pd.Series([r.get("lambda0", np.nan)]),
                                errors="coerce").iloc[0]
        if pd.isna(lambda0):
            continue

        if rep == "prescribed":
            delta = pd.to_numeric(
                pd.Series([r.get("policy_delta_final", np.nan)]),
                errors="coerce",
            ).iloc[0]
            if pd.isna(delta):
                continue
            lambda_final = float(lambda0) * (1.0 + float(delta))

            trajectory = str(r.get("policy_trajectory", "")).strip().lower()
            if trajectory == "flat" or target_year == start_year:
                curve = {y: float(lambda0) for y in years}
            else:
                curve = {
                    y: float(lambda0)
                    + (lambda_final - float(lambda0))
                    * (y - start_year) / (target_year - start_year)
                    for y in years
                }

        else:
            grp = result_groups.get(run_id)
            if grp is None or grp.empty:
                continue

            curve = {}
            for _, b in grp.iterrows():
                b0 = pd.to_numeric(
                    pd.Series([b.get("block_start_year", np.nan)]),
                    errors="coerce",
                ).iloc[0]
                b1 = pd.to_numeric(
                    pd.Series([b.get("block_end_year", np.nan)]),
                    errors="coerce",
                ).iloc[0]
                lam = pd.to_numeric(
                    pd.Series([b.get("lambda_applied", np.nan)]),
                    errors="coerce",
                ).iloc[0]
                if pd.isna(b0) or pd.isna(b1) or pd.isna(lam):
                    continue
                for y in range(int(b0), int(b1) + 1):
                    if start_year <= y <= target_year:
                        curve[y] = float(lam)

            # Defensive fill in case a block boundary is absent.
            last = float(lambda0)
            for y in years:
                if y in curve:
                    last = curve[y]
                else:
                    curve[y] = last

        for y in years:
            rows.append({
                "run_id": run_id,
                "representation": rep,
                "family": family,
                "future_id": r.get("future_id", ""),
                "lambda0": float(lambda0),
                "year": y,
                "carbon_price": curve.get(y, np.nan),
            })

    return pd.DataFrame(rows)


def _read_annual_co2_series(df):
    """Return year/value CO2 annual-emissions series from AnnualEmissions.csv."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["year", "annual_emissions_CO2"])

    ycol = named_column(df, ["y", "year"])
    ecol = named_column(df, ["e", "emission", "emissions", "emission_type"])
    vcol = value_column(
        df, ["AnnualEmissions", "annual_emissions", "annualemissions", "value"]
    )
    if ycol is None or ecol is None or vcol is None:
        return pd.DataFrame(columns=["year", "annual_emissions_CO2"])

    tmp = df[[ycol, ecol, vcol]].copy()
    tmp[ycol] = pd.to_numeric(tmp[ycol], errors="coerce")
    tmp[vcol] = pd.to_numeric(tmp[vcol], errors="coerce")

    labels = tmp[ecol].astype(str).str.strip().str.upper()
    exact = labels.eq("CO2")
    tmp = tmp.loc[exact if exact.any() else labels.str.contains("CO2", regex=False)]
    tmp = tmp.dropna(subset=[ycol, vcol])

    yearly = (
        tmp.groupby(ycol, as_index=False)[vcol]
        .sum()
        .rename(columns={ycol: "year", vcol: "annual_emissions_CO2"})
    )
    return yearly


def build_annual_emissions_trajectory_table(
    experiment_dir,
    index_df,
    start_year,
    target_year,
):
    """
    Extract annual CO2 trajectories from each run's final-stage
    AnnualEmissions.csv.

    IMPORTANT:
    these are final-stage full-horizon plan trajectories, not stitched
    realized sequential emissions by committed block.
    """
    rows = []

    for _, r in index_df.iterrows():
        rep = str(r.get("representation", "")).strip().lower()
        if rep not in {"prescribed", "closed_loop"}:
            continue

        family = _trajectory_family(r.get("future_id", ""))
        if family is None:
            continue

        run_id = str(r["run_id"])
        run_folder = resolve_run_folder(
            experiment_dir, r.get("run_folder", ""), run_id
        )
        res = locate_res_folder(run_folder)
        df = read_optional_csv(res, "AnnualEmissions.csv")
        yearly = _read_annual_co2_series(df)
        if yearly.empty:
            continue

        yearly = yearly[
            (yearly["year"] >= start_year) & (yearly["year"] <= target_year)
        ]

        for _, yr in yearly.iterrows():
            rows.append({
                "run_id": run_id,
                "representation": rep,
                "family": family,
                "future_id": r.get("future_id", ""),
                "lambda0": r.get("lambda0", np.nan),
                "year": int(yr["year"]),
                "annual_emissions_CO2": float(yr["annual_emissions_CO2"]),
            })

    return pd.DataFrame(rows)


def summarize_trajectory_quantiles(df, value_col):
    """Median, P10/P25/P75/P90, min and max by family/representation/year."""
    if df.empty:
        return pd.DataFrame()

    def q10(x): return x.quantile(0.10)
    def q25(x): return x.quantile(0.25)
    def q75(x): return x.quantile(0.75)
    def q90(x): return x.quantile(0.90)

    out = (
        df.groupby(["family", "representation", "year"])[value_col]
        .agg(
            n="count",
            minimum="min",
            p10=q10,
            p25=q25,
            median="median",
            p75=q75,
            p90=q90,
            maximum="max",
        )
        .reset_index()
    )
    return out


def plot_trajectory_medians(
    summary,
    value_col_prefix,
    ylabel,
    title,
    outpath,
):
    """1x2 Linear/Step panel with representation-level median trajectories."""
    fig, axes = plt.subplots(
        1, 2, figsize=(13.5, 5.2), sharey=True, constrained_layout=True
    )

    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    style = {
        "closed_loop": {"label": "CLPR", "color": colors[0]},
        "prescribed": {"label": "Prescribed", "color": colors[1]},
    }

    for ax, family in zip(axes, ["linear", "step"]):
        d = summary[summary["family"].eq(family)]
        for rep in ["closed_loop", "prescribed"]:
            r = d[d["representation"].eq(rep)].sort_values("year")
            if r.empty:
                continue
            ax.plot(
                r["year"],
                r["median"],
                linewidth=2.0,
                label=style[rep]["label"],
                color=style[rep]["color"],
            )

        ax.set_title(f"{family.title()} demand")
        ax.set_xlabel("Year")
        ax.grid(alpha=0.25)

    axes[0].set_ylabel(ylabel)
    axes[1].legend()
    fig.suptitle(title, fontsize=13)
    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(outpath, dpi=240, bbox_inches="tight")
    plt.close(fig)
    return outpath


def plot_emissions_trajectory_bands(
    summary,
    ylabel,
    title,
    outpath,
):
    """
    1x2 Linear/Step panel with median annual-emissions trajectories and
    P10–P90 bands for Prescribed and CLPR.
    """
    fig, axes = plt.subplots(
        1, 2, figsize=(13.5, 5.2), sharey=True, constrained_layout=True
    )

    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    style = {
        "closed_loop": {"label": "CLPR", "color": colors[0]},
        "prescribed": {"label": "Prescribed", "color": colors[1]},
    }

    for ax, family in zip(axes, ["linear", "step"]):
        d = summary[summary["family"].eq(family)]
        for rep in ["closed_loop", "prescribed"]:
            r = d[d["representation"].eq(rep)].sort_values("year")
            if r.empty:
                continue

            x = r["year"].to_numpy(dtype=float)
            med = r["median"].to_numpy(dtype=float)
            lo = r["p10"].to_numpy(dtype=float)
            hi = r["p90"].to_numpy(dtype=float)

            ax.fill_between(
                x, lo, hi,
                alpha=0.20,
                color=style[rep]["color"],
            )
            ax.plot(
                x, med,
                linewidth=2.0,
                color=style[rep]["color"],
                label=f'{style[rep]["label"]} median',
            )

        ax.set_title(f"{family.title()} demand")
        ax.set_xlabel("Year")
        ax.grid(alpha=0.25)

    axes[0].set_ylabel(ylabel)
    axes[1].legend()
    fig.suptitle(title, fontsize=13)
    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(outpath, dpi=240, bbox_inches="tight")
    plt.close(fig)
    return outpath



def _trajectory_scenario_group(future_id):
    """Map perturbed future IDs to LU, SU, LD, SD; BASE excluded."""
    fid = str(future_id).strip().upper()
    for prefix in ("LU", "SU", "LD", "SD"):
        if fid.startswith(prefix):
            return prefix
    return None


def summarize_trajectory_quantiles_by_scenario(df, value_col):
    """Median and P10-P90 by LU/SU/LD/SD, representation, and year."""
    if df.empty:
        return pd.DataFrame()

    data = df.copy()
    data["scenario_group"] = data["future_id"].map(_trajectory_scenario_group)
    data = data[data["scenario_group"].notna()].copy()

    def q10(x): return x.quantile(0.10)
    def q90(x): return x.quantile(0.90)

    return (
        data.groupby(["scenario_group", "representation", "year"])[value_col]
        .agg(n="count", p10=q10, median="median", p90=q90)
        .reset_index()
    )


def plot_trajectory_bands_2x2(
    summary,
    ylabel,
    title,
    outpath,
):
    """
    2x2 panel ordered LU, SU, LD, SD.
    Each panel shows CLPR and Prescribed median trajectories with P10-P90 bands.
    """
    order = [("LU", "Linear up"), ("SU", "Step up"),
             ("LD", "Linear down"), ("SD", "Step down")]

    fig, axes = plt.subplots(
        2, 2, figsize=(13.5, 9.0), sharex=True, sharey=True,
        constrained_layout=True
    )
    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    style = {
        "closed_loop": {"label": "CLPR", "color": colors[0]},
        "prescribed": {"label": "Prescribed", "color": colors[1]},
    }

    for ax, (scenario, panel_title) in zip(axes.flat, order):
        d = summary[summary["scenario_group"].eq(scenario)]
        for rep in ["closed_loop", "prescribed"]:
            r = d[d["representation"].eq(rep)].sort_values("year")
            if r.empty:
                continue
            x = r["year"].to_numpy(dtype=float)
            med = r["median"].to_numpy(dtype=float)
            lo = r["p10"].to_numpy(dtype=float)
            hi = r["p90"].to_numpy(dtype=float)

            ax.fill_between(
                x, lo, hi, alpha=0.20, color=style[rep]["color"]
            )
            ax.plot(
                x, med, linewidth=2.0, color=style[rep]["color"],
                label=style[rep]["label"]
            )

        ax.set_title(panel_title)
        ax.grid(alpha=0.25)

    axes[1, 0].set_xlabel("Year")
    axes[1, 1].set_xlabel("Year")
    axes[0, 0].set_ylabel(ylabel)
    axes[1, 0].set_ylabel(ylabel)

    handles, labels = axes[0, 0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="upper center",
                   bbox_to_anchor=(0.5, 0.965), ncol=2, frameon=False)

    fig.suptitle(title, fontsize=13)
    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(outpath, dpi=240, bbox_inches="tight")
    plt.close(fig)
    return outpath



def plot_raw_carbon_price_trajectories_2x2(
    trajectories,
    representation,
    title,
    outpath,
):
    """
    Plot every individual carbon-price trajectory (no aggregation/bands)
    in a 2x2 LU/SU/LD/SD panel for one policy representation only.
    """
    rep = str(representation).strip().lower()
    data = trajectories[
        trajectories["representation"].eq(rep)
    ].copy()
    data["scenario_group"] = data["future_id"].map(
        _trajectory_scenario_group
    )
    data = data[data["scenario_group"].notna()].copy()

    order = [
        ("LU", "Linear up"),
        ("SU", "Step up"),
        ("LD", "Linear down"),
        ("SD", "Step down"),
    ]

    fig, axes = plt.subplots(
        2, 2,
        figsize=(13.5, 9.0),
        sharex=True,
        sharey=True,
        constrained_layout=True,
    )

    for ax, (scenario, panel_title) in zip(axes.flat, order):
        d = data[data["scenario_group"].eq(scenario)]

        # One pure line per run/configuration.
        for run_id, r in d.groupby("run_id", sort=False):
            r = r.sort_values("year")
            ax.plot(
                r["year"],
                r["carbon_price"],
                linewidth=0.9,
                alpha=0.35,
            )

        ax.set_title(panel_title)
        ax.grid(alpha=0.20)

    axes[1, 0].set_xlabel("Year")
    axes[1, 1].set_xlabel("Year")
    axes[0, 0].set_ylabel("Carbon price")
    axes[1, 0].set_ylabel("Carbon price")

    fig.suptitle(title, fontsize=13)
    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(outpath, dpi=240, bbox_inches="tight")
    plt.close(fig)
    return outpath



def build_feedback_correction_metrics(index_df, results_df, target=0.0):
    """
    H4 — quantify the closed-loop correction after information revelation.

    Uses the projected terminal emissions stored at each sequential stage.
    The reveal-stage projection is taken from B2 when available, because
    revised demand information is first used in B2. The final projection is
    the last available block.

    R_E = (D_reveal - D_final) / |D_reveal|
    where D = |E_terminal - target|.

    Interpretation:
      R_E = 1   complete correction to target
      0 < R_E < 1 partial correction
      R_E = 0   no correction
      R_E < 0   final deviation worsened
    """
    cl_index = index_df[
        index_df["representation"].astype(str).str.lower().eq("closed_loop")
    ].copy()

    rows = []
    for _, cfg in cl_index.iterrows():
        run_id = str(cfg["run_id"])
        g = results_df[results_df["run_id"].astype(str).eq(run_id)].copy()
        if g.empty:
            continue

        g["block"] = pd.to_numeric(g["block"], errors="coerce")
        # In Experiment_Results.csv, "performance" is the projected
        # emissions at "performance_year" (2040 in this experiment).
        g["projected_terminal_emissions"] = pd.to_numeric(
            g["performance"], errors="coerce"
        )
        g["lambda_applied"] = pd.to_numeric(
            g["lambda_applied"], errors="coerce"
        )
        g = g.dropna(subset=["block", "projected_terminal_emissions"])
        if g.empty:
            continue
        g = g.sort_values("block")

        reveal = g[g["block"].eq(2)]
        if reveal.empty:
            reveal = g.iloc[[min(1, len(g)-1)]]
        final = g.iloc[[-1]]

        e_reveal = float(reveal.iloc[0]["projected_terminal_emissions"])
        e_final = float(final.iloc[0]["projected_terminal_emissions"])
        d_reveal = abs(e_reveal - target)
        d_final = abs(e_final - target)

        if d_reveal > 1e-12:
            correction_fraction = (d_reveal - d_final) / d_reveal
        else:
            correction_fraction = np.nan

        lam_reveal = pd.to_numeric(
            pd.Series([reveal.iloc[0].get("lambda_applied", np.nan)]),
            errors="coerce"
        ).iloc[0]
        lam_final = pd.to_numeric(
            pd.Series([final.iloc[0].get("lambda_applied", np.nan)]),
            errors="coerce"
        ).iloc[0]

        family = _trajectory_scenario_group(cfg.get("future_id", ""))

        rows.append({
            "run_id": run_id,
            "future_id": cfg.get("future_id", ""),
            "scenario_group": family,
            "lambda0": cfg.get("lambda0", np.nan),
            "kp": cfg.get("kp", np.nan),
            "E2040_reveal_B2": e_reveal,
            "E2040_final": e_final,
            "D_reveal": d_reveal,
            "D_final": d_final,
            "absolute_correction": d_reveal - d_final,
            "correction_fraction_RE": correction_fraction,
            "lambda_reveal": lam_reveal,
            "lambda_final": lam_final,
            "lambda_change_after_reveal": (
                float(lam_final - lam_reveal)
                if pd.notna(lam_reveal) and pd.notna(lam_final)
                else np.nan
            ),
            "correction_class": (
                "full"
                if pd.notna(correction_fraction) and correction_fraction >= 1 - 1e-9
                else "partial"
                if pd.notna(correction_fraction) and correction_fraction > 1e-9
                else "none"
                if pd.notna(correction_fraction) and abs(correction_fraction) <= 1e-9
                else "worsened"
                if pd.notna(correction_fraction)
                else "already_at_target_at_reveal"
            ),
        })

    return pd.DataFrame(rows)


def build_feedback_correction_summary(feedback):
    if feedback.empty:
        return pd.DataFrame()

    rows = []
    data = feedback[feedback["scenario_group"].isin(["LU","SU","LD","SD"])].copy()

    for scenario, g in data.groupby("scenario_group", sort=False):
        r = pd.to_numeric(g["correction_fraction_RE"], errors="coerce")
        a = pd.to_numeric(g["absolute_correction"], errors="coerce")
        dl = pd.to_numeric(g["lambda_change_after_reveal"], errors="coerce")
        cls = g["correction_class"].value_counts()

        rows.append({
            "scenario_group": scenario,
            "n_runs": len(g),
            "n_evaluable_RE": int(r.notna().sum()),
            "RE_median": r.median(),
            "RE_mean": r.mean(),
            "RE_p10": r.quantile(0.10),
            "RE_p90": r.quantile(0.90),
            "absolute_correction_median": a.median(),
            "lambda_change_median": dl.median(),
            "fraction_full_correction": cls.get("full", 0) / len(g),
            "fraction_partial_correction": cls.get("partial", 0) / len(g),
            "fraction_no_correction": cls.get("none", 0) / len(g),
            "fraction_worsened": cls.get("worsened", 0) / len(g),
            "fraction_already_target_at_reveal": (
                cls.get("already_at_target_at_reveal", 0) / len(g)
            ),
        })
    return pd.DataFrame(rows)


def plot_feedback_correction_box(feedback, outpath):
    """Distribution of R_E for LU/SU/LD/SD."""
    data = feedback[
        feedback["scenario_group"].isin(["LU","SU","LD","SD"])
    ].copy()
    order = ["LU","SU","LD","SD"]
    values = [
        pd.to_numeric(
            data.loc[data["scenario_group"].eq(sc), "correction_fraction_RE"],
            errors="coerce"
        ).dropna().to_numpy()
        for sc in order
    ]

    fig, ax = plt.subplots(figsize=(8.2, 5.8))
    ax.boxplot(values, labels=order, showfliers=True)
    ax.axhline(0.0, linewidth=1.0)
    ax.axhline(1.0, linewidth=1.0, linestyle="--")
    ax.set_xlabel("Demand perturbation family")
    ax.set_ylabel(r"Correction fraction, $R_E$")
    ax.set_title("Closed-loop correction after information revelation")
    ax.grid(axis="y", alpha=0.25)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(outpath, dpi=240, bbox_inches="tight")
    plt.close(fig)
    return outpath


def plot_feedback_stage_projection(feedback_results, outpath):
    """
    2x2 LU/SU/LD/SD panel of median projected terminal emissions by block,
    with P10-P90 bands. This directly visualizes the correction process.
    """
    data = feedback_results[
        feedback_results["scenario_group"].isin(["LU","SU","LD","SD"])
    ].copy()

    summary = (
        data.groupby(["scenario_group","block"])["projected_terminal_emissions"]
        .agg(
            p10=lambda x: x.quantile(0.10),
            median="median",
            p90=lambda x: x.quantile(0.90),
        )
        .reset_index()
    )

    order = [("LU","Linear up"),("SU","Step up"),
             ("LD","Linear down"),("SD","Step down")]
    fig, axes = plt.subplots(
        2,2,figsize=(12.5,8.5),sharex=True,sharey=True,
        constrained_layout=True
    )

    for ax,(scenario,title) in zip(axes.flat,order):
        d=summary[summary["scenario_group"].eq(scenario)].sort_values("block")
        if not d.empty:
            x=d["block"].to_numpy(dtype=float)
            med=d["median"].to_numpy(dtype=float)
            lo=d["p10"].to_numpy(dtype=float)
            hi=d["p90"].to_numpy(dtype=float)
            ax.fill_between(x,lo,hi,alpha=0.20)
            ax.plot(x,med,marker="o",linewidth=2.0)
        ax.axvline(2,linestyle="--",linewidth=1.0)
        ax.set_title(title)
        ax.set_xticks([1,2,3,4,5])
        ax.grid(alpha=0.25)

    axes[1,0].set_xlabel("Sequential block")
    axes[1,1].set_xlabel("Sequential block")
    axes[0,0].set_ylabel("Projected 2040 CO2 emissions")
    axes[1,0].set_ylabel("Projected 2040 CO2 emissions")
    fig.suptitle("Projected terminal emissions through sequential re-optimization")

    outpath.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(outpath,dpi=240,bbox_inches="tight")
    plt.close(fig)
    return outpath


def build_feedback_stage_table(index_df, results_df):
    """CLPR block-level table used by the H4 correction-process figure."""
    cl = index_df[
        index_df["representation"].astype(str).str.lower().eq("closed_loop")
    ][["run_id","future_id","lambda0","kp"]].copy()
    out = results_df.merge(cl, on="run_id", how="inner", suffixes=("","_cfg"))
    out["scenario_group"] = out["future_id"].map(_trajectory_scenario_group)
    out["block"] = pd.to_numeric(out["block"], errors="coerce")
    # Keep a descriptive H4 alias while sourcing the actual A5 column.
    out["projected_terminal_emissions"] = pd.to_numeric(
        out["performance"], errors="coerce"
    )
    out["lambda_applied"] = pd.to_numeric(
        out["lambda_applied"], errors="coerce"
    )
    return out



def plot_clpr_robustness_1x3(robustness_df, outpath):
    """
    H5 — Robustness of CLPR policy performance across demand futures.

    Panel A: target success fraction across futures
    Panel B: worst-case terminal target deviation
    Panel C: mean discounted reconstructed resource cost

    Axes are identical across panels:
        x = lambda0
        y = Kp
    """
    df = robustness_df.copy()

    # Flexible column aliases to remain compatible with the existing A6 table.
    lambda_col = named_column(df, ["lambda0", "lambda_0", "initial_carbon_price"])
    kp_col = named_column(df, ["kp", "Kp", "k_p"])
    success_col = named_column(
        df,
        ["target_success_fraction", "success_fraction", "fraction_target_met"]
    )
    worst_col = named_column(
        df,
        [
            "worst_target_deviation",
            "target_deviation_worst",
            "max_target_deviation",
            "terminal_target_deviation_max",
        ],
    )
    cost_col = named_column(
        df,
        [
            "mean_resource_cost",
            "resource_cost_mean",
            "discounted_resource_cost_mean",
            "resource_cost_pv_mean",
        ],
    )

    missing = [
        name for name, col in {
            "lambda0": lambda_col,
            "kp": kp_col,
            "success fraction": success_col,
            "worst-case target deviation": worst_col,
            "mean resource cost": cost_col,
        }.items() if col is None
    ]
    if missing:
        raise KeyError(
            "Robustness plot could not find columns for: " + ", ".join(missing)
            + f". Available columns: {list(df.columns)}"
        )

    for col in [lambda_col, kp_col, success_col, worst_col, cost_col]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(
        subset=[lambda_col, kp_col, success_col, worst_col, cost_col]
    )

    lambdas = sorted(df[lambda_col].unique())
    kps = sorted(df[kp_col].unique())

    def matrix(value_col):
        p = df.pivot_table(
            index=kp_col,
            columns=lambda_col,
            values=value_col,
            aggfunc="mean",
        )
        return p.reindex(index=kps, columns=lambdas)

    mats = [
        matrix(success_col),
        matrix(worst_col),
        matrix(cost_col),
    ]

    titles = [
        "A. Target success fraction",
        "B. Worst-case target deviation",
        "C. Mean resource cost",
    ]

    fig, axes = plt.subplots(
        1, 3, figsize=(17.0, 5.2), constrained_layout=True
    )

    for ax, mat, title in zip(axes, mats, titles):
        im = ax.imshow(
            mat.to_numpy(dtype=float),
            origin="lower",
            aspect="auto",
        )

        ax.set_xticks(range(len(lambdas)))
        ax.set_xticklabels(
            [f"{x:g}" for x in lambdas], rotation=45, ha="right"
        )
        ax.set_yticks(range(len(kps)))
        ax.set_yticklabels([f"{x:g}" for x in kps])

        ax.set_xlabel(r"Initial carbon price, $\lambda_0$ (USD/tCO$_2$)")
        ax.set_title(title)

        cbar = fig.colorbar(im, ax=ax, shrink=0.88)

        if title.startswith("A."):
            cbar.set_label("Fraction of demand futures")
        elif title.startswith("B."):
            cbar.set_label("Terminal target deviation")
        else:
            cbar.set_label("Discounted reconstructed resource cost")

    axes[0].set_ylabel(r"Proportional gain, $K_p$")

    fig.suptitle(
        "Robustness of CLPR policy performance across demand futures",
        fontsize=13,
    )

    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(outpath, dpi=240, bbox_inches="tight")
    plt.close(fig)
    return outpath



def plot_h5_matched_cost_performance_1x2(cp_cells, outpath):
    """
    H5 matched comparison, shown separately for Linear and Step futures.

    x > 0  : CLPR has a resource-cost premium relative to Prescribed.
    y > 0  : CLPR improves terminal target tracking.
    Each point is the median outcome for one matched (future, lambda0) cell.
    """
    fig, axes = plt.subplots(
        1, 2, figsize=(13.2, 5.5), sharex=True, sharey=True,
        constrained_layout=True
    )

    for ax, family in zip(axes, ["linear", "step"]):
        d = cp_cells[cp_cells["family"].eq(family)].copy()
        d["resource_cost_premium_CLPR_pct"] = pd.to_numeric(
            d["resource_cost_premium_CLPR_pct"], errors="coerce"
        )
        d["target_tracking_improvement_CLPR"] = pd.to_numeric(
            d["target_tracking_improvement_CLPR"], errors="coerce"
        )
        d = d.dropna(
            subset=[
                "resource_cost_premium_CLPR_pct",
                "target_tracking_improvement_CLPR",
            ]
        )

        ax.scatter(
            d["resource_cost_premium_CLPR_pct"],
            d["target_tracking_improvement_CLPR"],
            alpha=0.72,
        )
        ax.axvline(0.0, linewidth=1.0)
        ax.axhline(0.0, linewidth=1.0)
        ax.set_title(f"{family.title()} demand")
        ax.set_xlabel("CLPR resource-cost premium vs Prescribed (%)")
        ax.grid(alpha=0.22)

    axes[0].set_ylabel("CLPR target-tracking improvement")
    fig.suptitle(
        "Matched cost–performance comparison: CLPR vs Prescribed",
        fontsize=13,
    )

    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(outpath, dpi=240, bbox_inches="tight")
    plt.close(fig)
    return outpath


def plot_h5_pareto_frontier_composition_1x2(frontier_summary, outpath):
    """
    H5 Pareto-front composition by demand future.

    Panel A uses discounted reconstructed resource cost.
    Panel B uses discounted reconstructed total cost including emissions penalty.

    Bars show the number of Prescribed and CLPR runs on each future-specific
    Pareto frontier. This avoids pooling incomparable futures into one frontier.
    """
    df = frontier_summary.copy()
    df["future_id"] = df["future_id"].astype(str)
    df["n_frontier_prescribed"] = pd.to_numeric(
        df["n_frontier_prescribed"], errors="coerce"
    )
    df["n_frontier_clpr"] = pd.to_numeric(
        df["n_frontier_clpr"], errors="coerce"
    )

    metrics = list(df["cost_metric"].dropna().astype(str).unique())
    # Prefer resource-cost first, then cost including penalty.
    metrics = sorted(
        metrics,
        key=lambda x: (
            0 if "resource" in x.lower() else 1,
            x
        )
    )[:2]

    if len(metrics) < 2:
        # Still draw available metric(s), but preserve 1x2 geometry.
        metrics = metrics + [None] * (2 - len(metrics))

    fig, axes = plt.subplots(
        1, 2, figsize=(15.0, 5.8), sharey=False,
        constrained_layout=True
    )

    for ax, metric in zip(axes, metrics):
        if metric is None:
            ax.axis("off")
            continue

        d = df[df["cost_metric"].astype(str).eq(metric)].copy()
        d = d.sort_values("future_id")
        x = np.arange(len(d))

        pr = d["n_frontier_prescribed"].fillna(0).to_numpy(dtype=float)
        cl = d["n_frontier_clpr"].fillna(0).to_numpy(dtype=float)

        ax.bar(x, pr, label="Prescribed")
        ax.bar(x, cl, bottom=pr, label="CLPR")

        ax.set_xticks(x)
        ax.set_xticklabels(d["future_id"], rotation=45, ha="right")
        ax.set_xlabel("Demand future")
        ax.set_ylabel("Runs on Pareto frontier")
        ax.grid(axis="y", alpha=0.22)

        if "resource" in metric.lower():
            ax.set_title("A. Resource cost")
        else:
            ax.set_title("B. Cost including emissions penalty")

    handles, labels = axes[0].get_legend_handles_labels()
    if handles:
        fig.legend(
            handles, labels, loc="upper center",
            bbox_to_anchor=(0.5, 0.97), ncol=2, frameon=False
        )

    fig.suptitle(
        "Composition of future-specific Pareto frontiers",
        fontsize=13,
    )

    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(outpath, dpi=240, bbox_inches="tight")
    plt.close(fig)
    return outpath



def plot_h5_matched_cost_performance_2x2(cp_cells, outpath):
    """
    H5 matched CLPR-vs-Prescribed comparison.

    Columns: Linear / Step demand futures.
    Row 1: discounted reconstructed resource cost.
    Row 2: discounted reconstructed cost including emissions penalty.

    y > 0 means CLPR improves terminal target tracking.
    x > 0 means CLPR has a cost premium relative to Prescribed.
    """
    fig, axes = plt.subplots(
        2, 2, figsize=(13.2, 10.0),
        sharey=True, constrained_layout=True
    )

    row_specs = [
        (
            "resource_cost_premium_CLPR_pct",
            "Resource-cost premium of CLPR vs Prescribed (%)",
            "Resource cost",
        ),
        (
            "total_cost_premium_CLPR_pct",
            "Total-cost premium of CLPR vs Prescribed (%)",
            "Resource cost + emissions penalty",
        ),
    ]

    for row, (xcol, xlabel, row_label) in enumerate(row_specs):
        for col, family in enumerate(["linear", "step"]):
            ax = axes[row, col]
            d = cp_cells[cp_cells["family"].eq(family)].copy()

            d[xcol] = pd.to_numeric(d[xcol], errors="coerce")
            d["target_tracking_improvement_CLPR"] = pd.to_numeric(
                d["target_tracking_improvement_CLPR"], errors="coerce"
            )
            d = d.dropna(
                subset=[xcol, "target_tracking_improvement_CLPR"]
            )

            ax.scatter(
                d[xcol],
                d["target_tracking_improvement_CLPR"],
                alpha=0.72,
            )
            ax.axvline(0.0, linewidth=1.0)
            ax.axhline(0.0, linewidth=1.0)
            ax.grid(alpha=0.22)

            if row == 0:
                ax.set_title(f"{family.title()} demand")
            ax.set_xlabel(xlabel)

            if col == 0:
                ax.set_ylabel(
                    f"{row_label}\n\nCLPR target-tracking improvement"
                )

    fig.suptitle(
        "Matched cost–performance comparison: CLPR vs Prescribed",
        fontsize=13,
    )

    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(outpath, dpi=240, bbox_inches="tight")
    plt.close(fig)
    return outpath



def build_h8_sensitivity_tables(metrics, max_deviation=0.50):
    """
    H8 — Sensitivity of terminal target deviation to demand perturbation magnitude.

    For each family (linear/step), direction (up/down), representation, and lambda0:
      1) aggregate the five internal configurations by the median at each demand magnitude;
      2) compute local finite-difference sensitivities between consecutive magnitudes;
      3) compute an overall sensitivity from BASE (0) to the largest perturbation.

    Sensitivity definition:
        S_delta = Delta(abs target deviation) / Delta(demand perturbation fraction)

    Thus, for an UP future, positive S_delta means the target deviation worsens as
    demand increases. For a DOWN future, negative S_delta means the target deviation
    improves as the magnitude of the demand reduction increases.
    """
    reps = ["prescribed", "closed_loop"]
    rep_label = {"prescribed": "Prescribed", "closed_loop": "CLPR"}

    local_rows = []
    overall_rows = []

    for family in ["linear", "step"]:
        for direction in ["up", "down"]:
            data = metrics[
                metrics["representation_canonical"].isin(reps)
            ].copy()

            data["lambda0"] = pd.to_numeric(data["lambda0"], errors="coerce")
            data["absolute_target_deviation"] = pd.to_numeric(
                data["absolute_target_deviation"], errors="coerce"
            )
            data["_signed_level"] = data["future_id"].map(
                lambda x: _future_signed_level(x, family)
            )
            data = data[data["_signed_level"].notna()].copy()

            # BASE is shared. Select only the requested direction otherwise.
            if direction == "up":
                data = data[data["_signed_level"] >= 0].copy()
            else:
                data = data[data["_signed_level"] <= 0].copy()

            max_level = data["_signed_level"].abs().max()
            if pd.isna(max_level) or max_level == 0:
                continue

            # Positive magnitude for both UP and DOWN: 0 ... max_deviation.
            data["perturbation_magnitude"] = (
                data["_signed_level"].abs() / max_level * float(max_deviation)
            )
            data["perturbation_pct"] = 100.0 * data["perturbation_magnitude"]

            med = (
                data.groupby(
                    [
                        "representation_canonical",
                        "lambda0",
                        "perturbation_magnitude",
                        "perturbation_pct",
                    ],
                    as_index=False,
                )["absolute_target_deviation"]
                .median()
                .sort_values(
                    [
                        "representation_canonical",
                        "lambda0",
                        "perturbation_magnitude",
                    ]
                )
            )

            for (rep, lam), g in med.groupby(
                ["representation_canonical", "lambda0"], sort=True
            ):
                g = g.sort_values("perturbation_magnitude").reset_index(drop=True)
                if len(g) < 2:
                    continue

                # Local finite differences.
                for k in range(len(g) - 1):
                    a = g.iloc[k]
                    b = g.iloc[k + 1]
                    ddelta = (
                        b["perturbation_magnitude"] - a["perturbation_magnitude"]
                    )
                    if not np.isfinite(ddelta) or abs(ddelta) <= 1e-15:
                        continue
                    ddev = (
                        b["absolute_target_deviation"]
                        - a["absolute_target_deviation"]
                    )
                    local_rows.append(
                        {
                            "family": family,
                            "direction": direction,
                            "representation": rep_label[rep],
                            "representation_canonical": rep,
                            "lambda0": lam,
                            "delta_start_pct": a["perturbation_pct"],
                            "delta_end_pct": b["perturbation_pct"],
                            "target_deviation_start": a[
                                "absolute_target_deviation"
                            ],
                            "target_deviation_end": b[
                                "absolute_target_deviation"
                            ],
                            "delta_target_deviation": ddev,
                            "delta_demand_fraction": ddelta,
                            "S_delta": ddev / ddelta,
                            # Easier verbal interpretation: change in target
                            # deviation per +10 percentage points of perturbation.
                            "S_delta_per_10pct": (ddev / ddelta) * 0.10,
                        }
                    )

                # Overall finite difference: BASE -> maximum perturbation.
                a = g.iloc[0]
                b = g.iloc[-1]
                ddelta = (
                    b["perturbation_magnitude"] - a["perturbation_magnitude"]
                )
                if np.isfinite(ddelta) and abs(ddelta) > 1e-15:
                    ddev = (
                        b["absolute_target_deviation"]
                        - a["absolute_target_deviation"]
                    )
                    overall_rows.append(
                        {
                            "family": family,
                            "direction": direction,
                            "representation": rep_label[rep],
                            "representation_canonical": rep,
                            "lambda0": lam,
                            "delta_start_pct": a["perturbation_pct"],
                            "delta_end_pct": b["perturbation_pct"],
                            "target_deviation_start": a[
                                "absolute_target_deviation"
                            ],
                            "target_deviation_end": b[
                                "absolute_target_deviation"
                            ],
                            "delta_target_deviation": ddev,
                            "delta_demand_fraction": ddelta,
                            "S_delta": ddev / ddelta,
                            "S_delta_per_10pct": (ddev / ddelta) * 0.10,
                        }
                    )

    local = pd.DataFrame(local_rows)
    overall = pd.DataFrame(overall_rows)

    # Step minus Linear, matched by direction / representation / lambda0.
    if not overall.empty:
        lin = overall[overall["family"].eq("linear")].copy()
        stp = overall[overall["family"].eq("step")].copy()
        keys = [
            "direction",
            "representation",
            "representation_canonical",
            "lambda0",
        ]
        lin = lin[keys + ["S_delta", "S_delta_per_10pct"]].rename(
            columns={
                "S_delta": "S_delta_linear",
                "S_delta_per_10pct": "S_delta_per_10pct_linear",
            }
        )
        stp = stp[keys + ["S_delta", "S_delta_per_10pct"]].rename(
            columns={
                "S_delta": "S_delta_step",
                "S_delta_per_10pct": "S_delta_per_10pct_step",
            }
        )
        form = lin.merge(stp, on=keys, how="inner", validate="one_to_one")
        form["S_delta_step_minus_linear"] = (
            form["S_delta_step"] - form["S_delta_linear"]
        )
        form["S_delta_per_10pct_step_minus_linear"] = (
            form["S_delta_per_10pct_step"]
            - form["S_delta_per_10pct_linear"]
        )
    else:
        form = pd.DataFrame()

    return local, overall, form


def plot_h8_sensitivity_2x2(overall, outpath):
    """
    2x2: LU / SU / LD / SD.
    x = lambda0
    y = overall sensitivity from BASE to maximum perturbation,
        expressed as change in target deviation per +10 percentage points.
    """
    panel_specs = [
        ("linear", "up", "LU — Linear up"),
        ("step", "up", "SU — Step up"),
        ("linear", "down", "LD — Linear down"),
        ("step", "down", "SD — Step down"),
    ]

    fig, axes = plt.subplots(
        2, 2, figsize=(13.0, 9.2),
        sharex=True, sharey=True,
        constrained_layout=True,
    )

    for ax, (family, direction, title) in zip(axes.ravel(), panel_specs):
        d = overall[
            overall["family"].eq(family)
            & overall["direction"].eq(direction)
        ].copy()

        for rep in ["Prescribed", "CLPR"]:
            g = d[d["representation"].eq(rep)].sort_values("lambda0")
            if g.empty:
                continue
            ax.plot(
                g["lambda0"],
                g["S_delta_per_10pct"],
                marker="o",
                linewidth=1.7,
                label=rep,
            )

        ax.axhline(0.0, linewidth=1.0)
        ax.grid(alpha=0.22)
        ax.set_title(title)
        ax.set_xlabel(r"Initial carbon price $\lambda_0$ (USD/tCO$_2$)")
        ax.set_ylabel(
            r"Sensitivity $S_\delta$" + "\n"
            r"(change in target deviation per +10% demand perturbation)"
        )

    handles, labels = axes[0, 0].get_legend_handles_labels()
    if handles:
        fig.legend(
            handles, labels, loc="upper center",
            ncol=2, frameon=False, bbox_to_anchor=(0.5, 1.02)
        )

    fig.suptitle(
        "Sensitivity of terminal target tracking to demand perturbation magnitude",
        fontsize=13,
    )
    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(outpath, dpi=240, bbox_inches="tight")
    plt.close(fig)
    return outpath


def plot_h8_temporal_form_difference_1x2(form, outpath):
    """
    Compact Step-minus-Linear comparison.
    Positive values mean Step is more adverse / less favorable than Linear
    in terms of target-deviation sensitivity.
    """
    fig, axes = plt.subplots(
        1, 2, figsize=(12.5, 5.0),
        sharey=True, constrained_layout=True
    )

    for ax, direction, title in zip(
        axes, ["up", "down"], ["Demand increase", "Demand decrease"]
    ):
        d = form[form["direction"].eq(direction)].copy()
        for rep in ["Prescribed", "CLPR"]:
            g = d[d["representation"].eq(rep)].sort_values("lambda0")
            if g.empty:
                continue
            ax.plot(
                g["lambda0"],
                g["S_delta_per_10pct_step_minus_linear"],
                marker="o",
                linewidth=1.7,
                label=rep,
            )

        ax.axhline(0.0, linewidth=1.0)
        ax.grid(alpha=0.22)
        ax.set_title(title)
        ax.set_xlabel(r"Initial carbon price $\lambda_0$ (USD/tCO$_2$)")
        ax.set_ylabel(
            "Step − Linear sensitivity\n"
            "(target-deviation change per +10% demand perturbation)"
        )

    handles, labels = axes[0].get_legend_handles_labels()
    if handles:
        fig.legend(
            handles, labels, loc="upper center",
            ncol=2, frameon=False, bbox_to_anchor=(0.5, 1.03)
        )
    fig.suptitle(
        "Effect of perturbation temporal form on policy-performance sensitivity",
        fontsize=13,
    )

    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(outpath, dpi=240, bbox_inches="tight")
    plt.close(fig)
    return outpath



def build_h9_policy_authority(feedback_stage, index_df, target=0.0):
    """
    H9 — Diagnose effective policy authority in CLPR runs.

    Uses the sequential CLPR stage data directly.

    Policy effort:
        A_lambda = sum_j |lambda_{j+1} - lambda_j|

    Effective response over the sequential trajectory:
        correction = D_B2 - D_final
        authority_ratio = correction / A_lambda

    A local interval authority is also calculated:
        S_lambda_local = -(D_{j+1} - D_j) / |lambda_{j+1} - lambda_j|

    Positive authority means increasing/changing the policy is associated with
    lower target deviation. Near-zero authority with non-trivial policy effort
    indicates weak effective response. Negative authority indicates that target
    deviation worsened over that interval despite the policy change.

    This is an empirical policy-response diagnostic, not a formal control-theory
    stability or controllability metric.
    """
    if feedback_stage.empty:
        return pd.DataFrame(), pd.DataFrame()

    d=feedback_stage.copy()
    for c in ["block","lambda_applied","projected_terminal_emissions"]:
        d[c]=pd.to_numeric(d[c],errors="coerce")
    d=d.dropna(subset=["run_id","block","lambda_applied","projected_terminal_emissions"])
    d["D"]=abs(d["projected_terminal_emissions"]-float(target))

    # Bring lambda0 / kp / future metadata from index, using run_id as key.
    meta=index_df.copy()
    meta=meta[meta["representation"].astype(str).str.lower().eq("closed_loop")].copy()
    keep=[c for c in ["run_id","future_id","lambda0","kp"] if c in meta.columns]
    meta=meta[keep].drop_duplicates("run_id")
    d=d.merge(meta,on="run_id",how="left",suffixes=("","_idx"))
    if "future_id_idx" in d.columns:
        d["future_id"]=d["future_id"].fillna(d["future_id_idx"])
        d=d.drop(columns=["future_id_idx"])
    d["scenario_group"]=d["future_id"].map(_trajectory_scenario_group)

    interval_rows=[]
    run_rows=[]
    eps=1e-12

    for run_id,g in d.groupby("run_id",sort=False):
        g=g.sort_values("block").reset_index(drop=True)
        if len(g)<2:
            continue

        # H9 starts at B2, the first stage that uses revealed demand information.
        # This isolates post-revelation feedback response from the revelation shock itself.
        g_post=g[g["block"].ge(2)].copy().sort_values("block").reset_index(drop=True)
        if len(g_post)<2:
            continue

        lam=g_post["lambda_applied"].to_numpy(dtype=float)
        dev=g_post["D"].to_numpy(dtype=float)
        blk=g_post["block"].to_numpy(dtype=float)

        dl=np.diff(lam)
        dd=np.diff(dev)
        abs_dl=np.abs(dl)

        # Positive = target deviation reduced per unit policy movement.
        local_auth=np.where(abs_dl>eps,-dd/abs_dl,np.nan)

        for k in range(len(dl)):
            interval_rows.append({
                "run_id":run_id,
                "future_id":g.iloc[0].get("future_id",""),
                "scenario_group":g.iloc[0].get("scenario_group",""),
                "lambda0":g.iloc[0].get("lambda0",np.nan),
                "kp":g.iloc[0].get("kp",np.nan),
                "block_from":blk[k],
                "block_to":blk[k+1],
                "lambda_from":lam[k],
                "lambda_to":lam[k+1],
                "delta_lambda":dl[k],
                "abs_delta_lambda":abs_dl[k],
                "D_from":dev[k],
                "D_to":dev[k+1],
                "delta_D":dd[k],
                "S_lambda_local":local_auth[k],
            })

        effort=float(np.nansum(abs_dl))
        correction=float(dev[0]-dev[-1])
        authority_ratio=correction/effort if effort>eps else np.nan
        active=local_auth[np.isfinite(local_auth)]
        positive=active[active>0]

        run_rows.append({
            "run_id":run_id,
            "future_id":g.iloc[0].get("future_id",""),
            "scenario_group":g.iloc[0].get("scenario_group",""),
            "lambda0":g.iloc[0].get("lambda0",np.nan),
            "kp":g.iloc[0].get("kp",np.nan),
            "D_reveal_B2":dev[0],
            "D_final":dev[-1],
            "correction_post_reveal":correction,
            "A_lambda_post_reveal":effort,
            "needs_correction_at_B2":bool(dev[0] > 1e-6),
            "lambda_min_stage":float(np.nanmin(lam)),
            "lambda_max_stage":float(np.nanmax(lam)),
            "lambda_final":float(lam[-1]),
            "authority_ratio_correction_per_lambda":authority_ratio,
            "median_local_authority":float(np.nanmedian(active)) if active.size else np.nan,
            "min_local_authority":float(np.nanmin(active)) if active.size else np.nan,
            "max_local_authority":float(np.nanmax(active)) if active.size else np.nan,
            "n_active_policy_intervals":int(np.sum(abs_dl>eps)),
            "n_near_zero_response_intervals":int(
                np.sum((abs_dl>eps) & (np.abs(dd)<=1e-8))
            ),
            "fraction_near_zero_response_intervals":(
                float(np.sum((abs_dl>eps) & (np.abs(dd)<=1e-8)))
                / float(np.sum(abs_dl>eps))
                if np.sum(abs_dl>eps)>0 else np.nan
            ),
            "n_negative_response_intervals":int(
                np.sum((abs_dl>eps) & (local_auth<0))
            ),
        })

    intervals=pd.DataFrame(interval_rows)
    runs=pd.DataFrame(run_rows)

    # Data-driven diagnostic flags. These are descriptive screening categories,
    # not universal physical thresholds.
    if not runs.empty:
        valid_effort=runs["A_lambda_post_reveal"].replace([np.inf,-np.inf],np.nan).dropna()
        valid_auth=runs["authority_ratio_correction_per_lambda"].replace(
            [np.inf,-np.inf],np.nan
        ).dropna()
        effort_hi=float(valid_effort.quantile(0.75)) if not valid_effort.empty else np.nan
        auth_lo=float(valid_auth.quantile(0.25)) if not valid_auth.empty else np.nan
        runs["high_effort_threshold_q75"]=effort_hi
        runs["low_authority_threshold_q25"]=auth_lo
        runs["high_effort_low_authority_flag"]=(
            runs["needs_correction_at_B2"]
            & runs["A_lambda_post_reveal"].ge(effort_hi)
            & runs["authority_ratio_correction_per_lambda"].le(auth_lo)
        )

    return runs,intervals


def build_h9_policy_authority_summary(h9_runs):
    if h9_runs.empty:
        return pd.DataFrame()
    d=h9_runs[
        h9_runs["scenario_group"].isin(["LU","SU","LD","SD"])
        & h9_runs["needs_correction_at_B2"].fillna(False)
    ].copy()
    rows=[]
    for (scenario,lam),g in d.groupby(["scenario_group","lambda0"],sort=True):
        rows.append({
            "scenario_group":scenario,
            "lambda0":lam,
            "n_runs":len(g),
            "A_lambda_post_reveal_median":pd.to_numeric(g["A_lambda_post_reveal"],errors="coerce").median(),
            "correction_post_reveal_median":pd.to_numeric(
                g["correction_post_reveal"],errors="coerce"
            ).median(),
            "authority_ratio_median":pd.to_numeric(
                g["authority_ratio_correction_per_lambda"],errors="coerce"
            ).median(),
            "near_zero_response_fraction_median":pd.to_numeric(
                g["fraction_near_zero_response_intervals"],errors="coerce"
            ).median(),
            "high_effort_low_authority_fraction":pd.to_numeric(
                g["high_effort_low_authority_flag"],errors="coerce"
            ).mean(),
        })
    return pd.DataFrame(rows)


def plot_h9_effort_vs_correction(h9_runs,outpath):
    """
    Main H9 diagnostic.
    x = total policy movement A_lambda
    y = reduction in terminal target deviation over the sequential trajectory.
    High x + low y is the empirical weak-authority region.
    """
    d=h9_runs[
        h9_runs["scenario_group"].isin(["LU","SU","LD","SD"])
        & h9_runs["needs_correction_at_B2"].fillna(False)
    ].copy()
    fig,axes=plt.subplots(2,2,figsize=(13.0,9.2),sharex=True,sharey=True,
                          constrained_layout=True)
    scenarios=["LU","SU","LD","SD"]
    titles=["LU — Linear up","SU — Step up","LD — Linear down","SD — Step down"]

    for ax,sc,title in zip(axes.ravel(),scenarios,titles):
        g=d[d["scenario_group"].eq(sc)].copy()
        # Keep individual runs: this is specifically a regime diagnostic.
        normal=g[~g["high_effort_low_authority_flag"].fillna(False)]
        flagged=g[g["high_effort_low_authority_flag"].fillna(False)]
        ax.scatter(normal["A_lambda_post_reveal"],normal["correction_post_reveal"],
                   alpha=0.42,s=24,label="Other CLPR runs")
        if not flagged.empty:
            ax.scatter(flagged["A_lambda_post_reveal"],
                       flagged["correction_post_reveal"],
                       alpha=0.85,s=42,marker="x",
                       label="High effort / low authority")
        ax.axhline(0.0,linewidth=1.0)
        ax.grid(alpha=0.22)
        ax.set_title(title)
        ax.set_xlabel(r"Post-revelation policy effort $A_{\lambda,post}$")
        ax.set_ylabel("Post-revelation target correction (B2 to final)")

    handles,labels=axes[0,0].get_legend_handles_labels()
    if handles:
        fig.legend(handles,labels,loc="upper center",ncol=2,frameon=False,
                   bbox_to_anchor=(0.5,1.02))
    fig.suptitle("CLPR post-revelation policy effort versus target correction",fontsize=13)
    outpath.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(outpath,dpi=240,bbox_inches="tight")
    plt.close(fig)
    return outpath


def plot_h9_authority_vs_lambda0(h9_summary,outpath):
    """
    Secondary H9 plot: median empirical authority ratio by initial carbon price.
    """
    fig,axes=plt.subplots(2,2,figsize=(13.0,9.0),sharex=True,sharey=True,
                          constrained_layout=True)
    scenarios=["LU","SU","LD","SD"]
    titles=["LU — Linear up","SU — Step up","LD — Linear down","SD — Step down"]
    for ax,sc,title in zip(axes.ravel(),scenarios,titles):
        g=h9_summary[h9_summary["scenario_group"].eq(sc)].sort_values("lambda0")
        ax.plot(g["lambda0"],g["authority_ratio_median"],marker="o",linewidth=1.7)
        ax.axhline(0.0,linewidth=1.0)
        ax.grid(alpha=0.22)
        ax.set_title(title)
        ax.set_xlabel(r"Initial carbon price $\lambda_0$")
        ax.set_ylabel(
            "Median empirical policy authority\n"
            "(target-deviation reduction per unit policy movement)"
        )
    fig.suptitle("Effective CLPR policy authority across initial policy levels",
                 fontsize=13)
    outpath.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(outpath,dpi=240,bbox_inches="tight")
    plt.close(fig)
    return outpath


def build_policy_surface_data(metrics, family="linear", max_deviation=0.50):
    data = metrics.copy()
    data["lambda0"] = pd.to_numeric(data["lambda0"], errors="coerce")
    data["terminal_emissions"] = pd.to_numeric(
        data["terminal_emissions"], errors="coerce"
    )
    data["_level"] = data["future_id"].map(
        lambda x: _future_signed_level(x, family)
    )
    data = data[data["_level"].notna()].copy()

    max_level = data["_level"].abs().max()
    if pd.isna(max_level) or max_level == 0:
        max_level = 1.0
    data["future_deviation"] = data["_level"] / max_level * float(max_deviation)

    lambda_grid = sorted(
        data.loc[
            data["representation_canonical"].isin(["prescribed", "closed_loop"]),
            "lambda0"
        ].dropna().unique()
    )

    rows = []
    for rep in ["no_policy", "prescribed", "closed_loop"]:
        grp = data[data["representation_canonical"].eq(rep)].copy()

        if rep == "no_policy":
            base = (
                grp.groupby(["future_id", "future_deviation"], as_index=False)
                ["terminal_emissions"].median()
            )
            for _, r in base.iterrows():
                for lam in lambda_grid:
                    rows.append({
                        "representation": rep,
                        "future_id": r["future_id"],
                        "future_deviation": r["future_deviation"],
                        "lambda0": lam,
                        "terminal_emissions_median": r["terminal_emissions"],
                    })
        else:
            agg = (
                grp.groupby(
                    ["future_id", "future_deviation", "lambda0"],
                    as_index=False
                )["terminal_emissions"]
                .median()
                .rename(columns={"terminal_emissions":
                                 "terminal_emissions_median"})
            )
            agg["representation"] = rep
            rows.extend(agg.to_dict("records"))

    return pd.DataFrame(rows).sort_values(
        ["representation", "future_deviation", "lambda0"]
    )


def plot_policy_surface_3d(surface_data, representation, family, outdir, zmax):
    grp = surface_data[
        surface_data["representation"].eq(representation)
    ].copy()
    if grp.empty:
        return None

    pivot = grp.pivot_table(
        index="lambda0",
        columns="future_deviation",
        values="terminal_emissions_median",
        aggfunc="median",
    ).sort_index()

    X, Y = np.meshgrid(
        pivot.columns.to_numpy(dtype=float) * 100.0,
        pivot.index.to_numpy(dtype=float),
    )
    Z = pivot.to_numpy(dtype=float)

    fig = plt.figure(figsize=(7.4, 5.8))
    ax = fig.add_subplot(111, projection="3d")
    ax.plot_surface(
        X, Y, Z,
        linewidth=0.3,
        antialiased=True,
        alpha=0.9,
        cmap="viridis",
        vmin=0.0,
        vmax=zmax,
    )
    ax.scatter(X.ravel(), Y.ravel(), Z.ravel(), s=12, depthshade=False)
    ax.set_xlabel("Demand deviation (%)")
    ax.set_ylabel("Initial carbon price, λ₀ (USD/tCO$_2$)")
    ax.set_zlabel("2040 emissions (Mton)")
    ax.set_zlim(0, zmax)
    ax.set_title(
        f"{representation.replace('_',' ').title()} — {family.title()} futures"
    )
    ax.view_init(elev=25, azim=-55)
    fig.tight_layout()

    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"A6_surface_{family}_{representation}.png"
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def combine_surface_images(paths, output_path):
    from PIL import Image
    valid = [Path(p) for p in paths if p and Path(p).exists()]
    if not valid:
        return None

    imgs = [Image.open(p).convert("RGB") for p in valid]
    h = max(im.height for im in imgs)
    resized = []
    for im in imgs:
        if im.height != h:
            w = int(im.width * h / im.height)
            im = im.resize((w, h))
        resized.append(im)

    canvas = Image.new("RGB", (sum(im.width for im in resized), h), "white")
    x = 0
    for im in resized:
        canvas.paste(im, (x, 0))
        x += im.width

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, quality=95)
    for im in imgs:
        im.close()
    return output_path




def plot_policy_contour_2d(surface_data, representation, family, outdir, common_vmax):
    """2D contour projection of median 2040 emissions."""
    grp = surface_data[surface_data["representation"].eq(representation)].copy()
    if grp.empty:
        return None

    pivot = grp.pivot_table(
        index="lambda0",
        columns="future_deviation",
        values="terminal_emissions_median",
        aggfunc="median",
    ).sort_index()
    if pivot.empty:
        return None

    X, Y = np.meshgrid(
        pivot.columns.to_numpy(dtype=float) * 100.0,
        pivot.index.to_numpy(dtype=float),
    )
    Z = pivot.to_numpy(dtype=float)

    fig, ax = plt.subplots(figsize=(7.2, 5.5))
    levels = np.linspace(0.0, common_vmax, 12)
    cf = ax.contourf(
        X, Y, Z, levels=levels,
        cmap="viridis", vmin=0.0, vmax=common_vmax
    )
    cs = ax.contour(
        X, Y, Z, levels=levels, linewidths=0.7,
        cmap="viridis", vmin=0.0, vmax=common_vmax
    )
    ax.clabel(cs, inline=True, fontsize=7, fmt="%.3f")
    ax.set_xlabel("Demand deviation (%)")
    ax.set_ylabel("Initial carbon price, λ₀ (USD/tCO$_2$)")
    ax.set_title(
        f"{representation.replace('_',' ').title()} — {family.title()} futures"
    )
    cbar_ticks = np.linspace(0.0, common_vmax, 5)
    cbar = fig.colorbar(cf, ax=ax, ticks=cbar_ticks)
    cbar.ax.set_yticklabels([f"{v:.2f}" for v in cbar_ticks])
    cbar.set_label("Median 2040 emissions (Mton)")
    fig.tight_layout()

    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"A6_contour_{family}_{representation}.png"
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path



def plot_policy_contour_comparison(surface_data, family, outdir, common_vmax):
    """Three policy representations with one shared colorbar."""
    reps = [
        ("no_policy", "(a) No Policy"),
        ("prescribed", "(b) Prescribed"),
        ("closed_loop", "(c) Closed Loop"),
    ]

    fig, axes = plt.subplots(
        1, 3,
        figsize=(15.2, 4.8),
        sharex=True,
        sharey=True,
        constrained_layout=True,
    )

    levels = np.linspace(0.0, common_vmax, 12)
    contour_ref = None

    for ax, (rep, title) in zip(axes, reps):
        grp = surface_data[surface_data["representation"].eq(rep)].copy()
        pivot = grp.pivot_table(
            index="lambda0",
            columns="future_deviation",
            values="terminal_emissions_median",
            aggfunc="median",
        ).sort_index()

        X, Y = np.meshgrid(
            pivot.columns.to_numpy(dtype=float) * 100.0,
            pivot.index.to_numpy(dtype=float),
        )
        Z = pivot.to_numpy(dtype=float)

        contour_ref = ax.contourf(
            X, Y, Z,
            levels=levels,
            cmap="viridis",
            vmin=0.0,
            vmax=common_vmax,
        )
        cs = ax.contour(
            X, Y, Z,
            levels=levels,
            linewidths=0.55,
            cmap="viridis",
            vmin=0.0,
            vmax=common_vmax,
        )
        ax.clabel(cs, inline=True, fontsize=6.5, fmt="%.3f")
        ax.set_title(title)
        ax.set_xlabel("Demand deviation (%)")

    axes[0].set_ylabel("Initial carbon price, λ₀ (USD/tCO$_2$)")

    cbar_ticks = np.linspace(0.0, common_vmax, 5)
    cbar = fig.colorbar(
        contour_ref,
        ax=axes,
        ticks=cbar_ticks,
        shrink=0.95,
        pad=0.02,
    )
    cbar.ax.set_yticklabels([f"{v:.2f}" for v in cbar_ticks])
    cbar.set_label("Median 2040 emissions (Mton)")
    fig.suptitle(f"{family.title()} demand futures", fontsize=13)

    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"A6_contour_{family}_comparison.png"
    fig.savefig(path, dpi=240, bbox_inches="tight")
    plt.close(fig)
    return path



def plot_paper_cost_emission_relation_2x2(
    emissions_surface_data,
    cost_surface_data,
    family,
    outdir,
    emissions_vmax,
    cost_vmin,
    cost_vmax,
):
    """Paper Block 2: Prescribed vs CLPR emissions and total discounted cost.

    Creates one 2x2 figure per demand family:
      top row    : median 2040 emissions
      bottom row : median total discounted cost including emissions penalty
      columns    : Prescribed | CLPR

    No Policy is intentionally excluded.
    """
    reps = [
        ("prescribed", "Prescribed"),
        ("closed_loop", "CLPR"),
    ]

    fig, axes = plt.subplots(
        2, 2,
        figsize=(11.8, 9.0),
        sharex=True,
        sharey=True,
        constrained_layout=True,
    )

    emissions_levels = np.linspace(0.0, emissions_vmax, 12)
    cost_levels = np.linspace(cost_vmin, cost_vmax, 12)
    emissions_ref = None
    cost_ref = None

    panel_labels = [["(a)", "(b)"], ["(c)", "(d)"]]

    for col, (rep, rep_label) in enumerate(reps):
        # -------------------------
        # Top row: terminal emissions
        # -------------------------
        egrp = emissions_surface_data[
            emissions_surface_data["representation"].eq(rep)
        ].copy()
        epivot = egrp.pivot_table(
            index="lambda0",
            columns="future_deviation",
            values="terminal_emissions_median",
            aggfunc="median",
        ).sort_index()

        X_e, Y_e = np.meshgrid(
            epivot.columns.to_numpy(dtype=float) * 100.0,
            epivot.index.to_numpy(dtype=float),
        )
        Z_e = epivot.to_numpy(dtype=float)

        ax = axes[0, col]
        emissions_ref = ax.contourf(
            X_e, Y_e, Z_e,
            levels=emissions_levels,
            cmap="viridis",
            vmin=0.0,
            vmax=emissions_vmax,
        )
        ecs = ax.contour(
            X_e, Y_e, Z_e,
            levels=emissions_levels,
            linewidths=0.55,
            cmap="viridis",
            vmin=0.0,
            vmax=emissions_vmax,
        )
        ax.clabel(ecs, inline=True, fontsize=6.5, fmt="%.3f")
        ax.set_title(f"{panel_labels[0][col]} {rep_label} — Emissions")

        # -------------------------
        # Bottom row: total cost including penalty
        # -------------------------
        cgrp = cost_surface_data[
            cost_surface_data["representation"].eq(rep)
        ].copy()
        cpivot = cgrp.pivot_table(
            index="lambda0",
            columns="future_deviation",
            values="discounted_total_cost_with_penalty_median",
            aggfunc="median",
        ).sort_index()

        X_c, Y_c = np.meshgrid(
            cpivot.columns.to_numpy(dtype=float) * 100.0,
            cpivot.index.to_numpy(dtype=float),
        )
        Z_c = cpivot.to_numpy(dtype=float)

        ax = axes[1, col]
        cost_ref = ax.contourf(
            X_c, Y_c, Z_c,
            levels=cost_levels,
            cmap="viridis",
            vmin=cost_vmin,
            vmax=cost_vmax,
        )
        ccs = ax.contour(
            X_c, Y_c, Z_c,
            levels=cost_levels,
            linewidths=0.55,
            cmap="viridis",
            vmin=cost_vmin,
            vmax=cost_vmax,
        )
        ax.clabel(ccs, inline=True, fontsize=6.5, fmt="%.0f")
        ax.set_title(f"{panel_labels[1][col]} {rep_label} — Total discounted cost")
        ax.set_xlabel("Demand deviation (%)")

    axes[0, 0].set_ylabel("Initial carbon price, λ₀ (USD/tCO$_2$)")
    axes[1, 0].set_ylabel("Initial carbon price, λ₀ (USD/tCO$_2$)")

    # Shared colorbar for each row.
    e_ticks = np.linspace(0.0, emissions_vmax, 5)
    ebar = fig.colorbar(
        emissions_ref,
        ax=axes[0, :],
        ticks=e_ticks,
        shrink=0.92,
        pad=0.02,
    )
    ebar.ax.set_yticklabels([f"{v:.2f}" for v in e_ticks])
    ebar.set_label("Median 2040 emissions (Mton)")

    c_ticks = np.linspace(cost_vmin, cost_vmax, 5)
    cbar = fig.colorbar(
        cost_ref,
        ax=axes[1, :],
        ticks=c_ticks,
        shrink=0.92,
        pad=0.02,
    )
    cbar.ax.set_yticklabels([f"{v:.0f}" for v in c_ticks])
    cbar.set_label("Median total discounted cost (MUSD)")

    fig.suptitle(
        f"{family.title()} demand futures — emissions and total discounted cost",
        fontsize=13,
    )

    outdir.mkdir(parents=True, exist_ok=True)
    stem = outdir / f"Fig_Block2_{family}_cost_emission_relation"
    png_path = stem.with_suffix(".png")
    pdf_path = stem.with_suffix(".pdf")
    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    fig.savefig(pdf_path, bbox_inches="tight")
    plt.close(fig)
    return png_path, pdf_path


def plot_target_tracking(
    metrics: pd.DataFrame,
    future_id: str,
    outdir: Path,
) -> Optional[Path]:
    """
    First A6.5 analytical figure:
    absolute final-target deviation versus initial carbon price.
    """
    data = metrics[
        metrics["future_id"].astype(str).eq(str(future_id))
    ].copy()
    if data.empty:
        print(f">> Target-tracking plot skipped: no valid runs for future '{future_id}'.")
        return None

    fig, ax = plt.subplots(figsize=(8, 5.2))
    markers = {"no_policy": "X", "prescribed": "s", "closed_loop": "o"}

    for rep in ["no_policy", "prescribed", "closed_loop"]:
        grp = data[data["representation_canonical"].eq(rep)]
        if grp.empty:
            continue
        ax.scatter(
            pd.to_numeric(grp["lambda0"], errors="coerce"),
            pd.to_numeric(grp["absolute_target_deviation"], errors="coerce"),
            marker=markers[rep],
            alpha=0.75,
            label=rep.replace("_", " ").title(),
        )

    tol = pd.to_numeric(data["target_tolerance"], errors="coerce").dropna()
    if not tol.empty:
        ax.axhline(
            float(tol.iloc[0]),
            linestyle="--",
            linewidth=1,
            label="Target tolerance",
        )

    ax.set_xlabel("Initial carbon price, λ₀ (USD/tCO$_2$)")
    ax.set_ylabel("Absolute deviation from 2040 target")
    ax.set_title(f"Target tracking — future {future_id}")
    ax.grid(True, alpha=0.2)
    ax.legend()
    fig.tight_layout()

    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"A6_target_tracking_{future_id}.png"
    fig.savefig(path, dpi=220)
    plt.close(fig)
    return path


def plot_terminal_emissions(metrics: pd.DataFrame, future_id: str, outdir: Path) -> Optional[Path]:
    data = metrics[
        metrics["future_id"].astype(str).eq(str(future_id))
        & metrics["valid_run"].eq(True)
    ].copy()
    if data.empty:
        print(f">> Plot skipped: no valid runs for future '{future_id}'.")
        return None

    fig, ax = plt.subplots(figsize=(8, 5.2))
    markers = {"no_policy": "X", "prescribed": "s", "closed_loop": "o"}

    for rep in ["no_policy", "prescribed", "closed_loop"]:
        grp = data[data["representation"] == rep]
        if grp.empty:
            continue
        ax.scatter(
            pd.to_numeric(grp["lambda0"], errors="coerce"),
            pd.to_numeric(grp["terminal_emissions"], errors="coerce"),
            marker=markers[rep], alpha=0.75,
            label=rep.replace("_", " ").title(),
        )

    targets = pd.to_numeric(data["target"], errors="coerce").dropna().unique()
    if len(targets) == 1:
        ax.axhline(targets[0], linestyle="--", linewidth=1, label="Policy target")

    ax.set_xlabel("Initial carbon price, λ₀ (USD/tCO$_2$)")
    ax.set_ylabel(f"Projected emissions in {int(data['target_year'].iloc[0])}")
    ax.set_title(f"Terminal emissions — future {future_id}")
    ax.grid(True, alpha=0.2)
    ax.legend()
    fig.tight_layout()

    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"A6_terminal_emissions_{future_id}.png"
    fig.savefig(path, dpi=220)
    plt.close(fig)
    return path



# -----------------------------------------------------------------------------
# PAPER FIGURES — BLOCK 1: What changes? / Closed-loop policy response
# -----------------------------------------------------------------------------

def _paper_future_group(future_id):
    """Map A5 futures to broad pedagogical groups while preserving shape."""
    fid = str(future_id).strip().upper()
    if fid == "BASE":
        return "Base", "Base"
    if fid.startswith("LU"):
        return "Up", "Linear"
    if fid.startswith("LD"):
        return "Down", "Linear"
    if fid.startswith("SU"):
        return "Up", "Step"
    if fid.startswith("SD"):
        return "Down", "Step"
    return None, None


def build_paper_demand_trajectory_table(experiment_dir, index_df, start_year, target_year):
    """Annual exogenous demand trajectories for BASE + Linear + Step futures.

    Demand is exogenous, so No Policy is used only as a convenient source of the
    model demand trajectory. Values are summed over all rows in Demand.csv by year.
    """
    rows = []
    data = index_df.copy()
    mapped = data["future_id"].map(_paper_future_group)
    data["direction"] = [x[0] for x in mapped]
    data["shape"] = [x[1] for x in mapped]
    data = data[data["direction"].notna()]

    # Avoid duplicate demand trajectories across representations.
    npol = data[data["representation"].astype(str).str.lower().eq("no_policy")]
    if not npol.empty:
        data = npol
    else:
        data = data.sort_values(["future_id", "representation"]).drop_duplicates("future_id")

    for _, r in data.iterrows():
        run_id = str(r["run_id"])
        run_folder = resolve_run_folder(experiment_dir, r.get("run_folder", ""), run_id)
        res = locate_res_folder(run_folder)
        df = read_optional_csv(res, "Demand.csv")
        if df is None or df.empty:
            continue
        ycol = named_column(df, ["y", "year"])
        vcol = value_column(df, ["Demand", "demand", "value"])
        if ycol is None or vcol is None:
            continue
        tmp = df[[ycol, vcol]].copy()
        tmp[ycol] = pd.to_numeric(tmp[ycol], errors="coerce")
        tmp[vcol] = pd.to_numeric(tmp[vcol], errors="coerce")
        tmp = tmp.dropna()
        yearly = tmp.groupby(ycol, as_index=False)[vcol].sum()
        yearly = yearly[(yearly[ycol] >= start_year) & (yearly[ycol] <= target_year)]
        for _, z in yearly.iterrows():
            rows.append({
                "run_id": run_id,
                "future_id": r.get("future_id", ""),
                "direction": r["direction"],
                "shape": r["shape"],
                "demand_delta": pd.to_numeric(r.get("demand_delta", np.nan), errors="coerce"),
                "year": int(z[ycol]),
                "annual_demand": float(z[vcol]),
            })
    return pd.DataFrame(rows)


def build_paper_annual_emissions_table(experiment_dir, index_df, start_year, target_year):
    """Annual CO2 trajectories for BASE + all Linear/Step futures and representations."""
    rows = []
    data = index_df.copy()
    mapped = data["future_id"].map(_paper_future_group)
    data["direction"] = [x[0] for x in mapped]
    data["shape"] = [x[1] for x in mapped]
    data = data[data["direction"].notna()]

    for _, r in data.iterrows():
        run_id = str(r["run_id"])
        run_folder = resolve_run_folder(experiment_dir, r.get("run_folder", ""), run_id)
        res = locate_res_folder(run_folder)
        df = read_optional_csv(res, "AnnualEmissions.csv")
        yearly = _read_annual_co2_series(df)
        if yearly.empty:
            continue
        yearly = yearly[(yearly["year"] >= start_year) & (yearly["year"] <= target_year)]
        for _, z in yearly.iterrows():
            rows.append({
                "run_id": run_id,
                "representation": str(r.get("representation", "")).strip().lower(),
                "future_id": r.get("future_id", ""),
                "direction": r["direction"],
                "shape": r["shape"],
                "demand_delta": pd.to_numeric(r.get("demand_delta", np.nan), errors="coerce"),
                "lambda0": pd.to_numeric(r.get("lambda0", np.nan), errors="coerce"),
                "kp": pd.to_numeric(r.get("kp", np.nan), errors="coerce"),
                "policy_id": r.get("policy_id", ""),
                "policy_direction": r.get("policy_direction", ""),
                "policy_delta_final": pd.to_numeric(r.get("policy_delta_final", np.nan), errors="coerce"),
                "year": int(z["year"]),
                "annual_emissions_CO2": float(z["annual_emissions_CO2"]),
            })
    return pd.DataFrame(rows)


def _paper_save(fig, stem, figure_dir):
    """Paper export: PNG 300 dpi + vector PDF only."""
    figure_dir.mkdir(parents=True, exist_ok=True)
    png = figure_dir / f"{stem}.png"
    pdf = figure_dir / f"{stem}.pdf"
    fig.savefig(png, dpi=300, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    plt.close(fig)
    return png, pdf


def _paper_reveal_line(ax, reveal_year):
    ax.axvline(reveal_year, linestyle="--", linewidth=1.0, alpha=0.65)


def _mean_band(df, value_col):
    if df.empty:
        return pd.DataFrame(columns=["year", "mean", "p10", "p90"])
    return (
        df.groupby("year")[value_col]
        .agg(mean="mean", p10=lambda x: x.quantile(.10), p90=lambda x: x.quantile(.90))
        .reset_index()
        .sort_values("year")
    )


PAPER_COLOR_UP = "tab:blue"
PAPER_COLOR_DOWN = "tab:orange"
PAPER_COLOR_BASE = "0.20"
PAPER_LEGEND_FONTSIZE = 10  # Match Fig. 01(b) reference size across Block 1.


def _paper_direction_color(direction):
    return PAPER_COLOR_UP if str(direction).strip().lower() == "up" else PAPER_COLOR_DOWN


def _paper_panel_label(ax, label):
    """Legacy helper retained for compatibility; Block 1 panel labels are embedded in titles."""
    ax.text(0.015, 0.985, label, transform=ax.transAxes, ha="left", va="top",
            fontsize=10, fontweight="normal")


def _paper_ylim(values, pad_fraction=0.04, include_zero=True):
    vals = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    if vals.empty:
        return None
    lo, hi = float(vals.min()), float(vals.max())
    if include_zero:
        lo, hi = min(lo, 0.0), max(hi, 0.0)
    span = hi - lo
    pad = pad_fraction * (span if span > 0 else max(abs(hi), 1.0))
    return (lo - pad, hi + pad)


def _plot_mean_band(ax, q, label, linewidth=2.0, color=None):
    if q.empty:
        return
    line = ax.plot(q["year"], q["mean"], linewidth=linewidth,
                   label=f"{label} (mean, P10–P90 band)", color=color)[0]
    ax.fill_between(q["year"], q["p10"], q["p90"], alpha=0.16, color=line.get_color())


def plot_paper_fig1(demand_df, emissions_df, reveal_year, figure_dir, demand_unit="PJ", emission_ylim=None):
    """Fig. 1: model demand futures and No-Policy system response."""
    fig, axes = plt.subplots(1, 2, figsize=(12.2, 4.5), sharex=True)

    # (a) Exact model demand trajectories: Base + Linear + Step, Up and Down.
    ax = axes[0]
    if not demand_df.empty:
        base = demand_df[demand_df["direction"].eq("Base")]
        if not base.empty:
            b = base.groupby("year", as_index=False)["annual_demand"].mean()
            ax.plot(b["year"], b["annual_demand"], linewidth=2.7, label="Base", color=PAPER_COLOR_BASE)

        styles = {("Up", "Linear"): "-", ("Down", "Linear"): "-",
                  ("Up", "Step"): "--", ("Down", "Step"): "--"}
        # One legend entry per broad shape/direction; magnitudes remain visible as trajectories.
        used = set()
        for (direction, shape, delta), g in demand_df[demand_df["direction"].isin(["Up", "Down"])].groupby(
            ["direction", "shape", "demand_delta"]
        ):
            g = g.groupby("year", as_index=False)["annual_demand"].mean()
            key = (direction, shape)
            label = f"Demand {direction} — {shape}" if key not in used else None
            used.add(key)
            ax.plot(g["year"], g["annual_demand"], linestyle=styles.get(key, "-"),
                    alpha=0.58, linewidth=1.25, label=label, color=_paper_direction_color(direction))

    ax.set_title("(a) Demand trajectories", fontweight="normal")
    ax.set_xlabel("Year")
    ax.set_ylabel(f"Annual demand ({demand_unit})")
    ax.legend(fontsize=PAPER_LEGEND_FONTSIZE, ncol=1, loc="upper left", frameon=False)

    # (b) No-Policy emissions: broad Up and Down groups aggregate Linear + Step.
    ax = axes[1]
    e = emissions_df[emissions_df["representation"].eq("no_policy")].copy()
    base = e[e["direction"].eq("Base")]
    if not base.empty:
        b = base.groupby("year", as_index=False)["annual_emissions_CO2"].mean()
        ax.plot(b["year"], b["annual_emissions_CO2"], linewidth=2.7, label="Base", color=PAPER_COLOR_BASE)
    for direction in ["Up", "Down"]:
        q = _mean_band(e[e["direction"].eq(direction)], "annual_emissions_CO2")
        _plot_mean_band(ax, q, f"Demand {direction}", color=_paper_direction_color(direction))

    _paper_reveal_line(ax, reveal_year)
    if emission_ylim is not None:
        ax.set_ylim(*emission_ylim)
    ax.set_title("(b) No-Policy emissions", fontweight="normal")
    ax.set_xlabel("Year")
    ax.set_ylabel("Annual CO$_2$ emissions (Mton)")
    ax.legend(fontsize=PAPER_LEGEND_FONTSIZE, frameon=False)
    fig.suptitle("Exogenous perturbation and uncontrolled response", fontsize=13)
    fig.tight_layout()
    return _paper_save(fig, "Fig01_exogenous_perturbation_uncontrolled_response", figure_dir)


def plot_paper_fig2(price_df, emissions_df, reveal_year, figure_dir, emission_ylim=None, price_ylim=None):
    """Fig. 2: all Prescribed price trajectories and aggregate Up/Down emissions response."""
    fig, axes = plt.subplots(1, 2, figsize=(12.2, 4.5), sharex=True)

    # (a) All prescribed carbon-price trajectories for every lambda0.
    # Signals are future-independent, so retain one copy of each (lambda0, prescribed curve).
    ax = axes[0]
    p = price_df[price_df["representation"].eq("prescribed")].copy()
    p["lambda0"] = pd.to_numeric(p["lambda0"], errors="coerce")
    if not p.empty:
        # run_id repeats by future; reconstruct unique curve signatures from lambda0 and annual price.
        curves = []
        for run_id, g in p.groupby("run_id"):
            g = g.sort_values("year")
            if g.empty:
                continue
            curves.append((float(g["lambda0"].iloc[0]), tuple(np.round(g["carbon_price"].to_numpy(), 10)), g))
        seen = set()
        by_lambda = {}
        for lam, sig, g in curves:
            key = (lam, sig)
            if key in seen:
                continue
            seen.add(key)
            by_lambda.setdefault(lam, []).append(g)
        # Prescribed families are identified by the terminal percentage change
        # relative to their own initial carbon price: (lambda_f/lambda_0 - 1)*100.
        # This keeps the legend meaningful even though all lambda_0 values are shown.
        delta_seen = set()
        for lam in sorted(by_lambda):
            for g in by_lambda[lam]:
                prices = pd.to_numeric(g["carbon_price"], errors="coerce").dropna()
                if prices.empty or np.isclose(lam, 0.0):
                    continue
                lambda_final = float(prices.iloc[-1])
                delta_pct = 100.0 * (lambda_final / float(lam) - 1.0)
                # Round only for family identification / display; plotted data are unchanged.
                key = round(delta_pct, 6)
                label = None
                if key not in delta_seen:
                    if np.isclose(delta_pct, 0.0, atol=1e-6):
                        label = "0% (Flat)"
                    else:
                        label = f"{delta_pct:+.0f}%"
                    delta_seen.add(key)
                ax.plot(g["year"], g["carbon_price"], linewidth=1.05, alpha=0.48, label=label)

    if price_ylim is not None:
        ax.set_ylim(*price_ylim)
    ax.set_title("(a) Prescribed carbon-price trajectories", fontweight="normal")
    ax.set_xlabel("Year")
    ax.set_ylabel("Carbon price (USD/tCO$_2$)")
    ax.legend(fontsize=PAPER_LEGEND_FONTSIZE, ncol=2, frameon=False)

    # (b) Emissions bands across the complete prescribed experiment, grouped only
    # by direction of the demand perturbation. Linear and Step are pooled.
    ax = axes[1]
    e = emissions_df[emissions_df["representation"].eq("prescribed")].copy()
    for direction in ["Up", "Down"]:
        q = _mean_band(e[e["direction"].eq(direction)], "annual_emissions_CO2")
        _plot_mean_band(ax, q, f"Demand {direction}", color=_paper_direction_color(direction))
    _paper_reveal_line(ax, reveal_year)
    ax.axhline(0.0, linestyle=":", linewidth=1.0, alpha=0.7)
    if emission_ylim is not None:
        ax.set_ylim(*emission_ylim)
    ax.set_title("(b) Emissions under prescribed policy", fontweight="normal")
    ax.set_xlabel("Year")
    ax.set_ylabel("Annual CO$_2$ emissions (Mton)")
    ax.legend(fontsize=PAPER_LEGEND_FONTSIZE, frameon=False)
    fig.suptitle("Prescribed policy response", fontsize=13)
    fig.tight_layout()
    return _paper_save(fig, "Fig02_prescribed_policy_response", figure_dir)


def plot_paper_fig3(price_df, emissions_df, reveal_year, figure_dir, emission_ylim=None, price_ylim=None):
    """Fig. 3: CLPR response, pooling Linear + Step within Up and Down groups.

    Price panels retain all realized trajectories and group them visually by lambda0.
    Emission panels show mean and P10-P90 over the corresponding broad group.
    """
    fig, axes = plt.subplots(2, 2, figsize=(12.2, 8.1), sharex=True)

    p = price_df[price_df["representation"].eq("closed_loop")].copy()
    p["lambda0"] = pd.to_numeric(p["lambda0"], errors="coerce")
    meta = emissions_df[["run_id", "demand_delta", "kp"]].drop_duplicates("run_id")
    p = p.merge(meta, on="run_id", how="left")

    e = emissions_df[emissions_df["representation"].eq("closed_loop")].copy()
    e["lambda0"] = pd.to_numeric(e["lambda0"], errors="coerce")

    for row, direction in enumerate(["Up", "Down"]):
        axp, axe = axes[row, 0], axes[row, 1]
        dp = p[p["direction"].eq(direction)]
        de = e[e["direction"].eq(direction)]

        # All realized price trajectories. The legend identifies feedback gain Kp,
        # while all lambda0 values, demand magnitudes, and Linear/Step cases remain included.
        # A stronger mean trajectory is drawn for each Kp to make the feedback-gain
        # response readable without hiding the individual realizations.
        for kp in sorted(pd.to_numeric(dp["kp"], errors="coerce").dropna().unique()):
            gk = dp[np.isclose(pd.to_numeric(dp["kp"], errors="coerce"), kp)]
            first = True
            for _, g in gk.groupby("run_id"):
                g = g.sort_values("year")
                axp.plot(g["year"], g["carbon_price"], linewidth=0.85, alpha=0.16,
                         label=f"$K_p$={kp:g}" if first else None)
                first = False
            qm = gk.groupby("year", as_index=False)["carbon_price"].mean()
            axp.plot(qm["year"], qm["carbon_price"], linewidth=1.8, alpha=0.90)

        # Emissions: one mean + P10-P90 band for each broad direction.
        q = _mean_band(de, "annual_emissions_CO2")
        _plot_mean_band(axe, q, f"Demand {direction}", linewidth=2.2,
                        color=_paper_direction_color(direction))

        _paper_reveal_line(axe, reveal_year)
        axe.axhline(0.0, linestyle=":", linewidth=1.0, alpha=0.7)
        if price_ylim is not None:
            axp.set_ylim(*price_ylim)
        if emission_ylim is not None:
            axe.set_ylim(*emission_ylim)
        price_panel = "(a)" if row == 0 else "(c)"
        emis_panel = "(b)" if row == 0 else "(d)"
        axp.set_title(f"{price_panel} CLPR carbon price — Demand {direction}", fontweight="normal")
        axe.set_title(f"{emis_panel} Emissions — Demand {direction}", fontweight="normal")
        axp.set_ylabel("Carbon price (USD/tCO$_2$)")
        axe.set_ylabel("Annual CO$_2$ emissions (Mton)")
        axp.legend(fontsize=PAPER_LEGEND_FONTSIZE, ncol=2, loc="upper left", frameon=False)
        axe.legend(fontsize=PAPER_LEGEND_FONTSIZE, frameon=False)

    axes[1, 0].set_xlabel("Year")
    axes[1, 1].set_xlabel("Year")
    fig.suptitle("Closed-loop policy response", fontsize=13)
    fig.tight_layout()
    return _paper_save(fig, "Fig03_closed_loop_policy_response", figure_dir)


def generate_paper_block1(
    experiment_dir, index_df, results_df, metrics_df, outdir,
    start_year, target_year, reveal_year=2020, demand_unit="PJ"
):
    paper_dir = outdir
    figure_dir = outdir / "figures" / "block_1_closed_loop_response"
    data_dir = outdir / "data" / "block_1_closed_loop_response"
    figure_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    demand = build_paper_demand_trajectory_table(experiment_dir, index_df, start_year, target_year)
    emissions = build_paper_annual_emissions_table(experiment_dir, index_df, start_year, target_year)
    prices = build_carbon_price_trajectory_table(index_df, results_df, start_year, target_year)

    # Attach broad direction/shape metadata to reconstructed price trajectories.
    if not prices.empty:
        mapped = prices["future_id"].map(_paper_future_group)
        prices["direction"] = [x[0] for x in mapped]
        prices["shape"] = [x[1] for x in mapped]

    demand.to_csv(data_dir / "Fig01a_demand_trajectories.csv", index=False)
    emissions[emissions["representation"].eq("no_policy")].to_csv(
        data_dir / "Fig01b_no_policy_emissions.csv", index=False)
    prices[prices["representation"].eq("prescribed")].to_csv(
        data_dir / "Fig02a_prescribed_carbon_price.csv", index=False)
    emissions[emissions["representation"].eq("prescribed")].to_csv(
        data_dir / "Fig02b_prescribed_emissions.csv", index=False)
    prices[prices["representation"].eq("closed_loop")].to_csv(
        data_dir / "Fig03ac_CLPR_carbon_price.csv", index=False)
    emissions[emissions["representation"].eq("closed_loop")].to_csv(
        data_dir / "Fig03bd_CLPR_emissions.csv", index=False)

    outputs = {}
    # Shared paper scales for directly comparable panels. This prevents visual
    # exaggeration caused by independent autoscaling across representations.
    emission_ylim = _paper_ylim(emissions["annual_emissions_CO2"], include_zero=True)
    price_ylim = _paper_ylim(prices["carbon_price"], include_zero=True)

    outputs["fig1"] = plot_paper_fig1(
        demand, emissions, reveal_year, figure_dir, demand_unit, emission_ylim=emission_ylim
    )
    outputs["fig2"] = plot_paper_fig2(
        prices, emissions, reveal_year, figure_dir,
        emission_ylim=emission_ylim, price_ylim=price_ylim
    )
    outputs["fig3"] = plot_paper_fig3(
        prices, emissions, reveal_year, figure_dir,
        emission_ylim=emission_ylim, price_ylim=price_ylim
    )
    return paper_dir, outputs


# ============================================================================
# Exploratory analysis — cost-effectiveness dispersion across futures
# ============================================================================

def _cei_future_group(future_id: str) -> dict:
    """Return membership in the five requested future subsets."""
    fid = str(future_id).strip().upper()
    return {
        "All": True,
        "Demand Up": fid.startswith("LU") or fid.startswith("SU"),
        "Demand Down": fid.startswith("LD") or fid.startswith("SD"),
        "Linear": fid.startswith("LU") or fid.startswith("LD"),
        "Step": fid.startswith("SU") or fid.startswith("SD"),
    }


def _cei_config_fields(row: pd.Series) -> tuple[str, str]:
    """Build a stable configuration id/label across futures."""
    rep = str(row.get("representation_canonical", "")).strip().lower()
    lam0 = pd.to_numeric(pd.Series([row.get("lambda0", np.nan)]), errors="coerce").iloc[0]
    if rep == "prescribed":
        delta = pd.to_numeric(pd.Series([row.get("policy_delta_final", np.nan)]), errors="coerce").iloc[0]
        if pd.notna(delta):
            # A5 stores this as a fraction (e.g. 0.25) in the current experiment.
            pct = 100.0 * float(delta) if abs(float(delta)) <= 2.0 else float(delta)
            cfg = f"PR|lambda0={lam0:g}|delta_final_pct={pct:g}"
            label = f"λ0={lam0:g}, Δλf={pct:+g}%"
        else:
            lamf = pd.to_numeric(pd.Series([row.get("lambda_final", np.nan)]), errors="coerce").iloc[0]
            cfg = f"PR|lambda0={lam0:g}|lambda_final={lamf:g}"
            label = f"λ0={lam0:g}, λf={lamf:g}"
        return cfg, label
    if rep == "closed_loop":
        kp = pd.to_numeric(pd.Series([row.get("kp", np.nan)]), errors="coerce").iloc[0]
        cfg = f"CLPR|lambda0={lam0:g}|kp={kp:g}"
        label = f"λ0={lam0:g}, Kp={kp:g}"
        return cfg, label
    return str(row.get("run_id", "")), str(row.get("run_id", ""))


def verify_cost_effectiveness_columns(metrics: pd.DataFrame) -> pd.DataFrame:
    """Print and return the exact source-column mapping used by the CEI analysis."""
    mapping = [
        ("system/resource cost", "discounted_resource_cost"),
        ("total cost including emissions penalty", "discounted_total_cost_with_penalty"),
        ("cumulative emissions", "cumulative_emissions_CO2"),
        ("future", "future_id"),
        ("policy type", "representation_canonical"),
        ("lambda_0", "lambda0"),
        ("lambda_final (prescribed metadata)", "lambda_final"),
        ("lambda_final_actual (realized final policy)", "lambda_final_actual"),
        ("K_p", "kp"),
        ("prescribed final-change family", "policy_delta_final"),
    ]
    rows = []
    print("\n>> Cost-effectiveness dispersion — source-column verification")
    print(">> ----------------------------------------------------------")
    for meaning, col in mapping:
        exists = col in metrics.columns
        print(f">> {meaning}: {col} ({'FOUND' if exists else 'MISSING'})")
        rows.append({"meaning": meaning, "column": col, "found": bool(exists)})
    required = {
        "discounted_resource_cost", "discounted_total_cost_with_penalty",
        "cumulative_emissions_CO2", "future_id", "representation_canonical",
        "lambda0", "kp", "policy_delta_final",
    }
    missing = sorted(required - set(metrics.columns))
    if missing:
        raise KeyError("CEI analysis missing required columns: " + ", ".join(missing))
    return pd.DataFrame(rows)


def build_cost_effectiveness_run_table(metrics: pd.DataFrame, eps: float = 1e-12):
    """
    Calculate CEI relative to No Policy under exactly the same future.

    CEI_SYS = (C_SYS_p - C_SYS_NP) / (CumE_NP - CumE_p)
    CEI_TOT = (C_TOT_p - C_TOT_NP) / (CumE_NP - CumE_p)

    CEI is not calculated when avoided cumulative emissions are <= 0.
    """
    data = metrics.copy()
    data = data[data["representation_canonical"].isin(["prescribed", "closed_loop", "no_policy"])].copy()
    np_ref = (
        data[data["representation_canonical"].eq("no_policy")]
        .sort_values("run_id")
        .drop_duplicates("future_id", keep="first")
        [["future_id", "cumulative_emissions_CO2", "discounted_resource_cost", "discounted_total_cost_with_penalty"]]
        .rename(columns={
            "cumulative_emissions_CO2": "np_cumulative_emissions_CO2",
            "discounted_resource_cost": "np_discounted_resource_cost",
            "discounted_total_cost_with_penalty": "np_discounted_total_cost_with_penalty",
        })
    )
    pol = data[data["representation_canonical"].isin(["prescribed", "closed_loop"])].copy()

    # Some earlier A6 analyses may already have No-Policy reference columns
    # attached to `metrics`.  Remove any pre-existing NP-reference fields before
    # merging the CEI-specific reference table; otherwise pandas appends _x/_y
    # suffixes and the expected `np_*` names disappear.
    np_reference_cols = [
        "np_cumulative_emissions_CO2",
        "np_discounted_resource_cost",
        "np_discounted_total_cost_with_penalty",
    ]
    pol = pol.drop(columns=[c for c in np_reference_cols if c in pol.columns], errors="ignore")
    pol = pol.merge(np_ref, on="future_id", how="left", validate="many_to_one")

    numeric_cols = [
        "cumulative_emissions_CO2", "discounted_resource_cost",
        "discounted_total_cost_with_penalty", "np_cumulative_emissions_CO2",
        "np_discounted_resource_cost", "np_discounted_total_cost_with_penalty",
        "lambda0", "kp", "policy_delta_final", "lambda_final", "lambda_final_actual",
    ]
    for c in numeric_cols:
        if c in pol.columns:
            pol[c] = pd.to_numeric(pol[c], errors="coerce")

    pol["avoided_cumulative_emissions_CO2"] = (
        pol["np_cumulative_emissions_CO2"] - pol["cumulative_emissions_CO2"]
    )
    pol["incremental_system_cost"] = (
        pol["discounted_resource_cost"] - pol["np_discounted_resource_cost"]
    )
    pol["incremental_total_cost_with_penalty"] = (
        pol["discounted_total_cost_with_penalty"] - pol["np_discounted_total_cost_with_penalty"]
    )

    cfg = pol.apply(_cei_config_fields, axis=1, result_type="expand")
    cfg.columns = ["policy_configuration", "policy_configuration_label"]
    pol = pd.concat([pol.reset_index(drop=True), cfg.reset_index(drop=True)], axis=1)

    denom = pol["avoided_cumulative_emissions_CO2"]
    positive = denom > float(eps)
    pol["CEI_SYS_USD_per_tCO2_avoided"] = np.where(
        positive, pol["incremental_system_cost"] / denom, np.nan
    )
    pol["CEI_TOT_USD_per_tCO2_avoided"] = np.where(
        positive, pol["incremental_total_cost_with_penalty"] / denom, np.nan
    )

    def invalid_reason(v):
        if pd.isna(v): return "missing_avoided_emissions"
        if v < -float(eps): return "negative_avoided_emissions"
        if v <= float(eps): return "zero_avoided_emissions"
        return ""
    pol["cei_invalid_reason"] = denom.map(invalid_reason)
    invalid = pol[pol["cei_invalid_reason"].ne("")].copy()
    valid = pol[pol["cei_invalid_reason"].eq("")].copy()
    return pol, valid, invalid


def _cei_summary_stats(values: pd.Series) -> dict:
    x = pd.to_numeric(values, errors="coerce").dropna()
    if x.empty:
        return {
            "n_valid": 0, "mean": np.nan, "std": np.nan, "median": np.nan,
            "p10": np.nan, "p25": np.nan, "p75": np.nan, "p90": np.nan,
            "iqr": np.nan, "p90_p10": np.nan,
        }
    q = x.quantile([0.10, 0.25, 0.50, 0.75, 0.90])
    return {
        "n_valid": int(x.size),
        "mean": float(x.mean()),
        "std": float(x.std(ddof=1)) if x.size > 1 else 0.0,
        "median": float(q.loc[0.50]),
        "p10": float(q.loc[0.10]),
        "p25": float(q.loc[0.25]),
        "p75": float(q.loc[0.75]),
        "p90": float(q.loc[0.90]),
        "iqr": float(q.loc[0.75] - q.loc[0.25]),
        "p90_p10": float(q.loc[0.90] - q.loc[0.10]),
    }


def build_cost_effectiveness_configuration_summary(valid: pd.DataFrame, cei_col: str, cost_version: str) -> pd.DataFrame:
    """Per-policy-configuration CEI dispersion across requested future subsets."""
    subsets = ["All", "Demand Up", "Demand Down", "Linear", "Step"]
    rows = []
    for subset in subsets:
        mask = valid["future_id"].map(lambda x: _cei_future_group(x)[subset])
        d = valid[mask].copy()
        for (rep, cfg, label), g in d.groupby(
            ["representation_canonical", "policy_configuration", "policy_configuration_label"], sort=True
        ):
            stats = _cei_summary_stats(g[cei_col])
            rows.append({
                "cost_version": cost_version,
                "future_subset": subset,
                "representation": "Prescribed" if rep == "prescribed" else "CLPR",
                "policy_configuration": cfg,
                "policy_configuration_label": label,
                "n_futures_available": int(g["future_id"].nunique()),
                **stats,
            })
    return pd.DataFrame(rows)


def build_cost_effectiveness_dispersion_comparison(summary: pd.DataFrame) -> pd.DataFrame:
    """Representation-level diagnostic summary of configuration dispersions."""
    rows = []
    for (cost_version, subset, rep), g in summary.groupby(
        ["cost_version", "future_subset", "representation"], sort=False
    ):
        st = _cei_summary_stats(g["p90_p10"])
        rows.append({
            "cost_version": cost_version,
            "future_subset": subset,
            "representation": rep,
            "n_configurations": int(g["policy_configuration"].nunique()),
            "median_configuration_dispersion": st["median"],
            "mean_configuration_dispersion": st["mean"],
            "p10_configuration_dispersion": st["p10"],
            "p90_configuration_dispersion": st["p90"],
        })
    out = pd.DataFrame(rows)
    # Add an explicit, non-inferential hypothesis diagnostic for each subset.
    piv = out.pivot_table(
        index=["cost_version", "future_subset"], columns="representation",
        values="median_configuration_dispersion", aggfunc="first"
    ).reset_index()
    if "CLPR" in piv.columns and "Prescribed" in piv.columns:
        piv["median_dispersion_CLPR_minus_Prescribed"] = piv["CLPR"] - piv["Prescribed"]
        piv["median_dispersion_ratio_CLPR_over_Prescribed"] = np.where(
            piv["Prescribed"].abs() > 1e-12, piv["CLPR"] / piv["Prescribed"], np.nan
        )
    return out, piv


def _save_cei_figure(fig, stem: Path):
    stem.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(stem.with_suffix(".png"), dpi=300, bbox_inches="tight")
    fig.savefig(stem.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def plot_cei_figure_A(valid: pd.DataFrame, cei_col: str, cost_version: str, outdir: Path):
    """Figure A — raw CEI distributions across futures, Prescribed vs CLPR."""
    subsets = ["All", "Demand Up", "Demand Down", "Linear", "Step"]
    fig, axes = plt.subplots(2, 3, figsize=(12.0, 7.4), constrained_layout=True)
    axes = axes.ravel()
    rep_order = ["prescribed", "closed_loop"]
    labels = ["Prescribed", "CLPR"]
    for ax, subset in zip(axes, subsets):
        d = valid[valid["future_id"].map(lambda x: _cei_future_group(x)[subset])]
        vals = [pd.to_numeric(d[d["representation_canonical"].eq(rep)][cei_col], errors="coerce").dropna().values for rep in rep_order]
        ax.boxplot(vals, labels=labels, showfliers=False)
        ax.set_title(subset, fontweight="normal")
        ax.set_ylabel("CEI (USD/tCO$_2$ avoided)")
        ax.grid(axis="y", alpha=0.20)
    axes[-1].axis("off")
    fig.suptitle(f"CEI across futures — {cost_version}", fontweight="normal")
    _save_cei_figure(fig, outdir / f"Figure_A_CEI_across_futures_{cost_version}")


def plot_cei_figure_B(summary: pd.DataFrame, cost_version: str, outdir: Path):
    """Figure B — configuration median CEI vs P90-P10 dispersion."""
    subsets = ["All", "Demand Up", "Demand Down", "Linear", "Step"]
    fig, axes = plt.subplots(2, 3, figsize=(12.0, 7.4), constrained_layout=True)
    axes = axes.ravel()
    markers = {"Prescribed": "o", "CLPR": "^"}
    for ax, subset in zip(axes, subsets):
        d = summary[(summary["cost_version"].eq(cost_version)) & (summary["future_subset"].eq(subset))]
        for rep in ["Prescribed", "CLPR"]:
            g = d[d["representation"].eq(rep)]
            ax.scatter(g["median"], g["p90_p10"], marker=markers[rep], alpha=0.72, label=rep)
        ax.set_title(subset, fontweight="normal")
        ax.set_xlabel("Median CEI (USD/tCO$_2$ avoided)")
        ax.set_ylabel("P90–P10 CEI dispersion")
        ax.grid(alpha=0.20)
        if subset == "All": ax.legend(frameon=False)
    axes[-1].axis("off")
    fig.suptitle(f"Cost-effectiveness vs dispersion — {cost_version}", fontweight="normal")
    _save_cei_figure(fig, outdir / f"Figure_B_CEI_vs_dispersion_{cost_version}")


def plot_cei_figure_C(summary: pd.DataFrame, cost_version: str, outdir: Path):
    """Figure C — direct comparison of configuration P90-P10 dispersions."""
    subsets = ["All", "Demand Up", "Demand Down"]
    fig, axes = plt.subplots(1, 3, figsize=(11.2, 3.8), constrained_layout=True)
    for ax, subset in zip(axes, subsets):
        d = summary[(summary["cost_version"].eq(cost_version)) & (summary["future_subset"].eq(subset))]
        vals = [
            pd.to_numeric(d[d["representation"].eq(rep)]["p90_p10"], errors="coerce").dropna().values
            for rep in ["Prescribed", "CLPR"]
        ]
        ax.boxplot(vals, labels=["Prescribed", "CLPR"], showfliers=False)
        ax.set_title(subset, fontweight="normal")
        ax.set_ylabel("P90–P10 CEI dispersion")
        ax.grid(axis="y", alpha=0.20)
    fig.suptitle(f"Direct CEI dispersion comparison — {cost_version}", fontweight="normal")
    _save_cei_figure(fig, outdir / f"Figure_C_direct_dispersion_{cost_version}")


def run_cost_effectiveness_dispersion_analysis(metrics: pd.DataFrame, outdir: Path, make_plots: bool = True):
    """Run the complete exploratory CEI-dispersion analysis in an isolated folder."""
    root = outdir / "A6_cost_effectiveness_dispersion"
    tables_dir = root / "tables"
    figures_dir = root / "figures"
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    mapping = verify_cost_effectiveness_columns(metrics)
    mapping.to_csv(tables_dir / "CEI_Source_Column_Verification.csv", index=False)

    all_rows, valid, invalid = build_cost_effectiveness_run_table(metrics)
    all_rows.to_csv(tables_dir / "CEI_By_Run_All_Policies.csv", index=False)
    valid.to_csv(tables_dir / "CEI_By_Run_Valid.csv", index=False)
    invalid.to_csv(tables_dir / "CEI_Invalid_Zero_or_Negative_Avoided_Emissions.csv", index=False)

    invalid_summary = (
        invalid.groupby(["representation_canonical", "cei_invalid_reason"], dropna=False)
        .size().reset_index(name="n_cases") if not invalid.empty else pd.DataFrame(
            columns=["representation_canonical", "cei_invalid_reason", "n_cases"]
        )
    )
    invalid_summary.to_csv(tables_dir / "CEI_Invalid_Cases_Summary.csv", index=False)

    sys_summary = build_cost_effectiveness_configuration_summary(
        valid, "CEI_SYS_USD_per_tCO2_avoided", "SYS"
    )
    tot_summary = build_cost_effectiveness_configuration_summary(
        valid, "CEI_TOT_USD_per_tCO2_avoided", "TOT"
    )
    sys_summary.to_csv(tables_dir / "CEI_SYS_By_Configuration.csv", index=False)
    tot_summary.to_csv(tables_dir / "CEI_TOT_By_Configuration.csv", index=False)
    combined_summary = pd.concat([sys_summary, tot_summary], ignore_index=True)
    combined_summary.to_csv(tables_dir / "CEI_All_Cost_Versions_By_Configuration.csv", index=False)

    rep_summary, hypothesis = build_cost_effectiveness_dispersion_comparison(combined_summary)
    rep_summary.to_csv(tables_dir / "CEI_Dispersion_By_Representation.csv", index=False)
    hypothesis.to_csv(tables_dir / "CEI_Hypothesis_Diagnostic.csv", index=False)

    if make_plots:
        for version, col in [
            ("SYS", "CEI_SYS_USD_per_tCO2_avoided"),
            ("TOT", "CEI_TOT_USD_per_tCO2_avoided"),
        ]:
            version_dir = figures_dir / version
            version_dir.mkdir(parents=True, exist_ok=True)
            plot_cei_figure_A(valid, col, version, version_dir)
            plot_cei_figure_B(combined_summary, version, version_dir)
            plot_cei_figure_C(combined_summary, version, version_dir)

    print(f">> CEI dispersion analysis folder: {root}")
    print(f">> Valid CEI policy-future cases: {len(valid)}")
    print(f">> CEI cases excluded for zero/negative/missing avoided emissions: {len(invalid)}")
    if not hypothesis.empty:
        print(">> Median P90-P10 dispersion diagnostic (CLPR vs Prescribed):")
        for _, r in hypothesis.iterrows():
            print(
                f">>   {r.get('cost_version')} | {r.get('future_subset')}: "
                f"CLPR={r.get('CLPR', np.nan):.6g}, "
                f"Prescribed={r.get('Prescribed', np.nan):.6g}, "
                f"Δ={r.get('median_dispersion_CLPR_minus_Prescribed', np.nan):.6g}"
            )
    return root

def print_summary(index_df, results_df, validation_df, metrics_df) -> None:
    n_runs = len(index_df)
    n_valid = int(validation_df["valid_run"].sum())
    reps = index_df["representation"].astype(str).value_counts().to_dict()
    raw_emissions = int(validation_df["emissions_found"].sum())
    raw_costs = int(validation_df["annual_resource_cost_found"].sum())

    print("\n>> CLPR_ESOM A.6 — Results Analysis & Plotting")
    print(">> ------------------------------------------------")
    print(f">> Experiment runs: {n_runs}")
    print(f">> Result rows / blocks: {len(results_df)}")
    print(f">> Valid runs: {n_valid}")
    print(f">> Invalid runs: {n_runs - n_valid}")
    print(f">> Representations: {reps}")
    print(f">> Runs with raw annual emissions: {raw_emissions}/{n_runs}")
    print(f">> Runs with complete annual resource-cost outputs: {raw_costs}/{n_runs}")
    if not metrics_df.empty:
        print(
            f">> Terminal emissions range: {metrics_df['terminal_emissions'].min():.6g} "
            f"to {metrics_df['terminal_emissions'].max():.6g}"
        )
    print(">> Ready for analysis: " + ("YES" if n_valid == n_runs else "WITH VALIDATION WARNINGS"))
    print()


def build_cli() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="CLPR_ESOM A.6 - Results Analysis & Plotting")
    ap.add_argument("--experiment-dir", default="Experiment_A5")
    ap.add_argument("--outdir", default=None)
    ap.add_argument(
        "--start-year",
        type=int,
        default=2014,
        help="First year included in cumulative emissions and PV cost accounting.",
    )
    ap.add_argument("--target-year", type=int, default=2040)
    ap.add_argument(
        "--target-tolerance",
        type=float,
        default=1e-6,
        help="Absolute tolerance used only to classify whether the final target is met.",
    )
    ap.add_argument(
        "--future-max-deviation",
        type=float,
        default=0.50,
        help="Maximum absolute demand perturbation for LU/LD/SU/SD future axes.",
    )
    ap.add_argument(
        "--discount-rate",
        type=float,
        default=None,
        help=(
            "Optional DiscountRate override. If omitted, A6 searches "
            "the A5 experiment/run data files."
        ),
    )
    ap.add_argument("--future", default="BASE", help="Future for first plots plot")
    ap.add_argument("--demand-unit", default="PJ", help="Unit label used for annual demand in paper Figure 1.")
    ap.add_argument("--no-plots", action="store_true")
    return ap



# =============================================================================
# BLOCK 3 — Exploratory Policy Authority Test
# =============================================================================

def _policy_configuration_description(row: pd.Series) -> str:
    """Compact, traceable description of the policy configuration in one run."""
    rep = str(row.get("representation_canonical", ""))
    lam0 = pd.to_numeric(pd.Series([row.get("lambda0", np.nan)]), errors="coerce").iloc[0]
    if rep == "prescribed":
        p = pd.to_numeric(pd.Series([row.get("policy_delta_final", np.nan)]), errors="coerce").iloc[0]
        lf = pd.to_numeric(pd.Series([row.get("lambda_final", np.nan)]), errors="coerce").iloc[0]
        parts = ["Prescribed"]
        if np.isfinite(lam0):
            parts.append(f"lambda0={lam0:g}")
        if np.isfinite(p):
            parts.append(f"delta_final={100*p:+g}%")
        if np.isfinite(lf):
            parts.append(f"lambda_final={lf:g}")
        return "; ".join(parts)
    if rep == "closed_loop":
        kp = pd.to_numeric(pd.Series([row.get("kp", np.nan)]), errors="coerce").iloc[0]
        parts = ["CLPR"]
        if np.isfinite(lam0):
            parts.append(f"lambda0={lam0:g}")
        if np.isfinite(kp):
            parts.append(f"Kp={kp:g}")
        return "; ".join(parts)
    return str(row.get("representation", rep))


def build_policy_authority_data(
    metrics: pd.DataFrame,
    family: str,
    max_deviation: float = 0.50,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build Block 3 data for one demand-future family.

    Panel (a) uses the policy outcome spread separately for Prescribed and CLPR:
        P90(E2040) - P10(E2040)
    at each signed demand deviation. Panels (b) and (c) retain the same
    median/P10/P90 outcome summaries used in v40. No Policy is excluded.
    """
    if family not in {"linear", "step"}:
        raise ValueError("family must be 'linear' or 'step'")

    d = metrics[
        metrics["representation_canonical"].isin(["prescribed", "closed_loop"])
    ].copy()
    d["terminal_emissions"] = pd.to_numeric(d["terminal_emissions"], errors="coerce")
    d["discounted_total_cost_with_penalty"] = pd.to_numeric(
        d["discounted_total_cost_with_penalty"], errors="coerce"
    )
    d["lambda0"] = pd.to_numeric(d["lambda0"], errors="coerce")
    d["kp"] = pd.to_numeric(d["kp"], errors="coerce")
    d["policy_delta_final"] = pd.to_numeric(d["policy_delta_final"], errors="coerce")
    d["lambda_final"] = pd.to_numeric(d["lambda_final"], errors="coerce")

    d["_future_level"] = d["future_id"].map(lambda x: _future_signed_level(x, family))
    d = d[d["_future_level"].notna()].copy()
    if d.empty:
        return pd.DataFrame(), pd.DataFrame()

    max_level = pd.to_numeric(d["_future_level"], errors="coerce").abs().max()
    if pd.isna(max_level) or max_level == 0:
        max_level = 1.0
    d["demand_delta_fraction"] = d["_future_level"] / max_level * float(max_deviation)
    d["demand_delta_pct"] = 100.0 * d["demand_delta_fraction"]
    d["policy_type"] = d["representation_canonical"].map(
        {"prescribed": "Prescribed", "closed_loop": "CLPR"}
    )
    d["policy_configuration"] = d.apply(_policy_configuration_description, axis=1)
    d["family"] = family

    keep = [
        "run_id", "future_id", "family", "demand_delta", "demand_delta_fraction",
        "demand_delta_pct", "policy_type", "representation_canonical",
        "lambda0", "policy_delta_final", "lambda_final", "kp",
        "policy_configuration", "terminal_emissions",
        "discounted_total_cost_with_penalty",
    ]
    raw = d[[c for c in keep if c in d.columns]].copy()

    # Same summary drives panel (a), panel (b), and panel (c).
    outcome_rows = []
    for (delta, policy_type), g in d.groupby(
        ["demand_delta_fraction", "policy_type"], sort=True
    ):
        for metric, label in [
            ("terminal_emissions", "E2040"),
            ("discounted_total_cost_with_penalty", "Total discounted cost"),
        ]:
            x = pd.to_numeric(g[metric], errors="coerce").dropna()
            if x.empty:
                continue
            p10 = float(x.quantile(0.10))
            p90 = float(x.quantile(0.90))
            outcome_rows.append({
                "family": family,
                "demand_delta_fraction": float(delta),
                "demand_delta_pct": 100.0 * float(delta),
                "policy_type": policy_type,
                "metric": label,
                "n": int(len(x)),
                "min": float(x.min()),
                "p10": p10,
                "median": float(x.median()),
                "p90": p90,
                "max": float(x.max()),
                "policy_outcome_spread": p90 - p10 if label == "E2040" else np.nan,
            })
    outcomes = pd.DataFrame(outcome_rows)
    return outcomes, raw


def _plot_policy_authority_three_panel(
    family: str,
    outcomes: pd.DataFrame,
    outdir: Path,
    spread_ylim=None,
    emissions_ylim=None,
    cost_ylim=None,
):
    """Diagnostic 1x3 figure; only panel (a) differs from v40."""
    if outcomes.empty:
        return None

    fig, axes = plt.subplots(1, 3, figsize=(14.5, 4.4), constrained_layout=True)

    # (a) Policy outcome spread = P90(E2040) - P10(E2040), separately by type.
    s = outcomes[outcomes["metric"].eq("E2040")].copy()
    for policy_type in ["Prescribed", "CLPR"]:
        g = s[s["policy_type"].eq(policy_type)].sort_values("demand_delta_pct")
        if g.empty:
            continue
        axes[0].plot(
            g["demand_delta_pct"], g["policy_outcome_spread"],
            marker="o", linewidth=1.4, label=policy_type
        )
    axes[0].set_title("(a) Policy outcome spread", fontweight="normal")
    axes[0].set_xlabel("Demand deviation from Base (%)")
    axes[0].set_ylabel(r"$P90(E_{2040})-P10(E_{2040})$ (Mton)")
    axes[0].axvline(0, linestyle="--", linewidth=0.8)
    axes[0].grid(alpha=0.20)
    axes[0].legend(frameon=False)
    if spread_ylim is not None:
        axes[0].set_ylim(*spread_ylim)

    # (b) Environmental outcome — unchanged from v40.
    e = outcomes[outcomes["metric"].eq("E2040")].copy()
    for policy_type in ["Prescribed", "CLPR"]:
        g = e[e["policy_type"].eq(policy_type)].sort_values("demand_delta_pct")
        if g.empty:
            continue
        x = g["demand_delta_pct"].to_numpy(dtype=float)
        axes[1].plot(x, g["median"], marker="o", linewidth=1.4, label=policy_type)
        axes[1].fill_between(x, g["p10"], g["p90"], alpha=0.18)
    axes[1].set_title("(b) Environmental outcome", fontweight="normal")
    axes[1].set_xlabel("Demand deviation from Base (%)")
    axes[1].set_ylabel(r"2040 emissions (Mton)")
    axes[1].axvline(0, linestyle="--", linewidth=0.8)
    axes[1].grid(alpha=0.20)
    axes[1].legend(frameon=False)
    if emissions_ylim is not None:
        axes[1].set_ylim(*emissions_ylim)

    # (c) Economic consequence — unchanged from v40.
    c = outcomes[outcomes["metric"].eq("Total discounted cost")].copy()
    for policy_type in ["Prescribed", "CLPR"]:
        g = c[c["policy_type"].eq(policy_type)].sort_values("demand_delta_pct")
        if g.empty:
            continue
        x = g["demand_delta_pct"].to_numpy(dtype=float)
        axes[2].plot(x, g["median"], marker="o", linewidth=1.4, label=policy_type)
        axes[2].fill_between(x, g["p10"], g["p90"], alpha=0.18)
    axes[2].set_title("(c) Economic consequence", fontweight="normal")
    axes[2].set_xlabel("Demand deviation from Base (%)")
    axes[2].set_ylabel("Total discounted cost (Mton)")
    axes[2].axvline(0, linestyle="--", linewidth=0.8)
    axes[2].grid(alpha=0.20)
    axes[2].legend(frameon=False)
    if cost_ylim is not None:
        axes[2].set_ylim(*cost_ylim)

    fig.suptitle(f"{family.title()} demand futures", fontweight="normal")
    outdir.mkdir(parents=True, exist_ok=True)
    png = outdir / f"Policy_Authority_{family}.png"
    pdf = outdir / f"Policy_Authority_{family}.pdf"
    fig.savefig(png, dpi=300, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    plt.close(fig)
    return png, pdf


def run_policy_authority_test(
    metrics: pd.DataFrame,
    outdir: Path,
    max_deviation: float = 0.50,
    make_plots: bool = True,
):
    """Block 3 diagnostic outputs, isolated from Blocks 1 and 2."""
    root = outdir
    tables_dir = outdir / "data" / "block_3_policy_authority"
    figures_dir = outdir / "figures" / "block_3_policy_authority"
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    outcomes = {}
    raw = {}
    for family in ["linear", "step"]:
        outcomes[family], raw[family] = build_policy_authority_data(
            metrics, family=family, max_deviation=max_deviation
        )
        outcomes[family].to_csv(
            tables_dir / f"Policy_Authority_{family}_Outcome_Summary.csv", index=False
        )
        raw[family].to_csv(
            tables_dir / f"Policy_Authority_{family}_Disaggregated_Runs.csv", index=False
        )

        spread = outcomes[family][outcomes[family]["metric"].eq("E2040")][[
            "family", "demand_delta_fraction", "demand_delta_pct", "policy_type",
            "n", "p10", "p90", "policy_outcome_spread"
        ]].copy()
        spread.to_csv(
            tables_dir / f"Policy_Outcome_Spread_{family}_By_Demand.csv", index=False
        )

    out_all = pd.concat([x for x in outcomes.values() if not x.empty], ignore_index=True)
    out_all.to_csv(
        tables_dir / "Policy_Authority_Outcome_Summary_All_Families.csv", index=False
    )

    def _shared_ylim(values, floor_zero=False):
        x = pd.to_numeric(values, errors="coerce").dropna()
        if x.empty:
            return None
        lo, hi = float(x.min()), float(x.max())
        if floor_zero:
            lo = min(0.0, lo)
        span = hi - lo
        pad = 0.05 * span if span > 0 else max(abs(hi) * 0.05, 1e-6)
        return (lo - pad if not floor_zero else max(0.0, lo - pad), hi + pad)

    emissions_rows = out_all[out_all["metric"].eq("E2040")]
    cost_rows = out_all[out_all["metric"].eq("Total discounted cost")]
    spread_ylim = _shared_ylim(emissions_rows["policy_outcome_spread"], floor_zero=True)
    emissions_ylim = _shared_ylim(
        pd.concat([emissions_rows["p10"], emissions_rows["p90"]], ignore_index=True)
    )
    cost_ylim = _shared_ylim(
        pd.concat([cost_rows["p10"], cost_rows["p90"]], ignore_index=True)
    )

    if make_plots:
        for family in ["linear", "step"]:
            paths = _plot_policy_authority_three_panel(
                family=family,
                outcomes=outcomes[family],
                outdir=figures_dir,
                spread_ylim=spread_ylim,
                emissions_ylim=emissions_ylim,
                cost_ylim=cost_ylim,
            )
            if paths:
                print(f">> Policy Authority {family.title()}: {paths[0]} | {paths[1]}")

    definition = pd.DataFrame([
        {
            "item": "Panel (a): Policy outcome spread",
            "definition": "P90(E2040) - P10(E2040), calculated separately for Prescribed and CLPR at each demand deviation",
        },
        {
            "item": "policy space",
            "definition": "all explored Prescribed and CLPR configurations; No Policy excluded",
        },
        {
            "item": "environmental outcome bands",
            "definition": "median with empirical P10-P90 across configurations of each policy type",
        },
        {
            "item": "economic outcome bands",
            "definition": "median with empirical P10-P90 of discounted total cost including emissions penalty",
        },
    ])
    definition.to_csv(tables_dir / "Policy_Authority_Definition.csv", index=False)
    print(f">> Paper Block 3 data folder: {tables_dir}")
    print(f">> Paper Block 3 figure folder: {figures_dir}")
    return figures_dir, tables_dir


# =============================================================================
# BLOCK 4 — Exploratory ex-ante decision analysis
# =============================================================================

def _build_ex_ante_configuration_id(row: pd.Series) -> tuple[str, str]:
    """Return (policy_type, configuration_id) for one policy run."""
    rep = str(row.get("representation_canonical", ""))
    lam0 = pd.to_numeric(pd.Series([row.get("lambda0", np.nan)]), errors="coerce").iloc[0]

    if rep == "prescribed":
        p = pd.to_numeric(
            pd.Series([row.get("policy_delta_final", np.nan)]), errors="coerce"
        ).iloc[0]
        policy_type = "Prescribed"
        config_id = (
            f"Prescribed | lambda0={lam0:g} | delta_final={100*p:+g}%"
            if np.isfinite(lam0) and np.isfinite(p)
            else _policy_configuration_description(row)
        )
        return policy_type, config_id

    if rep == "closed_loop":
        kp = pd.to_numeric(pd.Series([row.get("kp", np.nan)]), errors="coerce").iloc[0]
        policy_type = "CLPR"
        config_id = (
            f"CLPR | lambda0={lam0:g} | Kp={kp:g}"
            if np.isfinite(lam0) and np.isfinite(kp)
            else _policy_configuration_description(row)
        )
        return policy_type, config_id

    return str(row.get("representation", rep)), _policy_configuration_description(row)


def _pareto_nondominated_mask(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    atol: float = 1e-12,
) -> pd.Series:
    """
    Return True for points not dominated when both objectives are minimized.

    A dominates B if:
      A_x <= B_x and A_y <= B_y,
    with at least one strict improvement.
    """
    x = pd.to_numeric(df[x_col], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(df[y_col], errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    out = np.zeros(len(df), dtype=bool)

    valid_idx = np.where(valid)[0]
    for i in valid_idx:
        dominated = False
        for j in valid_idx:
            if i == j:
                continue
            no_worse = (x[j] <= x[i] + atol) and (y[j] <= y[i] + atol)
            strictly_better = (x[j] < x[i] - atol) or (y[j] < y[i] - atol)
            if no_worse and strictly_better:
                dominated = True
                break
        out[i] = not dominated

    return pd.Series(out, index=df.index)


def build_ex_ante_decision_data(
    metrics: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Evaluate every Prescribed configuration and every CLPR rule across all
    demand futures already simulated.

    No Policy is excluded. No additional model runs are performed.

    Ex-post performance gap for future i and policy configuration pi:
        G_i,pi = E2040_i,pi - min_pi'(E2040_i,pi')

    The future-specific minimum is calculated over the complete explored
    Prescribed + CLPR policy space for that same future.

    The discounted-cost metric used here is:
        discounted_total_cost_with_penalty
    to remain consistent with Paper Blocks 2 and 3.
    """
    d = metrics[
        metrics["representation_canonical"].isin(["prescribed", "closed_loop"])
    ].copy()

    d["terminal_emissions"] = pd.to_numeric(
        d["terminal_emissions"], errors="coerce"
    )
    d["discounted_total_cost_with_penalty"] = pd.to_numeric(
        d["discounted_total_cost_with_penalty"], errors="coerce"
    )
    d["lambda0"] = pd.to_numeric(d["lambda0"], errors="coerce")
    d["kp"] = pd.to_numeric(d["kp"], errors="coerce")
    d["policy_delta_final"] = pd.to_numeric(
        d["policy_delta_final"], errors="coerce"
    )

    ids = d.apply(_build_ex_ante_configuration_id, axis=1)
    d["policy_type"] = [x[0] for x in ids]
    d["configuration_id"] = [x[1] for x in ids]

    # Target-performance gap relative to the policy target.
    # Here target = 0, therefore for non-negative terminal emissions:
    #   target_performance_gap = abs(E2040 - 0) = E2040
    target_E2040 = 0.0
    d["target_performance_gap"] = (
        d["terminal_emissions"] - target_E2040
    ).abs()

    # Preserve disaggregated run-level outcomes and target gap.
    raw_cols = [
        "run_id",
        "future_id",
        "policy_type",
        "representation_canonical",
        "configuration_id",
        "lambda0",
        "policy_delta_final",
        "kp",
        "terminal_emissions",
        "discounted_total_cost_with_penalty",
        "target_performance_gap",
    ]
    raw = d[[c for c in raw_cols if c in d.columns]].copy()

    # Configuration-level ex-ante summaries over all demand futures.
    rows = []
    group_cols = [
        "policy_type",
        "representation_canonical",
        "configuration_id",
        "lambda0",
    ]

    for keys, g in d.groupby(group_cols, sort=True, dropna=False):
        policy_type, rep, config_id, lam0 = keys

        e = pd.to_numeric(g["terminal_emissions"], errors="coerce").dropna()
        c = pd.to_numeric(
            g["discounted_total_cost_with_penalty"], errors="coerce"
        ).dropna()
        gap = pd.to_numeric(
            g["target_performance_gap"], errors="coerce"
        ).dropna()

        row = {
            "policy_type": policy_type,
            "representation_canonical": rep,
            "configuration_id": config_id,
            "lambda0": lam0,
            "policy_delta_final": (
                pd.to_numeric(g["policy_delta_final"], errors="coerce").dropna().iloc[0]
                if rep == "prescribed"
                and not pd.to_numeric(g["policy_delta_final"], errors="coerce").dropna().empty
                else np.nan
            ),
            "kp": (
                pd.to_numeric(g["kp"], errors="coerce").dropna().iloc[0]
                if rep == "closed_loop"
                and not pd.to_numeric(g["kp"], errors="coerce").dropna().empty
                else np.nan
            ),
            "n_futures": int(g["future_id"].nunique()),
            "E2040_median": float(e.median()) if not e.empty else np.nan,
            "E2040_p90": float(e.quantile(0.90)) if not e.empty else np.nan,
            "discounted_cost_median": float(c.median()) if not c.empty else np.nan,
            "discounted_cost_p90": float(c.quantile(0.90)) if not c.empty else np.nan,
            "target_gap_median": float(gap.median()) if not gap.empty else np.nan,
            "target_gap_p90": float(gap.quantile(0.90)) if not gap.empty else np.nan,
        }
        rows.append(row)

    summary = pd.DataFrame(rows)

    # Consistency check for target = 0 and non-negative E2040.
    # Under these conditions P90(target gap) must equal P90(E2040).
    if not summary.empty:
        nonnegative = bool((d["terminal_emissions"].dropna() >= -1e-12).all())
        if nonnegative:
            diff = (
                pd.to_numeric(summary["target_gap_p90"], errors="coerce")
                - pd.to_numeric(summary["E2040_p90"], errors="coerce")
            ).abs()
            max_diff = float(diff.max()) if not diff.empty else 0.0
            if max_diff > 1e-10:
                raise RuntimeError(
                    "Block 4 consistency check failed: with target=0 and "
                    "non-negative E2040, P90_target_gap must equal P90_E2040. "
                    f"Maximum difference = {max_diff:.6g}"
                )

    if not summary.empty:
        # GLOBAL Pareto mask: jointly over all Prescribed + CLPR configurations.
        summary["pareto_median_cost_vs_median_E2040"] = _pareto_nondominated_mask(
            summary,
            "discounted_cost_median",
            "E2040_median",
        )
        # GLOBAL Pareto mask for the second decision criterion.
        summary["pareto_median_cost_vs_p90_gap"] = _pareto_nondominated_mask(
            summary,
            "discounted_cost_median",
            "target_gap_p90",
        )
    else:
        summary["pareto_median_cost_vs_median_E2040"] = pd.Series(dtype=bool)
        summary["pareto_median_cost_vs_p90_gap"] = pd.Series(dtype=bool)

    return summary, raw



def select_representative_global_pareto(
    summary: pd.DataFrame,
    cost_col: str = "discounted_cost_median",
    gap_col: str = "target_gap_p90",
    pareto_col: str = "pareto_median_cost_vs_p90_gap",
) -> pd.DataFrame:
    """
    Guided A-H selection on the JOINT/global Pareto frontier of
    Median cost vs P90 target-performance gap.

    Requested pattern:
      A, B, G, H -> Prescribed
      C, D, E, F -> CLPR

    Selection is based on approximate normalized-cost positions taken from the
    requested visual layout. No simulation result is modified.

    Target normalized-cost positions:
      A=0.00, B=0.08, C=0.18, D=0.38,
      E=0.55, F=0.82, G=0.92, H=1.00
    """
    if summary.empty:
        return pd.DataFrame()

    front = summary[summary[pareto_col].astype(bool)].copy()
    front[cost_col] = pd.to_numeric(front[cost_col], errors="coerce")
    front[gap_col] = pd.to_numeric(front[gap_col], errors="coerce")
    front = front.dropna(subset=[cost_col, gap_col]).copy()
    if front.empty:
        return pd.DataFrame()

    cmin = float(front[cost_col].min())
    cmax = float(front[cost_col].max())
    dc = cmax - cmin
    front["_cost_norm"] = (front[cost_col] - cmin) / dc if dc > 0 else 0.0

    desired = [
        ("A", "Prescribed", 0.00, "minimum-cost extreme"),
        ("B", "Prescribed", 0.08, "low-cost prescribed"),
        ("C", "CLPR",       0.18, "central CLPR"),
        ("D", "CLPR",       0.38, "central CLPR"),
        ("E", "CLPR",       0.55, "central CLPR"),
        ("F", "CLPR",       0.82, "central/high-performance CLPR"),
        ("G", "Prescribed", 0.92, "high-performance prescribed"),
        ("H", "Prescribed", 1.00, "minimum-target-gap extreme"),
    ]

    used = set()
    rows = []

    for label, architecture, target_x, role in desired:
        cand = front[
            front["policy_type"].eq(architecture)
            & ~front.index.isin(used)
        ].copy()

        if cand.empty:
            cand = front[~front.index.isin(used)].copy()
        if cand.empty:
            break

        if label == "A":
            pick = cand.sort_values(
                [cost_col, gap_col, "configuration_id"],
                ascending=[True, True, True],
            ).index[0]
        elif label == "H":
            pick = cand.sort_values(
                [gap_col, cost_col, "configuration_id"],
                ascending=[True, True, True],
            ).index[0]
        else:
            cand["_distance"] = (cand["_cost_norm"] - target_x).abs()
            pick = cand.sort_values(
                ["_distance", gap_col, cost_col, "configuration_id"],
                ascending=[True, True, True, True],
            ).index[0]

        used.add(pick)
        row = front.loc[pick].copy()
        row["representative_label"] = label
        row["representative_role"] = role
        row["target_normalized_cost_position"] = target_x

        lam0 = pd.to_numeric(
            pd.Series([row.get("lambda0", np.nan)]), errors="coerce"
        ).iloc[0]

        if str(row["policy_type"]) == "CLPR":
            kp = pd.to_numeric(
                pd.Series([row.get("kp", np.nan)]), errors="coerce"
            ).iloc[0]
            row["lambda_final"] = np.nan
            row["display_configuration"] = (
                rf"$\lambda_0={lam0:g},\ K_p={kp:g}$"
                if np.isfinite(lam0) and np.isfinite(kp)
                else str(row.get("configuration_id", "CLPR"))
            )
        else:
            p = pd.to_numeric(
                pd.Series([row.get("policy_delta_final", np.nan)]),
                errors="coerce",
            ).iloc[0]
            if np.isfinite(lam0) and np.isfinite(p):
                lamf = lam0 * (1.0 + p)
                row["lambda_final"] = lamf
                row["display_configuration"] = (
                    rf"$\lambda_0={lam0:g},\ \lambda_f={lamf:g}$"
                )
            else:
                row["lambda_final"] = np.nan
                row["display_configuration"] = str(
                    row.get("configuration_id", "Prescribed")
                )

        rows.append(row)

    return pd.DataFrame(rows).drop(columns=["_cost_norm"], errors="ignore")


def _plot_ex_ante_map(
    summary: pd.DataFrame,
    representatives: pd.DataFrame,
    x_col: str,
    y_col: str,
    pareto_col: str,
    xlabel: str,
    ylabel: str,
    title: str,
    outpath: Path,
):
    """Show all configurations as context; highlight and label only A-E."""
    if summary.empty:
        return None

    fig, ax = plt.subplots(figsize=(8.6, 6.3), constrained_layout=True)
    markers = {"Prescribed": "o", "CLPR": "s"}

    for policy_type in ["Prescribed", "CLPR"]:
        g = summary[summary["policy_type"].eq(policy_type)].copy()
        if g.empty:
            continue
        ax.scatter(g[x_col], g[y_col], marker=markers[policy_type], s=28, alpha=0.30, label=policy_type, zorder=1)

    nd = summary[summary[pareto_col].astype(bool)].copy()
    if len(nd) >= 2:
        nd_line = nd.sort_values([x_col, y_col])
        ax.plot(nd_line[x_col], nd_line[y_col], linewidth=0.9, linestyle="--", alpha=0.55, zorder=2)

    if representatives is not None and not representatives.empty:
        for _, row in representatives.sort_values("representative_label").iterrows():
            policy_type = str(row["policy_type"])
            lab = str(row.get("display_configuration", row["representative_label"]))
            ax.scatter([row[x_col]],[row[y_col]],marker=markers.get(policy_type,"o"),s=120,facecolors="none",linewidths=1.8,zorder=4)
            rep_label = str(row.get("representative_label", ""))

            # Final label-placement test:
            # - CLPR labels -> lower-left with a thin leader line
            # - right-side Prescribed extremes G/H -> lower-left with a thin leader line
            # - other Prescribed labels -> unchanged
            use_lower_left = (
                policy_type == "CLPR"
                or (policy_type == "Prescribed" and rep_label in {"G", "H"})
            )

            if policy_type == "Prescribed" and rep_label == "H":
                # Right-most Prescribed label: left and slightly above so it
                # remains inside the plotting area.
                xytext = (-14, 0)
                ha = "right"
                va = "bottom"
            elif use_lower_left:
                # CLPR + Prescribed G: left/below.
                xytext = (-14, -16)
                ha = "right"
                va = "top"
            else:
                # Left-side Prescribed labels: retain previous placement.
                xytext = (6, 6)
                ha = "left"
                va = "bottom"

            # Very thin, light-gray connector for every highlighted label.
            arrowprops = dict(
                arrowstyle="-",
                linewidth=0.30,
                color="0.80",
                shrinkA=1,
                shrinkB=1,
            )

            ax.annotate(
                lab,
                xy=(row[x_col], row[y_col]),
                xytext=xytext,
                textcoords="offset points",
                fontsize=7.5,
                fontweight="normal",
                ha=ha,
                va=va,
                arrowprops=arrowprops,
                zorder=5,
            )

    ax.set_title(title, fontweight="normal")
    ax.set_xlabel(xlabel); ax.set_ylabel(ylabel); ax.grid(alpha=0.20); ax.legend(frameon=False,fontsize=8)
    outpath.parent.mkdir(parents=True,exist_ok=True)
    png=outpath.with_suffix(".png"); pdf=outpath.with_suffix(".pdf")
    fig.savefig(png,dpi=300,bbox_inches="tight"); fig.savefig(pdf,bbox_inches="tight"); plt.close(fig)
    return png,pdf


def run_ex_ante_decision_block(
    metrics: pd.DataFrame,
    outdir: Path,
    make_plots: bool = True,
):
    """
    Paper Block 4 — exploratory ex-ante decision comparison.

    Uses only existing simulation results. It does not alter or add runs.
    """
    figures_dir = (
        outdir / "figures" / "block_4_ex_ante_decision"
    )
    tables_dir = (
        outdir / "data" / "block_4_ex_ante_decision"
    )
    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    summary, raw = build_ex_ante_decision_data(metrics)

    representatives = select_representative_global_pareto(summary)

    summary.to_csv(
        tables_dir / "Ex_Ante_Configuration_Summary.csv",
        index=False,
    )
    raw.to_csv(
        tables_dir / "Ex_Ante_Target_Performance_Gap_By_Run.csv",
        index=False,
    )
    if not representatives.empty:
        representative_table = representatives[[
            "representative_label", "representative_role", "policy_type",
            "display_configuration", "configuration_id", "lambda0",
            "lambda_final", "kp", "discounted_cost_median", "E2040_median",
            "E2040_p90", "target_gap_p90",
        ]].copy().rename(columns={
            "representative_label":"Label",
            "representative_role":"Role",
            "policy_type":"Architecture",
            "display_configuration":"Configuration_label",
            "configuration_id":"Configuration",
            "lambda0":"lambda0",
            "lambda_final":"lambda_f",
            "kp":"Kp",
            "discounted_cost_median":"Median_cost",
            "E2040_median":"Median_E2040",
            "E2040_p90":"P90_E2040",
            "target_gap_p90":"P90_target_performance_gap",
        })
    else:
        representative_table = pd.DataFrame(columns=[
            "Label","Role","Architecture","Configuration_label","Configuration",
            "lambda0","lambda_f","Kp","Median_cost","Median_E2040",
            "P90_E2040","P90_target_performance_gap"
        ])
    representative_table.to_csv(
        tables_dir / "Ex_Ante_Representative_Pareto_Configurations_A_to_H.csv",
        index=False,
    )

    definition = pd.DataFrame(
        [
            {
                "item": "Policy configurations",
                "definition": (
                    "Prescribed: unique (lambda0, policy_delta_final); "
                    "CLPR: unique (lambda0, Kp)"
                ),
            },
            {
                "item": "Future set",
                "definition": (
                    "all demand futures already present in Experiment_A5, "
                    "including BASE; No Policy excluded"
                ),
            },
            {
                "item": "Target-performance gap",
                "definition": (
                    "G_i,pi = abs(E2040_i,pi - target), with target = 0; "
                    "for non-negative E2040, G_i,pi = E2040_i,pi"
                ),
            },
            {
                "item": "Cost metric",
                "definition": (
                    "discounted_total_cost_with_penalty, consistent with "
                    "Paper Blocks 2 and 3"
                ),
            },
            {
                "item": "Target-gap map non-dominated",
                "definition": (
                    "global Pareto frontier over all Prescribed + CLPR configurations; minimize median discounted cost and P90 target-performance gap"
                ),
            },
            {
                "item": "Highlighted configuration layout",
                "definition": (
                    "A,B,G,H are selected from Prescribed Pareto points and "
                    "C,D,E,F from CLPR Pareto points, guided by requested "
                    "normalized-cost positions; no simulation values are changed"
                ),
            },
        ]
    )
    definition.to_csv(
        tables_dir / "Ex_Ante_Decision_Definition.csv",
        index=False,
    )

    if make_plots and not summary.empty:
        paths2 = _plot_ex_ante_map(
            summary,
            representatives,
            x_col="discounted_cost_median",
            y_col="target_gap_p90",
            pareto_col="pareto_median_cost_vs_p90_gap",
            xlabel="Median total discounted cost (MUSD)",
            ylabel="P90 target-performance gap (Mton)",
            title="Median cost vs P90 target-performance gap",
            outpath=figures_dir / "Ex_Ante_Median_Cost_vs_P90_Target_Performance_Gap",
        )
        if paths2:
            print(f">> Paper Block 4 target-gap map: {paths2[0]} | {paths2[1]}")

    print(f">> Paper Block 4 data folder: {tables_dir}")
    print(f">> Paper Block 4 figure folder: {figures_dir}")
    return figures_dir, tables_dir

def main() -> None:
    """Generate only the figures intended for the paper.

    This lightweight execution path reuses the validated A6 calculations in
    memory, but does not write the regular A6 tables, diagnostics, exploratory
    analyses, or non-paper plots.

    Outputs are restricted to:
      Analysis_A6/figures/block_1_closed_loop_response
      Analysis_A6/figures/block_2_cost_emission_relation
      Analysis_A6/figures/block_3_policy_authority
      Analysis_A6/figures/block_4_ex_ante_decision

    The Block 1 helper may also write its traceability CSVs under
    Analysis_A6/paper/data, as in the existing paper workflow.
    """
    args, _unknown = build_cli().parse_known_args()
    cwd = Path.cwd().resolve()

    # --------------------------------------------------------------
    # Locate Experiment_A5 robustly, preserving the behavior of A6.
    # --------------------------------------------------------------
    experiment_arg = Path(args.experiment_dir)
    if experiment_arg.is_absolute():
        experiment_dir = experiment_arg.resolve()
    else:
        direct_candidate = (cwd / experiment_arg).resolve()
        if (direct_candidate / "Experiment_Index.csv").exists():
            experiment_dir = direct_candidate
        else:
            experiment_dir = None
            for base in [cwd, *cwd.parents]:
                candidate = (base / experiment_arg).resolve()
                if (candidate / "Experiment_Index.csv").exists():
                    experiment_dir = candidate
                    break
            if experiment_dir is None:
                experiment_dir = direct_candidate

    outdir = (
        Path(args.outdir).resolve()
        if args.outdir
        else experiment_dir.parent / "Analysis_A6"
    )

    print(">> PAPER BLOCKS 1-4")
    print(f">> Experiment folder: {experiment_dir}")
    print(f">> Paper output root: {outdir / 'paper'}")

    # --------------------------------------------------------------
    # Minimum calculations required by the paper figures.
    # Nothing from the standard A6 workflow is exported here.
    # --------------------------------------------------------------
    index_df, results_df = load_experiment(experiment_dir)
    validation = build_validation_report(experiment_dir, index_df, results_df)

    discount_rate, discount_rate_source = discover_discount_rate(
        experiment_dir,
        index_df,
        override=args.discount_rate,
    )
    if discount_rate is None:
        print(">> WARNING: DiscountRate could not be discovered.")
        print(">> Supply --discount-rate if discounted-cost figures cannot be built.")
    else:
        print(
            f">> DiscountRate: {discount_rate:.6g} "
            f"(source: {discount_rate_source})"
        )

    metrics = build_run_metrics(
        experiment_dir,
        index_df,
        results_df,
        validation,
        args.start_year,
        args.target_year,
        discount_rate,
        discount_rate_source,
    )
    metrics = add_target_tracking_metrics(
        metrics,
        target_tolerance=args.target_tolerance,
    )

    # --------------------------------------------------------------
    # PAPER — BLOCK 1: policy response sequence.
    # --------------------------------------------------------------
    reveal_vals = (
        pd.to_numeric(index_df["reveal_year"], errors="coerce").dropna()
        if "reveal_year" in index_df.columns
        else pd.Series(dtype=float)
    )
    paper_reveal_year = int(reveal_vals.iloc[0]) if len(reveal_vals) else 2020

    paper_block1 = generate_paper_block1(
        experiment_dir,
        index_df,
        results_df,
        metrics,
        outdir,
        args.start_year,
        args.target_year,
        reveal_year=paper_reveal_year,
        demand_unit=args.demand_unit,
    )
    print(f">> Paper Block 1 folder: {paper_block1[0]}")

    # --------------------------------------------------------------
    # PAPER — BLOCK 2: cost–emission relation.
    # Two separate 2x2 figures: Linear and Step.
    # No Policy excluded by the plotting helper.
    # Bottom row uses total discounted cost including emissions penalty.
    # --------------------------------------------------------------
    linear_surface_data = build_policy_surface_data(
        metrics,
        family="linear",
        max_deviation=args.future_max_deviation,
    )
    step_surface_data = build_policy_surface_data(
        metrics,
        family="step",
        max_deviation=args.future_max_deviation,
    )

    cost_surface_tables = {}
    for family in ["linear", "step"]:
        cost_surface_tables[family] = build_cost_surface_data(
            metrics,
            value_column="discounted_total_cost_with_penalty",
            value_label="discounted_total_cost_with_penalty",
            family=family,
            max_deviation=args.future_max_deviation,
        )

    emissions_values = pd.to_numeric(
        pd.concat(
            [
                linear_surface_data["terminal_emissions_median"],
                step_surface_data["terminal_emissions_median"],
            ],
            ignore_index=True,
        ),
        errors="coerce",
    ).dropna()
    global_vmax = float(emissions_values.max()) if not emissions_values.empty else 1.0

    total_cost_values = pd.concat(
        [
            pd.to_numeric(
                cost_surface_tables["linear"][
                    "discounted_total_cost_with_penalty_median"
                ],
                errors="coerce",
            ),
            pd.to_numeric(
                cost_surface_tables["step"][
                    "discounted_total_cost_with_penalty_median"
                ],
                errors="coerce",
            ),
        ],
        ignore_index=True,
    ).dropna()

    if total_cost_values.empty:
        print(">> WARNING: No valid total discounted cost values; Block 2 skipped.")
    else:
        paper_cost_min = float(total_cost_values.min())
        paper_cost_max = float(total_cost_values.max())
        paper_block2_dir = (
            outdir
            / "figures"
            / "block_2_cost_emission_relation"
        )
        paper_block2_data_dir = (
            outdir
            / "data"
            / "block_2_cost_emission_relation"
        )
        paper_block2_data_dir.mkdir(parents=True, exist_ok=True)

        # Traceability data used by the Block 2 figures.
        for family in ["linear", "step"]:
            cost_surface_tables[family].to_csv(
                paper_block2_data_dir / f"Block2_{family}_total_cost_with_penalty_surface.csv",
                index=False,
            )

        for family, emissions_data in [
            ("linear", linear_surface_data),
            ("step", step_surface_data),
        ]:
            emissions_data.to_csv(
                paper_block2_data_dir / f"Block2_{family}_E2040_surface.csv",
                index=False,
            )
            paper_paths = plot_paper_cost_emission_relation_2x2(
                emissions_surface_data=emissions_data,
                cost_surface_data=cost_surface_tables[family],
                family=family,
                outdir=paper_block2_dir,
                emissions_vmax=global_vmax,
                cost_vmin=paper_cost_min,
                cost_vmax=paper_cost_max,
            )
            print(
                f">> Paper Block 2 {family.title()}: "
                f"{paper_paths[0]} | {paper_paths[1]}"
            )

    # --------------------------------------------------------------
    # PAPER — BLOCK 3: exploratory Policy Authority.
    # No thresholds or regime labels.
    # --------------------------------------------------------------
    policy_authority_dirs = run_policy_authority_test(
        metrics,
        outdir,
        max_deviation=args.future_max_deviation,
        make_plots=not args.no_plots,
    )

    # --------------------------------------------------------------
    # PAPER — BLOCK 4: exploratory ex-ante decision analysis.
    # Existing runs only; no new simulations.
    # --------------------------------------------------------------
    ex_ante_dirs = run_ex_ante_decision_block(
        metrics,
        outdir,
        make_plots=not args.no_plots,
    )

    print(">> Done. Paper Blocks 1-4 executed.")


if __name__ == "__main__":
    main()
