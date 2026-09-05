
from __future__ import annotations
import argparse, csv
from pathlib import Path
from typing import Dict, List
from standalone_A1_base import run_glpsol
from standalone_A2_sequential import (
    comment_param_blocks, detect_years_from_data, load_newcapacity,
    split_years_into_n_blocks, validate_min_locks, write_active_block_minmax
)
from standalone_A3_controller import (
    compute_error, proportional_update, read_emission_at_year,
    read_initial_policy_value, update_future_policy_curve, write_active_policy
)

REPORT_FILE="CLPR_Run_Report.csv"

def build_cli():
    ap=argparse.ArgumentParser(description="CLPR_ESOM A.4 integrated stand-alone workflow")
    ap.add_argument("--model",default="osemosys_model.txt")
    ap.add_argument("--data",default="atlantis_data.txt")
    ap.add_argument("--revealed-data",default=None)
    ap.add_argument("--reveal-year",type=int,default=None)
    ap.add_argument("--policy",default="policy.txt")
    ap.add_argument("--workdir",default="CLPR_standalone_output")
    ap.add_argument("--blocks",type=int,default=5)
    ap.add_argument("--kp",type=float,default=250.0)
    ap.add_argument("--emission",default="CO2")
    ap.add_argument("--region",default="Atlantis_00A")
    ap.add_argument("--target",type=float,default=0.0)
    ap.add_argument("--lambda0",type=float,default=None)
    ap.add_argument("--lambda-min",type=float,default=0.0)
    ap.add_argument("--lambda-max",type=float,default=500.0)
    ap.add_argument("--tol",type=float,default=1e-6)
    ap.add_argument("--debug",action="store_true")
    return ap

def write_report(path: Path, rows: List[Dict[str,object]]):
    fields=["block","block_start_year","block_end_year","committed_through_year",
            "information_state","active_data","performance_year",
            "performance","target","error","lambda_applied",
            "lambda_next","n_locks","lock_violations","max_lock_violation",
            "objective","total_newcapacity","solver_status"]
    with Path(path).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

def main():
    args,_=build_cli().parse_known_args()
    here=Path(".").resolve()
    model=(here/args.model).resolve()
    data=(here/args.data).resolve()
    revealed_data=(here/args.revealed_data).resolve() if args.revealed_data else None
    policy_input=(here/args.policy).resolve()
    workdir=Path(args.workdir)
    if not workdir.is_absolute(): workdir=(here/workdir).resolve()
    workdir.mkdir(parents=True,exist_ok=True); (workdir/"res").mkdir(parents=True,exist_ok=True)

    if not model.exists() or not data.exists():
        raise FileNotFoundError("Missing model or initial data.")

    if revealed_data is not None and not revealed_data.exists():
        raise FileNotFoundError(f"Revealed data not found: {revealed_data}")

    if (revealed_data is None) != (args.reveal_year is None):
        raise ValueError(
            "--revealed-data and --reveal-year must be provided together."
        )

    if args.lambda0 is None and not policy_input.exists():
        raise FileNotFoundError("Provide policy.txt or --lambda0.")

    y0,yN=detect_years_from_data(data)
    years=list(range(y0,yN+1))
    blocks=split_years_into_n_blocks(years,args.blocks)

    if revealed_data is not None:
        ry0,ryN=detect_years_from_data(revealed_data)
        if (ry0,ryN)!=(y0,yN):
            raise ValueError("Initial and revealed data must use the same horizon.")

        valid_reveal_years=[bstart for bstart,_ in blocks]
        if args.reveal_year not in valid_reveal_years:
            raise ValueError(
                f"reveal_year={args.reveal_year} must match a block start year: "
                f"{valid_reveal_years}"
            )

    lambda0=float(args.lambda0) if args.lambda0 is not None else read_initial_policy_value(policy_input,args.emission)
    if lambda0 is None: raise ValueError("Could not determine lambda0.")

    def prepare_data_state(source: Path, tag: str):
        policy_data=comment_param_blocks(
            source,workdir/f"data_policy_{tag}.txt",
            ["EmissionsPenalty"]
        )
        block_data=comment_param_blocks(
            policy_data,workdir/f"data_clpr_blocks_{tag}.txt",
            [
                "TotalAnnualMinCapacityInvestment",
                "TotalAnnualMaxCapacityInvestment"
            ]
        )
        return policy_data,block_data

    data_policy_initial,data_clpr_initial=prepare_data_state(data,"initial")

    if revealed_data is not None:
        data_policy_revealed,data_clpr_revealed=prepare_data_state(
            revealed_data,"revealed"
        )
    else:
        data_policy_revealed=data_policy_initial
        data_clpr_revealed=data_clpr_initial

    curve: Dict[int,float]={y:lambda0 for y in years}
    policy_file=workdir/"policy_current.txt"
    block_file=workdir/"Block_current.txt"
    write_active_policy(policy_file,args.region,args.emission,years,curve)

    # SETUP always uses the initial information state.
    setup_obj,setup_status=run_glpsol(
        model,[data_policy_initial,policy_file],workdir,"A4_SETUP",args.debug
    )
    if setup_status != "OPTIMAL":
        raise RuntimeError(
            f"A4 SETUP failed with solver_status={setup_status}. "
            "Sequential CLPR run stopped before reading solver outputs."
        )

    prev_nc=load_newcapacity(workdir)
    current_lambda=lambda0
    report=[]

    info_msg="information=initial-only" if revealed_data is None else f"reveal_year={args.reveal_year}"
    print(
        f">> Setup | status={setup_status} | objective={setup_obj} "
        f"| lambda0={lambda0} | {info_msg}"
    )

    for j,(bstart,bend) in enumerate(blocks,start=1):
        revealed_now=(
            revealed_data is not None
            and bstart >= args.reveal_year
        )

        if revealed_now:
            active_source_data=revealed_data
            active_block_data=data_clpr_revealed
            information_state="revealed"
        else:
            active_source_data=data
            active_block_data=data_clpr_initial
            information_state="initial"

        # Sequential commitment logic:
        # B1 commits the first block using the SETUP solution.
        # From B2 onward, only decisions through the end of the
        # previous block are locked before solving the current block.
        if j == 1:
            committed_end = bend
        else:
            committed_end = blocks[j-2][1]

        committed=list(range(blocks[0][0],committed_end+1))

        block_file,nlocks=write_active_block_minmax(
            committed,
            prev_nc,
            active_source_data,
            workdir,
            block_file.name
        )

        obj,status=run_glpsol(
            model,[active_block_data,policy_file,block_file],
            workdir,f"A4_B{j}",args.debug
        )

        if status != "OPTIMAL":
            raise RuntimeError(
                f"A4 block {j} ({bstart}-{bend}) failed with "
                f"solver_status={status}. Sequential CLPR run stopped "
                "before reading or reusing solver outputs."
            )

        cur_nc=load_newcapacity(workdir)
        nviol,maxviol=validate_min_locks(prev_nc,cur_nc,committed,args.tol)

        # Long-term policy performance:
        # every sequential optimization solves the complete horizon,
        # so performance is always evaluated at the final model year.
        performance_year=yN
        performance=read_emission_at_year(
            workdir,
            args.emission,
            performance_year,
            args.region
        )
        error=compute_error(args.target,performance)

        if j<len(blocks):
            next_lambda=proportional_update(
                current_lambda,error,args.kp,args.lambda_min,args.lambda_max
            )
            curve=update_future_policy_curve(curve,years,bend,next_lambda)
            write_active_policy(policy_file,args.region,args.emission,years,curve)
        else:
            next_lambda=current_lambda

        report.append({
            "block":j,"block_start_year":bstart,"block_end_year":bend,
            "committed_through_year":committed_end,
            "information_state":information_state,
            "active_data":active_source_data.name,
            "performance_year":performance_year,
            "performance":performance,"target":args.target,"error":error,
            "lambda_applied":current_lambda,"lambda_next":next_lambda,
            "n_locks":nlocks,"lock_violations":nviol,
            "max_lock_violation":maxviol,
            "objective":obj if obj is not None else "",
            "total_newcapacity":sum(v for _,_,_,v in cur_nc),
            "solver_status":status
        })

        print(
            f">> Block {j}/{len(blocks)} | {bstart}-{bend} "
            f"| info={information_state} "
            f"| committed<= {committed_end} "
            f"| lambda={current_lambda:.6g} "
            f"| performance[{performance_year}]={performance:.6g} "
            f"| error={error:.6g} | next={next_lambda:.6g} "
            f"| locks={nlocks} | violations={nviol}"
        )

        prev_nc=cur_nc
        current_lambda=next_lambda

    report_path=workdir/REPORT_FILE
    write_report(report_path,report)
    print(f">> CLPR run completed. Final report: {report_path}")

if __name__=="__main__":
    main()