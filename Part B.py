#%%
import pandas as pd
import matplotlib.pyplot as plt
import pypsa

# Import technology data and annuity function from project files
from data.data import tech_data
from utils import annuity


#%%
def get_yearly_cf_series(file_path, country, target_year, snapshot_index):
    """
    Read one full year of hourly capacity factor data for a selected country,
    then align it to the model snapshots.
    """
    df = pd.read_csv(file_path, sep=";", index_col=0)
    df.index = pd.to_datetime(df.index)

    if country not in df.columns:
        raise KeyError(f"Country '{country}' not found in file: {file_path}")

    # Select the chosen weather year
    cf_series = df.loc[df.index.year == target_year, country]

    if cf_series.empty:
        raise ValueError(f"No data found for year {target_year} in {file_path}")

    # Sort by time
    cf_series = cf_series.sort_index()

    # Remove timezone information for safe alignment
    cf_series.index = cf_series.index.tz_localize(None)
    snapshot_index = pd.DatetimeIndex(snapshot_index).tz_localize(None)

    # Align to model snapshots exactly
    cf_series = cf_series.reindex(snapshot_index)

    # Fill any missing values created during reindexing
    cf_series = cf_series.interpolate(method="time").ffill().bfill()

    return cf_series


#%%
def build_aligned_demand_series(df_elec, country, demand_year, snapshot_index):
    """
    Build a demand time series aligned to the selected weather year snapshots.

    The demand profile shape is kept from demand_year, but timestamps are remapped
    to the target snapshot year. This isolates weather variability from demand variability.
    """
    demand_series = df_elec.loc[df_elec.index.year == demand_year, country]

    if demand_series.empty:
        raise ValueError(f"No demand data found for year {demand_year}")

    # Sort by time
    demand_series = demand_series.sort_index()

    # Remove timezone information
    demand_series.index = demand_series.index.tz_localize(None)
    snapshot_index = pd.DatetimeIndex(snapshot_index).tz_localize(None)

    source_year = demand_series.index[0].year
    target_year = snapshot_index[0].year

    # If the source year differs from the target year, rebuild timestamps
    if source_year != target_year:
        new_index = []
        valid_values = []

        for t, val in demand_series.items():
            try:
                new_index.append(t.replace(year=target_year))
                valid_values.append(val)
            except ValueError:
                # Skip impossible dates such as Feb 29 in non-leap years
                pass

        demand_series = pd.Series(valid_values, index=pd.DatetimeIndex(new_index))

    # Align demand to snapshots
    demand_aligned = demand_series.reindex(snapshot_index)
    demand_aligned = demand_aligned.interpolate(method="time").ffill().bfill()

    return demand_aligned


#%%
def build_network(country="DEU", demand_year=2015, weather_year=2015):
    """
    Build a single-node PyPSA network for one weather year.

    The model structure is kept fixed, while the wind and solar capacity factors
    change with the selected weather year.
    """
    network = pypsa.Network()

    # Define hourly snapshots for the selected weather year
    hours = pd.date_range(
        f"{weather_year}-01-01 00:00Z",
        f"{weather_year}-12-31 23:00Z",
        freq="h"
    )
    network.set_snapshots(hours.values)

    # Add one electricity bus (single-node / copper-plate model)
    network.add("Bus", "electricity bus")

    # -------------------------------------------------------------------------
    # Add electricity demand
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # Add carriers
    # -------------------------------------------------------------------------
    network.add("Carrier", "gas", co2_emissions=0.19)   # tCO2/MWh_th
    network.add("Carrier", "onshorewind")
    network.add("Carrier", "solar")
    network.add("Carrier", "hydro")

    # -------------------------------------------------------------------------
    # Add onshore wind
    # -------------------------------------------------------------------------
    cf_wind = get_yearly_cf_series(
        file_path="data/onshore_wind_1979-2017.csv",
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

    # -------------------------------------------------------------------------
    # Add utility-scale solar and rooftop solar
    # Both use the same solar CF series in this simplified model
    # -------------------------------------------------------------------------
    cf_solar = get_yearly_cf_series(
        file_path="data/pv_optimal.csv",
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

    # -------------------------------------------------------------------------
    # Add existing hydro as fixed capacities
    # These are simplified proxy generators rather than detailed hydro models
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # Add OCGT
    # -------------------------------------------------------------------------
    capital_cost_ocgt = (
        annuity(tech_data["OCGT"]["lifetime"], 0.07)
        * tech_data["OCGT"]["overnight_cost"]
        * (1 + tech_data["OCGT"]["capital_cost_increase"])
    )

    fuel_cost = tech_data["OCGT"]["fuel_cost"]      # €/MWh_th
    efficiency = tech_data["OCGT"]["efficiency"]    # MWh_el / MWh_th
    marginal_cost_ocgt = fuel_cost / efficiency     # €/MWh_el

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

        # Store optimal generator capacities for this weather year
        capacities = network.generators.p_nom_opt.copy()
        capacities.name = year
        results.append(capacities)

    # Combine all yearly capacity results into one DataFrame
    capacities_by_year = pd.DataFrame(results)
    capacities_by_year.index.name = "weather_year"

    # Compute summary statistics across weather years
    summary_stats = pd.DataFrame({
        "mean_MW": capacities_by_year.mean(axis=0),
        "std_MW": capacities_by_year.std(axis=0),
        "min_MW": capacities_by_year.min(axis=0),
        "max_MW": capacities_by_year.max(axis=0),
    })

    return capacities_by_year, summary_stats


#%%
def plot_capacities_by_weather_year(capacities_by_year):
    """
    Plot optimal installed capacities for all generators
    across different weather years.
    """
    ax = capacities_by_year.plot(kind="bar", figsize=(12, 6))
    ax.set_xlabel("Weather year")
    ax.set_ylabel("Installed capacity [MW]")
    ax.set_title("Optimal capacities under different weather years")
    plt.xticks(rotation=0)
    plt.tight_layout()
    plt.show()


#%%
def plot_average_capacity_with_variability(summary_stats):
    """
    Plot average installed capacity and standard deviation
    for all generators.
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
    plt.show()


#%%
def plot_wind_solar_only(capacities_by_year):
    """
    Plot wind and total solar capacities only,
    where total solar = utility-scale solar + rooftop solar.
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
    plt.show()

    return wind_solar


#%%
def plot_wind_solar_average_variability(wind_solar_df):
    """
    Plot average capacity and standard deviation
    for wind and total solar only.
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
    plt.show()

    return wind_solar_summary


#%%
if __name__ == "__main__":
    # Fixed country and demand year
    # Demand is kept fixed so that only weather variability is tested
    country = "DEU"
    demand_year = 2015
    weather_years = [2013, 2014, 2015, 2016, 2017]

    # Run optimization for all selected weather years
    capacities_by_year, summary_stats = run_weather_variability_analysis(
        country=country,
        demand_year=demand_year,
        weather_years=weather_years,
        solver_name="gurobi"
    )

    # Print detailed results
    print("\nOptimal capacities by weather year [MW]:")
    print(capacities_by_year)

    print("\nAverage capacity and variability [MW]:")
    print(summary_stats)

    # Save full results to CSV
    capacities_by_year.to_csv("b_capacities_by_weather_year.csv")
    summary_stats.to_csv("b_summary_statistics.csv")

    # Plot all-generator results
    plot_capacities_by_weather_year(capacities_by_year)
    plot_average_capacity_with_variability(summary_stats)

    # Plot wind and solar focused results
    wind_solar_df = plot_wind_solar_only(capacities_by_year)
    wind_solar_summary = plot_wind_solar_average_variability(wind_solar_df)

    # Save wind and solar focused results to CSV
    wind_solar_df.to_csv("b_wind_solar_by_weather_year.csv")
    wind_solar_summary.to_csv("b_wind_solar_summary.csv")