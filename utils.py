import pandas as pd

def startdate_enddate(df):
    """Get the start and end date from the DataFrame"""
    start_date = df['DateTime'].min()
    end_date = df['DateTime'].max()
    return start_date, end_date

def missing_data(df, start_date, end_date):
    """Identify missing hours in the DataFrame based on a complete hourly date range"""
    all_hours = pd.date_range(start=start_date, end=end_date, freq='h')
    missing_hours = all_hours.difference(df['DateTime'])
    return missing_hours

def fill_missing_data(df, missing_hours):
    """Fill missing hours in the DataFrame with zero consumption"""
    for hour in missing_hours:
        df = pd.concat([df, pd.DataFrame({'DateTime': [hour], 'ConsumptionMWh': [0]})], ignore_index=True)
    df = df.sort_values('DateTime').reset_index(drop=True)
    return df

def clean_outliers(df, column='ConsumptionMWh', z_threshold=3):
    """Remove outliers from the DataFrame based on Z-score."""
    mean = df[column].mean()
    std = df[column].std()
    df['z_score'] = (df[column] - mean) / std
    cleaned_df = df[df['z_score'].abs() <= z_threshold].copy()
    cleaned_df.drop(columns=['z_score'], inplace=True)
    return cleaned_df

