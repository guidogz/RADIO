# CLPR-ESOM

## Closed-Loop Policy Representation in Energy System Optimization Models

This repository contains the code used for the proof-of-concept implementation presented in:

**Closed-Loop Policy Representation in Energy System Optimization Models: A Proof of Concept in OSeMOSYS**

The repository implements a sequential modeling structure in which an Energy System Optimization Model (ESOM) is repeatedly solved while previously committed system decisions are retained and new information is introduced. The Closed-Loop Policy Representation (CLPR) extends this sequential structure by linking projected system performance to subsequent adjustments of a policy instrument.

The proof of concept uses **OSeMOSYS** and the standard **ATLANTIS** test system. Carbon pricing is used as the illustrative policy instrument, with a proportional feedback rule linking projected CO2 emissions to subsequent carbon-price adjustments.

## Repository structure

The implementation is organized as a sequence of standalone scripts. Each script introduces an additional component of the modeling framework.

```text
CLPR-ESOM/
│
├── atlantis_data
├── osemosys_model
├── policy
│
├── standalone_A1_base.py
├── standalone_A2_sequential.py
├── standalone_A3_controller.py
├── standalone_A4_CLPR.py
├── standalone_A5_experiment.py
└── standalone_A6_visualization.py
```

### Input files

**`atlantis_data`**  
Contains the input data for the ATLANTIS test energy system.

**`osemosys_model`**  
Contains the OSeMOSYS mathematical model used in the optimization runs.

**`policy`**  
Contains the policy-related input data used to define the carbon-pricing configurations.

### Standalone scripts

**`standalone_A1_base.py` — Base model**

Runs the original ATLANTIS OSeMOSYS model and provides the reference implementation used to verify the model, solver, and data configuration.

**`standalone_A2_sequential.py` — Sequential optimization**

Introduces the sequential optimization structure. The ESOM is solved repeatedly over the full planning horizon while capacity investments associated with committed temporal blocks are transferred to subsequent optimization stages. Future decisions remain subject to re-optimization.

**`standalone_A3_controller.py` — Policy-adjustment mechanism**

Introduces the proportional policy-adjustment mechanism used in the proof of concept. This module provides the feedback logic required to update the policy instrument according to deviations between projected system performance and the policy target.

**`standalone_A4_CLPR.py` — Closed-Loop Policy Representation**

Integrates the sequential ESOM structure and the policy-adjustment mechanism. Projected emissions are evaluated against the policy target and used to update the carbon price for the subsequent optimization stage, closing the policy-adjustment loop.

**`standalone_A5_experiment.py` — Exploratory analysis**

Runs the complete set of futures and policy configurations used in the paper. The analysis compares prescribed and closed-loop carbon-pricing representations across alternative demand futures and policy configurations.

**`standalone_A6_visualization.py` — Results and visualization**

Processes the outputs of the exploratory analysis and generates the data and figures used to characterize policy trajectories, environmental outcomes, economic consequences, policy-dependent outcome variation, and ex-ante cost–target-performance trade-offs.

## Conceptual structure

CLPR separates two operations that occur between successive ESOM optimizations:

1. **Model update:** previously committed system decisions are retained and changes in exogenous conditions are introduced.
2. **Policy update:** projected system performance is evaluated against a policy objective and used to determine the policy instrument for the subsequent optimization.

The general policy update can be expressed as

\[
\lambda_{j+1}=F(\lambda_j,e_j)
\]

where \(\lambda_j\) is the policy instrument at sequential stage \(j\), \(e_j\) is the deviation from the policy objective, and \(F(\cdot)\) represents the policy-adjustment rule.

For the proof of concept, \(F(\cdot)\) is implemented using proportional feedback and the policy instrument is a carbon price.

## Requirements

The implementation requires:

- Python 3
- OSeMOSYS
- GLPK / GLPSOL

Additional Python package requirements can be identified from the imports in the standalone scripts.

## Running the implementation

The scripts are organized according to the development and validation sequence of the proof of concept:

```text
A1 → A2 → A3 → A4 → A5 → A6
```

For reproducing the complete exploratory analysis, the main execution script is:

```bash
python standalone_A5_experiment.py
```

The resulting outputs can then be processed using:

```bash
python standalone_A6_visualization.py
```

The preceding scripts are retained to make the construction and validation of the CLPR implementation transparent and reproducible.

## Citation

If you use this repository, please cite:

> Godínez-Zamora, G., et al.  
> *Closed-Loop Policy Representation in Energy System Optimization Models: A Proof of Concept in OSeMOSYS.*  
> Manuscript under review.

Citation information will be updated upon publication.

## License

License information will be added to the repository.