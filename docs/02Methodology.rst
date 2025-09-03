2. Analytical Approach
=======================================

2.1 Desicion estructuring 
+++++++++

It is widely recognized that participatory processes lead to comprehensive solutions and allow for the establishment of an adequate understanding of the problem at hand. In general, these processes are carried out in coordination with government bodies responsible for energy or climate change policy, which facilitate the identification and involvement of key stakeholders in order to gather their perspectives. The outcome of this stage is organized into a matrix known as XLRM, which defines: performance metrics (X), strategies or actions (L), models and data (R), and uncertainties (M) embedded in the problem to be addressed. Through workshops with a balanced representation of stakeholders, mechanisms are generated to respond to questions such as:

1- What models are used to analyze energy systems, and what databases do they rely on?

2- What strategies do governments propose to achieve a sustainable and just energy transition?

3- What metrics are applied to quantify the impact of decisions and uncertainties?

4- What is the role of regulators, planners, and operators of energy systems?

In the field of energy systems, the Latin American region presents many similar characteristics: a predominantly hydroelectric generation base, regional electricity interconnections under development, natural gas and oil energy potential, hydrocarbon imports from other geopolitical regions, challenges in passenger mobility and freight transport, a vehicle fleet largely dependent on hydrocarbons, and the pressing need to reformulate urban development

.. figure:: Figures/XLRM_matrix.png
   :align:   center
   :width:   700 px

   *Figure X.X: XLRM Matrix of References for the Transformation of Energy Systems.*


The matrix provides inputs for the development of a modelling framework that supports the energy transition toward decarbonization and affordability. The information reflects a national-scale perspective and will serve as a reference for the present study, in which the main focus lies in the methodological formulation and its initial application.


+++++++++



2.2 Exploratory modelling 
+++++++++

In the scenario exploration stage, the information obtained from the participatory process is consolidated into a simulation platform, which unidirectionally combines an energy model with a module to study system costs. Next tigure  illustrates how the information contained in the XLRM matrix enters the simulation process and is subsequently sent to the vulnerability analysis stage. In this process, the models must be adapted to address the objective of the problem under study, adequately consider temporal and spatial resolution, the characterization of technologies or processes, boundary conditions of the analysis, uncertainty, and techniques for effective communication of results.


.. figure:: Figures/Diagram.png
   :align:   center
   :width:   700 px

   *Figure X.X: Explore.....*


For the energy system, an optimization model is used to provide discounted investment and operating costs, installed system capacity, energy flows, and levels of greenhouse gas (GHG) emissions, among other variables, across different energy supply chains. The process begins with calibration in a base year, which responds to an energy balance, existing infrastructure, and utilization factors, among others, in order to emulate the behavior of the energy system. For this purpose, aspects such as technology substitution dynamics according to lifetime, technology cost trajectories, discount rates, carbon dioxide emission factors, and investment plans are considered. For flexibility, these models are also employed in accounting mode, including constraints to conduct “what-if” analyses. The objective of this stage is to generate evidence for subsequent analysis, rather than to identify a particular optimal solution.

The process includes an experimental design in which parameters within the model are combined using formal sampling techniques to generate multiple futures. Given the condition of deep uncertainty or the difficulty in characterizing parameters, this approach does not rely on the assignment of probability functions. Instead, it consists of defining and combining parameters to generate multiple futures efficiently. Once the input combinations are generated, a large set of simulations is conducted in which different parameter vectors are progressively introduced, subjecting the models to computational stress to generate evidence at scale. Each future may combine policy actions or technological innovations (e.g., electric vehicles, batteries, distributed generation, among others) with uncertainties (e.g., technology costs, utilization factors, adoption curves, among others). Each parameterization will yield different results and provide relevant information for decision-making (e.g., emissions, total costs, and levelized costs).

An additional module will quantify cost metrics: total system (investment and operation) and component-level costs, as well as the levelized cost of electricity. Gradually, this will allow the incorporation of new perspectives or decision-making needs, making it possible to assess the effect of introducing new strategies. Furthermore, as a starting point, simple approaches are sought in order to provide a general perspective, reduce computational requirements, and progressively increase the modeling granularity.

The experimental design constitutes the initial stage of the exploratory process, in which policy objectives and the uncertainties to be explored are defined, together with their corresponding ranges of variation and the number of pathways to be implemented (usually in the thousands). In this project, we use the statistical method Latin Hypercube Sampling (LHS) to generate a multidimensional data distribution that enables the exploration of variable relationships efficiently, without the need to sample the entire space. Next figure illustrates this concept using a system with two independent variables, where the space is progressively divided into equal parts while preserving the memory of the points already selected.


Linear programing and next multiobjetive (section 6)... ( in process)


.. figure:: Figures/Diagram.png
   :align:   center
   :width:   700 px

   *Figure X.X: LHP*


The LHS algorithm selects combinations of these variables that allow for a uniform distribution across the entire data space, in which only one variable per dimension is permitted (i.e., for each row or column only one value is allowed). In this simple example, each point in the space represents a possibility that combines two parameters, which in turn will be modeled. Thus, each generated future corresponds to a specific combination of parameters (an input parameter package). In general, uniformity must be maintained, considering that these parameter packages are evaluated equally across each central scenario.

For this project, approximately XXX  independent parameters are being combined per future. Rather than representing a single point, each future is associated with a long-term trajectory.


2.4 Vulnerability Analysis 
+++++++++

This stage shares similarities with general sensitivity analyses, in which the effect of varying model input parameters on output variables is explored. Under the concept of robustness, the quantification focuses on identifying the conditions under which policy actions or strategies are prone to failure, or where the stated objectives are not successfully achieved, given the influence of uncertainties. Since the exploratory process generates a substantial amount of data, it is common to employ computational techniques from Machine Learning. This process, known as scenario discovery, is used to inform the effects of uncertainties.

At this point, the analysis explores how the set of strategies is affected by uncertainty, which is determined through variations in the metrics. These indicators are defined during the participatory process, estimated in the exploration stage, and structured to provide information related to the continuity of energy supply, the costs of access to energy services, and the sustainability levels of this activity. Considering that reliability is the cornerstone of this trilemma and must be satisfied a priori, the set of metrics will primarily reflect the system cost component and the levels of pollution or carbon dioxide emissions. Cost–benefit assessments are commonly carried out to evaluate the feasibility of strategies. Subsequently, the uncertainties with the greatest impact on achieving objectives are identified through a data classification process. The following figure provides a synthesis of this process, which includes an important visualization stage.

.. figure:: Figures/Diagram.png
   :align:   center
   :width:   700 px

   *Figure X.X: Vulnerability*

La búsqueda de patrones de interés se realiza seleccionando umbrales para cada métrica determinada. Usualmente, los tomadores de decisión definen estos valores y se convierten en los objetivos a cumplir. Considerando las premisas descritas en las etapas anteriores se definirán como punto de partida las siguientes métricas y umbrales de interés: i) Confiabilidad, con 100% satisfacción de la demanda, ii) Emisiones de dióxido de carbono, con un 90% de reducciones al 2050, en comparación a las registradas en 2020 y ii) Costos totales y costos nivelados de la electricidad con un aumento no mayor al 10% en 2050. Existe una riqueza en la aplicación de este enfoque novedoso debido al nivel de flexibilidad para responder preguntas de política y brindar señales claras del desempeño. Esta condición es relevante porque genera conciencia situacional sobre los tomadores de decisión y los motiva a seguir experimentando junto a los equipos de modelación. Estos equipos también tienen la tarea de mantener la rigurosidad científica y la transparencia para promover los mejores principios de gobernanza.


This process aims to contrast the combinations of uncertainties or input parameters in the model against the set of defined metrics. Additionally, it allows for the definition of parameter ranges that generate conditions of vulnerability, as well as a classification based on their impact on the results. In this study, we employ the Patient Rule Induction Method (PRIM) algorithm, as it is considered useful for being highly interactive, offering multiple options for scenario selection, and providing visualizations that help users balance the three measures of scenario quality: coverage, density, and interpretability. The following figure illustrates this concept, considering a series of results separated by a threshold that is usually defined a priori. Based on this threshold, the scenarios of interest are defined. In other words, scenario discovery seeks to identify the combination of input parameters that lead to results exceeding this threshold.

.. figure:: Figures/Diagram.png
   :align:   center
   :width:   700 px

   *Figure X.X: PRIM*

While coverage measures the effect of uncertainties on overall results (analogous to sensitivity), density measures the purity of the scenario (analogous to positive predictive value). These two variables are in tension, as increasing coverage often decreases density. On the other hand, interpretability refers to the ease with which this technique allows the information to be understood and used. Scenario discovery is carried out by creating “boxes” that seek to enclose and describe the range in which these scenarios occur. Finally, the method includes the construction of multidimensional boxes that account for the combination of all uncertainties.


Falta CART ... 
