3. Energy model: Framework 
=======================================

This section presents the general structure of the energy module, also known as OSeMOSYS-CR, of CLEW-CR. 

3.1 General model structure 
+++++++++

The Costa Rican energy sector is enterly modeled in OSeMOSYS. However, while the transport and electricity sectors are subject to linear optimization, other smaller demands, such as the firewood used in the residential sector or the coke consumption by industries, are only represented with trends to account for their possible greenhouse gases (GHG) contributions. The overall structure of the model can be represented by the reference energy system shown in Figure 2.1. The primary energy supply consists of four main sources: renewable, imports of fossil fuels, biomass and electricity imports. These sources are transformed in order to satisfy different demands including industrial, residential and commercial requirements, and the transport demands of passengers (public and private) and cargo (light and heavy). 

.. figure:: doc_imgs/ElectricityModel.png
   :align:   center
   :width:   700 px

   *(a)*
   
.. figure:: doc_imgs/TransportModel.png
   :align:   center
   :width:   700 px

   *(b)*
   
   *Figure: Simplified Reference Energy System of the Costa Rica model for the (a) Electricity and (b) Transport sectors*
   

In OSeMOSYS-CR, the connection between the electricity and transport sectors is crucial for understanding the technological transition of fossil-powered vehicles to other options with lower or zero carbon emissions. The next section describes the group of sets considered in OSeMOSYS-CR for representing the elements commented above. 

3.2 Sets 
+++++++++

The sets are responsible for defining the structure of the model (i.e. temporal space, geographic space, elements of the system, etc.). In OSeMOSYS, the group of sets include: years, fuels, technologies, emissions and modes of operation. As it going to be further explained, the sets are characterized through parameters. These subsections present the sets that compose the current version of OSeMOSYS-CR.  

3.2.1 Year
---------

This corresponds to the period of analysis. For OSeMOSYS-CR it is from 2015 to 2050. However, the data from 2015 to 2018 is set acccording to historical information. 

3.2.2 Fuels and technologies
---------

A complete list of the fuels and technologies of the land-use module can be found in the Model codification section.

3.2.3 Emissions
---------

Table 2.3 shows a description of the emissions included in the model. In general, to quantify GHG contributions, the values are in terms of equivalent carbon dioxide (CO2e). 

*Table: Summary of emissions included in the energy module of CLEWCR.*

.. table::
   :align:   center 
   
+-----------------+--------------------------------------------+
| Code            | Name                                       |                                                                 
+=================+============================================+
| CO2_sources     | Carbon Dioxide from primary sources        |                                                                      
+-----------------+--------------------------------------------+
| CO2_transport   | Carbon Dioxide from transport              |                                                                      
+-----------------+--------------------------------------------+
| CO2_AGR         | Carbon Dioxide from agriculture            |                                                                         
+-----------------+--------------------------------------------+
| CO2_COM         | Carbon Dioxide from the commercial sector  |                                                                         
+-----------------+--------------------------------------------+
| CO2_IND         | Carbon Dioxide from the industrial sector  |                                                                         
+-----------------+--------------------------------------------+
| CO2_RES         | Carbon Dioxide from the residential sector |                                                                         
+-----------------+--------------------------------------------+
| CO2_Freigt      | Carbon Dioxide from freigt transport       |                                                                         
+-----------------+--------------------------------------------+
| CO2_HeavyCargo  | Carbon Dioxide from heavy cargo            |                                                                         
+-----------------+--------------------------------------------+
| CO2_LightCargo  | Carbon Dioxide from light cargo            |                                                                         
+-----------------+--------------------------------------------+

In addition, with this set the model incorporates benefits resulting from the implementation of mitigation policies in the energy sector. These are:

* Health improvements of the population as a result of a reduction in GHG emissions.
* Reduction of congestion, which leads to an increase in the country's productivity.
* Reduction of accidents on the national roads.

3.2.4 Mode of operation
---------
    
The model has one mode of operation, Mode 1, for representing the normal operation of the system.

3.2.4 Region
---------
    
The model has a nationwide scope, therefore it only has one region: Costa Rica (CR). 
  
A more detailed documentation of this energy module, OSeMOSYS-CR, can be found in a separate `Documentation <https://osemosys-cr.readthedocs.io/en/latest/>`_ .

