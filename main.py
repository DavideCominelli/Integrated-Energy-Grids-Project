#%%
import pandas as pd
import pypsa
import logging
from data.data import load_wind, preprocessing_consumption_data, load_raw_consumption_data
from plots import plot_demand
#%%
# Configure logging
logging.basicConfig(level=logging.INFO)
#%%
year = 2030
url = f"https://raw.githubusercontent.com/PyPSA/technology-data/v0.11.0/outputs/costs_{year}.csv"
costs = pd.read_csv(url, index_col=[0, 1])

#%%
# input data for the network
logging.info("Loading consumptiondata...")
df_demand = preprocessing_consumption_data(load_raw_consumption_data())
plot_demand(df_demand)


#%%
logging.info("Loading wind data...")
wind_data = load_wind()

# %%
logging.info("Inicialize empty network...")
n = pypsa.Network()
hours_in_2024 = pd.date_range('2024-01-01 00:00Z',
                              '2024-12-31 23:00Z',
                              freq='h')


n.add("Bus",
            "electricity")

n.set_snapshots(hours_in_2024.values)

carriers = [
    "onwind",
    "solar",
    "OCGT", #open cycle gas turbine
    "CCGT", #combined cycle gas turbine
    "battery storage",
]

n.add(
    "Carrier",
    carriers,
    color=["dodgerblue", "gold", "indianred","yellow-green", "brown"],
)
# %%
logging.info("Add demanda into the network...")
n.add("Load",
      "demand",
      bus="electricity",
      p_set=df_demand['ConsumptionMWh'].values)

# %%
