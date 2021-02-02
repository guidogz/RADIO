2. Land model: Framework 
=======================================

In this section, we give an insight to the general structure of the land-use module of CLEWCR. The land-use sector is a cross-cutting topic in the decarbonization plan. However, it is explicitly considered in the last three lines of actions: 

- Line of action 8 - The promotion of efficient agricultural food systems that generate low-carbon local export goods and consumption.
- Line of action 9 - Consolidation of an eco-competitive livestock model based on productive efficiency and reduction of greenhouse gases.
- Line of action 10 -Management of rural, urban and coastal territories that considers nature-based solutions (Conservation of forests and ecosystems).

The land-use module aims at representing and quantifying cover changes, livestock and crops yields, changes in emissions as a result of different production practices, ecosystem services, production costs, local production, exports, imports and demands, among other factors. 

2.1 General model structure 
+++++++++

The modeling framework structure is divided into six different land covers: 

- Crops: 
   - Rice.
   - Banana.
   - Coffee.
   - Sugar cane. 
   - Palm oil. 
   - Pineapple. 
   - Other agricultural products. 
   
- Grassland: 
   - Meat. 
   - Milk. 
   
- Forests: 
   - Mangroves primary and secondary forest.
   - Moist primary and secondary forest.
   - Palm primary and secondary forest. 
   - Moist primary and secondary forest. 
   - Dry primary and secondary forest.
   - Wet primary and secondary forest.
   - Forest plantations (timber production).
   
- **Urban areas.** 
 
- **Other covers.** 
 
Overall, the land-use modeling framework represents supply chains of goods and services produced by the different land cover/use system types. In this context, land supply, demand, and land use change are conditioned by, for the most part, on national and international market forces, policies, institutional factors and production schemes yield. 

.. figure::  doc_imgs/Land__diagram.png
   :align:   center
   :width:   700 px
   
   *Figure: General structure of the land-use module of CLEWCR* 


2.2 Sets 
+++++++++

The sets are responsible for defining the structure of the model (i.e. temporal space, geographic space, elements of the system, etc.). In OSeMOSYS, the group of sets include: years, fuels, technologies, emissions and modes of operation. As it going to be further explained, the sets are characterized through parameters. These subsections present the sets that compose the current version of CLEWCR.  

2.2.1 Year
---------

This corresponds to the period of analysis. For CLEWCR it is from 2015 to 2050. However, the data from 2015 to 2018 is set acccording to historical information. 

2.2.2 Fuels and technologies
---------

A complete list of the fuels and technologies of the land-use module can be found in the :ref:`Codification` section. 

2.2.3 Emissions
---------

*Table: Summary of emissions included in the land module of CLEWCR.*

.. table::
   :align:   center 
   
+---------------------+--------------------------------------------------+
| Emission            | Description                                      |
+=====================+==================================================+
|CR02_LULUCF_ABS      | L_Forest removals                                |
+---------------------+--------------------------------------------------+
|CR02_LULUCF_EMI      | L_Land use change emissions                      |
+---------------------+--------------------------------------------------+
|CRCO2_EQ_ESTIERCOL   | L_Eq carbon dioxide manure management            |
+---------------------+--------------------------------------------------+
|CRCO2_EQ_FERMEN      | L_Eq carbon dioxide from enteric fermentation    |
+---------------------+--------------------------------------------------+
|CRCO2_ABS_P_FOR      | L_Removals from forest plantations               |
+---------------------+--------------------------------------------------+
|CRCO2_CULTIVOS       | L_Emissions from crops                           |
+---------------------+--------------------------------------------------+
|SE_DRY_Forest        | L_Ecosystem services from dry forest             |
+---------------------+--------------------------------------------------+
|SE_MANGRO_Forest     | L_Ecosystem servoces from Mangroves              |
+---------------------+--------------------------------------------------+
|SE_PALM_Fosrest      | L_Ecosystem services from Palm Forest            |
+---------------------+--------------------------------------------------+
|SE_WET_MOIST_Forest  | L_Ecosystem services from Moist Forest           |
+---------------------+--------------------------------------------------+

2.2.4 Mode of operation
---------
    
The model has one mode of operation, Mode 1, for representing the normal operation of the system.

2.2.5 Region
---------
    
The model has a nationwide scope, therefore it only has one region: Costa Rica (CR).  
  
