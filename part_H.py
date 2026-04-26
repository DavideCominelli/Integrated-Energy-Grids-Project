#%%
"""
Part H - CO2 price analysis based on the interconnected electricity model from Part D.

Task focus:
- Use the interconnected four-node electricity model from Part D.
- Select a decarbonisation target equal to 30% of the unconstrained Part D baseline emissions.
- Apply a system-wide CO2 price to gas-fired OCGT generation.
- Use bisection search to find the approximate critical CO2 price.
- Run a small number of additional trend points for plotting.
- Save result tables and figures.

Model basis:
- Countries: DEU, CHE, CZE, AUT
- HVAC interconnectors with fixed NTC capacities
- Linearised AC power flow / DC approximation through PyPSA lines
- No gas pipeline network

Run options:
- Fast mode:
    python part_h.py

- Full hourly mode:
    python part_h.py --full
"""

from pathlib import Path
import argparse

import numpy as np
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

# Decarbonisation target:
# 30% of the unconstrained baseline emissions of the Part D interconnected model.
TARGET_CAP_FRACTION = 0.30

# Bisection search settings
PRICE_LOW = 0.0
PRICE_HIGH = 500.0
PRICE_TOLERANCE = 1.0
MAX_ITERATIONS = 20

# Extra trend points for plotting.
# The final required price found by bisection will be added automatically.
TREND_PRICE_POINTS = [0, 25, 50, 75, 100, 125, 150, 200, 300, 500]

parser = argparse.ArgumentParser(
    description="Part H carbon price analysis based on Part D model"
)
parser.add_argument(
    "--full",
    action="store_true",
    help="Run full hourly model. Default is faster downsampled mode.",
)
args = parser.parse_args()

FAST_MODE = not args.full
SNAPSHOT_STRIDE_H = 3 if FAST_MODE else 1

SOLVER_OPTIONS = {
    "output_flag": 0,
    "threads": 4,
}

OUTPUT_DIR = Path("output_H")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


#%% 2) Helper functions

def align_to_snapshots(series: pd.Series, snapshots) -> pd.Series:
    """
    Align an input time series to the model snapshots.

    This makes the code work for both full hourly mode and fast downsampled mode.
    """
    snapshot_idx = pd.DatetimeIndex(snapshots)

    if snapshot_idx.tz is not None:
        snapshot_idx = snapshot_idx.tz_convert(None)

    aligned = series.copy()
    aligned.index = pd.to_datetime(aligned.index)

    if aligned.index.tz is not None:
        aligned.index = aligned.index.tz_convert(None)

    aligned = aligned.reindex(snapshot_idx)
    aligned = aligned.interpolate(method="time").ffill().bfill()

    return aligned


def build_part_d_network_with_carbon_price(
    co2_price_eur_per_tonne: float,
) -> pypsa.Network:
    """
    Build the interconnected electricity model from Part D.

    CO2 price treatment:
    - OCGT is modelled as a Generator.
    - Its normal marginal cost is fuel_cost / efficiency [EUR/MWh_el].
    - Its emissions intensity is gas_co2_factor / efficiency [tCO2/MWh_el].
    - Therefore, carbon cost added to OCGT is:

        CO2 price [EUR/tCO2] * gas_co2_factor / efficiency

      giving an additional cost in [EUR/MWh_el].
    """
    network = pypsa.Network()

    #%% Snapshots
    hours = pd.date_range(
        f"{TARGET_YEAR}-01-01 00:00Z",
        f"{TARGET_YEAR}-12-31 23:00Z",
        freq=f"{SNAPSHOT_STRIDE_H}h",
    )

    network.set_snapshots(hours.values)

    # In fast mode, each snapshot represents more than one hour.
    # This keeps annual energy, emissions and objective values comparable.
    if SNAPSHOT_STRIDE_H > 1:
        network.snapshot_weightings = network.snapshot_weightings * SNAPSHOT_STRIDE_H

    #%% Carriers
    network.add("Carrier", "AC")
    network.add("Carrier", "gas", co2_emissions=0.19)  # tCO2 / MWh_th
    network.add("Carrier", "onshorewind")
    network.add("Carrier", "solar")
    network.add("Carrier", "hydro")
    network.add("Carrier", "battery")
    network.add("Carrier", "H2")

    #%% Buses
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

    #%% Fixed HVAC interconnectors
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

    #%% Load data
    df_elec = pd.read_csv("data/electricity_demand.csv", sep=";", index_col=0)
    df_elec.index = pd.to_datetime(df_elec.index)

    df_wind = pd.read_csv("data/onshore_wind_1979-2017.csv", sep=";", index_col=0)
    df_wind.index = pd.to_datetime(df_wind.index)

    df_solar = pd.read_csv("data/pv_optimal.csv", sep=";", index_col=0)
    df_solar.index = pd.to_datetime(df_solar.index)

    #%% Cost assumptions
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
    gas_co2_factor = network.carriers.at["gas", "co2_emissions"]

    marginal_cost_ocgt_without_co2 = fuel_cost / ocgt_efficiency
    carbon_cost_ocgt = co2_price_eur_per_tonne * gas_co2_factor / ocgt_efficiency
    marginal_cost_ocgt = marginal_cost_ocgt_without_co2 + carbon_cost_ocgt

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
        capital_cost_battery_power
        + capital_cost_battery_energy * battery_max_hours
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

    if pumped_hydro_max_power <= 0:
        raise ValueError("Pumped_Hydro max_power_capacity must be > 0")

    pumped_hydro_max_hours = pumped_hydro_max_energy / pumped_hydro_max_power
    total_capital_cost_pumped_hydro = capital_cost_pumped_hydro_power

    #%% Add all country systems
    for c in COUNTRIES:
        demand = align_to_snapshots(df_elec[c], network.snapshots)
        cf_wind = align_to_snapshots(df_wind[c], network.snapshots)
        cf_solar = align_to_snapshots(df_solar[c], network.snapshots)

        network.add(
            "Load",
            f"load_{c}",
            bus=f"{c} bus",
            p_set=demand.values,
        )

        network.add(
            "Generator",
            f"onshorewind_{c}",
            bus=f"{c} bus",
            p_nom_extendable=True,
            carrier="onshorewind",
            capital_cost=capital_cost_onshorewind,
            marginal_cost=0,
            p_max_pu=cf_wind.values,
        )

        network.add(
            "Generator",
            f"solar_{c}",
            bus=f"{c} bus",
            p_nom_extendable=True,
            carrier="solar",
            capital_cost=capital_cost_solar,
            marginal_cost=0,
            p_max_pu=cf_solar.values,
        )

        network.add(
            "Generator",
            f"solar_rooftop_{c}",
            bus=f"{c} bus",
            p_nom_extendable=True,
            carrier="solar",
            capital_cost=capital_cost_rooftop_solar,
            marginal_cost=0,
            p_max_pu=cf_solar.values,
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

    return network


def annual_co2_tonnes(network: pypsa.Network) -> float:
    """
    Calculate annual CO2 emissions [tCO2/year] from OCGT generators.

    OCGT output is electrical MWh.
    Thermal input = electrical output / efficiency.
    CO2 = thermal input * gas CO2 factor.

    Snapshot weightings are included.
    """
    gas_gens = network.generators.index[network.generators.carrier == "gas"]

    if len(gas_gens) == 0:
        return 0.0

    weights = network.snapshot_weightings.generators

    gas_generation_mwh_el_by_gen = (
        network.generators_t.p[gas_gens]
        .mul(weights, axis=0)
        .sum(axis=0)
    )

    efficiencies = network.generators.efficiency.reindex(gas_gens)
    thermal_input_mwh_th = (gas_generation_mwh_el_by_gen / efficiencies).sum()

    gas_co2_factor = network.carriers.at["gas", "co2_emissions"]

    return float(thermal_input_mwh_th * gas_co2_factor)


def generation_by_carrier_twh(network: pypsa.Network) -> pd.Series:
    """
    Aggregate annual electricity generation by carrier [TWh].
    Includes snapshot weightings.
    """
    weights = network.snapshot_weightings.generators

    annual_gen_mwh = (
        network.generators_t.p
        .mul(weights, axis=0)
        .sum(axis=0)
    )

    carrier = network.generators.carrier.reindex(annual_gen_mwh.index)
    annual_by_carrier_mwh = annual_gen_mwh.groupby(carrier).sum()

    h2_fc_links = [
        link for link in network.links.index
        if link.startswith("H2_Fuel_Cell_")
    ]

    if h2_fc_links:
        h2_output_mwh = (
            -network.links_t.p1[h2_fc_links]
            .mul(weights, axis=0)
            .sum()
            .sum()
        )

        # Avoid very small negative numerical artefacts such as -0.0000.
        h2_output_mwh = max(0.0, float(h2_output_mwh))

        annual_by_carrier_mwh.loc["H2 fuel cell"] = h2_output_mwh

    # Remove tiny numerical noise before converting to TWh.
    annual_by_carrier_mwh[annual_by_carrier_mwh.abs() < 1e-6] = 0.0

    return (annual_by_carrier_mwh / 1e6).sort_values(ascending=False)


def capacity_by_carrier_mw(network: pypsa.Network) -> pd.Series:
    """
    Aggregate installed capacities by carrier [MW].
    Includes generators and H2 conversion links.
    """
    result = {}

    gen_caps = network.generators.p_nom_opt.groupby(network.generators.carrier).sum()

    for carrier, value in gen_caps.items():
        result[carrier] = result.get(carrier, 0.0) + value

    for link_name, row in network.links.iterrows():
        p_nom_opt = row.get("p_nom_opt", 0.0)

        if link_name.startswith("H2_Electrolysis_"):
            result["H2 electrolysis"] = result.get("H2 electrolysis", 0.0) + p_nom_opt

        elif link_name.startswith("H2_Fuel_Cell_"):
            result["H2 fuel cell"] = result.get("H2 fuel cell", 0.0) + p_nom_opt

    result_series = pd.Series(result)
    result_series[result_series.abs() < 1e-6] = 0.0

    return result_series.sort_values(ascending=False)


def solve_model_at_price(co2_price: float) -> tuple[pypsa.Network, float, float]:
    """
    Build and optimise the Part D model at a given CO2 price.

    Returns
    -------
    network : pypsa.Network
        Optimised network.
    emissions_t : float
        Annual CO2 emissions [tCO2/year].
    objective_eur : float
        Objective value [EUR/year].
    """
    print(f"\nSolving CO2 price = {co2_price:.2f} EUR/tCO2 ...")

    network = build_part_d_network_with_carbon_price(co2_price)

    status, condition = network.optimize(
        solver_name="gurobi",
        solver_options=SOLVER_OPTIONS,
    )

    if status != "ok":
        raise RuntimeError(
            f"Optimisation failed at {co2_price:.2f} EUR/tCO2: {status}, {condition}"
        )

    emissions_t = annual_co2_tonnes(network)
    objective_eur = float(network.objective)

    print(
        f"  Emissions = {emissions_t / 1e6:.3f} MtCO2/year | "
        f"Objective = {objective_eur / 1e9:.3f} billion EUR"
    )

    return network, emissions_t, objective_eur


def find_required_carbon_price_bisection(
    target_co2_t: float,
    price_low: float,
    price_high: float,
    tolerance_price: float,
    max_iterations: int,
    low_solution: tuple[pypsa.Network, float, float] | None = None,
) -> dict:
    """
    Find the minimum CO2 price required to reach the target using bisection search.

    Assumption:
    CO2 emissions generally decrease as CO2 price increases.
    """
    records = []

    # Lower bound
    if low_solution is None:
        net_low, co2_low, obj_low = solve_model_at_price(price_low)
    else:
        net_low, co2_low, obj_low = low_solution

    records.append(
        {
            "type": "bisection",
            "co2_price_eur_per_tco2": price_low,
            "realized_co2_mt": co2_low / 1e6,
            "target_co2_mt": target_co2_t / 1e6,
            "target_achieved": co2_low <= target_co2_t,
            "objective_billion_eur": obj_low / 1e9,
        }
    )

    if co2_low <= target_co2_t:
        return {
            "required_price": price_low,
            "required_emissions_t": co2_low,
            "required_objective_eur": obj_low,
            "required_network": net_low,
            "records": records,
            "message": "Target already achieved at the lower price bound.",
        }

    # Upper bound
    net_high, co2_high, obj_high = solve_model_at_price(price_high)

    records.append(
        {
            "type": "bisection",
            "co2_price_eur_per_tco2": price_high,
            "realized_co2_mt": co2_high / 1e6,
            "target_co2_mt": target_co2_t / 1e6,
            "target_achieved": co2_high <= target_co2_t,
            "objective_billion_eur": obj_high / 1e9,
        }
    )

    # Automatically expand upper bound if needed
    while co2_high > target_co2_t:
        print(
            f"\nUpper bound {price_high:.2f} EUR/tCO2 did not reach the target. "
            "Expanding upper bound..."
        )

        price_low = price_high
        co2_low = co2_high
        obj_low = obj_high
        net_low = net_high

        price_high *= 2

        if price_high > 10000:
            raise RuntimeError(
                "Even a very high CO2 price did not reach the target. "
                "The target may be infeasible with the current technology set."
            )

        net_high, co2_high, obj_high = solve_model_at_price(price_high)

        records.append(
            {
                "type": "bisection",
                "co2_price_eur_per_tco2": price_high,
                "realized_co2_mt": co2_high / 1e6,
                "target_co2_mt": target_co2_t / 1e6,
                "target_achieved": co2_high <= target_co2_t,
                "objective_billion_eur": obj_high / 1e9,
            }
        )

    best_price = price_high
    best_emissions_t = co2_high
    best_objective_eur = obj_high
    best_network = net_high

    # Bisection loop
    for iteration in range(max_iterations):
        price_mid = 0.5 * (price_low + price_high)

        net_mid, co2_mid, obj_mid = solve_model_at_price(price_mid)

        records.append(
            {
                "type": "bisection",
                "co2_price_eur_per_tco2": price_mid,
                "realized_co2_mt": co2_mid / 1e6,
                "target_co2_mt": target_co2_t / 1e6,
                "target_achieved": co2_mid <= target_co2_t,
                "objective_billion_eur": obj_mid / 1e9,
            }
        )

        if co2_mid <= target_co2_t:
            best_price = price_mid
            best_emissions_t = co2_mid
            best_objective_eur = obj_mid
            best_network = net_mid
            price_high = price_mid
        else:
            price_low = price_mid

        interval_width = price_high - price_low

        print(
            f"  Iteration {iteration + 1}: "
            f"interval = [{price_low:.2f}, {price_high:.2f}] EUR/tCO2"
        )

        if interval_width <= tolerance_price:
            break

    return {
        "required_price": best_price,
        "required_emissions_t": best_emissions_t,
        "required_objective_eur": best_objective_eur,
        "required_network": best_network,
        "records": records,
        "message": "Bisection search completed.",
    }


#%% 3) Baseline and target

print("\n=== Part H settings ===")
print("Model basis: Part D interconnected electricity model")
print("Mode:", "FAST" if FAST_MODE else "FULL")
print("Snapshot stride [h]:", SNAPSHOT_STRIDE_H)
print(f"Target definition: {TARGET_CAP_FRACTION * 100:.0f}% of Part D baseline emissions")

baseline_network, baseline_emissions_t, baseline_objective_eur = solve_model_at_price(0.0)

target_co2_t = baseline_emissions_t * TARGET_CAP_FRACTION
target_co2_mt = target_co2_t / 1e6

print("\n=== Part D baseline and selected target ===")
print(f"Baseline emissions        : {baseline_emissions_t / 1e6:.3f} MtCO2/year")
print(f"Baseline objective        : {baseline_objective_eur / 1e9:.3f} billion EUR")
print(f"Target fraction           : {TARGET_CAP_FRACTION:.2f}")
print(f"Selected CO2 allowance    : {target_co2_mt:.3f} MtCO2/year")


#%% 4) Bisection search

search_result = find_required_carbon_price_bisection(
    target_co2_t=target_co2_t,
    price_low=PRICE_LOW,
    price_high=PRICE_HIGH,
    tolerance_price=PRICE_TOLERANCE,
    max_iterations=MAX_ITERATIONS,
    low_solution=(baseline_network, baseline_emissions_t, baseline_objective_eur),
)

required_price = search_result["required_price"]
required_emissions_t = search_result["required_emissions_t"]
required_objective_eur = search_result["required_objective_eur"]
required_network = search_result["required_network"]

bisection_df = pd.DataFrame(search_result["records"])
bisection_df = bisection_df.sort_values("co2_price_eur_per_tco2")
bisection_df.to_csv(OUTPUT_DIR / "bisection_search_summary.csv", index=False)

print("\n=== Required carbon price result ===")
print(f"Selected target CO2 allowance : {target_co2_mt:.3f} MtCO2/year")
print(f"Required CO2 price            : {required_price:.2f} EUR/tCO2")
print(f"Realized emissions at price   : {required_emissions_t / 1e6:.3f} MtCO2/year")
print(f"Objective at required price   : {required_objective_eur / 1e9:.3f} billion EUR")
print(search_result["message"])


#%% 5) Additional trend points for plots

plot_prices = sorted(set(TREND_PRICE_POINTS + [round(required_price, 2)]))

trend_records = []
mix_records = []
cap_records = []

for price in plot_prices:
    if abs(price - required_price) <= 1e-9:
        net = required_network
        co2_t = required_emissions_t
        obj_eur = required_objective_eur

    elif abs(price - 0.0) <= 1e-9:
        net = baseline_network
        co2_t = baseline_emissions_t
        obj_eur = baseline_objective_eur

    else:
        net, co2_t, obj_eur = solve_model_at_price(price)

    mix_twh = generation_by_carrier_twh(net)
    mix_share = mix_twh / mix_twh.sum()
    caps_mw = capacity_by_carrier_mw(net)

    trend_records.append(
        {
            "type": "trend",
            "co2_price_eur_per_tco2": price,
            "realized_co2_mt": co2_t / 1e6,
            "target_co2_mt": target_co2_mt,
            "target_achieved": co2_t <= target_co2_t,
            "objective_billion_eur": obj_eur / 1e9,
            "cost_increase_vs_baseline_billion_eur": (
                obj_eur - baseline_objective_eur
            ) / 1e9,
        }
    )

    mix_row = {
        "co2_price_eur_per_tco2": price,
        "realized_co2_mt": co2_t / 1e6,
    }

    for carrier in [
        "onshorewind",
        "solar",
        "hydro",
        "gas",
        "H2 fuel cell",
    ]:
        mix_row[f"{carrier}_twh"] = float(mix_twh.get(carrier, 0.0))
        mix_row[f"{carrier}_share"] = float(mix_share.get(carrier, 0.0))

    mix_records.append(mix_row)

    cap_row = {
        "co2_price_eur_per_tco2": price,
        "realized_co2_mt": co2_t / 1e6,
    }

    for carrier in [
        "onshorewind",
        "solar",
        "hydro",
        "gas",
        "H2 electrolysis",
        "H2 fuel cell",
    ]:
        cap_row[f"{carrier}_mw"] = float(caps_mw.get(carrier, 0.0))

    cap_records.append(cap_row)


trend_df = pd.DataFrame(trend_records).sort_values("co2_price_eur_per_tco2")
mix_df = pd.DataFrame(mix_records).sort_values("co2_price_eur_per_tco2")
cap_df = pd.DataFrame(cap_records).sort_values("co2_price_eur_per_tco2")

trend_df.to_csv(OUTPUT_DIR / "carbon_price_trend_summary.csv", index=False)
mix_df.to_csv(OUTPUT_DIR / "generation_mix_vs_carbon_price.csv", index=False)
cap_df.to_csv(OUTPUT_DIR / "capacity_mix_vs_carbon_price.csv", index=False)


#%% 6) Print summary tables

print("\n=== Bisection search summary ===")
print(bisection_df.round(4).to_string(index=False))

print("\n=== Carbon price trend summary ===")
print(trend_df.round(4).to_string(index=False))

print("\n=== Generation mix shares vs carbon price ===")
share_cols = [
    "co2_price_eur_per_tco2",
    "realized_co2_mt",
    "onshorewind_share",
    "solar_share",
    "hydro_share",
    "gas_share",
    "H2 fuel cell_share",
]
existing_share_cols = [col for col in share_cols if col in mix_df.columns]
print(mix_df[existing_share_cols].round(4).to_string(index=False))

print("\n=== Capacity mix [MW] vs carbon price ===")
cap_cols = [
    "co2_price_eur_per_tco2",
    "realized_co2_mt",
    "onshorewind_mw",
    "solar_mw",
    "hydro_mw",
    "gas_mw",
    "H2 electrolysis_mw",
    "H2 fuel cell_mw",
]
existing_cap_cols = [col for col in cap_cols if col in cap_df.columns]
print(cap_df[existing_cap_cols].round(2).to_string(index=False))


#%% 7) Plot emissions vs carbon price

fig, ax = plt.subplots(figsize=(9, 5))

ax.plot(
    trend_df["co2_price_eur_per_tco2"],
    trend_df["realized_co2_mt"],
    marker="o",
    label="Trend points",
)

ax.scatter(
    [required_price],
    [required_emissions_t / 1e6],
    s=80,
    zorder=5,
    label=f"Required price ≈ {required_price:.1f} EUR/tCO2",
)

ax.axhline(
    target_co2_mt,
    color="black",
    linestyle="--",
    linewidth=1,
    label=f"Target = {target_co2_mt:.2f} MtCO2/year",
)

ax.axvline(
    required_price,
    color="gray",
    linestyle=":",
    linewidth=1,
)

ax.set_xlabel("CO2 price [EUR/tCO2]")
ax.set_ylabel("Annual CO2 emissions [MtCO2/year]")
ax.set_title("System CO2 emissions as a function of CO2 price")
ax.grid(alpha=0.3)
ax.legend()

plt.tight_layout()
plt.savefig(
    OUTPUT_DIR / "co2_emissions_vs_carbon_price.png",
    dpi=200,
    bbox_inches="tight",
)
plt.show()


#%% 8) Plot generation mix vs carbon price

plot_df = mix_df.copy()
x = plot_df["co2_price_eur_per_tco2"].values

stack_carriers = [
    "onshorewind",
    "solar",
    "hydro",
    "gas",
    "H2 fuel cell",
]

shares = []
labels = []

for carrier in stack_carriers:
    col = f"{carrier}_share"
    if col in plot_df.columns:
        shares.append(plot_df[col].values)
        labels.append(carrier)

fig, ax = plt.subplots(figsize=(10, 6))

ax.stackplot(x, shares, labels=labels, alpha=0.9)

ax.axvline(
    required_price,
    color="gray",
    linestyle=":",
    linewidth=1,
    label=f"Required price ≈ {required_price:.1f} EUR/tCO2",
)

ax.set_xlabel("CO2 price [EUR/tCO2]")
ax.set_ylabel("Generation share [-]")
ax.set_title("Generation mix sensitivity to CO2 price")
ax.set_ylim(0, 1.0)
ax.grid(alpha=0.2)

# Put legend outside the figure area to avoid covering the plot.
ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))

plt.tight_layout()
plt.savefig(
    OUTPUT_DIR / "generation_mix_vs_carbon_price.png",
    dpi=200,
    bbox_inches="tight",
)
plt.show()


#%% 9) Save short text result

result_txt = OUTPUT_DIR / "part_h_result.txt"

with open(result_txt, "w", encoding="utf-8") as f:
    f.write("Part H - Carbon price result based on Part D model\n")
    f.write("==================================================\n\n")
    f.write(f"Mode: {'FAST' if FAST_MODE else 'FULL'}\n")
    f.write(f"Snapshot stride [h]: {SNAPSHOT_STRIDE_H}\n")
    f.write(f"Baseline emissions [MtCO2/year]: {baseline_emissions_t / 1e6:.3f}\n")
    f.write(f"Baseline objective [billion EUR]: {baseline_objective_eur / 1e9:.3f}\n")
    f.write(f"Target fraction of baseline emissions [-]: {TARGET_CAP_FRACTION:.2f}\n")
    f.write(f"Selected target [MtCO2/year]: {target_co2_mt:.3f}\n")
    f.write(f"Required CO2 price [EUR/tCO2]: {required_price:.2f}\n")
    f.write(f"Realized emissions at required price [MtCO2/year]: {required_emissions_t / 1e6:.3f}\n")
    f.write(f"Objective at required price [billion EUR]: {required_objective_eur / 1e9:.3f}\n")
    f.write(f"Bisection tolerance [EUR/tCO2]: {PRICE_TOLERANCE:.2f}\n")

print("\nSaved outputs in:", OUTPUT_DIR)
print("Result text file:", result_txt)