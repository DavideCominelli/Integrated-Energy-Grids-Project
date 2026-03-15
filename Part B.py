#%%
import pandas as pd
import matplotlib.pyplot as plt
import pypsa

from data.data import tech_data
from utils import annuity




#%%
def get_yearly_cf_series(file_path, country, target_year, snapshot_index):
    
    df = pd.read_csv(file_path, sep=";", index_col=0)
    df.index = pd.to_datetime(df.index)

    if country not in df.columns:
        raise KeyError(f"Country '{country}' not found in file: {file_path}")

    # Select the target year
    cf_series = df.loc[df.index.year == target_year, country]

    if cf_series.empty:
        raise ValueError(
            f"No data found for year {target_year} in file: {file_path}"
        )

    cf_series = cf_series.sort_index()

    # Remove timezone for safe alignment
    cf_series.index = cf_series.index.tz_localize(None)
    snapshot_index = pd.DatetimeIndex(snapshot_index).tz_localize(None)

    # Align to snapshots exactly
    cf_series = cf_series.reindex(snapshot_index)

    # Fill possible missing values created during alignment
    cf_series = cf_series.interpolate(method="time").ffill().bfill()

    return cf_series


#%%
def build_aligned_demand_series(df_elec, country, demand_year, snapshot_index):
    
    demand_series = df_elec.loc[df_elec.index.year == demand_year, country]

    if demand_series.empty:
        print(f"Warning: no demand data found for {demand_year}, using 2015 demand instead.")
        demand_series = df_elec.loc[df_elec.index.year == 2015, country]

    if demand_series.empty:
        raise ValueError(
            f"No electricity demand found for year {demand_year}, and fallback year 2015 also not found."
        )

    demand_series = demand_series.sort_index()

    # Remove timezone
    demand_series.index = demand_series.index.tz_localize(None)
    snapshot_index = pd.DatetimeIndex(snapshot_index).tz_localize(None)

    # Rebuild timestamps so month/day/hour pattern matches the snapshot year
    # This is important when using one demand profile shape with another year.
    source_year = demand_series.index[0].year
    target_year = snapshot_index[0].year

    if source_year != target_year:
        new_index = []
        for t in demand_series.index:
            try:
                new_index.append(t.replace(year=target_year))
            except ValueError:
                # Handles Feb 29 issues when source/target leap-year status differs
                # Use interpolation later after reindexing
                continue
        demand_series = demand_series.iloc[:len(new_index)].copy()
        demand_series.index = pd.DatetimeIndex(new_index)

    # Align to snapshots
    demand_aligned = demand_series.reindex(snapshot_index)
    demand_aligned = demand_aligned.interpolate(method="time").ffill().bfill()

    return demand_aligned


#%%
def build_network(country="DEU", demand_year=2015, weather_year=2015):
    

    
    # 1. Create network and define hourly snapshots for the weather year
    
    network = pypsa.Network()

    hours = pd.date_range(
        f"{weather_year}-01-01 00:00Z",
        f"{weather_year}-12-31 23:00Z",
        freq="h"
    )
    network.set_snapshots(hours.values)

    
    # 2. Add one electricity bus (single-node / copper-plate system)
  
    network.add("Bus", "electricity bus")

   
    # 3. Add electricity demand
   
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

   
    # 4. Add carriers
    
    network.add("Carrier", "gas", co2_emissions=0.19)  # tCO2/MWh_th
    network.add("Carrier", "onshorewind")
    network.add("Carrier", "solar")
    network.add("Carrier", "hydro")

    
    # 5. Add wind generator using the selected weather year
    
    cf_wind = get_yearly_cf_series(
        file_path="data/onshore_wind_1979-2017.csv",
        country=country,
        target_year=weather_year,
        snapshot_index=network.snapshots
    )

    if len(cf_wind) != len(network.snapshots):
        raise ValueError(
            f"Wind CF length ({len(cf_wind)}) does not match model snapshots "
            f"({len(network.snapshots)})."
        )

    capital_cost_onshorewind = (
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
        capital_cost=capital_cost_onshorewind,
        marginal_cost=0,
        p_max_pu=cf_wind.values
    )

    
    # 6. Add solar generators using the selected weather year
    
    cf_solar = get_yearly_cf_series(
        file_path="data/pv_optimal.csv",
        country=country,
        target_year=weather_year,
        snapshot_index=network.snapshots
    )

    if len(cf_solar) != len(network.snapshots):
        raise ValueError(
            f"Solar CF length ({len(cf_solar)}) does not match model snapshots "
            f"({len(network.snapshots)})."
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

    
    # 7. Add hydro as fixed existing capacities
    
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

    
    # 8. Add OCGT
    
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

    
    # Debug prints
   
    print(f"\nWeather year = {weather_year}")
    print("Demand length:", len(demand_aligned), "NaN:", demand_aligned.isna().sum())
    print("Wind CF length:", len(cf_wind), "min:", cf_wind.min(), "max:", cf_wind.max(), "NaN:", cf_wind.isna().sum())
    print("Solar CF length:", len(cf_solar), "min:", cf_solar.min(), "max:", cf_solar.max(), "NaN:", cf_solar.isna().sum())

    return network


#%%
def aggregate_capacities(raw_capacities):
    """
    Aggregate generator capacities into broader technology groups.
    """
    agg = pd.Series(dtype=float)

    agg["wind"] = raw_capacities.get("onshorewind", 0.0)
    agg["solar_total"] = (
        raw_capacities.get("solar", 0.0) +
        raw_capacities.get("solar_rooftop", 0.0)
    )
    agg["hydro_total"] = (
        raw_capacities.get("run_of_river", 0.0) +
        raw_capacities.get("hydro_reservoir", 0.0)
    )
    agg["gas"] = raw_capacities.get("OCGT", 0.0)

    return agg


#%%
def run_weather_variability_analysis(
    country="DEU",
    demand_year=2015,
    weather_years=None,
    solver_name="gurobi"
):
    """
    Run the optimization for a list of weather years and collect results.
    """
    if weather_years is None:
        weather_years = [2013, 2014, 2015, 2016, 2017]

    all_results = []

    for year in weather_years:
        print("=" * 70)
        print(f"Solving for weather year {year}")

        network = build_network(
            country=country,
            demand_year=demand_year,
            weather_year=year
        )

        network.optimize(solver_name=solver_name)

        # Save LP model if needed
        network.model.to_file(f"model_weather_{year}.lp")

        raw_capacities = network.generators.p_nom_opt.copy()
        agg_capacities = aggregate_capacities(raw_capacities)
        agg_capacities.name = year

        all_results.append(agg_capacities)

    capacities_by_year = pd.DataFrame(all_results)
    capacities_by_year.index.name = "weather_year"

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
    Plot installed capacities for each technology across weather years.
    """
    ax = capacities_by_year.plot(kind="bar", figsize=(11, 6))
    ax.set_xlabel("Weather year")
    ax.set_ylabel("Installed capacity [MW]")
    ax.set_title("Optimal capacities for different weather years")
    plt.xticks(rotation=0)
    plt.tight_layout()
    plt.show()

#%%
def extract_wind_solar_only(capacities_by_year):
    """
    Keep only wind and solar_total columns for a focused comparison.
    """
    return capacities_by_year[["wind", "solar_total"]].copy()

#%%
def plot_average_capacity_with_variability(summary_stats):
    """
    Plot average capacity with variability (standard deviation) as error bars.
    """
    fig, ax = plt.subplots(figsize=(9, 6))

    ax.bar(
        x=summary_stats.index,
        height=summary_stats["mean_MW"],
        yerr=summary_stats["std_MW"],
        capsize=6
    )

    ax.set_xlabel("Technology")
    ax.set_ylabel("Installed capacity [MW]")
    ax.set_title("Average capacity and variability across weather years")
    plt.tight_layout()
    plt.show()

#%%
def plot_wind_solar_by_weather_year(wind_solar_df):
    """
    Plot only wind and solar capacities across weather years.
    """
    ax = wind_solar_df.plot(kind="bar", figsize=(10, 6))
    ax.set_xlabel("Weather year")
    ax.set_ylabel("Installed capacity [MW]")
    ax.set_title("Optimal wind and solar capacities for different weather years")
    plt.xticks(rotation=0)
    plt.tight_layout()
    plt.show()


#%%
def plot_wind_solar_average_variability(wind_solar_summary):
    """
    Plot average capacity with variability for wind and solar only.
    """
    fig, ax = plt.subplots(figsize=(8, 6))

    ax.bar(
        x=wind_solar_summary.index,
        height=wind_solar_summary["mean_MW"],
        yerr=wind_solar_summary["std_MW"],
        capsize=6
    )

    ax.set_xlabel("Technology")
    ax.set_ylabel("Installed capacity [MW]")
    ax.set_title("Average capacity and variability of wind and solar")
    plt.tight_layout()
    plt.show()

#%%
if __name__ == "__main__":

   
    # Fixed settings
    
    country = "DEU"        
    demand_year = 2015     # keep demand profile fixed to isolate weather effects

    
    # Weather years to compare
    
    weather_years = [2013, 2014, 2015, 2016, 2017]

    capacities_by_year, summary_stats = run_weather_variability_analysis(
        country=country,
        demand_year=demand_year,
        weather_years=weather_years,
        solver_name="gurobi"
    )

    
    # Print all results
  
    print("\nOptimal capacities by weather year [MW]:")
    print(capacities_by_year)

    print("\nAverage capacity and variability [MW]:")
    print(summary_stats)

   
    #  wind and solar only
    
    wind_solar_by_year = extract_wind_solar_only(capacities_by_year)

    wind_solar_summary = pd.DataFrame({
    "mean_MW": wind_solar_by_year.mean(axis=0),
    "std_MW": wind_solar_by_year.std(axis=0),
    "min_MW": wind_solar_by_year.min(axis=0),
    "max_MW": wind_solar_by_year.max(axis=0),
    })

    print("\nWind and solar capacities only [MW]:")
    print(wind_solar_by_year)

    print("\nWind and solar summary statistics [MW]:")
    print(wind_solar_summary)

   
    # Save results
   
    capacities_by_year.to_csv("weather_variability_capacities_by_year.csv")
    summary_stats.to_csv("weather_variability_summary_stats.csv")

    wind_solar_by_year.to_csv("weather_variability_wind_solar_by_year.csv")
    wind_solar_summary.to_csv("weather_variability_wind_solar_summary.csv")

   
    # Plot results
   
    plot_capacities_by_weather_year(capacities_by_year)
    plot_average_capacity_with_variability(summary_stats)

    plot_wind_solar_by_weather_year(wind_solar_by_year)
    plot_wind_solar_average_variability(wind_solar_summary)