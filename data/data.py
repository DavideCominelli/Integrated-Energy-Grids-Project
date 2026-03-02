#%%
import pandas as pd
import os


#%%
# The system consist of 12 conventional power plants and 6 wind power plants

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
        print(df)
        wind_data[plant_key] = df
    return wind_data