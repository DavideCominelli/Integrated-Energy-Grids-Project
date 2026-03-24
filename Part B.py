#%%
import pandas as pd
import matplotlib.pyplot as plt
import pypsa
from pathlib import Path

# Import technology data and annuity function from project files
from data.data import tech_data
from utils import annuity


#%%
# -------------------------------------------------------------------------
# Global settings
# -------------------------------------------------------------------------
country = "DEU"
demand_year = 2015
weather_years = [2013, 2014, 2015, 2016, 2017]

wind_file = "data/onshore_wind_1979-2017.csv"
solar_file = "data/pv_optimal.csv"

# Output folders
OUTPUT_DIR = Path("output_b")
FIG_DIR = OUTPUT_DIR / "figures"
DATA_DIR = OUTPUT_DIR / "data"

# Create folders if they do not exist
FIG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)


#%%
# -------------------------------------------------------------------------
# Section 1: Resource-side helper functions
# -------------------------------------------------------------------------
def load_cf_data(file_path, country):
    """
    Load capacity factor data from a CSV file and return the selected country
    as a pandas time series.
    """
    df = pd.read_csv(file_path, sep=";", index_col=0)
    df.index = pd.to_datetime(df.index)

    if country not in df.columns:
        raise KeyError(f"Country '{country}' not found in {file_path}")

    series = df[country].copy()
    series.name = country
    return series


#%%
def extract_selected_years(series, years):
    """
    Keep only the selected weather years from a time series.
    """
    return series[series.index.year.isin(years)].copy()


#%%
def resource_analysis(country, weather_years, wind_file, solar_file):
    """
    Analyze wind and solar resource variability across the selected weather years.

    Outputs:
    - annual mean CF table
    - monthly mean CF tables
    - seasonal average profiles
    """
    # Load full wind and solar CF series
    wind_cf = load_cf_data(wind_file, country)
    solar_cf = load_cf_data(solar_file, country)

    # Keep only the selected years
    wind_cf = extract_selected_years(wind_cf, weather_years)
    solar_cf = extract_selected_years(solar_cf, weather_years)

    # Annual mean CF
    annual_mean_cf = pd.DataFrame({
        "wind_mean_cf": wind_cf.groupby(wind_cf.index.year).mean(),
        "solar_mean_cf": solar_cf.groupby(solar_cf.index.year).mean(),
    })
    annual_mean_cf = annual_mean_cf.loc[weather_years]

    # Monthly mean CF for each year
    wind_monthly = (
        wind_cf.groupby([wind_cf.index.year.rename("year"),
                         wind_cf.index.month.rename("month")])
        .mean()
        .unstack(level=0)
    )

    solar_monthly = (
        solar_cf.groupby([solar_cf.index.year.rename("year"),
                          solar_cf.index.month.rename("month")])
        .mean()
        .unstack(level=0)
    )

    wind_monthly = wind_monthly.loc[1:12]
    solar_monthly = solar_monthly.loc[1:12]

    # Average seasonal profiles across all selected years
    seasonal_profiles = pd.DataFrame({
        "wind_mean_2013_2017": wind_cf.groupby(wind_cf.index.month).mean(),
        "solar_mean_2013_2017": solar_cf.groupby(solar_cf.index.month).mean(),
    })

    return wind_cf, solar_cf, annual_mean_cf, wind_monthly, solar_monthly, seasonal_profiles


#%%
# -------------------------------------------------------------------------
# Section 2: Resource-side plotting functions
# -------------------------------------------------------------------------
def plot_annual_mean_cf(annual_mean_cf, weather_years, save_path):
    """
    Plot annual mean wind and solar capacity factors for the selected years.
    """
    fig, ax = plt.subplots(figsize=(9, 6))

    x = range(len(weather_years))
    width = 0.35

    ax.bar(
        [i - width/2 for i in x],
        annual_mean_cf["wind_mean_cf"],
        width=width,
        label="Onshore wind"
    )

    ax.bar(
        [i + width/2 for i in x],
        annual_mean_cf["solar_mean_cf"],
        width=width,
        label="Solar PV"
    )

    ax.set_xticks(list(x))
    ax.set_xticklabels(weather_years)
    ax.set_xlabel("Weather year")
    ax.set_ylabel("Annual mean capacity factor [-]")
    ax.set_title("Annual mean wind and solar capacity factors (2013-2017)")
    ax.legend()
    plt.tight_layout()
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.show()
    plt.close(fig)


#%%
def plot_monthly_mean_cf(wind_monthly, solar_monthly, weather_years, save_path):
    """
    Plot monthly mean wind and solar capacity factors for each weather year.
    """
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharex=True)

    for year in weather_years:
        axes[0].plot(wind_monthly.index, wind_monthly[year], label=str(year))
    axes[0].set_title("Monthly mean onshore wind CF")
    axes[0].set_xlabel("Month")
    axes[0].set_ylabel("Capacity factor [-]")
    axes[0].set_xticks(range(1, 13))

    for year in weather_years:
        axes[1].plot(solar_monthly.index, solar_monthly[year], label=str(year))
    axes[1].set_title("Monthly mean solar PV CF")
    axes[1].set_xlabel("Month")
    axes[1].set_ylabel("Capacity factor [-]")
    axes[1].set_xticks(range(1, 13))

    axes[1].legend(title="Year", bbox_to_anchor=(1.02, 1), loc="upper left")
    plt.tight_layout()
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.show()
    plt.close(fig)


#%%
def plot_wind_solar_scatter(annual_mean_cf, weather_years, save_path):
    """
    Plot the relationship between annual mean wind CF and solar CF.
    """
    fig, ax = plt.subplots(figsize=(7, 6))

    ax.scatter(
        annual_mean_cf["wind_mean_cf"],
        annual_mean_cf["solar_mean_cf"]
    )

    for year in weather_years:
        ax.annotate(
            str(year),
            (
                annual_mean_cf.loc[year, "wind_mean_cf"],
                annual_mean_cf.loc[year, "solar_mean_cf"]
            ),
            xytext=(5, 5),
            textcoords="offset points"
        )

    ax.set_xlabel("Annual mean wind CF [-]")
    ax.set_ylabel("Annual mean solar CF [-]")
    ax.set_title("Relationship between annual mean wind and solar CF")
    plt.tight_layout()
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.show()
    plt.close(fig)


#%%
def plot_seasonal_profiles(seasonal_profiles, save_path):
    """
    Plot the average seasonal wind and solar profiles across all selected years.
    """
    fig, ax = plt.subplots(figsize=(9, 5))

    ax.plot(
        seasonal_profiles.index,
        seasonal_profiles["wind_mean_2013_2017"],
        marker="o",
        label="Onshore wind"
    )
    ax.plot(
        seasonal_profiles.index,
        seasonal_profiles["solar_mean_2013_2017"],
        marker="o",
        label="Solar PV"
    )

    ax.set_xlabel("Month")
    ax.set_ylabel("Capacity factor [-]")
    ax.set_title("Average seasonal wind and solar profiles (2013-2017)")
    ax.set_xticks(range(1, 13))
    ax.legend()
    plt.tight_layout()
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.show()
    plt.close(fig)


#%%
# -------------------------------------------------------------------------
# Section 3: System-side helper functions
# -------------------------------------------------------------------------
def get_yearly_cf_series(file_path, country, target_year, snapshot_index):
    """
    Read one full year of hourly capacity factor data for a selected country,
    then align it to the model snapshots.
    """
    df = pd.read_csv(file_path, sep=";", index_col=0)
    df.index = pd.to_datetime(df.index)

    if country not in df.columns:
        raise KeyError(f"Country '{country}' not found in file: {file_path}")

    cf_series = df.loc[df.index.year == target_year, country]

    if cf_series.empty:
        raise ValueError(f"No data found for year {target_year} in {file_path}")

    cf_series = cf_series.sort_index()
    cf_series.index = cf_series.index.tz_localize(None)
    snapshot_index = pd.DatetimeIndex(snapshot_index).tz_localize(None)

    cf_series = cf_series.reindex(snapshot_index)
    cf_series = cf_series.interpolate(method="time").ffill().bfill()

    return cf_series


#%%
def build_aligned_demand_series(df_elec, country, demand_year, snapshot_index):
    """
    Build a demand time series aligned to the selected weather year snapshots.
    """
    demand_series = df_elec.loc[df_elec.index.year == demand_year, country]

    if demand_series.empty:
        raise ValueError(f"No demand data found for year {demand_year}")

    demand_series = demand_series.sort_index()
    demand_series.index = demand_series.index.tz_localize(None)
    snapshot_index = pd.DatetimeIndex(snapshot_index).tz_localize(None)

    source_year = demand_series.index[0].year
    target_year = snapshot_index[0].year

    if source_year != target_year:
        new_index = []
        valid_values = []

        for t, val in demand_series.items():
            try:
                new_index.append(t.replace(year=target_year))
                valid_values.append(val)
            except ValueError:
                pass

        demand_series = pd.Series(valid_values, index=pd.DatetimeIndex(new_index))

    demand_aligned = demand_series.reindex(snapshot_index)
    demand_aligned = demand_aligned.interpolate(method="time").ffill().bfill()

    return demand_aligned


#%%
def build_network(country="DEU", demand_year=2015, weather_year=2015):
    """
    Build a single-node PyPSA network for one weather year.
    """
    network = pypsa.Network()

    hours = pd.date_range(
        f"{weather_year}-01-01 00:00Z",
        f"{weather_year}-12-31 23:00Z",
        freq="h"
    )
    network.set_snapshots(hours.values)

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

    # Solar
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


#%%
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

    results = []

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
            solver_options={"output_flag": 0, "logtoconsole": 0}
        )

        capacities = network.generators.p_nom_opt.copy()
        capacities.name = year
        results.append(capacities)

    capacities_by_year = pd.DataFrame(results)
    capacities_by_year.index.name = "weather_year"

    summary_stats = pd.DataFrame({
        "mean_MW": capacities_by_year.mean(axis=0),
        "std_MW": capacities_by_year.std(axis=0),
        "min_MW": capacities_by_year.min(axis=0),
        "max_MW": capacities_by_year.max(axis=0),
    })

    return capacities_by_year, summary_stats


#%%
# -------------------------------------------------------------------------
# Section 4: System-side plotting functions
# -------------------------------------------------------------------------
def plot_capacities_by_weather_year(capacities_by_year, save_path):
    """
    Plot optimal installed capacities for all generators across weather years.
    """
    ax = capacities_by_year.plot(kind="bar", figsize=(12, 6))
    ax.set_xlabel("Weather year")
    ax.set_ylabel("Installed capacity [MW]")
    ax.set_title("Optimal capacities under different weather years")
    plt.xticks(rotation=0)
    plt.tight_layout()
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.show()
    plt.close()


#%%
def plot_average_capacity_with_variability(summary_stats, save_path):
    """
    Plot average installed capacity and standard deviation for all generators.
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    ax.bar(
        x=summary_stats.index,
        height=summary_stats["mean_MW"],
        yerr=summary_stats["std_MW"],
        capsize=6
    )

    ax.set_xlabel("Generator")
    ax.set_ylabel("Installed capacity [MW]")
    ax.set_title("Average installed capacity and variability across weather years")
    plt.xticks(rotation=20)
    plt.tight_layout()
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.show()
    plt.close(fig)


#%%
def plot_wind_solar_only(capacities_by_year, save_path):
    """
    Plot wind and total solar capacities only.
    """
    wind_solar = pd.DataFrame(index=capacities_by_year.index)
    wind_solar["onshorewind"] = capacities_by_year["onshorewind"]
    wind_solar["solar_total"] = capacities_by_year["solar"] + capacities_by_year["solar_rooftop"]

    ax = wind_solar.plot(kind="bar", figsize=(10, 6))
    ax.set_xlabel("Weather year")
    ax.set_ylabel("Installed capacity [MW]")
    ax.set_title("Wind and total solar capacities under different weather years")
    plt.xticks(rotation=0)
    plt.tight_layout()
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.show()
    plt.close()

    return wind_solar


#%%
def plot_wind_solar_average_variability(wind_solar_df, save_path):
    """
    Plot average capacity and standard deviation for wind and total solar only.
    """
    wind_solar_summary = pd.DataFrame({
        "mean_MW": wind_solar_df.mean(axis=0),
        "std_MW": wind_solar_df.std(axis=0),
        "min_MW": wind_solar_df.min(axis=0),
        "max_MW": wind_solar_df.max(axis=0),
    })

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.bar(
        x=wind_solar_summary.index,
        height=wind_solar_summary["mean_MW"],
        yerr=wind_solar_summary["std_MW"],
        capsize=6
    )
    ax.set_xlabel("Technology")
    ax.set_ylabel("Installed capacity [MW]")
    ax.set_title("Average capacity and variability of wind and total solar")
    plt.tight_layout()
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.show()
    plt.close(fig)

    return wind_solar_summary


#%%
if __name__ == "__main__":
    # =====================================================================
    # Part 1: Resource-side analysis
    # =====================================================================
    wind_cf, solar_cf, annual_mean_cf, wind_monthly, solar_monthly, seasonal_profiles = resource_analysis(
        country=country,
        weather_years=weather_years,
        wind_file=wind_file,
        solar_file=solar_file
    )

    print("\nAnnual mean capacity factors:")
    print(annual_mean_cf)

    # Save resource-side data
    annual_mean_cf.to_csv(DATA_DIR / "annual_mean_cf_2013_2017.csv")
    wind_monthly.to_csv(DATA_DIR / "monthly_wind_cf_2013_2017.csv")
    solar_monthly.to_csv(DATA_DIR / "monthly_solar_cf_2013_2017.csv")
    seasonal_profiles.to_csv(DATA_DIR / "seasonal_profiles_2013_2017.csv")

    # Plot resource-side figures
    plot_annual_mean_cf(annual_mean_cf, weather_years, FIG_DIR / "annual_mean_cf.png")
    plot_monthly_mean_cf(wind_monthly, solar_monthly, weather_years, FIG_DIR / "monthly_mean_cf.png")
    plot_wind_solar_scatter(annual_mean_cf, weather_years, FIG_DIR / "wind_solar_scatter.png")
    plot_seasonal_profiles(seasonal_profiles, FIG_DIR / "seasonal_profiles.png")

    # =====================================================================
    # Part 2: System-side optimization analysis
    # =====================================================================
    capacities_by_year, summary_stats = run_weather_variability_analysis(
        country=country,
        demand_year=demand_year,
        weather_years=weather_years,
        solver_name="gurobi"
    )

    print("\nOptimal capacities by weather year [MW]:")
    print(capacities_by_year)

    print("\nAverage capacity and variability [MW]:")
    print(summary_stats)

    # Save system-side data
    capacities_by_year.to_csv(DATA_DIR / "b_capacities_by_weather_year.csv")
    summary_stats.to_csv(DATA_DIR / "b_summary_statistics.csv")

    # Plot all-generator results
    plot_capacities_by_weather_year(
        capacities_by_year,
        FIG_DIR / "b_capacities_by_weather_year.png"
    )
    plot_average_capacity_with_variability(
        summary_stats,
        FIG_DIR / "b_summary_statistics.png"
    )

    # Plot wind and solar focused results
    wind_solar_df = plot_wind_solar_only(
        capacities_by_year,
        FIG_DIR / "b_wind_solar_by_weather_year.png"
    )
    wind_solar_summary = plot_wind_solar_average_variability(
        wind_solar_df,
        FIG_DIR / "b_wind_solar_summary.png"
    )

    # Save wind and solar focused data
    wind_solar_df.to_csv(DATA_DIR / "b_wind_solar_by_weather_year.csv")
    wind_solar_summary.to_csv(DATA_DIR / "b_wind_solar_summary.csv")

    print("\nAll outputs saved under:")
    print(f"- Figures: {FIG_DIR.resolve()}")
    print(f"- Data:    {DATA_DIR.resolve()}")