3. Linear Programming Structure
=======================================

3.1 Modelling Approach
+++++++++++++++++++++++++++

scope

3.2 Mathematical Formulation
+++++++++++++++++++++++++++

- Decision variables, parameter..

3.3 Objective function
+++++++++++++++++++++++++++

\begin{align}
\min \; Z = & 
\sum_{y \in Y} \sum_{r \in R} \sum_{t \in T} 
\frac{ \text{TotalCost}_{y,r,t} }{ (1 + \text{DiscountRate})^{\,y - \min(Y)}} \nonumber \\
&+ \sum_{y \in Y} \sum_{r \in R} \sum_{s \in S} 
\frac{ \text{TotalStorageCost}_{y,r,s} }{ (1 + \text{DiscountRate})^{\,y - \min(Y)}} \nonumber \\
&+ \sum_{y \in Y} \sum_{r \in R} \sum_{rr \in R} \sum_{h \in H} \sum_{f \in F} 
\frac{ \text{TradeCostFactor}_{f} \cdot \text{TradeDistance}_{r,rr} \cdot \text{Export}_{y,rr,r,h,f} \cdot \text{YearlyDifferenceMultiplier}_{y} }
{ (1 + \text{DiscountRate})^{\,y - \min(Y)}} \nonumber \\
&- \sum_{y \in Y} \sum_{r \in R} \sum_{t \in T} 
\frac{ \text{SalvageValue}_{y,r,t} }{ (1 + \text{DiscountRate})^{\,y - \min(Y)}} \nonumber \\
&- \sum_{y \in Y} \sum_{r \in R} \sum_{s \in S} 
\frac{ \text{StorageSalvageValue}_{y,r,s} }{ (1 + \text{DiscountRate})^{\,y - \min(Y)}}
\end{align}


3.4 Constraints
+++++++++++++++++++++++++++

Generation must meet demand

\begin{equation}
\sum_{t \in T} FuelProductionByTechnology_{y,r,h,t,f}
+ \sum_{s \in S} StorageDischarge_{y,r,s,h,f}
+ \sum_{rr \in R} Import_{y,r,rr,h,f}
=
Demand_{y,r,f} \cdot DemandProfile_{r,h,f}
+ \sum_{t \in T} FuelUseByTechnology_{y,r,h,t,f}
+ Curtailment_{y,r,h,f}
+ \sum_{s \in S} StorageCharge_{y,r,s,h,f}
+ \sum_{rr \in R} Export_{y,r,rr,h,f}
\quad \forall y,r,h,f
\end{equation}


Calculate the total cost

\begin{equation}
\left( \sum_{f \in F} \sum_{h \in H} FuelProductionByTechnology_{y,r,h,t,f} \right) \cdot VariableCost_{y,t} \cdot YearlyDifferenceMultiplier_{y}
+ NewCapacity_{y,r,t} \cdot InvestmentCost_{y,t}
= TotalCost_{y,r,t}
\quad \forall y,r,t
\end{equation}


\begin{equation}
SalvageValue_{y,r,t} =
\begin{cases}
0, & \text{si } y + OperationalLife_t - 1 \leq \max(Y) \\[8pt]
NewCapacity_{y,r,t} \cdot InvestmentCost_{y,t} \cdot 
\left(1 - \dfrac{\max(Y) - y + 1}{OperationalLife_t}\right),
& \text{si } y + OperationalLife_t - 1 > \max(Y)
\end{cases}
\quad \forall y,r,t
\end{equation}


Dispatchable production limited by installed capacity

\begin{equation}
FuelProductionByTechnology_{y,r,h,t,f}
\leq OutputRatio_{t,f} \cdot AccumulatedCapacity_{y,r,t} \cdot CapacityFactor_{r,h,t}
\quad \forall t \in T^{disp}, y,r,h,f
\end{equation}


Variable renewables (must equal max output)

\begin{equation}
FuelProductionByTechnology_{y,r,h,t,f}
= OutputRatio_{t,f} \cdot AccumulatedCapacity_{y,r,t} \cdot CapacityFactor_{r,h,t}
\quad \forall t \in T^{res}, y,r,h,f
\end{equation}

Define use by production

\begin{equation}
FuelUseByTechnology_{y,r,h,t,f}
= InputRatio_{t,f} \cdot \sum_{ff \in F} FuelProductionByTechnology_{y,r,h,t,ff}
\quad \forall y,r,h,t,f
\end{equation}


Define the emissions
\begin{equation}
\sum_{f \in F} \sum_{h \in H} FuelProductionByTechnology_{y,r,h,t,f} \cdot EmissionRatio_t
= AnnualTechnologyEmissions_{y,r,t}
\quad \forall y,r,t
\end{equation}


Annual emission limit
\begin{equation}
\sum_{t \in T} \sum_{r \in R} AnnualTechnologyEmissions_{y,r,t}
\leq AnnualEmissionLimit_y
\quad \forall y
\end{equation}


Installed capacity limited by max capacity
\begin{equation}
AccumulatedCapacity_{y,r,t} \leq MaxCapacity_{y,r,t}
\quad \forall y,r,t
\end{equation}

Capacity accounting

\begin{equation}
\sum_{\substack{yy \in Y \\ yy \leq y, \; yy + OperationalLife_t > y}} NewCapacity_{yy,r,t}
+ ResidualCapacity_{y,r,t}
= AccumulatedCapacity_{y,r,t}
\quad \forall y,r,t
\end{equation}



Trade equations

\begin{equation}
Import_{y,r,rr,h,f}
= Export_{y,rr,r,h,f} \cdot (1 - TradeLossFactor_f \cdot TradeDistance_{r,rr})
\quad \forall y,r,rr,h,f
\end{equation}

\begin{equation}
Import_{y,r,rr,h,f}
\leq MaxTradeCapacity_{y,r,rr,f}
\quad \forall y,r,rr,h,f
\end{equation}


Total emission limit (model horizon)

\begin{equation}
\sum_{y \in Y} \sum_{r \in R} \sum_{t \in T} \sum_{f \in F} \sum_{h \in H}
FuelProductionByTechnology_{y,r,h,t,f} \cdot EmissionRatio_t \cdot YearlyDifferenceMultiplier_y
\leq ModelPeriodEmissionLimit
\end{equation}

Storage constraints

\begin{align}
&\text{(a) Charge limit:} &&
StorageCharge_{y,r,s,h,f} \leq \frac{ AccumulatedStorageEnergyCapacity_{y,r,s,f} }{ E2PRatio_s }
\quad \forall y,r,s,h,f \label{eq:storage_charge} \\[6pt]
%
&\text{(b) Discharge limit:} &&
StorageDischarge_{y,r,s,h,f} \leq \frac{ AccumulatedStorageEnergyCapacity_{y,r,s,f} }{ E2PRatio_s }
\quad \forall y,r,s,h,f \label{eq:storage_discharge} \\[6pt]
%
&\text{(c) Energy balance (h>1):} &&
StorageLevel_{y,r,s,h,f} =
StorageLevel_{y,r,s,h-1,f} \cdot StorageLosses_{s,f}
+ StorageCharge_{y,r,s,h,f}\cdot StorageChargeEfficiency_{s,f}
- \frac{ StorageDischarge_{y,r,s,h,f} }{ StorageDischargeEfficiency_{s,f}}
\quad \forall y,r,s,h,f>1 \label{eq:storage_balance} \\[6pt]
%
&\text{(d) Initial level (h=1):} &&
StorageLevel_{y,r,s,1,f} =
0.5 \cdot AccumulatedStorageEnergyCapacity_{y,r,s,f}\cdot StorageLosses_{s,f}
+ StorageCharge_{y,r,s,1,f}\cdot StorageChargeEfficiency_{s,f}
- \frac{ StorageDischarge_{y,r,s,1,f} }{ StorageDischargeEfficiency_{s,f}}
\quad \forall y,r,s,f \label{eq:storage_start} \\[6pt]
%
&\text{(e) Max storage level:} &&
StorageLevel_{y,r,s,h,f} \leq AccumulatedStorageEnergyCapacity_{y,r,s,f}
\quad \forall y,r,s,h,f \label{eq:storage_max} \\[6pt]
%
&\text{(f) Annual balance:} &&
StorageLevel_{y,r,s,n\_hour,f} = 0.5 \cdot AccumulatedStorageEnergyCapacity_{y,r,s,f}
\quad \forall y,r,s,f \label{eq:storage_annual} \\[6pt]
%
&\text{(g) Cost accounting:} &&
TotalStorageCost_{y,r,s} = \sum_{f \in F}
NewStorageEnergyCapacity_{y,r,s,f} \cdot InvestmentCostStorage_{y,s}
\quad \forall y,r,s \label{eq:storage_cost} \\[6pt]
%
&\text{(h) Capacity limit:} &&
\sum_{f \in F} AccumulatedStorageEnergyCapacity_{y,r,s,f}
\leq MaxStorageCapacity_{y,r,s}
\quad \forall y,r,s \label{eq:storage_capacity_limit} \\[6pt]
%
&\text{(i) Capacity accounting:} &&
\sum_{\substack{yy \in Y \\ yy \leq y}} NewStorageEnergyCapacity_{yy,r,s,f}
= AccumulatedStorageEnergyCapacity_{y,r,s,f}
\quad \forall y,r,s,f \label{eq:storage_accounting}
\end{align}

\begin{equation}
StorageSalvageValue_{y,r,s} =
\begin{cases}
0, & \text{si } y + StorageOperationalLife_s - 1 \leq \max(Y) \\[8pt]
InvestmentCostStorage_{y,s} \cdot 
\left(1 - \dfrac{\max(Y) - y + 1}{StorageOperationalLife_s}\right),
& \text{si } y + StorageOperationalLife_s - 1 > \max(Y)
\end{cases}
\quad \forall y,r,s
\end{equation}


