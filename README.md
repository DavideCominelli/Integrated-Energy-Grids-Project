# Integrated-Energy-Grids-Project

a) Choose one country/region/city/system and calculate the optimal capacities for renewable and non-renewable generators. You can add as many technologies as you want. Remember to provide a reference for the costs and other technological assumptions. Plot the dispatch time series for a week in summer and winter. Plot the annual electricity mix. Use the duration curves or the capacity factor to investigate the contribution of different technologies.

solved in main.py

b) Investigate how sensitive your results are to the interannual variability of solar and wind generation. Plot the average capacity and variability obtained for every generator using different weather years.

solved in part_B.py

c) Add some storage technology/ies and investigate how they behave and what their impact is on the optimal system configuration. Discuss what strategies your system is using to balance the renewable generation at different time scales (intraday, seasonal, etc.)

solved in part_C.py

d) Connect your country to at least three neighbouring countries using HVAC lines, making sure that the network includes at least one closed cycle. Look for information on the existing capacities of those interconnectors and set the capacities fixed. Assume a voltage level of 400 kV and a unitary reactance x=0.1. You can assume that the generation capacities in the neighbouring countries are fixed or co-optimise the whole system. Optimise the whole system, assuming linearised AC power flow (DC approximation) and discuss the results.

solved in part_D.py

e) (Note: this section must be solved with pen and paper. The objective is to replicate the power flows that you obtained for the first time step in your simulation. )
Calculate the incidence matrix and the power transfer distribution factor (PTDF) matrix of the network that you defined in the previous section. Read from your PyPSA model the imbalances in the first time step in every node (i.e. generation - demand). Assuming linearised AC power flows, and the previously determined PTDF matrix, calculate the optimal power flowing through every line and check that it coincides with the modelled results.
