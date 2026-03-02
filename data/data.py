import pandas as pd
import os
import sys

# Add parent directory to path to import utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from plots import plot_demand
from utils import startdate_enddate, missing_data, fill_missing_data, clean_outliers

# Unit costs for conventional power plants, The unit cost for wind power plants is 0.
unit_cost_G = {
    "Unit": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    "C_i": [13.32, 13.32, 20.7, 20.93, 26.11, 10.52, 10.52, 6.02, 5.47, 0, 10.52, 10.89],
    "C_u": [15, 15, 10, 8, 7, 16, 16, 0, 0, 0, 17, 16],
    "C_d": [14, 14, 9, 7, 5, 14, 14, 0, 0, 0, 16, 14],
    "C_plus": [15, 15, 24, 25, 28, 16, 16, 0, 0, 0, 14, 16],
    "C_minus": [11, 11, 16, 17, 23, 7, 7, 0, 0, 0, 8, 8],
    "C_su": [1430.4, 1430.4, 1725, 3056.7, 437, 312, 312, 0, 0, 0, 624, 2298],
    "P_ini": [76, 76, 0, 0, 0, 0, 124, 240, 240, 240, 248, 280],
    "U_ini": [1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1],
    "T_ini": [22, 22, -2, -1, -1, -2, 10, 50, 16, 24, 10, 50]
}
# Technical data for conventional power plants
technical_data_G= {
    "Unit": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    "Node": [1, 2, 7, 13, 15, 15, 16, 18, 21, 22, 23, 23],
    "P_max": [152, 152, 350, 591, 60, 155, 155, 400, 400, 300, 310, 350],
    "P_min": [30.4, 30.4, 75, 206.85, 12, 54.25, 54.25, 100, 100, 300, 108.5, 140],
    "R_plus": [40, 40, 70, 180, 60, 30, 30, 0, 0, 0, 60, 40],
    "R_minus": [40, 40, 70, 180, 60, 30, 30, 0, 0, 0, 60, 40],
    "R_U": [120, 120, 350, 240, 60, 155, 155, 280, 280, 300, 180, 240],
    "R_D": [120, 120, 350, 240, 60, 155, 155, 280, 280, 300, 180, 240],
    "UT": [8, 8, 8, 12, 4, 8, 8, 1, 1, 0, 8, 8],
    "DT": [4, 4, 8, 10, 2, 8, 8, 1, 1, 0, 8, 8]
}


# Technical data for wind power plants
technical_data_W = {
    "Unit": [1, 2, 3, 4, 5, 6],
    "Node": [3, 5, 7, 16, 21, 23],
    "Lat": [],
    "Lon": [],
    "P_max": [103, 104, 85, 81, 85, 82]
}

# wind forecast as max capaciy for each hour
def load_wind(date='2024-01-01'):
    """Load hourly wind capacity forecasts"""
    wind_data = {}
    base_path = os.path.join(os.path.dirname(__file__), 'windforecast')
    
    csv_files = sorted([f for f in os.listdir(base_path) if f.endswith('.csv')])
    for idx, filename in enumerate(csv_files, start=1):
        file_path = os.path.join(base_path, filename)
        plant_key = f'w{idx}'
        df = pd.read_csv(file_path, skiprows=3)
        df['date'] = pd.to_datetime(df['time']).dt.date
        df['electricity'] = df['electricity']/1000
        wind_data[plant_key] = df
    return wind_data

# # demand data
# def load_consumption_data(filepath='data/ConsumptionConsumerCategoryHour.csv'):
#     """Load and process consumption data from CSV file.
    
#     Args:
#         filepath (str): Path to the consumption CSV file
        
#     Returns:
#         pd.DataFrame: Hourly aggregated consumption data with DateTime and ConsumptionMWh columns
#     """
#     df = pd.read_csv(filepath, sep=';')
#     df['DateTime'] = pd.to_datetime(df['TimeUTC'])

#     df['ConsumptionkWh'] = pd.to_numeric(
#         df['ConsumptionkWh'].astype(str).str.replace(',', '.').str.strip(), 
#         errors='coerce')

#     df['ConsumptionkWh'] = df['ConsumptionkWh'].fillna(0)
#     df['ConsumptionMWh'] = df['ConsumptionkWh'] / 1000
    
#     # aggregate consumption by date-time in hourly resolution
#     df_hourly = df.groupby('DateTime')['ConsumptionMWh'].sum().reset_index()
    
#     return df_hourly


def load_raw_consumption_data(filepath='data/monthly_hourly_load_values_2024.csv'):
    """Load and process consumption data from CSV file.
    
    Args:
        filepath (str): Path to the consumption CSV file
        
    Returns:
        pd.DataFrame: Hourly aggregated consumption data with DateTime and ConsumptionMWh columns
    """
    df = pd.read_csv(filepath, sep='\t')
    
    # Parse the DateTime from the DateUTC column
    df['DateTime'] = pd.to_datetime(df['DateUTC'], format='%d-%m-%Y %H:%M')

    # Convert Value to numeric
    df['Value'] = pd.to_numeric(
        df['Value'].astype(str).str.replace(',', '.').str.strip(), 
        errors='coerce')
    df = df[df['CountryCode'] == 'DK']  # Filter for Denmark only
    df['Value'] = df['Value'].fillna(0)
    df['ConsumptionMWh'] = df['Value']
    
    # Aggregate consumption by date-time in hourly resolution (sum across all countries)
    df_hourly = df.groupby('DateTime')['ConsumptionMWh'].sum().reset_index()
    
    return df_hourly

def preprocessing_consumption_data(df):
    """Preprocess the consumption data by identifying and filling missing hours.
    
    Args:
        df (pd.DataFrame): DataFrame with DateTime and ConsumptionMWh columns
        
    Returns:
        pd.DataFrame: DataFrame with missing hours filled
        pd.DatetimeIndex: DatetimeIndex of missing hours that were filled
    """
    start_date, end_date = startdate_enddate(df)
    missing_hours = missing_data(df, start_date, end_date)
    print(f"Missing hours in the demand data: {missing_hours}")
    
    df_filled = fill_missing_data(df, missing_hours)
    print(f'len(df_filled): {len(df_filled)}')
    df_cleaned = clean_outliers(df_filled)
    print(f'len(df_cleaned): {len(df_cleaned)}')
    
    return df_cleaned

df_demand_raw = load_raw_consumption_data()
df_demand = preprocessing_consumption_data(df_demand_raw)
