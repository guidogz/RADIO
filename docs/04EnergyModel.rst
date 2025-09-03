4. Modelling the Power Sector
=======================================


4.1 Modelling approach
+++++++++


4.2 Model structure
+++++++++

(i.e. temporal space, geographic space, elements of the system, etc.)

Technologies, fuels, emissions  


.. figure:: Figures/CR_Regions.png
   :align:   center
   :width:   600 px
   
   *Figure 4.1: Historical and Forecasting electricity consumption by sector in Costa Rica* 


4.3 Electricity Demand 
+++++++++
Based on the historical data of the energy balance, the demand projections were developed by using ARIMA models. These models are one of the most widely used approaches for time series forecasting. They correspond to simple univariate models focused on the long trend trajectory of the different time series. Their general structure is shown below:

General equation: 

.. math::

   \phi \left(B\right){\phi}_s\left(B\right)Z_t=\mu +\theta \left(B\right){\theta }_s\left(B\right)a_t
   
Simple delays: 
 
.. math::

   \phi \left(B\right)=1-{\phi }_1B-{\phi }_2B^2-...-{\phi }_pB^b\ \wedge \ \ \phi \left(B\right)=1-{\phi }_{1s}B^s-{\phi }_{2s}B^{2s}-...-{\phi }_{Ps}B^{Pb}
   
.. math::
   
   \theta \left(B\right)=1-{\phi }_1B-{\phi }_2B^2-...-{\phi }_qB^q\wedge \ \theta \left(B\right)=1-{\phi }_{1s}B-{\phi }_{2s}B^{2s}-...-{\phi }_{Qs}B^{qs}

where *ϕ* corresponds to operators, *μ* is the media  of *ϕ*, *θ* is a coefficient, and *s* is a stational component. 

This forecasting model gives good approximations of the data registered by institutions. The estimation begins with the analysis and forecasting of the time series corresponding to the primary sources. With these long term values, a specific trend is fixed by using the shares defined in the base year. A Hierarchical process was develop considering that the shares by each sector are the same on the base year.

.. figure:: Figures/Energy_Forecast_Plot.png
   :align:   center
   :width:   600 px
   
   *Figure 4.1: Historical and Forecasting electricity consumption by sector in Costa Rica* 



-Specified Annual Demand

-Specified Annual Demand

-Series intervention 

4.4 Supply and performance

Capacity Factor
Availability Factor
Operational Life
Residual Capacity
Input Activity Ratio
Output Activity Ratio



.. figure:: Figures/GenerationR1.png
   :align:   center
   :width:   850 px
   
   *Figure XXX: Generation Region 1* 


.. figure:: Figures/GenerationR2.png
   :align:   center
   :width:   800 px
   
   *Figure XXX: Generation Region 2* 


.. figure:: Figures/GenerationR3.png
   :align:   center
   :width:   800 px
   
   *Figure XXX: Generation Region 3* 


.. figure:: Figures/InterchangeNicaragua.png
   :align:   center
   :width:   900 px
   
   *Figure XXX: Interchange Nicaragua* 


.. figure:: Figures/InterchangePanama.png
   :align:   center
   :width:   900 px
   
   *Figure XXX: Interchange Panama* 


.. figure:: Figures/GenerationNationalInterchange.png
   :align:   center
   :width:   800 px
   
   *Figure XXX: Generation National and Interchange* 







.. figure:: Figures/OperationalCFR1.png
   :align:   center
   :width:   800 px
   
   *Figure XXX: Operational CF R1* 



.. figure:: Figures/OperationalCFR2.png
   :align:   center
   :width:   800 px
   
   *Figure XXX: OperationalCFR2* 


4.5 Technology costs

Capital and Fixed


4.6 Decision Variables 
+++++++++





