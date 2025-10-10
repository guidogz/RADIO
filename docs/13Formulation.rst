Supplement A - Mathematical Formulation
=======================================

3.1 Modelling Approach
+++++++++++++++++++++++++++

scope

3.2 Mathematical Formulation
+++++++++++++++++++++++++++

- Decision variables, parameter..

3.3 Objective function
+++++++++++++++++++++++++++

The optimization problem minimizes the **total discounted system cost**,
including generation, storage, and trade costs, while accounting for salvage values:

.. math::

    \min \; Z = 
    \sum_{y \in \text{year}} \sum_{r \in \text{regions}} 
    \left[
        \sum_{t \in \text{technologies}} 
        \frac{\text{TotalCost}_{y,r,t}}{(1+\text{DiscountRate})^{(y - \min(\text{year}))}}
        +
        \sum_{s \in \text{storages}} 
        \frac{\text{TotalStorageCost}_{y,r,s}}{(1+\text{DiscountRate})^{(y - \min(\text{year}))}}
    \right]
    + 
    \sum_{y \in \text{year}} 
    \sum_{r,rr \in \text{regions}} 
    \sum_{h \in \text{hour}} 
    \sum_{f \in \text{fuels}} 
    \frac{
        \text{TradeCostFactor}_{f}
        \cdot \text{TradeDistance}_{r,rr}
        \cdot \text{Export}_{y,rr,r,h,f}
        \cdot \text{YearlyDifferenceMultiplier}_{y}
    }{(1+\text{DiscountRate})^{(y - \min(\text{year}))}}
    -
    \sum_{y \in \text{year}} \sum_{r \in \text{regions}} 
    \left[
        \sum_{t \in \text{technologies}} 
        \frac{\text{SalvageValue}_{y,r,t}}{(1+\text{DiscountRate})^{(y - \min(\text{year}))}}
        +
        \sum_{s \in \text{storages}} 
        \frac{\text{StorageSalvageValue}_{y,r,s}}{(1+\text{DiscountRate})^{(y - \min(\text{year}))}}
    \right]

where:

- :math:`y` = planning year  
- :math:`r, rr` = regions  
- :math:`t` = generation technologies  
- :math:`s` = storage technologies  
- :math:`f` = fuels  
- :math:`h` = time slices or hours  
- :math:`\text{DiscountRate}` = annual discount rate  

This formulation ensures that all future costs are discounted and salvage values are subtracted, yielding the **net present system cost** to be minimized.


3.4 Constraints
+++++++++++++++++++++++++++

Generation must meet demand

.. math::

   \sum_{t \in T} FuelProductionByTechnology_{y,r,h,t,f}
   + \sum_{s \in S} StorageDischarge_{y,r,s,h,f}
   + \sum_{rr \in R} Import_{y,r,rr,h,f}

   =
   Demand_{y,r,f} \cdot DemandProfile_{r,h,f}
   + \sum_{t \in T} FuelUseByTechnology_{y,r,h,t,f}
   + Curtailment_{y,r,h,f}
   + \sum_{s \in S} StorageCharge_{y,r,s,h,f}
   + \sum_{rr \in R} Export_{y,r,rr,h,f}


Calculate the total cost

.. math::

   \left( \sum_{f \in F} \sum_{h \in H} FuelProductionByTechnology_{y,r,h,t,f} \right)
   \cdot VariableCost_{y,t} \cdot YearlyDifferenceMultiplier_{y}
   + NewCapacity_{y,r,t} \cdot InvestmentCost_{y,t}
   =
   TotalCost_{y,r,t}


Salvage value (zero and positive cases)

.. math::

   SalvageValue_{y,r,t} =
   \begin{cases}
      0, & \text{si } y + OperationalLife_t - 1 \leq \max(Y) \\[6pt]
      NewCapacity_{y,r,t} \cdot InvestmentCost_{y,t}
      \cdot \left(1 - \dfrac{\max(Y) - y + 1}{OperationalLife_t}\right),
      & \text{si } y + OperationalLife_t - 1 > \max(Y)
   \end{cases}


Dispatchable production limited by installed capacity

.. math::

   FuelProductionByTechnology_{y,r,h,t,f}
   \leq OutputRatio_{t,f} \cdot AccumulatedCapacity_{y,r,t} \cdot CapacityFactor_{r,h,t}


Variable renewables (must equal maximum output)

.. math::

   FuelProductionByTechnology_{y,r,h,t,f}
   = OutputRatio_{t,f} \cdot AccumulatedCapacity_{y,r,t} \cdot CapacityFactor_{r,h,t}


Use function

.. math::

   FuelUseByTechnology_{y,r,h,t,f}
   = InputRatio_{t,f} \cdot \sum_{ff \in F} FuelProductionByTechnology_{y,r,h,t,ff}


Technology emissions

.. math::

   \sum_{f \in F} \sum_{h \in H} FuelProductionByTechnology_{y,r,h,t,f} \cdot EmissionRatio_{t}
   = AnnualTechnologyEmissions_{y,r,t}


Annual emissions limit

.. math::

   \sum_{t \in T} \sum_{r \in R} AnnualTechnologyEmissions_{y,r,t}
   \leq AnnualEmissionLimit_{y}


Max installed capacity

.. math::

   AccumulatedCapacity_{y,r,t} \leq MaxCapacity_{y,r,t}


Capacity accounting

.. math::

   \sum_{\substack{yy \in Y \\ yy \leq y, \; yy + OperationalLife_t > y}} NewCapacity_{yy,r,t}
   + ResidualCapacity_{y,r,t}
   = AccumulatedCapacity_{y,r,t}


Storage constraints

(a) Charge limit

.. math::

   StorageCharge_{y,r,s,h,f} \leq \frac{AccumulatedStorageEnergyCapacity_{y,r,s,f}}{E2PRatio_s}

(b) Discharge limit

.. math::

   StorageDischarge_{y,r,s,h,f} \leq \frac{AccumulatedStorageEnergyCapacity_{y,r,s,f}}{E2PRatio_s}


(c) Storage balance (h>1)

.. math::

   StorageLevel_{y,r,s,h,f}
   =
   StorageLevel_{y,r,s,h-1,f} \cdot StorageLosses_{s,f}
   + StorageCharge_{y,r,s,h,f} \cdot StorageChargeEfficiency_{s,f}
   - \frac{StorageDischarge_{y,r,s,h,f}}{StorageDischargeEfficiency_{s,f}}

(d) Storage start (h=1)

.. math::

   StorageLevel_{y,r,s,1,f}
   =
   0.5 \cdot AccumulatedStorageEnergyCapacity_{y,r,s,f} \cdot StorageLosses_{s,f}
   + StorageCharge_{y,r,s,1,f} \cdot StorageChargeEfficiency_{s,f}
   - \frac{StorageDischarge_{y,r,s,1,f}}{StorageDischargeEfficiency_{s,f}}

e) Max storage level

.. math::

   StorageLevel_{y,r,s,h,f} \leq AccumulatedStorageEnergyCapacity_{y,r,s,f}

(f) Annual balance

.. math::

   StorageLevel_{y,r,s,n\_hour,f} = 0.5 \cdot AccumulatedStorageEnergyCapacity_{y,r,s,f}


(g) Storage cost

.. math::

   TotalStorageCost_{y,r,s} = \sum_{f \in F} NewStorageEnergyCapacity_{y,r,s,f} \cdot InvestmentCostStorage_{y,s}


(h) Max storage capacity limit

.. math::

   \sum_{f \in F} AccumulatedStorageEnergyCapacity_{y,r,s,f} \leq MaxStorageCapacity_{y,r,s}

(i) Storage capacity accounting

.. math::

   \sum_{\substack{yy \in Y \\ yy \leq y}} NewStorageEnergyCapacity_{yy,r,s,f}
   = AccumulatedStorageEnergyCapacity_{y,r,s,f}


13. Storage salvage value

.. math::

   StorageSalvageValue_{y,r,s} =
   \begin{cases}
      0, & \text{si } y + StorageOperationalLife_s - 1 \leq \max(Y) \\[6pt]
      InvestmentCostStorage_{y,s} \cdot
      \left(1 - \dfrac{\max(Y) - y + 1}{StorageOperationalLife_s}\right),
      & \text{si } y + StorageOperationalLife_s - 1 > \max(Y)
   \end{cases}


14. Trade constraints

(a) Import-export balance

.. math::

   Import_{y,r,rr,h,f}
   =
   Export_{y,rr,r,h,f} \cdot (1 - TradeLossFactor_f \cdot TradeDistance_{r,rr})

(b) Max import capacity

.. math::

   Import_{y,r,rr,h,f} \leq MaxTradeCapacity_{y,r,rr,f}


15. Total emission limit (model horizon)

.. math::

   \sum_{y \in Y} \sum_{r \in R} \sum_{t \in T} \sum_{f \in F} \sum_{h \in H}
   FuelProductionByTechnology_{y,r,h,t,f} \cdot EmissionRatio_t \cdot YearlyDifferenceMultiplier_y
   \leq ModelPeriodEmissionLimit



