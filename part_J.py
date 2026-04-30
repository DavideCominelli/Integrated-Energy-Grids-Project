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

# NIMBY: set fixed onshore wind capacity for Germany (MW).
# Set to None to keep onshore wind extendable as before.
NIMBY_ONSHORE_DEU_CAP_MW = 68000

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

    cf_wind = df_wind[c][snapshot_cols].values
    cf_solar = df_solar[c][snapshot_cols].values

    # If NIMBY fixed capacity is set for Germany, create a fixed (non-extendable) generator
    if c == "DEU" and NIMBY_ONSHORE_DEU_CAP_MW is not None:
        network.add(
            "Generator",
            f"onshorewind_{c}",
            bus=f"{c} bus",
            p_nom=NIMBY_ONSHORE_DEU_CAP_MW,
            p_nom_extendable=False,
            carrier="onshorewind",
            capital_cost=capital_cost_onshorewind,
            marginal_cost=0,
            p_max_pu=cf_wind,
        )
    else:
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
network.optimize(solver_name="gurobi", solver_options={"output_flag": 0})

network.model.to_file("model_D.lp")
print("Model saved to: model_D.lp")
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

from pypsa.plot import add_legend_patches


#%% 11) Map plot (PyPSA style): storage mix pies + transmission lines


# Disable the failing PyPSA-style map call
# plot_storage_mix_and_lines_pypsa(network, COUNTRIES)

def plot_storage_all_and_lines_map(network, coords, countries):
    fig = plt.figure(figsize=(10, 7))
    ax = plt.axes(projection=ccrs.PlateCarree())

    lons = [coords[c][0] for c in countries]
    lats = [coords[c][1] for c in countries]
    pad_lon, pad_lat = 3.0, 2.5
    ax.set_extent(
        [min(lons) - pad_lon, max(lons) + pad_lon, min(lats) - pad_lat, max(lats) + pad_lat],
        crs=ccrs.PlateCarree(),
    )

    ax.add_feature(cfeature.LAND, facecolor="#e8e4a8", edgecolor="none")
    ax.add_feature(cfeature.OCEAN, facecolor="#9bc6d8", edgecolor="none")
    ax.add_feature(cfeature.COASTLINE, linewidth=0.5, edgecolor="gray")
    ax.add_feature(cfeature.BORDERS, linewidth=0.4, edgecolor="gray")

    # --- lines ---
    s_nom = network.lines["s_nom"]
    lw_min, lw_max = 1.5, 14.0
    smin, smax = float(s_nom.min()), float(s_nom.max())

    for _, row in network.lines.iterrows():
        c0 = row.bus0.split()[0]
        c1 = row.bus1.split()[0]
        x0, y0 = coords[c0]
        x1, y1 = coords[c1]
        if smax > smin:
            lw = lw_min + (row.s_nom - smin) / (smax - smin) * (lw_max - lw_min)
        else:
            lw = (lw_min + lw_max) / 2
        ax.plot(
            [x0, x1], [y0, y1],
            color="gray",
            linewidth=lw,
            alpha=0.9,
            transform=ccrs.PlateCarree(),
            zorder=2,
        )

    # --- storage values [GWh] ---
    h2, batt, ph, total = {}, {}, {}, {}
    for c in countries:
        h2_name = f"H2_Tank_{c}"
        b_name = f"battery_{c}"
        ph_name = f"Pumped_Hydro_{c}"

        h2[c] = float(network.stores.at[h2_name, "e_nom_opt"]) / 1000.0 if h2_name in network.stores.index else 0.0
        batt[c] = (
            float(network.storage_units.at[b_name, "p_nom_opt"]) * float(network.storage_units.at[b_name, "max_hours"]) / 1000.0
            if b_name in network.storage_units.index else 0.0
        )
        ph[c] = (
            float(network.storage_units.at[ph_name, "p_nom_opt"]) * float(network.storage_units.at[ph_name, "max_hours"]) / 1000.0
            if ph_name in network.storage_units.index else 0.0
        )
        total[c] = h2[c] + batt[c] + ph[c]

    # Bubble area scale (points^2 per GWh)
    area_scale = 20.0
    s_min, s_max = 80.0, 2600.0

    def size_from_gwh(gwh):
        return float(np.clip(gwh * area_scale, s_min, s_max))

    # draw pie bubble at (x, y) via wedge markers
    def draw_pie_bubble(x, y, values, colors, s):
        t = sum(values)
        if t <= 0:
            return
        start = 0.0
        for v, col in zip(values, colors):
            if v <= 0:
                continue
            frac = v / t
            theta = np.linspace(2 * np.pi * start, 2 * np.pi * (start + frac), 40)
            verts = np.column_stack([np.r_[0, np.cos(theta), 0], np.r_[0, np.sin(theta), 0]])
            ax.scatter(
                [x], [y],
                marker=verts,
                s=s,
                facecolor=col,
                edgecolor="none",
                alpha=0.95,
                transform=ccrs.PlateCarree(),
                zorder=5
            )
            start += frac

        # outline
        ax.scatter(
            [x], [y],
            s=s,
            marker="o",
            facecolor="none",
            edgecolor="black",
            linewidth=0.5,
            transform=ccrs.PlateCarree(),
            zorder=6
        )

    colors = ["#f2b6c6", "#6cc24a", "#8c6d31"]  # H2, Battery, Pumped Hydro

    for c in countries:
        x, y = coords[c]
        s = size_from_gwh(total[c])
        draw_pie_bubble(x, y, [h2[c], batt[c], ph[c]], colors, s)

    ax.set_title("Installed storage capacities and transmission lines", fontsize=15)

    # Legends
    leg_lines = ax.legend(
        handles=[
            Line2D([0], [0], color="gray", lw=2, label="100 MW"),
            Line2D([0], [0], color="gray", lw=8, label="1000 MW"),
        ],
        loc="upper left",
        frameon=False,
        title="Lines",
    )
    ax.add_artist(leg_lines)

    leg_types = ax.legend(
        handles=[
            Line2D([0], [0], marker="o", linestyle="None", markerfacecolor="#f2b6c6", markeredgecolor="black", label="H2"),
            Line2D([0], [0], marker="o", linestyle="None", markerfacecolor="#6cc24a", markeredgecolor="black", label="Battery"),
            Line2D([0], [0], marker="o", linestyle="None", markerfacecolor="#8c6d31", markeredgecolor="black", label="Pumped Hydro"),
        ],
        loc="lower right",
        frameon=False,
        title="Storage share",
    )
    ax.add_artist(leg_types)

    # Use smaller proxy marker sizes in legend to avoid text overlap
    ms10 = 10
    ms100 = 18

    # Convert scatter area (points^2) to legend marker size (points)
    def legend_ms_from_gwh(gwh):
        return np.sqrt(size_from_gwh(gwh))

    ms10 = legend_ms_from_gwh(10.0)
    ms100 = legend_ms_from_gwh(100.0)

    leg_size = ax.legend(
        handles=[
            Line2D([0], [0], marker="o", linestyle="None",
                   markerfacecolor="lightgray", markeredgecolor="black",
                   markersize=ms10, label="10 GWh"),
            Line2D([0], [0], marker="o", linestyle="None",
                   markerfacecolor="lightgray", markeredgecolor="black",
                   markersize=ms100, label="100 GWh"),
        ],
        loc="upper right",
        frameon=False,
        title="Total storage",
        labelspacing=2.3,
        handletextpad=1.8,
        borderpad=0.4,
    )
    ax.add_artist(leg_size)

    plt.show()


plot_storage_all_and_lines_map(network, COORDS, COUNTRIES)




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
# %%
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
# ...existing code...

def plot_country_nodes_and_lines_map(network, coords, countries):
    fig = plt.figure(figsize=(10, 7))
    ax = plt.axes(projection=ccrs.PlateCarree())

    # map extent
    lons = [coords[c][0] for c in countries]
    lats = [coords[c][1] for c in countries]
    pad_lon = 3.0
    pad_lat_south = 1.5
    pad_lat_north = 0.8   # smaller value => less far north shown

    ax.set_extent(
        [
            min(lons) - pad_lon,
            max(lons) + pad_lon,
            min(lats) - pad_lat_south,
            max(lats) + pad_lat_north,
        ],
        crs=ccrs.PlateCarree(),
    )

    # background
    ax.add_feature(cfeature.LAND, facecolor="#e8e4a8", edgecolor="none")
    ax.add_feature(cfeature.OCEAN, facecolor="#9bc6d8", edgecolor="none")
    ax.add_feature(cfeature.COASTLINE, linewidth=0.5, edgecolor="gray")
    ax.add_feature(cfeature.BORDERS, linewidth=0.4, edgecolor="gray")

    # transmission lines: width scaled by s_nom
    s_nom = network.lines["s_nom"]
    lw_min, lw_max = 1.5, 14.0
    smin, smax = float(s_nom.min()), float(s_nom.max())

    for _, row in network.lines.iterrows():
        c0 = row.bus0.split()[0]
        c1 = row.bus1.split()[0]
        x0, y0 = coords[c0]
        x1, y1 = coords[c1]

        if smax > smin:
            lw = lw_min + (row.s_nom - smin) / (smax - smin) * (lw_max - lw_min)
        else:
            lw = (lw_min + lw_max) / 2

        ax.plot(
            [x0, x1], [y0, y1],
            color="gray",
            linewidth=lw,
            alpha=0.9,
            transform=ccrs.PlateCarree(),
            zorder=2,
        )

    # always draw 1 bubble per country (fixed size)
    bubble_size = 1200  # points^2
    for c in countries:
        x, y = coords[c]
        ax.scatter(
            x, y,
            s=bubble_size,
            color="#cfcfcf",
            edgecolor="black",
            linewidth=0.7,
            transform=ccrs.PlateCarree(),
            zorder=5,
        )
        ax.text(
            x + 0.25, y + 0.15, c,
            fontsize=9,
            transform=ccrs.PlateCarree(),
            zorder=6,
        )

    ax.set_title("Country nodes and transmission lines", fontsize=15)

    # line legend only
    leg_lines = ax.legend(
        handles=[
            Line2D([0], [0], color="gray", lw=2, label="100 MW"),
            Line2D([0], [0], color="gray", lw=8, label="1000 MW"),
        ],
        loc="upper left",
        frameon=False,
        title="Lines",
    )
    ax.add_artist(leg_lines)

    plt.tight_layout()
    plt.show()

# Use this instead of the storage pie map
plot_country_nodes_and_lines_map(network, COORDS, COUNTRIES)

# ...existing code...
# %%
# ...existing code...

def extra_metrics(network, home_country="DEU"):
    home_bus = f"{home_country} bus"
    load_name = f"load_{home_country}"

    # Demand
    deu_demand_mwh = float(network.loads_t.p_set[load_name].sum())
    total_demand_mwh = float(network.loads_t.p_set.sum().sum())

    # DEU generators and dispatch
    deu_gen_idx = network.generators.index[network.generators.bus == home_bus]
    deu_gen_t = network.generators_t.p[deu_gen_idx]
    deu_gen_total_mwh = float(deu_gen_t.sum().sum())

    # By carrier
    deu_gens = network.generators.loc[deu_gen_idx]
    ren_mask = deu_gens.carrier.isin(["onshorewind", "solar", "hydro"])
    gas_mask = deu_gens.carrier.eq("gas")

    deu_ren_mwh = float(deu_gen_t[deu_gens.index[ren_mask]].sum().sum()) if ren_mask.any() else 0.0
    deu_gas_mwh = float(deu_gen_t[deu_gens.index[gas_mask]].sum().sum()) if gas_mask.any() else 0.0

    # Curtailment (DEU wind + solar + rooftop solar)
    vre_units = [f"onshorewind_{home_country}", f"solar_{home_country}", f"solar_rooftop_{home_country}"]
    vre_units = [g for g in vre_units if g in network.generators.index]
    if vre_units:
        available = (network.generators_t.p_max_pu[vre_units] * network.generators.p_nom_opt[vre_units]).sum().sum()
        dispatched = network.generators_t.p[vre_units].sum().sum()
        curtailment_pct = float((available - dispatched) / available * 100) if available > 0 else 0.0
    else:
        curtailment_pct = 0.0

    # Net imports for DEU (positive = import)
    net_import_ts = pd.Series(0.0, index=network.snapshots)
    for line_name, row in network.lines.iterrows():
        f = network.lines_t.p0[line_name]
        if row.bus0 == home_bus:
            net_import_ts += -f
        elif row.bus1 == home_bus:
            net_import_ts += f
    deu_net_import_mwh = float(net_import_ts.sum())

    # Prices
    deu_price = network.buses_t.marginal_price[home_bus]
    deu_price_mean = float(deu_price.mean())
    deu_price_std = float(deu_price.std())
    deu_price_p95 = float(deu_price.quantile(0.95))

    # Congestion on DEU-connected lines
    deu_lines = [ln for ln, r in network.lines.iterrows() if (r.bus0 == home_bus or r.bus1 == home_bus)]
    if deu_lines:
        loading = network.lines_t.p0[deu_lines].abs().divide(network.lines.loc[deu_lines, "s_nom"], axis=1)
        deu_congestion_hours = int((loading >= 0.999).sum().sum())
    else:
        deu_congestion_hours = 0

    # System cost intensity
    system_cost_per_mwh = float(network.objective / total_demand_mwh) if total_demand_mwh > 0 else np.nan

    out = pd.Series({
        "System cost [B€]": network.objective / 1e9,
        "System cost intensity [€/MWh]": system_cost_per_mwh,
        "DEU demand [TWh]": deu_demand_mwh / 1e6,
        "DEU generation [TWh]": deu_gen_total_mwh / 1e6,
        "DEU renewable generation [TWh]": deu_ren_mwh / 1e6,
        "DEU gas generation [TWh]": deu_gas_mwh / 1e6,
        "DEU renewable share of demand [%]": (deu_ren_mwh / deu_demand_mwh * 100) if deu_demand_mwh > 0 else np.nan,
        "DEU curtailment (wind+solar) [%]": curtailment_pct,
        "DEU net import [TWh]": deu_net_import_mwh / 1e6,
        "DEU import dependency [% demand]": (deu_net_import_mwh / deu_demand_mwh * 100) if deu_demand_mwh > 0 else np.nan,
        "DEU mean price [€/MWh]": deu_price_mean,
        "DEU price std [€/MWh]": deu_price_std,
        "DEU price p95 [€/MWh]": deu_price_p95,
        "DEU-connected congestion hours [h]": deu_congestion_hours,
    })

    return out

m = extra_metrics(network, HOME_COUNTRY)
print("\n=== Additional useful metrics ===")
print(m.to_string(float_format=lambda x: f"{x:,.2f}"))
# ...existing code...
# %%
# Quick curtailment check
vre_gen = [f"onshorewind_{HOME_COUNTRY}", f"solar_{HOME_COUNTRY}", f"solar_rooftop_{HOME_COUNTRY}"]
available = (network.generators_t.p_max_pu[vre_gen] * network.generators.p_nom_opt[vre_gen]).sum().sum()
curtailed = available - network.generators_t.p[vre_gen].sum().sum()
print(f"Curtailment: {curtailed:,.0f} MWh ({curtailed/available*100:.1f}%)")
# %%

def objective_breakdown(n):
    w = n.snapshot_weightings.objective  # snapshot weights used in objective

    # CAPEX (only extendable assets)
    gen_capex = (n.generators.loc[n.generators.p_nom_extendable, "capital_cost"]
                 * n.generators.loc[n.generators.p_nom_extendable, "p_nom_opt"]).sum()

    su_capex = (n.storage_units.loc[n.storage_units.p_nom_extendable, "capital_cost"]
                * n.storage_units.loc[n.storage_units.p_nom_extendable, "p_nom_opt"]).sum()

    link_capex = (n.links.loc[n.links.p_nom_extendable, "capital_cost"]
                  * n.links.loc[n.links.p_nom_extendable, "p_nom_opt"]).sum()

    store_capex = (n.stores.loc[n.stores.e_nom_extendable, "capital_cost"]
                   * n.stores.loc[n.stores.e_nom_extendable, "e_nom_opt"]).sum()

    line_capex = 0.0
    if "s_nom_extendable" in n.lines.columns and n.lines.s_nom_extendable.any():
        line_capex = (n.lines.loc[n.lines.s_nom_extendable, "capital_cost"]
                      * n.lines.loc[n.lines.s_nom_extendable, "s_nom_opt"]).sum()

    # OPEX (marginal costs)
    gen_opex = (
        n.generators_t.p.mul(w, axis=0)
        .mul(n.generators.marginal_cost, axis=1)
        .sum().sum()
    )

    su_opex = 0.0
    if (n.storage_units.marginal_cost != 0).any():
        su_opex = (
            n.storage_units_t.p.mul(w, axis=0)
            .mul(n.storage_units.marginal_cost, axis=1)
            .sum().sum()
        )

    link_opex = 0.0
    if (n.links.marginal_cost != 0).any():
        link_opex = (
            n.links_t.p0.mul(w, axis=0)
            .mul(n.links.marginal_cost, axis=1)
            .sum().sum()
        )

    parts = pd.Series({
        "Generator CAPEX": gen_capex,
        "StorageUnit CAPEX": su_capex,
        "Link CAPEX": link_capex,
        "Store CAPEX": store_capex,
        "Line CAPEX": line_capex,
        "Generator OPEX": gen_opex,
        "StorageUnit OPEX": su_opex,
        "Link OPEX": link_opex,
    })

    total_from_parts = parts.sum()
    print("\n=== Objective breakdown [€] ===")
    print(parts.round(2).to_string())
    print(f"\nSum of parts: {total_from_parts:,.2f} €")
    print(f"network.objective: {n.objective:,.2f} €")
    print(f"Difference: {n.objective - total_from_parts:,.2f} €")

objective_breakdown(network)

# ...existing code...
# %%
# ...existing code...

def print_generator_capex_breakdown(network):
    g = network.generators.copy()

    # Objective-relevant generator CAPEX (capacity decision variables)
    g["capex_eur"] = 0.0
    ext = g["p_nom_extendable"].fillna(False)
    g.loc[ext, "capex_eur"] = g.loc[ext, "capital_cost"] * g.loc[ext, "p_nom_opt"]

    # Helpful columns
    g["country"] = g["bus"].str.split().str[0]
    cols = ["bus", "carrier", "p_nom_extendable", "p_nom_opt", "capital_cost", "capex_eur"]
    g_out = g[cols + ["country"]].sort_values("capex_eur", ascending=False)

    print("\n=== Generator CAPEX by unit [€] ===")
    print(g_out.round(2).to_string())

    print("\n=== Generator CAPEX by carrier [€] ===")
    print(g_out.groupby("carrier")["capex_eur"].sum().sort_values(ascending=False).round(2).to_string())

    print("\n=== Generator CAPEX by country [€] ===")
    print(g_out.groupby("country")["capex_eur"].sum().sort_values(ascending=False).round(2).to_string())

    print(f"\nTotal generator CAPEX (from units): € {g_out['capex_eur'].sum():,.2f}")

print_generator_capex_breakdown(network)

