#%%
import pandas as pd
import pypsa
from data.data import tech_data
from utils import (
    annuity,
    plot_dispatch_week,
    plot_electricity_mix,
    plot_duration_curves,
    calculate_capacity_factors,
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

# %%
network.optimize(solver_name='gurobi')

# Save the model to LP format
network.model.to_file('model_A.lp')
print(f"Model saved to: model_A.lp")

# %%
optimal_capacities = network.generators.p_nom_opt.sort_values(ascending=False)
print("\nOptimal capacities [MW]:")
print(optimal_capacities)

capacity_factors = calculate_capacity_factors(network)
print("\nAnnual capacity factors [-]:")
print(capacity_factors)

# %%
# Representative winter and summer weeks for 2015.
plot_dispatch_week(
    network,
    week_start="2015-01-12 00:00:00",
    title="Winter Dispatch (Week of 12 Jan 2015)",
)

plot_dispatch_week(
    network,
    week_start="2015-07-13 00:00:00",
    title="Summer Dispatch (Week of 13 Jul 2015)",
)

plot_electricity_mix(network)
plot_duration_curves(network)
# %%
