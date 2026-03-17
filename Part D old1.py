#%%
import pandas as pd
import pypsa
import matplotlib.pyplot as plt

from data.data import tech_data
from utils import annuity

#%% 1) Settings
HOME_COUNTRY = "DEU"
COUNTRIES = ["DEU", "CHE", "CZE", "AUT"]  # DEU + 3 neighbours

# Fixed yearly interconnector capacities [MW]
INTERCONNECTORS_MW = {
    ("DEU", "CHE"): 4200,
    ("DEU", "CZE"): 2900,
    ("DEU", "AUT"): 4900,
    ("CZE", "AUT"): 900,
    ("AUT", "CHE"): 1200,  # closed cycle exists
}

COORDS = {
    "DEU": (10.45, 51.16),
    "CHE": (8.23, 46.82),
    "CZE": (15.47, 49.82),
    "AUT": (14.55, 47.51),
}

#%% 2) Build network and snapshots
network = pypsa.Network()

# add snapshots for the whole year of 2015 in hourly resolution
hours_in_2015 = pd.date_range('2015-01-01 00:00Z',
                              '2015-12-31 23:00Z',
                              freq='h')

network.set_snapshots(hours_in_2015.values)
# this part ^ is the same as hours_in_2015 in Part C, (but my copilot called it something else)
#Ill edit it later, but for now snapshot is used below

#%% 3) Add buses (400 kV) and carriers
network.add("Carrier", "AC")
network.add("Carrier", "gas", co2_emissions=0.19)
network.add("Carrier", "onshorewind")
network.add("Carrier", "solar")
network.add("Carrier", "hydro")
network.add("Carrier", "battery")
network.add("Carrier", "H2")

for c in COUNTRIES:
    x, y = COORDS[c]
    network.add(
        "Bus",
        f"{c} bus",
        carrier="AC",
        v_nom=400,   # task requirement
        #should i add "lenght=x"
        x=x,
        y=y,
    )

#%% 4) Add fixed HVAC interconnectors (DC approximation via linear OPF)
# x=0.1 as requested
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

snapshot_cols = [h.strftime("%Y-%m-%dT%H:%M:%SZ") for h in network.snapshots]

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

#%% 7) Add country systems (co-optimise all countries)
for c in COUNTRIES:
    # Load
    network.add(
        "Load",
        f"load_{c}",
        bus=f"{c} bus",
        p_set=df_elec[c].values,
    )

    # Capacity factors
    cf_wind = df_wind[c][snapshot_cols].values
    cf_solar = df_solar[c][snapshot_cols].values

    # Generators
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
        f"OCGT_{c}",
        bus=f"{c} bus",
        p_nom_extendable=True,
        carrier="gas",
        capital_cost=capital_cost_OCGT,
        marginal_cost=marginal_cost_OCGT,
    )

# Optional: keep hydro fixed only in DEU (from Part C assumptions)
network.add(
    "Generator",
    "run_of_river_DEU",
    bus="DEU bus",
    p_nom=tech_data["run_of_river"]["fixed_capacity"],
    carrier="hydro",
    capital_cost=0,
    marginal_cost=0,
    p_max_pu=tech_data["run_of_river"]["availability"],
)

network.add(
    "Generator",
    "hydro_reservoir_DEU",
    bus="DEU bus",
    p_nom=tech_data["hydro_reservoir"]["fixed_capacity"],
    carrier="hydro",
    capital_cost=0,
    marginal_cost=0,
    p_max_pu=tech_data["hydro_reservoir"]["availability"],
)

#%% 8) Keep DEU storage from Part C (optional, but useful for comparison)
# Battery in DEU
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
total_capital_cost_battery = (
    capital_cost_battery_power
    + capital_cost_battery_energy * tech_data["battery"]["max_hours"]
)

network.add(
    "StorageUnit",
    "battery_DEU",
    bus="DEU bus",
    p_nom_extendable=True,
    capital_cost=total_capital_cost_battery,
    max_hours=tech_data["battery"]["max_hours"],
    efficiency_store=tech_data["battery"]["efficiency_store"],
    efficiency_dispatch=tech_data["battery"]["efficiency_dispatch"],
    cyclic_state_of_charge=True,
    p_min_pu=-1,
)




#%% 9) Optimise (linear OPF => DC approximation with lines)
network.optimize(solver_name="gurobi")

network.model.to_file("model_D.lp")
print("Model saved to: model_D.lp")

#%% 10) Main outputs
print("\n=== Generator capacities [MW] ===")
print(network.generators.p_nom_opt.sort_values(ascending=False))

print("\n=== Storage capacities [MW] ===")
print(network.storage_units.p_nom_opt.sort_values(ascending=False))

print("\n=== Line loadings (max |flow| / s_nom) ===")
line_loading = network.lines_t.p0.abs().max() / network.lines.s_nom
print(line_loading.sort_values(ascending=False))

# DEU net imports (MWh): positive = net import
deu_bus = "DEU bus"
deu_net_import_ts = pd.Series(0.0, index=network.snapshots)

for line_name, row in network.lines.iterrows():
    f = network.lines_t.p0[line_name]  # positive bus0 -> bus1
    if row.bus0 == deu_bus:
        deu_net_import_ts += -f
    elif row.bus1 == deu_bus:
        deu_net_import_ts += f

print(f"\nDEU annual net import [MWh]: {deu_net_import_ts.sum():.0f}")

#%% 11) Simple flow plot for DEU interconnectors (one winter week + one summer week)
winter = slice("2015-01-12", "2015-01-18 23:00")
summer = slice("2015-07-13", "2015-07-19 23:00")

deu_lines = [
    ln for ln, r in network.lines.iterrows()
    if (r.bus0 == deu_bus) or (r.bus1 == deu_bus)
]

plt.figure(figsize=(12, 4))
for ln in deu_lines:
    r = network.lines.loc[ln]
    f = network.lines_t.p0[ln]
    # orient as positive import to DEU
    if r.bus0 == deu_bus:
        imp = -f
    else:
        imp = f
    imp.loc[winter].plot(label=ln)
plt.axhline(0, color="k", linewidth=0.8)
plt.title("DEU interconnector flows (positive = import) - winter week")
plt.ylabel("MW")
plt.legend()
plt.tight_layout()
plt.show()

plt.figure(figsize=(12, 4))
for ln in deu_lines:
    r = network.lines.loc[ln]
    f = network.lines_t.p0[ln]
    if r.bus0 == deu_bus:
        imp = -f
    else:
        imp = f
    imp.loc[summer].plot(label=ln)
plt.axhline(0, color="k", linewidth=0.8)
plt.title("DEU interconnector flows (positive = import) - summer week")
plt.ylabel("MW")
plt.legend()
plt.tight_layout()
plt.show()

#%%

