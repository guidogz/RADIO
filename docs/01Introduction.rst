.. Title:

1. Introduction 
=====================================

1.1 Projects overview
+++++++++

The creation of CLEW-CR is part of the ”Development and assessment of decarbonization pathways to inform dialogue with Costa Rica regarding the updating process of Nationally Determined Contribution (NDC)” project, which was contracted by the World Bank Group for the Directorate of Climate Change (DCC) of the Ministry of Environment and Energy in Costa Rica (MINAE). This project involved the development of land-use and water models of Costa Rica, and the integration of them with a pre-existing energy model, all of them developed in the Open Source energy Modelling System (OSeMOSYS). The CLEW-CR team is composed by researchers from the University of Costa Rica (UCR) and the Royal Institute of Technology (KTH) in Stockholm.

The energy module of CLEW-CR started as part of the “Deep Decarbonization Pathways Project in Latin America and the Caribbean (DDPP-LAC)” project, which is coordinated by the Institute for Sustainable Development and International Relations (IDDRI) and the Inter-American Development Bank (IADB). The project involves six different teams, and each team is formed by experts from a Latin American (LA) country (Argentina, Colombia, Costa Rica, Ecuador, Mexico, and Peru) and experts from other countries (France, USA, Sweden and Brazil). The main purpose of these alliances is to transfer capacities from one country to another, while engaging with policy makers to address a modeling aspect of local importance.

In addition, the development of this energy module has been supported by the project “Assessing Options to Decarbonize the Transport Sector under Technological Uncertainty: The Case of Costa Rica”. This work was contracted by the Interamerican Development Bank (IADB) for the DCC-MINAE. The project aimed at developing a framework to evaluate mitigation actions in the Costa Rican transport sector that contribute to achieve the deep decarbonization, considering its uncertainty and socioeconomic impact, and implementing it in OSeMOSYS-CR to evaluate multiple climate actions towards a clean transport sector.

1.2 Motivation and problem statement
+++++++++

Costa Rica is a Latin American country worldwide known for its environmental protection, political, social and economic stability, and renewable electricity generation. Despite these achievements, there are many challenges to tackle in order to decarbonise its economy. The CLEWCR model aims at supporting policymakers in Costa Rica to understand the most suitable strategies to achieve a deep decarbonization in the land-use, energy, transport and water treatment sectors. In order to achieve this, CLEWCR presents two typical scenarios of interest: a BAU scenario representing current trends of actions and policies, and a National Decarbonization Plan (NDP) policy decarbonization scenario.

In addition, the CLEWCR model aims at representing the main interconnections between the Climate, Land, Energy and Water sectors and the society needs, i.e., the CLEWs nexus. The framework consists of an existing energy model, two new land and water models and the inclusion of climate variables such as precipitation. While each modeling frameworks characterize the corresponding sectors, their integration allow a broader, economy-wide assessment of different policy measures as the CLEW model captures their interactions and optimizes the overall cost of the system subject to restrictions.

.. figure::  doc_imgs/General_diagram.png
   :align:   center
   :width:   350 px
   
   *Figure: CLEWCR model and the nexus concept* 


1.3 The Open Source energy Modelling System (OSeMOSYS) and CLEWCR
+++++++++

OSeMOSYS is an optimization software for long-term energy planning. It is an open source model structured in blocks of functionality that allows easy modifications to the code, providing a great flexibility for the creative process of the solution. The models built on OSeMOSYS are based upon two general components: technologies (or processes) and fuels (or products/goods). In the case of CLEWCR, the processes include, but are not limited to, the purification and distribution of water, the generation of electricity, and the production of pineapple and coffee. On the other hand, examples of fuels are superficial water, electricity, electric vehicles and produced sugar. Every process is associated to input and output fuels. 

In addition, processes are described by a wide variety of parameters that allow a realistic modelling. These parameters are related to aspects such as costs, capacity, lifetime, implementation limits or targets, emissions factors in the case of processes and demands, and availability in the case of fuels. Parameters such as demands can vary over the different time slides considered in the modelling, and emission targets can be included. For CLEWCR, these parameters were included with the best available information, which is most of the time national data. The purpose of this documentation is to present the data values and sources used to parametrized the CLEWCR model. 

.. figure::  doc_imgs/Technology.png
   :align:   center
   :width:   550 px
   
   *Figure: OSeMOSYS parametrization* 

The models that are built in OSeMOSYS minimize the total cost of the system for a certain period of time, defining the configuration of the supply system, considering the restrictions on activity, capacity, and emissions of technologies set by the parameters :cite:`HOWELLS20115850`. This is shown in the following equation: 

.. math::

   Minimize \sum_{y,t,r}Total\ discounted\ cost_{y,t,r},
   
where: *y* corresponds to the year, *t* to the technology and *r* to the region. 

The discounted cost can be expressed as follows: 

.. math::

   \forall _{y,t,r}\  Total\ discounted\ cost_{y,t,r}\  =   DOC_{y,t,r} + DCI_{y,t,r}  + DTEP_{y,t,r} - DSV_{y,t,r},
 
where: 

*	*DOC (Discounted Operational Cost):* Corresponds to the cost related to maintenance (fixed, usually associate to capacity) and operation of technologies (variable, linked to fuel uses and level of activity).  
*	*DCI (Discounted Capital Investment):* It is the cost of investment of all technologies selected to supply energy on the whole period. 
*	*DTEP (Discounted Technology Emission Penalty):* It is associated to the use of pollutants. The calculation is based on the emission factor and the activity of technologies and the specific cost by pollutant.    
*	*DSV (Discounted Salvage Value):* As the capital cost is discounted in the first year a technology is acquired, if in the last year of study the technologies have remaining years of operational life, the corresponding value is counted.

The general `documentation of OSeMOSYS <https://osemosys.readthedocs.io/en/latest/manual/Structure%20of%20OSeMOSYS.html>`_ is also available.  
