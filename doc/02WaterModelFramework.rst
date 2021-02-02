4. Water model: Framework 
=======================================

In this section, we give an insight to the general framework of the water module of CLEWCR. The water sector is a cross-cutting topic in the decarbonization plan, and it is explicitly considered in the 7th line of action: Development of an integrated waste management system based in the separation, reuse, revaluation, and high  efficiency and low-GHG final disposal.

4.1 General model structure 
+++++++++

The modeling framework is structued as follow:

- Water availability: 
   - Precipitation.
      - Evapotranspiraton. 
      - Surface runoff. 
      - Groundwater recharge.
      
- Extraction: 
   - Superficial extraction. 
   - Underground extraction. 
   
- Potabilization. 

- Irrigation. 

- Concessions: 
   -Industrial. 
   - For agriculture. 

- Water distribution. 

- Water demands. 
   - For human consumption. 
   - Industrial. 
   - For agriculture. 

- Water disposal.    
   - Sewage. 
   - Septic tank.
   - Water treatment. 
      - From human consumption. 
      - Industrial. 
   - Water without treatment. 

.. figure::  doc_imgs/Water__diagram.png
   :align:   center
   :width:   700 px
   
   *Figure: General structure of the water module of CLEWCR* 

4.2 Sets 
+++++++++

The sets are responsible for defining the structure of the model (i.e. temporal space, geographic space, elements of the system, etc.). In OSeMOSYS, the group of sets include: years, fuels, technologies, emissions and modes of operation. As it going to be further explained, the sets are characterized through parameters. These subsections present the sets that compose the current version of CLEWCR.  

4.2.1 Year
---------

This corresponds to the period of analysis. For CLEWCR it is from 2015 to 2050. However, the data from 2015 to 2018 is set acccording to historical information. 

4.2.2 Fuels and technologies
---------

A complete list of the fuels and technologies of the land-use module can be found in the :ref:`Codification` section. 

4.2.3 Emissions
---------

*Table: Summary of emissions included in the water module of CLEWCR.*

.. table::
   :align:   center 
   
+---------------------+--------------------------------------------------+
| Emissions           | Description                                      |
+=====================+==================================================+
|CO2                  | W_Emissions from waste water                     |
+---------------------+--------------------------------------------------+
|CR_A_ANC_entrada     | Economic benefits of reducing water losses       |
+---------------------+--------------------------------------------------+
|CR_A_ANC_salida      | Benefits in health of water treatment            |
+---------------------+--------------------------------------------------+

4.2.4 Mode of operation
---------
    
The model has one mode of operation, Mode 1, for representing the normal operation of the system.

4.2.5 Region
---------
    
The model has a nationwide scope, therefore it only has one region: Costa Rica (CR). 
  
