#%%

#https://www.entsoe.eu/eraa/2024/modelling-data/#Inputs
#source for ^ ntc capacity
import pandas as pd
import pypsa
import matplotlib.pyplot as plt

import numpy as np
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from matplotlib.lines import Line2D

from data.data import tech_data
from utils import (
    annuity,
    plot_dispatch_week_storage,
    plot_electricity_mix_storage,
    plot_duration_curves_storage,
    calculate_capacity_factors_storage,
    plot_storage_soc,
)


#%% 1) Settings
HOME_COUNTRY = "DEU"
COUNTRIES = ["DEU", "CHE", "CZE", "AUT"]

#we use ntc values for interconnectors
#it has been refrence in the pypsa tutorial 

INTERCONNECTORS_MW = {
    ("DEU", "CHE"): 4200,
    ("DEU", "CZE"): 2900,
    ("DEU", "AUT"): 4900,
    ("CZE", "AUT"): 900,
    ("AUT", "CHE"): 1200,
}

COORDS = {
    "DEU": (10.45, 51.16),
    "CHE": (8.23, 46.82),
    "CZE": (15.47, 49.82),
    "AUT": (14.55, 47.51),
}

#%% 2) Build network and snapshots
network = pypsa.Network()

hours_in_2015 = pd.date_range(
    "2015-01-01 00:00Z",
    "2015-12-31 23:00Z",
    freq="h",
)
network.set_snapshots(hours_in_2015.values)

#%% 3) Add buses and carriers
network.add("Carrier", "AC")
network.add("Carrier", "gas", co2_emissions=0.19)
network.add("Carrier", "onshorewind")
network.add("Carrier", "solar")
network.add("Carrier", "hydro")
network.add("Carrier", "battery")
network.add("Carrier", "H2")
network.add("Carrier", "heat")

for c in COUNTRIES:
    x, y = COORDS[c]
    network.add(
        "Bus",
        f"{c} bus",
        carrier="AC",
        v_nom=400,
        x=x,
        y=y,
    )

    network.add(
        "Bus",
        f"{c} heat bus",
        carrier="heat",
        x=x + 0.2,  # offset for better visualization
        y=y - 0.2,
    )



#%% 4) Add fixed interconnectors
for (c0, c1), cap in INTERCONNECTORS_MW.items():
    network.add(
        "Line",
        f"{c0}-{c1}",
        bus0=f"{c0} bus",
        bus1=f"{c1} bus",
        x=0.1,
        s_nom=cap,
        s_nom_extendable=False,
        carrier="AC",
    )

#%% 5) Load data
df_elec = pd.read_csv("data/electricity_demand.csv", sep=";", index_col=0)
df_elec.index = pd.to_datetime(df_elec.index)

df_wind = pd.read_csv("data/onshore_wind_1979-2017.csv", sep=";", index_col=0)
df_wind.index = pd.to_datetime(df_wind.index)

df_solar = pd.read_csv("data/pv_optimal.csv", sep=";", index_col=0)
df_solar.index = pd.to_datetime(df_solar.index)

#The heat demand series is taken from the course github repo for 2015
df_heat = pd.read_csv("data/heat_demand.csv", sep=";", index_col=0)
df_heat.index = pd.to_datetime(df_heat.index, utc=True)
df_heat = df_heat[COUNTRIES].reindex(hours_in_2015)

snapshot_cols = [h.strftime("%Y-%m-%dT%H:%M:%SZ") for h in network.snapshots]

#cost model is the same used in exercise 12.02

#source https://github.com/PyPSA/technology-data/tree/v0.11.0

#will be used for heat sector 
year = 2030
url = f"https://raw.githubusercontent.com/PyPSA/technology-data/v0.11.0/outputs/costs_{year}.csv"
costs = pd.read_csv(url, index_col=[0, 1])

#%%
costs.loc[costs.unit.str.contains("/kW"), "value"] *= 1e3
costs.unit = costs.unit.str.replace("/kW", "/MW")

defaults = {
    "FOM": 0,
    "VOM": 0,
    "efficiency": 1,
    "fuel": 0,
    "investment": 0,
    "lifetime": 25,
    "CO2 intensity": 0,
    "discount rate": 0.07,
}
costs = costs.value.unstack().fillna(defaults)

#def annuity2(r, n):
#    return r / (1.0 - 1.0 / (1.0 + r) ** n)


#%%

annuity2 = costs.apply(
    lambda x: annuity(x["lifetime"], x["discount rate"]),  # <- fixed order
    axis=1
)

costs["capital_cost"] = (annuity2 + costs["FOM"] / 100) * costs["investment"]

#%%

# These are the new techinical data needed for taks I with heat sector
HEAT_HP_COP = costs.at["central air-sourced heat pump", "efficiency"]
HEAT_HP_CAPITAL_COST = costs.at["central air-sourced heat pump", "capital_cost"]
#The heat pump capital cost is 79869 eur/MW/a


# choose one storage type:
#Long-term thermal energy storage
#there are a few options, either Water tank storage, or molten salt, or solid sensible heat storage through sand, 
#i choose central water, since it was the cheapest option at 3.1374 €/kWh in 2030, compared with 58 €/kWh for molten salt, and 6.7 €/kWh for solid sensible heat storage through sand.
HEAT_STORAGE_CAPITAL_COST = costs.at["central water tank storage", "capital_cost"]

HEAT_STORAGE_EFFICIENCY = costs.at["central water tank storage", "efficiency"]

HEAT_STORAGE_MAX_HOURS = costs.at["central water tank storage", "energy to power ratio"]  # ~60.3448 h

HEAT_STORAGE_CAPITAL_COST_P = HEAT_STORAGE_CAPITAL_COST * HEAT_STORAGE_MAX_HOURS

HEAT_GAS_BOILER_EFFICIENCY = costs.at["central gas boiler", "efficiency"]
HEAT_GAS_BOILER_CAPITAL_COST = costs.at["central gas boiler", "capital_cost"]

#%% 6) Cost assumptions
capital_cost_onshorewind = (
    annuity(tech_data["onshorewind"]["lifetime"], 0.07)
    * tech_data["onshorewind"]["overnight_cost"]
    * (1 + tech_data["onshorewind"]["capital_cost_increase"])
)

capital_cost_solar = (
    annuity(tech_data["solar"]["lifetime"], 0.07)
    * tech_data["solar"]["overnight_cost"]
    * (1 + tech_data["solar"]["capital_cost_increase"])
)

capital_cost_rooftop_solar = (
    annuity(tech_data["solar_rooftop"]["lifetime"], 0.07)
    * tech_data["solar_rooftop"]["overnight_cost"]
    * (1 + tech_data["solar_rooftop"]["capital_cost_increase"])
)

capital_cost_OCGT = (
    annuity(tech_data["OCGT"]["lifetime"], 0.07)
    * tech_data["OCGT"]["overnight_cost"]
    * (1 + tech_data["OCGT"]["capital_cost_increase"])
)

fuel_cost = tech_data["OCGT"]["fuel_cost"]
efficiency = tech_data["OCGT"]["efficiency"]
marginal_cost_OCGT = fuel_cost / efficiency

capital_cost_pumped_hydro_power = (
    annuity(tech_data["Pumped_Hydro"]["lifetime"], 0.07)
    * tech_data["Pumped_Hydro"]["overnight_cost_power"]
    * (1 + tech_data["Pumped_Hydro"]["capital_cost_increase"])
)
#capital_cost_pumped_hydro_energy = (
 #   annuity(tech_data["Pumped_Hydro"]["lifetime"], 0.07)
  #  * tech_data["Pumped_Hydro"]["overnight_cost_energy"]
   # * (1 + tech_data["Pumped_Hydro"]["capital_cost_increase"])
#)

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
battery_max_hours = tech_data["battery"].get("max_hours", 4)
total_capital_cost_battery = capital_cost_battery_power + capital_cost_battery_energy * battery_max_hours


capital_cost_h2_tank = (
    annuity(tech_data["hydrogen_storage"]["lifetime"], 0.07)
    * tech_data["hydrogen_storage"]["overnight_cost_energy"]
    * (1 + tech_data["hydrogen_storage"]["capital_cost_increase"])
)

capital_cost_h2_electrolysis = (
    annuity(tech_data["hydrogen_electrolysis"]["lifetime"], 0.07)
    * tech_data["hydrogen_electrolysis"]["overnight_cost_power"]
    * (1 + tech_data["hydrogen_electrolysis"]["capital_cost_increase"])
)

capital_cost_h2_fuel_cell = (
    annuity(tech_data["hydrogen_fuel_cell"]["lifetime"], 0.07)
    * tech_data["hydrogen_fuel_cell"]["overnight_cost_power"]
    * (1 + tech_data["hydrogen_fuel_cell"]["capital_cost_increase"])
)
pumped_hydro_max_power = tech_data["Pumped_Hydro"]["max_power_capacity"]
pumped_hydro_max_energy = tech_data["Pumped_Hydro"]["max_energy_capacity"]
if pumped_hydro_max_power <= 0:
    raise ValueError("Pumped_Hydro max_power_capacity must be > 0")

# New data provides absolute power and energy limits. Convert to equivalent storage duration.
pumped_hydro_max_hours = pumped_hydro_max_energy / pumped_hydro_max_power
total_capital_cost_pumped_hydro = capital_cost_pumped_hydro_power



#%% 7) Add all country systems (all technologies in loop)
for c in COUNTRIES:
    network.add(
        "Load",
        f"load_{c}",
        bus=f"{c} bus",
        p_set=df_elec[c].values,
    )

    network.add(
        "Load",
        f"heat_load_{c}",
        bus=f"{c} heat bus",
        p_set=df_heat[c].values,
    )
    network.add(
        "Link",
        f"heat_pump_{c}",
        bus0=f"{c} bus",
        bus1=f"{c} heat bus",
        p_nom_extendable=True,
        efficiency=HEAT_HP_COP, 
        capital_cost=HEAT_HP_CAPITAL_COST,
    )


    # Add heat storage as a Store on the heat bus
    network.add(
        "StorageUnit",
        f"heat_storage_{c}",
        bus=f"{c} heat bus",
        capital_cost=HEAT_STORAGE_CAPITAL_COST_P,   
        efficiency_store=HEAT_STORAGE_EFFICIENCY,
        efficiency_dispatch=HEAT_STORAGE_EFFICIENCY,
        p_min_pu=-1,
        cyclic_state_of_charge=True,
        p_nom_extendable=True,
        max_hours=HEAT_STORAGE_MAX_HOURS,         # <-- set from data
        standing_loss=0.001, # <-- small standing loss to prevent infinite storage without cost
    )


    # Add Gas Boiler (Alternative heat source)
    # Simplest way: Add it as a generator on the heat bus using 'gas' carrier
    network.add(
        "Generator",
        f"{c} gas boiler",
        bus=f"{c} heat bus",
        carrier="gas",
        efficiency=HEAT_GAS_BOILER_EFFICIENCY, 
        marginal_cost=fuel_cost/HEAT_GAS_BOILER_EFFICIENCY, 
        p_nom_extendable=True,
        capital_cost=HEAT_GAS_BOILER_CAPITAL_COST, 
    )


    cf_wind = df_wind[c][snapshot_cols].values
    cf_solar = df_solar[c][snapshot_cols].values

    network.add(
        "Generator",
        f"onshorewind_{c}",
        bus=f"{c} bus",
        p_nom_extendable=True,
        carrier="onshorewind",
        capital_cost=capital_cost_onshorewind,
        marginal_cost=0,
        p_max_pu=cf_wind,
    )

    network.add(
        "Generator",
        f"solar_{c}",
        bus=f"{c} bus",
        p_nom_extendable=True,
        carrier="solar",
        capital_cost=capital_cost_solar,
        marginal_cost=0,
        p_max_pu=cf_solar,
    )

    network.add(
        "Generator",
        f"solar_rooftop_{c}",
        bus=f"{c} bus",
        p_nom_extendable=True,
        carrier="solar",
        capital_cost=capital_cost_rooftop_solar,
        marginal_cost=0,
        p_max_pu=cf_solar,
    )

    network.add(
        "Generator",
        f"run_of_river_{c}",
        bus=f"{c} bus",
        p_nom=tech_data["run_of_river"]["fixed_capacity"],
        carrier="hydro",
        capital_cost=0,
        marginal_cost=0,
        p_max_pu=tech_data["run_of_river"]["availability"],
    )

    network.add(
        "Generator",
        f"hydro_reservoir_{c}",
        bus=f"{c} bus",
        p_nom=tech_data["hydro_reservoir"]["fixed_capacity"],
        carrier="hydro",
        capital_cost=0,
        marginal_cost=0,
        p_max_pu=tech_data["hydro_reservoir"]["availability"],
    )

    network.add(
        "Generator",
        f"OCGT_{c}",
        bus=f"{c} bus",
        p_nom_extendable=True,
        carrier="gas",
        capital_cost=capital_cost_OCGT,
        marginal_cost=marginal_cost_OCGT,
    )

    network.add(
        "StorageUnit",
        f"Pumped_Hydro_{c}",
        bus=f"{c} bus",
        p_nom_extendable=True,
        p_nom_max=pumped_hydro_max_power,
        capital_cost=total_capital_cost_pumped_hydro,
        max_hours=pumped_hydro_max_hours,
        efficiency_store=tech_data["Pumped_Hydro"]["efficiency_store"],
        efficiency_dispatch=tech_data["Pumped_Hydro"]["efficiency_dispatch"],
        cyclic_state_of_charge=True,
        inflow=0,
        p_min_pu=-1,
    )

    network.add(
        "StorageUnit",
        f"battery_{c}",
        bus=f"{c} bus",
        p_nom_extendable=True,
        capital_cost=total_capital_cost_battery,
        max_hours=battery_max_hours,
        efficiency_store=tech_data["battery"]["efficiency_store"],
        efficiency_dispatch=tech_data["battery"]["efficiency_dispatch"],
        cyclic_state_of_charge=True,
        p_min_pu=-1,
    )

    h2_bus = f"H2_{c}"
    network.add("Bus", h2_bus, carrier="H2")

    network.add(
        "Store",
        f"H2_Tank_{c}",
        bus=h2_bus,
        e_nom_extendable=True,
        e_cyclic=True,
        capital_cost=capital_cost_h2_tank,
    )

    network.add(
        "Link",
        f"H2_Electrolysis_{c}",
        bus0=f"{c} bus",
        bus1=h2_bus,
        p_nom_extendable=True,
        efficiency=tech_data["hydrogen_electrolysis"]["efficiency"],
        capital_cost=capital_cost_h2_electrolysis,
    )

    network.add(
        "Link",
        f"H2_Fuel_Cell_{c}",
        bus0=h2_bus,
        bus1=f"{c} bus",
        p_nom_extendable=True,
        efficiency=tech_data["hydrogen_fuel_cell"]["efficiency"],
        capital_cost=capital_cost_h2_fuel_cell,
    )

#%% 8) Optimise


network.optimize(solver_name="gurobi", solver_options={"output_flag": 0, "threads": 4})

network.model.to_file("model_I.lp")
print("Model saved to: model_I.lp")
print("Everything below this line is for post-processing and analysis of results, not part of the optimization model itself.")

#%% 9) Main outputs #unsure if i need this atm /its legacy from task C 
print("\n=== Generator capacities [MW] ===")
print(network.generators.p_nom_opt.sort_values(ascending=False))

print("\n=== Storage capacities [MW] ===")
print(network.storage_units.p_nom_opt.sort_values(ascending=False))

print("\n=== Line loadings (max |flow| / s_nom) ===")
line_loading = network.lines_t.p0.abs().max() / network.lines.s_nom
print(line_loading.sort_values(ascending=False))

home_bus = f"{HOME_COUNTRY} bus"
home_net_import_ts = pd.Series(0.0, index=network.snapshots)

for line_name, row in network.lines.iterrows():
    f = network.lines_t.p0[line_name]
    if row.bus0 == home_bus:
        home_net_import_ts += -f
    elif row.bus1 == home_bus:
        home_net_import_ts += f

print(f"\n{HOME_COUNTRY} annual net import [MWh]: {home_net_import_ts.sum():.0f}")

#%% 10) Simple flow plot for HOME_COUNTRY interconnectors
winter = slice("2015-01-12", "2015-01-18 23:00")
summer = slice("2015-07-13", "2015-07-19 23:00")

home_lines = [
    ln for ln, r in network.lines.iterrows()
    if (r.bus0 == home_bus) or (r.bus1 == home_bus)
]

plt.figure(figsize=(12, 4))
for ln in home_lines:
    r = network.lines.loc[ln]
    f = network.lines_t.p0[ln]
    imp = -f if r.bus0 == home_bus else f
    imp.loc[winter].plot(label=ln)
plt.axhline(0, color="k", linewidth=0.8)
plt.title(f"{HOME_COUNTRY} interconnector flows (positive = import) - winter week")
plt.ylabel("MW")
plt.legend()
plt.tight_layout()
plt.show()

plt.figure(figsize=(12, 4))
for ln in home_lines:
    r = network.lines.loc[ln]
    f = network.lines_t.p0[ln]
    imp = -f if r.bus0 == home_bus else f
    imp.loc[summer].plot(label=ln)
plt.axhline(0, color="k", linewidth=0.8)
plt.title(f"{HOME_COUNTRY} interconnector flows (positive = import) - summer week")
plt.ylabel("MW")
plt.legend()
plt.tight_layout()
plt.show()

#%%

# Hours congested per line
line_loading_ts = network.lines_t.p0.abs().divide(network.lines.s_nom, axis=1)
hours_congested = (line_loading_ts >= 0.999).sum().sort_values(ascending=False)
print("\n=== Hours congested per line [h] ===")
print(hours_congested)





#%% 12) Renewable Curtailment (DEU)
print(f"\n=== Renewable Curtailment in {HOME_COUNTRY} ===")

# Filter for just DEU wind and solar
vre_generators = [f"onshorewind_{HOME_COUNTRY}", f"solar_{HOME_COUNTRY}", f"solar_rooftop_{HOME_COUNTRY}"]

total_available = 0
total_dispatched = 0

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
print(f"Total {HOME_COUNTRY} VRE Curtailment: {total_curtailed:,.0f} MWh ({(total_curtailed/total_available)*100:.2f}%)")






# %%
# Positive means exporter, negative means importer
net_balance = network.buses_t.p.sum() 
print(net_balance)
#%% 16) Total System Cost (Interconnected)
total_cost_interconnected = network.objective
print(f"\n=== Total System Cost (Interconnected) ===")
print(f"Total Cost: € {total_cost_interconnected:,.0f}")


# %%
# Mean electricity price per node
print(network.buses_t.marginal_price.mean())

# %%
# %%



#%%


def print_storage_totals(network, countries):
    h2_gwh = pd.Series({
        c: (float(network.stores.at[f"H2_Tank_{c}", "e_nom_opt"]) / 1000.0
            if f"H2_Tank_{c}" in network.stores.index else 0.0)
        for c in countries
    }, name="H2_GWh")

    battery_gwh = pd.Series({
        c: (float(network.storage_units.at[f"battery_{c}", "p_nom_opt"]) *
            float(network.storage_units.at[f"battery_{c}", "max_hours"]) / 1000.0
            if f"battery_{c}" in network.storage_units.index else 0.0)
        for c in countries
    }, name="Battery_GWh")

    pumped_gwh = pd.Series({
        c: (float(network.storage_units.at[f"Pumped_Hydro_{c}", "p_nom_opt"]) *
            float(network.storage_units.at[f"Pumped_Hydro_{c}", "max_hours"]) / 1000.0
            if f"Pumped_Hydro_{c}" in network.storage_units.index else 0.0)
        for c in countries
    }, name="Pumped_Hydro_GWh")

    df = pd.concat([h2_gwh, battery_gwh, pumped_gwh], axis=1)
    df["Total_GWh"] = df.sum(axis=1)

    print("\n=== Storage capacity by country [GWh] ===")
    print(df.round(3).to_string())

    print("\n=== System totals [GWh] ===")
    print(df.sum().round(3).to_string())


# after network.optimize(...)
print_storage_totals(network, COUNTRIES)

# %%
# ...existing code...
print("\n=== StorageUnits p_nom_opt [MW] ===")
print(network.storage_units[["p_nom_opt", "max_hours"]].round(3))

print("\n=== H2 Stores e_nom_opt [MWh] ===")
print(network.stores[["e_nom_opt"]].round(3))

print("\n=== H2 Links p_nom_opt [MW] ===")
print(network.links.loc[
    network.links.index.str.contains("H2_Electrolysis|H2_Fuel_Cell"),
    ["p_nom_opt"]
].round(3))

print("\n=== Mean nodal prices [€/MWh] ===")
print(network.buses_t.marginal_price.mean().round(2))

#%% 17) Extract Information for Task (e) - Manual PTDF Calculation
print("\n=== Data Extraction for Task (e) ===")

# 1. Get the first time step
t0 = network.snapshots[0]
print(f"First time step: {t0}")

# 2. Network Topology (to build Incidence Matrix K and Reactance Matrix X)
print("\n--- Network Topology (Lines and Reactances) ---")
line_info = network.lines[['bus0', 'bus1', 'x']]
print(line_info.to_string())

print("\n--- List of Buses (Nodes) ---")
print(list(network.buses.index))

# 3. Nodal Imbalances (Generation - Demand) for the first time step
# PyPSA stores the net active power injection at each bus in network.buses_t.p
print(f"\n--- Nodal Imbalances (Net Injection) at {t0} [MW] ---")
imbalances = network.buses_t.p.loc[t0]
print(imbalances.round(2).to_string())

# Note: The sum of these imbalances should be very close to 0 (accounting for minor numerical losses/rounding)
print(f"Sum of imbalances: {imbalances.sum():.4f} MW")

# 4. Modelled Line Flows (to check your manual math at the end)
print(f"\n--- PyPSA Modelled Line Flows at {t0} [MW] ---")
modelled_flows = network.lines_t.p0.loc[t0]
print(modelled_flows.round(2).to_string())

# %%

print("\n=== Heat diagnostics ===")
print("HEAT_HP_COP:", HEAT_HP_COP)
print("HEAT_HP_CAPITAL_COST [€/MW/a?]:", HEAT_HP_CAPITAL_COST)
print("HEAT_STORAGE_CAPITAL_COST [€/MWh/a?]:", HEAT_STORAGE_CAPITAL_COST)
print("HEAT_GAS_BOILER_EFFICIENCY:", HEAT_GAS_BOILER_EFFICIENCY)
print("fuel_cost used [€/MWh_fuel]:", fuel_cost)
print("implied gas boiler marginal [€/MWh_heat]:", fuel_cost / HEAT_GAS_BOILER_EFFICIENCY)

print("\nHeat demand stats [assumed MW]:")
print(df_heat.describe().loc[["mean", "max"]])


# %% 

#%% 18) Sectoral Energy Mix (Generation & Heat)
print("\n=== Electricity Generation Mix (TWh) ===")
# Group generators by carrier and sum their dispatch
elec_gen = network.generators_t.p.sum() / 1e6 # Convert MWh to TWh
elec_mix = elec_gen.groupby(network.generators.carrier).sum()
print(elec_mix)

print("\n=== Heat Production Mix (TWh) ===")
# Heat comes from Gas Boilers (Generators) and Heat Pumps (Links)
heat_from_boilers = network.generators_t.p.loc[:, network.generators.index.str.contains("gas boiler")].sum()
heat_from_hp = (network.links_t.p1.loc[:, network.links.index.str.contains("heat_pump")].abs()).sum()

heat_mix = pd.Series({
    "Gas Boiler": heat_from_boilers.sum() / 1e6,
    "Heat Pump": heat_from_hp.sum() / 1e6
})
print(heat_mix)

#%%
#%% 19) Flexibility & Integration
# Calculate how much electricity the heat pumps consumed
hp_elec_consumption = network.links_t.p0.loc[:, network.links.index.str.contains("heat_pump")].sum().sum() / 1e6
print(f"\nTotal Electricity consumed by Heat Pumps: {hp_elec_consumption:.2f} TWh")

# Check if heat storage is actually being used (Total throughput)
heat_storage_dispatch = network.storage_units_t.p_dispatch.loc[:, network.storage_units.index.str.contains("heat_storage")].sum().sum() / 1e6
print(f"Total Heat Storage Throughput: {heat_storage_dispatch:.2f} TWh")

# %%

#%% Extraction for Task (i): Heat Sector Analysis

# 1. Total Heat Supply by Technology (TWh)
heat_pump_supply = (network.links_t.p1.filter(like="heat_pump").abs().sum() / 1e6) # p1 is output to heat bus
gas_boiler_supply = (network.generators_t.p.filter(like="gas boiler").sum() / 1e6)

heat_mix = pd.DataFrame({
    "Heat Pump [TWh]": heat_pump_supply.rename(index=lambda x: x.split("_")[-1]),
    "Gas Boiler [TWh]": gas_boiler_supply.rename(index=lambda x: x.split(" ")[0])
})

print("\n=== Heat Production Mix by Country ===")
print(heat_mix.round(2))
print(f"\nSystem-wide Heat Pump Share: {100 * heat_mix['Heat Pump [TWh]'].sum() / heat_mix.sum().sum():.1f}%")

#%%

# 2. Storage Throughput (Total energy cycled)
def get_throughput(component_type, name_filter):
    if component_type == "StorageUnit":
        return network.storage_units_t.p_dispatch.filter(like=name_filter).sum().sum() / 1e6
    elif component_type == "Store":
        return network.stores_t.p.filter(like=name_filter).abs().sum().sum() / 1e6

print("\n=== Storage Utilization (TWh) ===")
print(f"Heat Storage Throughput: {get_throughput('StorageUnit', 'heat_storage'):.3f} TWh")
print(f"Battery Throughput:      {get_throughput('StorageUnit', 'battery'):.3f} TWh")
print(f"H2 Storage Throughput:   {get_throughput('Store', 'H2_Tank'):.3f} TWh")
# %%

# ...existing code...

def summarize_results(network, countries, home_country):
    MW_TO_TWh = 1e6

    print("\n================ REPORT SUMMARY ================")

    # 1) Installed capacities
    gen_caps = network.generators.p_nom_opt.groupby(network.generators.carrier).sum()
    stor_caps = network.storage_units.p_nom_opt.groupby(network.storage_units.index.str.extract(r'^(.*?)_')[0]).sum()

    print("\n--- Installed generator capacity by carrier [MW] ---")
    print(gen_caps.round(2).to_string())

    print("\n--- Storage unit installed power by type [MW] ---")
    print(network.storage_units.p_nom_opt.round(2).to_string())

    # 2) Electricity generation mix
    elec_gen_twh = (network.generators_t.p.sum() / MW_TO_TWh).groupby(network.generators.carrier).sum()
    print("\n--- Electricity generation by carrier [TWh] ---")
    print(elec_gen_twh.round(2).to_string())

    # 3) Heat sector mix
    heat_hp_twh = -network.links_t.p1.filter(like="heat_pump").sum().sum() / MW_TO_TWh
    heat_boiler_twh = network.generators_t.p.filter(like="gas boiler").sum().sum() / MW_TO_TWh
    heat_total_twh = heat_hp_twh + heat_boiler_twh

    print("\n--- Heat supply [TWh] ---")
    print(f"Heat pumps:  {heat_hp_twh:.2f}")
    print(f"Gas boilers: {heat_boiler_twh:.2f}")
    print(f"Total heat:  {heat_total_twh:.2f}")
    if heat_total_twh > 0:
        print(f"Heat pump share: {100 * heat_hp_twh / heat_total_twh:.1f}%")

    # 4) Sector coupling
    hp_elec_twh = network.links_t.p0.filter(like="heat_pump").sum().sum() / MW_TO_TWh
    elec_demand_twh = network.loads_t.p.sum().sum() / MW_TO_TWh
    print("\n--- Sector coupling ---")
    print(f"Electricity consumed by heat pumps [TWh]: {hp_elec_twh:.2f}")
    print(f"Electricity demand [TWh]: {elec_demand_twh:.2f}")
    if elec_demand_twh > 0:
        print(f"Heat pump electricity as % of electricity demand: {100 * hp_elec_twh / elec_demand_twh:.1f}%")

    # 5) Storage use
    heat_storage_twh = network.storage_units_t.p_dispatch.filter(like="heat_storage").sum().sum() / MW_TO_TWh
    battery_twh = network.storage_units_t.p_dispatch.filter(like="battery").sum().sum() / MW_TO_TWh
    pumped_hydro_twh = network.storage_units_t.p_dispatch.filter(like="Pumped_Hydro").sum().sum() / MW_TO_TWh

    print("\n--- Storage throughput [TWh] ---")
    print(f"Heat storage:   {heat_storage_twh:.2f}")
    print(f"Battery:        {battery_twh:.2f}")
    print(f"Pumped hydro:   {pumped_hydro_twh:.2f}")

    # 6) Curtailment
    print(f"\n--- Renewable curtailment in {home_country} ---")
    vre_generators = [
        f"onshorewind_{home_country}",
        f"solar_{home_country}",
        f"solar_rooftop_{home_country}",
    ]
    for gen in vre_generators:
        if gen in network.generators.index:
            available = network.generators_t.p_max_pu[gen] * network.generators.p_nom_opt[gen]
            dispatched = network.generators_t.p[gen]
            curtailed = (available - dispatched).sum()
            available_sum = available.sum()
            share = 100 * curtailed / available_sum if available_sum > 0 else 0
            print(f"{gen}: {curtailed:,.0f} MWh curtailed ({share:.2f}% of available)")

    # 7) Imports/exports for home country
    home_bus = f"{home_country} bus"
    net_import_ts = pd.Series(0.0, index=network.snapshots)
    for line_name, row in network.lines.iterrows():
        f = network.lines_t.p0[line_name]
        if row.bus0 == home_bus:
            net_import_ts += -f
        elif row.bus1 == home_bus:
            net_import_ts += f

    print(f"\n--- {home_country} cross-border balance ---")
    print(f"Annual net import [MWh]: {net_import_ts.sum():.0f}")
    print(f"Peak import [MW]: {net_import_ts.max():.2f}")
    print(f"Peak export [MW]: {net_import_ts.min():.2f}")

    # 8) Congestion
    line_loading_ts = network.lines_t.p0.abs().divide(network.lines.s_nom, axis=1)
    hours_congested = (line_loading_ts >= 0.999).sum().sort_values(ascending=False)

    print("\n--- Hours congested per line [h] ---")
    print(hours_congested.to_string())

    # 9) System cost
    print("\n--- Objective value ---")
    print(f"Total system cost [€]: {network.objective:,.0f}")

    # 10) Mean prices
    print("\n--- Mean nodal prices [€/MWh] ---")
    print(network.buses_t.marginal_price.mean().round(2).to_string())


summarize_results(network, COUNTRIES, HOME_COUNTRY)
#%%
# ...existing code...

print("\n=== Country-by-country summary ===")
for c in COUNTRIES:
    elec_demand = network.loads_t.p[f"load_{c}"].sum() / 1e6
    heat_demand = network.loads_t.p[f"heat_load_{c}"].sum() / 1e6
    
    wind = network.generators_t.p[f"onshorewind_{c}"].sum() / 1e6
    solar = (
        network.generators_t.p[f"solar_{c}"].sum() +
        network.generators_t.p[f"solar_rooftop_{c}"].sum()
    ) / 1e6
    hydro = (
        network.generators_t.p[f"run_of_river_{c}"].sum() +
        network.generators_t.p[f"hydro_reservoir_{c}"].sum()
    ) / 1e6
    
    hp_heat = -network.links_t.p1[f"heat_pump_{c}"].sum() / 1e6
    boiler_heat = network.generators_t.p[f"{c} gas boiler"].sum() / 1e6
    
    print(f"\n--- {c} ---")
    print(f"Electricity demand [TWh]: {elec_demand:.2f}")
    print(f"Heat demand [TWh]:        {heat_demand:.2f}")
    print(f"Wind generation [TWh]:    {wind:.2f}")
    print(f"Solar generation [TWh]:   {solar:.2f}")
    print(f"Hydro generation [TWh]:   {hydro:.2f}")
    print(f"Heat pumps [TWh]:         {hp_heat:.2f}")
    print(f"Gas boilers [TWh]:        {boiler_heat:.2f}")
# ...existing code...
#%%