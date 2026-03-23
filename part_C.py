#%%
import pandas as pd
import pypsa
from data.data import tech_data
from utils import (
    annuity,
    plot_dispatch_week_storage,
    plot_electricity_mix_storage,
    plot_duration_curves_storage,
    calculate_capacity_factors_storage,
    plot_storage_soc,
)

#%% create a new PyPSA network
network = pypsa.Network()

# add snapshots for the whole year of 2015 in hourly resolution
hours_in_2015 = pd.date_range('2015-01-01 00:00Z',
                              '2015-12-31 23:00Z',
                              freq='h')

network.set_snapshots(hours_in_2015.values)

# copper plate model (1 bus bar)
network.add("Bus",
            "electricity bus")


#%% add demand data
# load electricity demand data
df_elec = pd.read_csv('data/electricity_demand.csv', sep=';', index_col=0) # in MWh
df_elec.index = pd.to_datetime(df_elec.index) #change index to datatime
country= 'DEU' # Germany

# add load to the bus
network.add("Load",
            "load",
            bus="electricity bus",
            p_set=df_elec[country].values)


#%% include solar, wind and gas generators
network.add("Carrier", "gas", co2_emissions=0.19) # in t_CO2/MWh_th
network.add("Carrier", "onshorewind")
network.add("Carrier", "solar")
network.add("Carrier", "hydro")
network.add("Carrier", "battery")
network.add("Carrier", "H2")

# add onshore wind generator
df_onshorewind = pd.read_csv('data/onshore_wind_1979-2017.csv', sep=';', index_col=0)
df_onshorewind.index = pd.to_datetime(df_onshorewind.index)
CF_wind = df_onshorewind[country][[hour.strftime("%Y-%m-%dT%H:%M:%SZ") for hour in network.snapshots]]
capital_cost_onshorewind = (
    annuity(tech_data["onshorewind"]["lifetime"], 0.07)
    * tech_data["onshorewind"]["overnight_cost"]
    * (1 + tech_data["onshorewind"]["capital_cost_increase"])
) # in €/MW

# %%
network.add("Generator",
            "onshorewind",
            bus="electricity bus",
            p_nom_extendable=True,
            carrier="onshorewind",
            #p_nom_max=1000, # maximum capacity can be limited due to environmental constraints
            capital_cost = capital_cost_onshorewind,
            marginal_cost = 0,
            p_max_pu = CF_wind.values)
# %%
df_solar = pd.read_csv('data/pv_optimal.csv', sep=';', index_col=0)
df_solar.index = pd.to_datetime(df_solar.index)
CF_solar = df_solar[country][[hour.strftime("%Y-%m-%dT%H:%M:%SZ") for hour in network.snapshots]]
capital_cost_solar = (
    annuity(tech_data["solar"]["lifetime"], 0.07)
    * tech_data["solar"]["overnight_cost"]
    * (1 + tech_data["solar"]["capital_cost_increase"])
) # in €/MW
capital_cost_rooftop_solar = (
    annuity(tech_data["solar_rooftop"]["lifetime"], 0.07)
    * tech_data["solar_rooftop"]["overnight_cost"]
    * (1 + tech_data["solar_rooftop"]["capital_cost_increase"])
) # in €/MW
network.add("Generator",
            "solar",
            bus="electricity bus",
            p_nom_extendable=True,
            carrier="solar",
            #p_nom_max=1000, # maximum capacity can be limited due to environmental constraints
            capital_cost = capital_cost_solar,
            marginal_cost = 0,
            p_max_pu = CF_solar.values)
network.add("Generator",
            "solar_rooftop",
            bus="electricity bus",
            p_nom_extendable=True,
            carrier="solar",
            capital_cost=capital_cost_rooftop_solar,
            marginal_cost=0,
            p_max_pu=CF_solar.values)
# Conservative hydro proxies: fixed existing capacities with simplified availability.
# This avoids unconstrained hydro expansion in the absence of inflow time series.
network.add("Generator",
            "run_of_river",
            bus="electricity bus",
            p_nom=tech_data["run_of_river"]["fixed_capacity"],
            carrier="hydro",
            capital_cost=0,
            marginal_cost=0,
            p_max_pu=tech_data["run_of_river"]["availability"])
network.add("Generator",
            "hydro_reservoir",
            bus="electricity bus",
            p_nom=tech_data["hydro_reservoir"]["fixed_capacity"],
            carrier="hydro",
            capital_cost=0,
            marginal_cost=0,
            p_max_pu=tech_data["hydro_reservoir"]["availability"])
# %%
capital_cost_OCGT = (
    annuity(tech_data["OCGT"]["lifetime"], 0.07)
    * tech_data["OCGT"]["overnight_cost"]
    * (1 + tech_data["OCGT"]["capital_cost_increase"])
) # in €/MW
fuel_cost = tech_data["OCGT"]["fuel_cost"] # in €/MWh_th
efficiency = tech_data["OCGT"]["efficiency"] # MWh_elec/MWh_th
marginal_cost_OCGT = fuel_cost/efficiency # in €/MWh_el
network.add("Generator",
            "OCGT",
            bus="electricity bus",
            p_nom_extendable=True,
            carrier="gas",
            #p_nom_max=1000,
            capital_cost = capital_cost_OCGT,
            marginal_cost = marginal_cost_OCGT)

# %% add storage technologies

# Pumped hydro storage
capital_cost_pumped_hydro_power = (
    annuity(tech_data["Pumped_Hydro"]["lifetime"], 0.07)
    * tech_data["Pumped_Hydro"]["overnight_cost_power"]
    * (1 + tech_data["Pumped_Hydro"]["capital_cost_increase"])
)
capital_cost_pumped_hydro_energy = (
    annuity(tech_data["Pumped_Hydro"]["lifetime"], 0.07)
    * tech_data["Pumped_Hydro"]["overnight_cost_energy"]
    * (1 + tech_data["Pumped_Hydro"]["capital_cost_increase"])
)

total_capital_cost_pumped_hydro = capital_cost_pumped_hydro_power + capital_cost_pumped_hydro_energy * tech_data["Pumped_Hydro"]["max_hours"]
network.add("StorageUnit", 
            "Pumped_Hydro", 
            bus="electricity bus", 
            p_nom_extendable=True,   
            capital_cost= total_capital_cost_pumped_hydro, 
            max_hours=tech_data["Pumped_Hydro"]["max_hours"],             
            efficiency_store=tech_data["Pumped_Hydro"]["efficiency_store"],     
            efficiency_dispatch=tech_data["Pumped_Hydro"]["efficiency_dispatch"],  
            cyclic_state_of_charge=True,
            inflow=0,                 # closed system (no inflow) (i dont have any time series for inflow, so I set it to 0)
            p_min_pu=-1              # minimum load of 5% (technical constraint)
            )

# Li-ion battery storage
capital_cost_battery_power = (
    annuity(tech_data["battery"]["lifetime"], 0.07)
    * tech_data["battery"]["overnight_cost_power"]
    * (1 + tech_data["battery"]["capital_cost_increase"])
)
capital_cost_battery_energy = (
    annuity(tech_data["battery"]["lifetime"], 0.07)
    * tech_data["battery"]["overnight_cost_energy"]
    * (1 + tech_data["battery"]["capital_cost_increase"])
)

total_capital_cost_battery = capital_cost_battery_power + capital_cost_battery_energy * tech_data["battery"]["max_hours"]
network.add("StorageUnit", 
            "battery", 
            bus="electricity bus", 
            p_nom_extendable=True,   
            capital_cost= total_capital_cost_battery, 
            max_hours=tech_data["battery"]["max_hours"],             
            efficiency_store=tech_data["battery"]["efficiency_store"],     
            efficiency_dispatch=tech_data["battery"]["efficiency_dispatch"],  
            cyclic_state_of_charge=True, 
            p_min_pu=-1)

# Hydrogen storage
network.add("Bus",
          "H2",
          carrier = "H2")
network.add("Store",
          "H2 Tank",
          bus = "H2",
          e_nom_extendable = True,
          e_cyclic = True,
          capital_cost = annuity(25, 0.07)*57000*(1+0.011))
#Add the link "H2 Electrolysis" that transport energy from the electricity bus (bus0) to the H2 bus (bus1)
#with 80% efficiency
network.add("Link",
          "H2 Electrolysis",
          bus0 = "electricity bus",
          bus1 = "H2",
          p_nom_extendable = True,
          efficiency = 0.8,
          capital_cost = annuity(25, 0.07)*600000*(1+0.05))

#Add the link "H2 Fuel Cell" that transports energy from the H2 bus (bus0) to the electricity bus (bus1)
#with 58% efficiency
network.add("Link",
          "H2 Fuel Cell",
          bus0 = "H2",
          bus1 = "electricity bus",
          p_nom_extendable = True,
          efficiency = 0.58,
          capital_cost = annuity(10, 0.07)*1300000*(1+0.05))    

# %%
network.optimize(solver_name='gurobi')

# Save the model to LP format
network.model.to_file('model_C.lp')
print(f"Model saved to: model_C.lp")

# %%
optimal_capacities = network.generators.p_nom_opt.sort_values(ascending=False)
print("\nOptimal capacities [MW]:")
print(optimal_capacities)
optimal_storage_capacities = network.storage_units.p_nom_opt.sort_values(ascending=False)
print("\nOptimal storage capacities [MW]:")
print(optimal_storage_capacities)

capacity_factors = calculate_capacity_factors_storage(network)
print("\nAnnual capacity factors [-]:")
print(capacity_factors)

# %%
# Representative winter and summer weeks for 2015.
plot_dispatch_week_storage(
    network,
    week_start="2015-01-12 00:00:00",
    title="Winter Dispatch (Week of 12 Jan 2015)",
)

plot_dispatch_week_storage(
    network,
    week_start="2015-07-13 00:00:00",
    title="Summer Dispatch (Week of 13 Jul 2015)",
)

plot_electricity_mix_storage(network)
plot_duration_curves_storage(network)
plot_storage_soc(network)
# %%
#%% 12) Renewable Curtailment and System Cost (Isolated)
print("\n=== SYSTEM METRICS (ISOLATED) ===")

# 1. Total System Cost
total_cost_isolated = network.objective
print(f"Total System Cost: € {total_cost_isolated:,.0f}")

# 2. Renewable Curtailment
vre_generators = ["onshorewind", "solar", "solar_rooftop"]

total_available = 0
total_dispatched = 0

print("\n--- Curtailment Breakdown ---")
for gen in vre_generators:
    # Available energy = optimal capacity * capacity factor profile
    available = network.generators_t.p_max_pu[gen] * network.generators.p_nom_opt[gen]
    # Dispatched energy = what the solver actually used
    dispatched = network.generators_t.p[gen]
    
    curtailed = available - dispatched
    curtailed_sum = curtailed.sum()
    available_sum = available.sum()
    
    total_available += available_sum
    total_dispatched += dispatched.sum()
    
    print(f"{gen}: {curtailed_sum:,.0f} MWh curtailed ({(curtailed_sum/available_sum)*100:.2f}% of available)")

total_curtailed = total_available - total_dispatched
print(f"\nTotal VRE Curtailment: {total_curtailed:,.0f} MWh ({(total_curtailed/total_available)*100:.2f}%)")