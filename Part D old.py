#%% 1) Imports
import pandas as pd
import matplotlib.pyplot as plt
import pypsa

from data.data import tech_data
from utils import annuity


#%% 2) Settings
YEAR = 2015
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


#%% 3) Build network + snapshots
n = pypsa.Network()
hours = pd.date_range(f"{YEAR}-01-01 00:00Z", f"{YEAR}-12-31 23:00Z", freq="h")
n.set_snapshots(hours.values)

# Part C carriers + multi-country
n.add("Carrier", "gas", co2_emissions=0.19)
n.add("Carrier", "onshorewind")
n.add("Carrier", "solar")
n.add("Carrier", "hydro")
n.add("Carrier", "battery")
n.add("Carrier", "H2")

# 400 kV assumption is here
for c in COUNTRIES:
    x, y = COORDS[c]
    n.add("Bus", c, x=x, y=y, v_nom=400, carrier="AC")


#%% 4) Demand
df_elec = pd.read_csv("data/electricity_demand.csv", sep=";", index_col=0)
df_elec.index = pd.to_datetime(df_elec.index)

for c in COUNTRIES:
    n.add("Load", f"{c} load", bus=c, p_set=df_elec[c].values)


#%% 5) Weather data + costs (same logic as Part C)
df_wind = pd.read_csv("data/onshore_wind_1979-2017.csv", sep=";", index_col=0)
df_wind.index = pd.to_datetime(df_wind.index)

df_solar = pd.read_csv("data/pv_optimal.csv", sep=";", index_col=0)
df_solar.index = pd.to_datetime(df_solar.index)

snapshot_str = [h.strftime("%Y-%m-%dT%H:%M:%SZ") for h in n.snapshots]

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
capital_cost_ocgt = (
    annuity(tech_data["OCGT"]["lifetime"], 0.07)
    * tech_data["OCGT"]["overnight_cost"]
    * (1 + tech_data["OCGT"]["capital_cost_increase"])
)

fuel_cost = tech_data["OCGT"]["fuel_cost"]
efficiency_ocgt = tech_data["OCGT"]["efficiency"]
marginal_cost_ocgt = fuel_cost / efficiency_ocgt


#%% 6) Add generators in all countries (co-optimised)
for c in COUNTRIES:
    cf_wind = df_wind[c][snapshot_str].values
    cf_solar = df_solar[c][snapshot_str].values

    n.add("Generator", f"{c} onshorewind",
          bus=c, carrier="onshorewind",
          p_nom_extendable=True,
          capital_cost=capital_cost_onshorewind,
          marginal_cost=0,
          p_max_pu=cf_wind)

    n.add("Generator", f"{c} solar",
          bus=c, carrier="solar",
          p_nom_extendable=True,
          capital_cost=capital_cost_solar,
          marginal_cost=0,
          p_max_pu=cf_solar)

    n.add("Generator", f"{c} solar_rooftop",
          bus=c, carrier="solar",
          p_nom_extendable=True,
          capital_cost=capital_cost_rooftop_solar,
          marginal_cost=0,
          p_max_pu=cf_solar)

    # Conservative hydro proxies (same idea as Part C)
    n.add("Generator", f"{c} run_of_river",
          bus=c, carrier="hydro",
          p_nom=tech_data["run_of_river"]["fixed_capacity"],
          capital_cost=0, marginal_cost=0,
          p_max_pu=tech_data["run_of_river"]["availability"])

    n.add("Generator", f"{c} hydro_reservoir",
          bus=c, carrier="hydro",
          p_nom=tech_data["hydro_reservoir"]["fixed_capacity"],
          capital_cost=0, marginal_cost=0,
          p_max_pu=tech_data["hydro_reservoir"]["availability"])

    n.add("Generator", f"{c} OCGT",
          bus=c, carrier="gas",
          p_nom_extendable=True,
          capital_cost=capital_cost_ocgt,
          marginal_cost=marginal_cost_ocgt,
          efficiency=efficiency_ocgt)


#%% 7) Add storage in all countries (extension of Part C)
# Pumped hydro
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

# Battery
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

for c in COUNTRIES:
    n.add("StorageUnit", f"{c} Pumped_Hydro",
          bus=c,
          p_nom_extendable=True,
          capital_cost=total_capital_cost_pumped_hydro,
          max_hours=tech_data["Pumped_Hydro"]["max_hours"],
          efficiency_store=tech_data["Pumped_Hydro"]["efficiency_store"],
          efficiency_dispatch=tech_data["Pumped_Hydro"]["efficiency_dispatch"],
          cyclic_state_of_charge=True,
          inflow=0,
          p_min_pu=-1)

    n.add("StorageUnit", f"{c} battery",
          bus=c,
          p_nom_extendable=True,
          capital_cost=total_capital_cost_battery,
          max_hours=tech_data["battery"]["max_hours"],
          efficiency_store=tech_data["battery"]["efficiency_store"],
          efficiency_dispatch=tech_data["battery"]["efficiency_dispatch"],
          cyclic_state_of_charge=True,
          p_min_pu=-1)

    # H2 storage chain per country
    n.add("Bus", f"{c} H2", carrier="H2")
    n.add("Store", f"{c} H2 Tank",
          bus=f"{c} H2",
          e_nom_extendable=True,
          e_cyclic=True,
          capital_cost=annuity(25, 0.07) * 57000 * (1 + 0.011))
    n.add("Link", f"{c} H2 Electrolysis",
          bus0=c, bus1=f"{c} H2",
          p_nom_extendable=True,
          efficiency=0.8,
          capital_cost=annuity(25, 0.07) * 600000 * (1 + 0.05))
    n.add("Link", f"{c} H2 Fuel Cell",
          bus0=f"{c} H2", bus1=c,
          p_nom_extendable=True,
          efficiency=0.58,
          capital_cost=annuity(10, 0.07) * 1300000 * (1 + 0.05))


#%% 8) Add fixed HVAC lines (Task D)
# x=0.1 unitary reactance assumption for DC approximation
for (a, b), cap in INTERCONNECTORS_MW.items():
    n.add("Line", f"{a}-{b}",
          bus0=a, bus1=b,
          s_nom=cap, s_nom_extendable=False,
          x=0.1, r=0.0)


#%% 9) Optimize (linearised AC = DC approximation)
n.optimize(solver_name="gurobi")
n.model.to_file("model_D.lp")
print("Model saved: model_D.lp")
print(f"Objective [M€]: {n.objective/1e6:.2f}")


#%% 10) Results: transmission + capacities
print("\n=== Fixed line capacities [MW] ===")
print(n.lines.s_nom)

print("\n=== Max absolute line flow [MW] ===")
print(n.lines_t.p0.abs().max().sort_values(ascending=False))

loading = (n.lines_t.p0.abs().max() / n.lines.s_nom * 100).sort_values(ascending=False)
print("\n=== Max line loading [%] ===")
print(loading)

print("\n=== Optimal generator capacities [MW] ===")
print(n.generators.p_nom_opt.sort_values(ascending=False).head(30))

print("\n=== Optimal storage power capacities [MW] ===")
print(n.storage_units.p_nom_opt.sort_values(ascending=False))


#%% 11) Results: annual generation mix
gen_by_carrier = n.generators_t.p.groupby(n.generators.carrier, axis=1).sum().sum()
gen_by_carrier = gen_by_carrier[gen_by_carrier > 0]

plt.figure(figsize=(6, 6))
plt.pie(gen_by_carrier.values, labels=gen_by_carrier.index, autopct="%1.1f%%")
plt.title("Annual electricity mix (all countries)")
plt.tight_layout()
plt.show()


#%% 12) Results: DEU dispatch (winter + summer week)
def plot_dispatch_week(country_code, week_start, title):
    cols = [
        f"{country_code} onshorewind",
        f"{country_code} solar",
        f"{country_code} solar_rooftop",
        f"{country_code} run_of_river",
        f"{country_code} hydro_reservoir",
        f"{country_code} OCGT",
    ]
    end = pd.Timestamp(week_start) + pd.Timedelta(days=7)
    gen = n.generators_t.p[cols].loc[week_start:end]
    demand = n.loads_t.p[f"{country_code} load"].loc[gen.index]

    ax = gen.plot(figsize=(11, 4), lw=1)
    demand.plot(ax=ax, color="black", lw=2, label="demand")
    ax.set_title(title)
    ax.set_ylabel("Power [MW]")
    ax.legend(loc="upper right", ncol=2)
    plt.tight_layout()
    plt.show()

plot_dispatch_week(HOME_COUNTRY, "2015-01-12 00:00:00", f"{HOME_COUNTRY} winter dispatch")
plot_dispatch_week(HOME_COUNTRY, "2015-07-13 00:00:00", f"{HOME_COUNTRY} summer dispatch")


#%% 13) Results: first snapshot imbalance + flows (for Part E)
t0 = n.snapshots[0]
gen_t0 = n.generators_t.p.loc[t0].groupby(n.generators.bus).sum()
load_t0 = n.loads_t.p.loc[t0].groupby(n.loads.bus).sum()
imbalance_t0 = gen_t0.reindex(COUNTRIES, fill_value=0) - load_t0.reindex(COUNTRIES, fill_value=0)

print(f"\n=== First snapshot: {t0} ===")
print("\nNodal imbalance = generation - demand [MW]")
print(imbalance_t0)

print("\nLine flows p0 [MW] at first snapshot")
print(n.lines_t.p0.loc[t0])