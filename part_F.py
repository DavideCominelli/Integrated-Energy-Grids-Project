#%%
"""
Part F - CO2 sensitivity analysis using the interconnected model from Part D.

Task focus:
- Sweep a global CO2 cap.
- Show how the annual generation mix and optimal capacities change.
- Compare model CO2 caps with historical Germany emissions references.
"""

from pathlib import Path
import argparse
import pandas as pd
import pypsa
import matplotlib.pyplot as plt

from data.data import tech_data
from utils import annuity


#%% 1) Settings
HOME_COUNTRY = "DEU"
COUNTRIES = ["DEU", "CHE", "CZE", "AUT"]

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

DISCOUNT_RATE = 0.07
TARGET_YEAR = 2015

# Default: quick mode for faster iteration. Use --full for final, hourly results.
parser = argparse.ArgumentParser(description="Part F CO2 sensitivity analysis")
parser.add_argument("--full", action="store_true", help="Run full hourly model and full CO2 cap sweep")
args = parser.parse_args()

FAST_MODE = not args.full
SNAPSHOT_STRIDE_H = 3 if FAST_MODE else 1
CO2_CAP_FRACTIONS = [1.00, 0.60, 0.30, 0.10] if FAST_MODE else [1.00, 0.80, 0.60, 0.40, 0.25, 0.15, 0.10, 0.05]

SOLVER_OPTIONS = {
    "output_flag": 0,
    "threads": 4,
}

# Historical references for Germany power sector emissions (contextual allowances):
# Approximate values for electricity/energy-industry CO2 levels from public German
# energy transition reporting (UBA / Agora-style reporting conventions).
# These are used as sector-relevant reference markers for the cap analysis.
DEU_POWER_SECTOR_CO2_MT = {
    "DEU power sector CO2 1990 (ref.)": 356.0,
    "DEU power sector CO2 2023 (ref.)": 171.0,
}

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


#%% 2) Helpers

def build_interconnected_network() -> pypsa.Network:
    """Create the interconnected model from Part D with the same assumptions."""
    network = pypsa.Network()

    hours = pd.date_range(
        f"{TARGET_YEAR}-01-01 00:00Z",
        f"{TARGET_YEAR}-12-31 23:00Z",
        freq=f"{SNAPSHOT_STRIDE_H}h",
    )
    network.set_snapshots(hours.values)
    if SNAPSHOT_STRIDE_H > 1:
        network.snapshot_weightings = network.snapshot_weightings * SNAPSHOT_STRIDE_H

    network.add("Carrier", "AC")
    network.add("Carrier", "gas", co2_emissions=0.19)  # t_CO2 / MWh_th
    network.add("Carrier", "onshorewind")
    network.add("Carrier", "solar")
    network.add("Carrier", "hydro")
    network.add("Carrier", "battery")
    network.add("Carrier", "H2")

    for c in COUNTRIES:
        x, y = COORDS[c]
        network.add("Bus", f"{c} bus", carrier="AC", v_nom=400, x=x, y=y)

    for (c0, c1), cap in INTERCONNECTORS_MW.items():
        network.add(
            "Line",
            f"{c0}-{c1}",
            bus0=f"{c0} bus",
            bus1=f"{c1} bus",
            x=0.1,
            r=1e-4,
            s_nom=cap,
            s_nom_extendable=False,
            carrier="AC",
        )

    df_elec = pd.read_csv("data/electricity_demand.csv", sep=";", index_col=0)
    df_elec.index = pd.to_datetime(df_elec.index)

    df_wind = pd.read_csv("data/onshore_wind_1979-2017.csv", sep=";", index_col=0)
    df_wind.index = pd.to_datetime(df_wind.index)

    df_solar = pd.read_csv("data/pv_optimal.csv", sep=";", index_col=0)
    df_solar.index = pd.to_datetime(df_solar.index)

    snapshot_idx = pd.DatetimeIndex(network.snapshots)
    if snapshot_idx.tz is not None:
        snapshot_idx = snapshot_idx.tz_convert(None)

    def align_to_snapshots(series: pd.Series) -> pd.Series:
        """Align an hourly series to model snapshots (supports downsampled runs)."""
        aligned = series.copy()
        aligned.index = pd.to_datetime(aligned.index)
        if aligned.index.tz is not None:
            aligned.index = aligned.index.tz_convert(None)
        aligned = aligned.reindex(snapshot_idx)
        aligned = aligned.interpolate(method="time").ffill().bfill()
        return aligned

    capital_cost_onshorewind = (
        annuity(tech_data["onshorewind"]["lifetime"], DISCOUNT_RATE)
        * tech_data["onshorewind"]["overnight_cost"]
        * (1 + tech_data["onshorewind"]["capital_cost_increase"])
    )

    capital_cost_solar = (
        annuity(tech_data["solar"]["lifetime"], DISCOUNT_RATE)
        * tech_data["solar"]["overnight_cost"]
        * (1 + tech_data["solar"]["capital_cost_increase"])
    )

    capital_cost_rooftop_solar = (
        annuity(tech_data["solar_rooftop"]["lifetime"], DISCOUNT_RATE)
        * tech_data["solar_rooftop"]["overnight_cost"]
        * (1 + tech_data["solar_rooftop"]["capital_cost_increase"])
    )

    capital_cost_ocgt = (
        annuity(tech_data["OCGT"]["lifetime"], DISCOUNT_RATE)
        * tech_data["OCGT"]["overnight_cost"]
        * (1 + tech_data["OCGT"]["capital_cost_increase"])
    )

    fuel_cost = tech_data["OCGT"]["fuel_cost"]
    ocgt_efficiency = tech_data["OCGT"]["efficiency"]
    marginal_cost_ocgt = fuel_cost / ocgt_efficiency

    capital_cost_pumped_hydro_power = (
        annuity(tech_data["Pumped_Hydro"]["lifetime"], DISCOUNT_RATE)
        * tech_data["Pumped_Hydro"]["overnight_cost_power"]
        * (1 + tech_data["Pumped_Hydro"]["capital_cost_increase"])
    )

    capital_cost_battery_power = (
        annuity(tech_data["battery"]["lifetime"], DISCOUNT_RATE)
        * tech_data["battery"]["overnight_cost_power"]
        * (1 + tech_data["battery"]["capital_cost_increase"])
    )
    capital_cost_battery_energy = (
        annuity(tech_data["battery"]["lifetime"], DISCOUNT_RATE)
        * tech_data["battery"]["overnight_cost_energy"]
        * (1 + tech_data["battery"]["capital_cost_increase"])
    )
    battery_max_hours = tech_data["battery"].get("max_hours", 4)
    total_capital_cost_battery = (
        capital_cost_battery_power + capital_cost_battery_energy * battery_max_hours
    )

    capital_cost_h2_tank = (
        annuity(tech_data["hydrogen_storage"]["lifetime"], DISCOUNT_RATE)
        * tech_data["hydrogen_storage"]["overnight_cost_energy"]
        * (1 + tech_data["hydrogen_storage"]["capital_cost_increase"])
    )

    capital_cost_h2_electrolysis = (
        annuity(tech_data["hydrogen_electrolysis"]["lifetime"], DISCOUNT_RATE)
        * tech_data["hydrogen_electrolysis"]["overnight_cost_power"]
        * (1 + tech_data["hydrogen_electrolysis"]["capital_cost_increase"])
    )

    capital_cost_h2_fuel_cell = (
        annuity(tech_data["hydrogen_fuel_cell"]["lifetime"], DISCOUNT_RATE)
        * tech_data["hydrogen_fuel_cell"]["overnight_cost_power"]
        * (1 + tech_data["hydrogen_fuel_cell"]["capital_cost_increase"])
    )

    pumped_hydro_max_power = tech_data["Pumped_Hydro"]["max_power_capacity"]
    pumped_hydro_max_energy = tech_data["Pumped_Hydro"]["max_energy_capacity"]
    pumped_hydro_max_hours = pumped_hydro_max_energy / pumped_hydro_max_power

    for c in COUNTRIES:
        demand = align_to_snapshots(df_elec[c])
        network.add("Load", f"load_{c}", bus=f"{c} bus", p_set=demand.values)

        cf_wind = align_to_snapshots(df_wind[c]).values
        cf_solar = align_to_snapshots(df_solar[c]).values

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

        # Efficiency is explicitly set so CO2 accounting uses thermal input correctly.
        network.add(
            "Generator",
            f"OCGT_{c}",
            bus=f"{c} bus",
            p_nom_extendable=True,
            carrier="gas",
            capital_cost=capital_cost_ocgt,
            marginal_cost=marginal_cost_ocgt,
            efficiency=ocgt_efficiency,
        )

        network.add(
            "StorageUnit",
            f"Pumped_Hydro_{c}",
            bus=f"{c} bus",
            p_nom_extendable=True,
            p_nom_max=pumped_hydro_max_power,
            capital_cost=capital_cost_pumped_hydro_power,
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

    return network


def add_global_co2_cap(network: pypsa.Network, cap_tonnes: float) -> None:
    """Add a system-wide CO2 cap in tonnes CO2/year."""
    network.add(
        "GlobalConstraint",
        "co2_limit",
        type="primary_energy",
        carrier_attribute="co2_emissions",
        sense="<=",
        constant=float(cap_tonnes),
    )


def annual_co2_tonnes(network: pypsa.Network) -> float:
    """Calculate annual CO2 emissions [tCO2] from gas generators."""
    gas_gens = network.generators.index[network.generators.carrier == "gas"]
    if len(gas_gens) == 0:
        return 0.0

    gas_dispatch_mwh = network.generators_t.p[gas_gens].sum(axis=0)
    efficiencies = network.generators.efficiency.reindex(gas_gens)
    thermal_input_mwh_th = (gas_dispatch_mwh / efficiencies).sum()

    gas_co2 = network.carriers.at["gas", "co2_emissions"]
    return float(thermal_input_mwh_th * gas_co2)


def generation_by_carrier_twh(network: pypsa.Network) -> pd.Series:
    """Aggregate annual electricity generation by carrier [TWh]."""
    annual_gen_mwh_by_gen = network.generators_t.p.sum(axis=0)
    carrier = network.generators.carrier.reindex(annual_gen_mwh_by_gen.index)
    annual_by_carrier_mwh = annual_gen_mwh_by_gen.groupby(carrier).sum()
    return (annual_by_carrier_mwh / 1e6).sort_values(ascending=False)


def capacity_by_carrier_mw(network: pypsa.Network) -> pd.Series:
    """Aggregate optimal installed generator capacities by carrier [MW]."""
    by_carrier = network.generators.p_nom_opt.groupby(network.generators.carrier).sum()
    return by_carrier.sort_values(ascending=False)


#%% 3) Baseline (unconstrained) run
baseline = build_interconnected_network()
baseline.optimize(solver_name="gurobi", solver_options=SOLVER_OPTIONS)

baseline_emissions_t = annual_co2_tonnes(baseline)
baseline_mix_twh = generation_by_carrier_twh(baseline)
print("Baseline annual emissions [MtCO2]:", round(baseline_emissions_t / 1e6, 3))
print("Mode:", "FAST" if FAST_MODE else "FULL")
print("Snapshot stride [h]:", SNAPSHOT_STRIDE_H)
print("\nBaseline generation mix [TWh]:")
print(baseline_mix_twh.round(3).to_string())


#%% 4) CO2 cap sensitivity sweep
records = []
mix_records = []
cap_records = []

for frac in CO2_CAP_FRACTIONS:
    if frac == 1.0:
        records.append(
            {
                "cap_fraction": 1.0,
                "co2_cap_mt": baseline_emissions_t / 1e6,
                "realized_co2_mt": baseline_emissions_t / 1e6,
                "objective_billion_eur": float(baseline.objective) / 1e9,
            }
        )
        base_mix_share = baseline_mix_twh / baseline_mix_twh.sum()
        base_caps = capacity_by_carrier_mw(baseline)
        mix_row = {"cap_fraction": 1.0, "co2_cap_mt": baseline_emissions_t / 1e6}
        for carrier in ["onshorewind", "solar", "hydro", "gas"]:
            mix_row[f"{carrier}_share"] = float(base_mix_share.get(carrier, 0.0))
            mix_row[f"{carrier}_twh"] = float(baseline_mix_twh.get(carrier, 0.0))
        mix_records.append(mix_row)

        cap_row = {"cap_fraction": 1.0, "co2_cap_mt": baseline_emissions_t / 1e6}
        for carrier in ["onshorewind", "solar", "hydro", "gas"]:
            cap_row[f"{carrier}_mw"] = float(base_caps.get(carrier, 0.0))
        cap_records.append(cap_row)
        continue

    cap_t = baseline_emissions_t * frac

    net = build_interconnected_network()
    add_global_co2_cap(net, cap_t)
    status, condition = net.optimize(
        solver_name="gurobi",
        solver_options=SOLVER_OPTIONS,
    )

    if status != "ok":
        print(f"Warning: run at fraction={frac:.2f} did not solve cleanly ({status}, {condition}).")
        continue

    co2_t = annual_co2_tonnes(net)
    obj_eur = float(net.objective)

    mix_twh = generation_by_carrier_twh(net)
    mix_share = mix_twh / mix_twh.sum()
    caps_mw = capacity_by_carrier_mw(net)

    row = {
        "cap_fraction": frac,
        "co2_cap_mt": cap_t / 1e6,
        "realized_co2_mt": co2_t / 1e6,
        "objective_billion_eur": obj_eur / 1e9,
    }
    records.append(row)

    mix_row = {"cap_fraction": frac, "co2_cap_mt": cap_t / 1e6}
    for carrier in ["onshorewind", "solar", "hydro", "gas"]:
        mix_row[f"{carrier}_share"] = float(mix_share.get(carrier, 0.0))
        mix_row[f"{carrier}_twh"] = float(mix_twh.get(carrier, 0.0))
    mix_records.append(mix_row)

    cap_row = {"cap_fraction": frac, "co2_cap_mt": cap_t / 1e6}
    for carrier in ["onshorewind", "solar", "hydro", "gas"]:
        cap_row[f"{carrier}_mw"] = float(caps_mw.get(carrier, 0.0))
    cap_records.append(cap_row)

summary_df = pd.DataFrame(records).sort_values("co2_cap_mt", ascending=False)
mix_df = pd.DataFrame(mix_records).sort_values("co2_cap_mt", ascending=False)
cap_df = pd.DataFrame(cap_records).sort_values("co2_cap_mt", ascending=False)

summary_df.to_csv(OUTPUT_DIR / "co2_sensitivity_summary.csv", index=False)
mix_df.to_csv(OUTPUT_DIR / "generation_mix_vs_co2_cap.csv", index=False)
cap_df.to_csv(OUTPUT_DIR / "capacity_mix_vs_co2_cap.csv", index=False)

print("\n=== CO2 sensitivity summary ===")
print(summary_df.round(4).to_string(index=False))

print("\n=== Generation mix shares vs cap ===")
print(
    mix_df[
        [
            "co2_cap_mt",
            "onshorewind_share",
            "solar_share",
            "hydro_share",
            "gas_share",
        ]
    ]
    .round(4)
    .to_string(index=False)
)

print("\n=== Capacity mix [MW] vs cap ===")
print(
    cap_df[
        [
            "co2_cap_mt",
            "onshorewind_mw",
            "solar_mw",
            "hydro_mw",
            "gas_mw",
        ]
    ]
    .round(2)
    .to_string(index=False)
)


#%% 5) Plot generation mix as function of CO2 cap
plot_df = mix_df.copy()
plot_df = plot_df.sort_values("co2_cap_mt")

x = plot_df["co2_cap_mt"].values
shares = [
    plot_df["onshorewind_share"].values,
    plot_df["solar_share"].values,
    plot_df["hydro_share"].values,
    plot_df["gas_share"].values,
]
labels = ["Onshore wind", "Solar", "Hydro", "Gas (OCGT)"]
colors = ["#1f77b4", "#ff7f0e", "#2a9d8f", "#8c564b"]

fig, ax = plt.subplots(figsize=(10, 6))
ax.stackplot(x, shares, labels=labels, colors=colors, alpha=0.9)
ax.set_xlabel("Global CO2 cap [MtCO2/year]")
ax.set_ylabel("Generation share [-]")
ax.set_title("Generation mix sensitivity to global CO2 cap (interconnected model)")
ax.set_ylim(0, 1.0)
ax.grid(alpha=0.2)
ax.legend(loc="upper left")

# Add historical references as contextual vertical lines when within x-range.
xmin, xmax = x.min(), x.max()
for label, value_mt in DEU_POWER_SECTOR_CO2_MT.items():
    if xmin <= value_mt <= xmax:
        ax.axvline(value_mt, color="black", linestyle="--", linewidth=1)
        ax.text(value_mt, 0.02, label, rotation=90, va="bottom", ha="right", fontsize=8)

plt.tight_layout()
plt.savefig(OUTPUT_DIR / "generation_mix_vs_co2_cap.png", dpi=200, bbox_inches="tight")
plt.show()


#%% 6) Historical reference allowance table
historical_allowance = pd.DataFrame(
    {
        "Reference": list(DEU_POWER_SECTOR_CO2_MT.keys()),
        "Power-sector CO2 reference [MtCO2/yr]": list(DEU_POWER_SECTOR_CO2_MT.values()),
    }
)

# Add model baseline for direct comparison.
historical_allowance.loc[len(historical_allowance)] = [
    "Model baseline (interconnected, no CO2 cap)",
    baseline_emissions_t / 1e6,
]

historical_allowance.to_csv(OUTPUT_DIR / "historical_allowance_reference.csv", index=False)

print("\n=== Historical emissions reference (context) ===")
print(historical_allowance.round(3).to_string(index=False))

print("\nSaved outputs in:", OUTPUT_DIR)
#%%
