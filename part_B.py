#%%
from pathlib import Path
from utils import annuity
from data.data import tech_data

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import pypsa

# -------------------------------------------------------------------------
# Global settings
# -------------------------------------------------------------------------
country = "DEU"
demand_year = 2015
weather_years = [2013, 2014, 2015, 2016, 2017]

wind_file = "data/onshore_wind_1979-2017.csv"
solar_file = "data/pv_optimal.csv"

OUTPUT_DIR = Path("output_b")
FIG_DIR = OUTPUT_DIR / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)


#%%
# -------------------------------------------------------------------------
# Section 1: Resource-side helper functions
# -------------------------------------------------------------------------
def load_cf_data(file_path, country):
    """
    Load capacity factor data from CSV and return one country as a time series.
    """
    df = pd.read_csv(file_path, sep=";", index_col=0)
    df.index = pd.to_datetime(df.index)

    if country not in df.columns:
        raise KeyError(f"Country '{country}' not found in {file_path}")

    series = df[country].copy()
    series.name = country
    return series


def extract_selected_years(series, years):
    """
    Keep only the selected weather years from a time series.
    """
    return series[series.index.year.isin(years)].copy()


def resource_analysis(country, weather_years, wind_file, solar_file):
    """
    Compute annual mean wind and solar capacity factors for selected years.
    """
    wind_cf = load_cf_data(wind_file, country)
    solar_cf = load_cf_data(solar_file, country)

    wind_cf = extract_selected_years(wind_cf, weather_years)
    solar_cf = extract_selected_years(solar_cf, weather_years)

    annual_mean_cf = pd.DataFrame({
        "wind_mean_cf": wind_cf.groupby(wind_cf.index.year).mean(),
        "solar_mean_cf": solar_cf.groupby(solar_cf.index.year).mean(),
    })

    annual_mean_cf = annual_mean_cf.loc[weather_years]
    return annual_mean_cf


#%%
# -------------------------------------------------------------------------
# Section 2: System-side helper functions
# -------------------------------------------------------------------------
def get_yearly_cf_series(file_path, country, target_year, snapshot_index):
    """
    Read one full year of hourly capacity factor data and align it to snapshots.
    """
    df = pd.read_csv(file_path, sep=";", index_col=0)
    df.index = pd.to_datetime(df.index)

    if country not in df.columns:
        raise KeyError(f"Country '{country}' not found in file: {file_path}")

    cf_series = df.loc[df.index.year == target_year, country]

    if cf_series.empty:
        raise ValueError(f"No data found for year {target_year} in {file_path}")

    cf_series = cf_series.sort_index()

    if getattr(cf_series.index, "tz", None) is not None:
        cf_series.index = cf_series.index.tz_localize(None)

    snapshot_index = pd.DatetimeIndex(snapshot_index)
    if getattr(snapshot_index, "tz", None) is not None:
        snapshot_index = snapshot_index.tz_localize(None)

    cf_series = cf_series.reindex(snapshot_index)
    cf_series = cf_series.interpolate(method="time").ffill().bfill()

    return cf_series


def build_aligned_demand_series(df_elec, country, demand_year, snapshot_index):
    """
    Build a demand time series aligned to the selected weather year snapshots.
    """
    demand_series = df_elec.loc[df_elec.index.year == demand_year, country]

    if demand_series.empty:
        raise ValueError(f"No demand data found for year {demand_year}")

    demand_series = demand_series.sort_index()

    if getattr(demand_series.index, "tz", None) is not None:
        demand_series.index = demand_series.index.tz_localize(None)

    snapshot_index = pd.DatetimeIndex(snapshot_index)
    if getattr(snapshot_index, "tz", None) is not None:
        snapshot_index = snapshot_index.tz_localize(None)

    source_year = demand_series.index[0].year
    target_year = snapshot_index[0].year

    # Move 2015 demand profile to the target weather year if needed
    if source_year != target_year:
        new_index = []
        valid_values = []

        for t, val in demand_series.items():
            try:
                new_index.append(t.replace(year=target_year))
                valid_values.append(val)
            except ValueError:
                # Skip invalid dates such as Feb 29 when needed
                pass

        demand_series = pd.Series(valid_values, index=pd.DatetimeIndex(new_index))

    demand_aligned = demand_series.reindex(snapshot_index)
    demand_aligned = demand_aligned.interpolate(method="time").ffill().bfill()

    return demand_aligned


def build_network(country="DEU", demand_year=2015, weather_year=2015):
    """
    Build a single-node PyPSA network for one weather year.
    """
    network = pypsa.Network()

    hours = pd.date_range(
        f"{weather_year}-01-01 00:00",
        f"{weather_year}-12-31 23:00",
        freq="h"
    )
    network.set_snapshots(hours)

    network.add("Bus", "electricity bus")

    # Demand
    df_elec = pd.read_csv("data/electricity_demand.csv", sep=";", index_col=0)
    df_elec.index = pd.to_datetime(df_elec.index)

    demand_aligned = build_aligned_demand_series(
        df_elec=df_elec,
        country=country,
        demand_year=demand_year,
        snapshot_index=network.snapshots
    )

    network.add(
        "Load",
        "load",
        bus="electricity bus",
        p_set=demand_aligned.values
    )

    # Carriers
    network.add("Carrier", "gas", co2_emissions=0.19)
    network.add("Carrier", "onshorewind")
    network.add("Carrier", "solar")
    network.add("Carrier", "hydro")

    # Wind
    cf_wind = get_yearly_cf_series(
        file_path=wind_file,
        country=country,
        target_year=weather_year,
        snapshot_index=network.snapshots
    )

    capital_cost_wind = (
        annuity(tech_data["onshorewind"]["lifetime"], 0.07)
        * tech_data["onshorewind"]["overnight_cost"]
        * (1 + tech_data["onshorewind"]["capital_cost_increase"])
    )

    network.add(
        "Generator",
        "onshorewind",
        bus="electricity bus",
        p_nom_extendable=True,
        carrier="onshorewind",
        capital_cost=capital_cost_wind,
        marginal_cost=0,
        p_max_pu=cf_wind.values
    )

    # Solar utility-scale
    cf_solar = get_yearly_cf_series(
        file_path=solar_file,
        country=country,
        target_year=weather_year,
        snapshot_index=network.snapshots
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

    network.add(
        "Generator",
        "solar",
        bus="electricity bus",
        p_nom_extendable=True,
        carrier="solar",
        capital_cost=capital_cost_solar,
        marginal_cost=0,
        p_max_pu=cf_solar.values
    )

    # Solar rooftop
    network.add(
        "Generator",
        "solar_rooftop",
        bus="electricity bus",
        p_nom_extendable=True,
        carrier="solar",
        capital_cost=capital_cost_rooftop_solar,
        marginal_cost=0,
        p_max_pu=cf_solar.values
    )

    # Existing hydro
    network.add(
        "Generator",
        "run_of_river",
        bus="electricity bus",
        p_nom=tech_data["run_of_river"]["fixed_capacity"],
        carrier="hydro",
        capital_cost=0,
        marginal_cost=0,
        p_max_pu=tech_data["run_of_river"]["availability"]
    )

    network.add(
        "Generator",
        "hydro_reservoir",
        bus="electricity bus",
        p_nom=tech_data["hydro_reservoir"]["fixed_capacity"],
        carrier="hydro",
        capital_cost=0,
        marginal_cost=0,
        p_max_pu=tech_data["hydro_reservoir"]["availability"]
    )

    # OCGT
    capital_cost_ocgt = (
        annuity(tech_data["OCGT"]["lifetime"], 0.07)
        * tech_data["OCGT"]["overnight_cost"]
        * (1 + tech_data["OCGT"]["capital_cost_increase"])
    )

    fuel_cost = tech_data["OCGT"]["fuel_cost"]
    efficiency = tech_data["OCGT"]["efficiency"]
    marginal_cost_ocgt = fuel_cost / efficiency

    network.add(
        "Generator",
        "OCGT",
        bus="electricity bus",
        p_nom_extendable=True,
        carrier="gas",
        capital_cost=capital_cost_ocgt,
        marginal_cost=marginal_cost_ocgt,
        efficiency=efficiency
    )

    return network


def run_weather_variability_analysis(
    country="DEU",
    demand_year=2015,
    weather_years=None,
    solver_name="gurobi"
):
    """
    Solve the optimization model for multiple weather years
    and collect optimal capacities.
    """
    if weather_years is None:
        weather_years = [2013, 2014, 2015, 2016, 2017]

    results = {}

    for year in weather_years:
        print("=" * 70)
        print(f"Solving model for weather year {year}")

        network = build_network(
            country=country,
            demand_year=demand_year,
            weather_year=year
        )

        network.optimize(
            solver_name=solver_name,
            solver_options={"OutputFlag": 0, "LogToConsole": 0}
        )

        capacities = network.generators.p_nom_opt[
            ["onshorewind", "solar", "solar_rooftop",
             "run_of_river", "hydro_reservoir", "OCGT"]
        ].copy()

        results[year] = capacities

    capacities_by_year = pd.DataFrame.from_dict(results, orient="index")
    capacities_by_year.index.name = "weather_year"

    return capacities_by_year


#%%
# -------------------------------------------------------------------------
# Section 3: Plotting functions
# -------------------------------------------------------------------------
def plot_capacity_boxplot(capacities_by_year, save_path):
    """
    Plot installed capacity distribution across weather years as a boxplot.
    Add a legend so readers can identify median and mean directly.
    """
    fig, ax = plt.subplots(figsize=(11, 6))

    data = [capacities_by_year[col].dropna().values for col in capacities_by_year.columns]

    ax.boxplot(
        data,
        labels=capacities_by_year.columns,
        showmeans=True,
        medianprops=dict(color="orange", linewidth=1.8),
        meanprops=dict(
            marker="^",
            markerfacecolor="tab:green",
            markeredgecolor="tab:green",
            markersize=7
        )
    )

    ax.set_xlabel("Generator")
    ax.set_ylabel("Installed capacity [MW]")
    ax.set_title("Installed capacity distribution across weather years")
    plt.xticks(rotation=20)

    # Custom legend for median line and mean triangle
    legend_handles = [
        Line2D([0], [0], color="orange", lw=2, label="Median"),
        Line2D(
            [0], [0],
            marker="^",
            color="tab:green",
            markerfacecolor="tab:green",
            markeredgecolor="tab:green",
            linestyle="None",
            markersize=8,
            label="Mean"
        )
    ]
    ax.legend(handles=legend_handles, loc="upper right")

    plt.tight_layout()
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.show()
    plt.close(fig)


def plot_two_panel_summary(annual_mean_cf, capacities_by_year, weather_years, save_path):
    """
    Create a two-panel figure:
    Left : annual mean wind and solar capacity factors
    Right: wind and total solar capacities under different weather years
    """
    wind_solar = pd.DataFrame(index=capacities_by_year.index)
    wind_solar["onshorewind"] = capacities_by_year["onshorewind"]
    wind_solar["solar_total"] = capacities_by_year["solar"] + capacities_by_year["solar_rooftop"]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Left panel: annual mean CF
    x = np.arange(len(weather_years))
    width = 0.35

    axes[0].bar(
        x - width / 2,
        annual_mean_cf["wind_mean_cf"].values,
        width=width,
        label="Onshore wind"
    )
    axes[0].bar(
        x + width / 2,
        annual_mean_cf["solar_mean_cf"].values,
        width=width,
        label="Solar PV"
    )

    axes[0].set_xticks(x)
    axes[0].set_xticklabels(weather_years)
    axes[0].set_xlabel("Weather year")
    axes[0].set_ylabel("Annual mean capacity factor [-]")
    axes[0].set_title("Annual mean wind and solar capacity factors (2013-2017)")
    axes[0].legend()

    # Right panel: wind and solar capacities
    x2 = np.arange(len(wind_solar.index))

    axes[1].bar(
        x2 - width / 2,
        wind_solar["onshorewind"].values,
        width=width,
        label="onshorewind"
    )
    axes[1].bar(
        x2 + width / 2,
        wind_solar["solar_total"].values,
        width=width,
        label="solar_total"
    )

    axes[1].set_xticks(x2)
    axes[1].set_xticklabels(wind_solar.index.astype(str))
    axes[1].set_xlabel("Weather year")
    axes[1].set_ylabel("Installed capacity [MW]")
    axes[1].set_title("Wind and total solar capacities under different weather years")
    axes[1].legend()

    plt.tight_layout()
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.show()
    plt.close(fig)


#%%
# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------
if __name__ == "__main__":
    # 1) Resource-side analysis
    annual_mean_cf = resource_analysis(
        country=country,
        weather_years=weather_years,
        wind_file=wind_file,
        solar_file=solar_file
    )

    print("\nAnnual mean capacity factors:")
    print(annual_mean_cf)

    # 2) System-side optimization analysis
    capacities_by_year = run_weather_variability_analysis(
        country=country,
        demand_year=demand_year,
        weather_years=weather_years,
        solver_name="gurobi"
    )

    print("\nOptimal capacities by weather year [MW]:")
    print(capacities_by_year)

    # 3) Plot only the required 3 charts
    # Figure 1: boxplot with legend
    plot_capacity_boxplot(
        capacities_by_year,
        FIG_DIR / "figure1_capacity_boxplot.png"
    )

    # Figure 2: two-panel figure containing the other 2 charts
    plot_two_panel_summary(
        annual_mean_cf,
        capacities_by_year,
        weather_years,
        FIG_DIR / "figure2_two_panel_summary.png"
    )

    print("\nOnly the required figures have been saved to:")
    print(FIG_DIR.resolve())