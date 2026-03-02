import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def plot_demand(df_filled):
    """Plot complete demand data time series with missing hours highlighted.
    
    Args:
        df_filled: DataFrame with filled data (must have 'DateTime' and 'ConsumptionMWh' columns)
        
    Returns:
        fig: Plotly figure object
    """
    fig = go.Figure()
    
    # Add main demand line
    fig.add_trace(go.Scatter(
        x=df_filled['DateTime'],
        y=df_filled['ConsumptionMWh'],
        mode='lines',
        name='Demand',
        line=dict(color='blue', width=1)
    ))
    
    fig.update_layout(
        title='Demand',
        xaxis_title='DateTime',
        yaxis_title='Consumption (MWh)',
        hovermode='x unified',
        height=600,
        showlegend=True
    )
    fig.show()
    return fig