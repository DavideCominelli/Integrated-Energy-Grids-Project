#%%
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
total_capital_cost_pumped_hydro = (
    capital_cost_pumped_hydro_power
    + capital_cost_pumped_hydro_energy * tech_data["Pumped_Hydro"]["max_hours"]
)

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

capital_cost_h2_tank = annuity(25, 0.07) * 57000 * (1 + 0.011)
capital_cost_h2_electrolyser = annuity(25, 0.07) * 600000 * (1 + 0.05)
capital_cost_h2_fuel_cell = annuity(10, 0.07) * 1300000 * (1 + 0.05)

#%% 7) Add all country systems (all technologies in loop)
for c in COUNTRIES:
    network.add(
        "Load",
        f"load_{c}",
        bus=f"{c} bus",
        p_set=df_elec[c].values,
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
        capital_cost=total_capital_cost_pumped_hydro,
        max_hours=tech_data["Pumped_Hydro"]["max_hours"],
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
        max_hours=tech_data["battery"]["max_hours"],
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
        efficiency=0.8,
        capital_cost=capital_cost_h2_electrolyser,
    )

    network.add(
        "Link",
        f"H2_Fuel_Cell_{c}",
        bus0=h2_bus,
        bus1=f"{c} bus",
        p_nom_extendable=True,
        efficiency=0.58,
        capital_cost=capital_cost_h2_fuel_cell,
    )

#%% 8) Optimise
network.optimize(solver_name="gurobi", solver_options={"output_flag": 0})

network.model.to_file("model_D.lp")
print("Model saved to: model_D.lp")

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



#%% 11) Map plot: storage (H2) + transmission lines
def plot_storage_and_lines_map(network, coords, countries):
    fig = plt.figure(figsize=(10, 7))
    ax = plt.axes(projection=ccrs.PlateCarree())

    # map extent around central Europe
    lons = [coords[c][0] for c in countries]
    lats = [coords[c][1] for c in countries]
    pad_lon, pad_lat = 8, 6
    ax.set_extent(
        [min(lons) - pad_lon, max(lons) + pad_lon, min(lats) - pad_lat, max(lats) + pad_lat],
        crs=ccrs.PlateCarree(),
    )

    ax.add_feature(cfeature.LAND, facecolor="#e8e4a8", edgecolor="none")
    ax.add_feature(cfeature.OCEAN, facecolor="#9bc6d8", edgecolor="none")
    ax.add_feature(cfeature.COASTLINE, linewidth=0.5, edgecolor="gray")
    ax.add_feature(cfeature.BORDERS, linewidth=0.4, edgecolor="gray")

    # --- transmission lines (width by s_nom) ---
    s_nom = network.lines["s_nom"]
    lw_min, lw_max = 1.5, 14.0
    smin, smax = float(s_nom.min()), float(s_nom.max())

    for line_name, row in network.lines.iterrows():
        c0 = row.bus0.split()[0]  # "DEU bus" -> "DEU"
        c1 = row.bus1.split()[0]
        x0, y0 = coords[c0]
        x1, y1 = coords[c1]

        if smax > smin:
            lw = lw_min + (row.s_nom - smin) / (smax - smin) * (lw_max - lw_min)
        else:
            lw = (lw_min + lw_max) / 2

        ax.plot([x0, x1], [y0, y1], color="gray", linewidth=lw, alpha=0.9, transform=ccrs.PlateCarree(), zorder=2)

    # --- storage bubbles: H2 tanks in GWh ---
    h2_gwh = {}
    for c in countries:
        store_name = f"H2_Tank_{c}"
        e_mwh = network.stores.at[store_name, "e_nom_opt"] if store_name in network.stores.index else 0.0
        h2_gwh[c] = e_mwh / 1000.0

    vals = np.array([h2_gwh[c] for c in countries], dtype=float)
    vmin, vmax = vals.min(), vals.max()

    s_min, s_max = 700, 2600  # marker areas
    for c in countries:
        x, y = coords[c]
        v = h2_gwh[c]
        if vmax > vmin:
            size = s_min + (v - vmin) / (vmax - vmin) * (s_max - s_min)
        else:
            size = (s_min + s_max) / 2
        ax.scatter(
            x, y,
            s=size,
            color="#f2b6c6", edgecolor="none", alpha=0.95,
            transform=ccrs.PlateCarree(), zorder=3
        )

    ax.set_title("Installed storage capacities and transmission lines", fontsize=15)

    # --- legends ---
    # line legend (reference widths)
    line_handles = [
        Line2D([0], [0], color="gray", lw=2, label="100 MW"),
        Line2D([0], [0], color="gray", lw=8, label="1000 MW"),
    ]
    leg1 = ax.legend(handles=line_handles, loc="upper left", frameon=False, title=None)
    ax.add_artist(leg1)

    # bubble legend (reference sizes)
    bubble_10 = plt.scatter([], [], s=s_min + 0.1*(s_max - s_min), color="#f2b6c6", label="10 GWh")
    bubble_100 = plt.scatter([], [], s=s_min + 0.9*(s_max - s_min), color="#f2b6c6", label="100 GWh")
    leg2 = ax.legend(handles=[bubble_10, bubble_100], loc="lower right", frameon=False, title="H2")
    ax.add_artist(leg2)

    plt.tight_layout()
    plt.show()


# call after optimize
plot_storage_and_lines_map(network, COORDS, COUNTRIES)
# %% keyerror load
#if i want to add it i need to make a new formula that does load_{c} for country
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



#%% 13) Nodal Prices (Market Convergence)
# Let's look at a winter week where congestion is likely
winter_week = slice("2015-01-12", "2015-01-18 23:00")

plt.figure(figsize=(10, 5))
network.buses_t.marginal_price["DEU bus"].loc[winter_week].plot(label="Germany (DEU)", color="blue")
network.buses_t.marginal_price["CZE bus"].loc[winter_week].plot(label="Czechia (CZE)", color="orange")

plt.title("Wholesale Electricity Prices: Germany vs Czechia (Winter Week)")
plt.ylabel("Price (€ / MWh)")
plt.legend()
plt.tight_layout()
plt.show()

#%% 14) Import/Export Duration Curve for DEU
# Sort the net imports from highest (max import) to lowest (max export)
sorted_imports = home_net_import_ts.sort_values(ascending=False).values

plt.figure(figsize=(10, 5))
plt.plot(sorted_imports, color="purple", linewidth=2)
plt.axhline(0, color="black", linestyle="--")
plt.fill_between(range(len(sorted_imports)), sorted_imports, 0, where=(sorted_imports > 0), color="red", alpha=0.3, label="Net Import Hours")
plt.fill_between(range(len(sorted_imports)), sorted_imports, 0, where=(sorted_imports < 0), color="green", alpha=0.3, label="Net Export Hours")

plt.title(f"{HOME_COUNTRY} Net Import Duration Curve")
plt.xlabel("Hours of the year (Sorted)")
plt.ylabel("Net Import (MW) -> Negative means Export")
plt.legend()
plt.tight_layout()
plt.show()

#%% 15) Regional Capacity Mix Comparison
import seaborn as sns

# Extract capacities and carriers
caps = network.generators.p_nom_opt.copy()
caps.index = network.generators.carrier
df_caps = caps.reset_index()
df_caps.columns = ["Carrier", "Capacity (MW)"]

# Map generators to their respective countries
country_map = []
for gen_name in network.generators.index:
    # Extracts the last 3 letters (e.g., 'DEU' from 'onshorewind_DEU')
    country_map.append(gen_name[-3:]) 
df_caps["Country"] = country_map

# Pivot the data for a stacked bar chart
pivot_caps = df_caps.groupby(["Country", "Carrier"])["Capacity (MW)"].sum().unstack().fillna(0)

# Plot
pivot_caps.plot(kind="bar", stacked=True, figsize=(10, 6), colormap="tab20")
plt.title("Optimal Generation Capacity Mix by Country")
plt.ylabel("Installed Capacity (MW)")
plt.xlabel("Country")
plt.legend(title="Technology", bbox_to_anchor=(1.05, 1), loc='upper left')
plt.tight_layout()
plt.show()
# %%
#%% 16) Total System Cost (Interconnected)
total_cost_interconnected = network.objective
print(f"\n=== Total System Cost (Interconnected) ===")
print(f"Total Cost: € {total_cost_interconnected:,.0f}")