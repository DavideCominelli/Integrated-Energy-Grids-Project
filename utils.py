import plotly.graph_objs as go
import pandas as pd

def annuity(n,r):
    """ Calculate the annuity factor for an asset with lifetime n years and
    discount rate  r """

    if r > 0:
        return r/(1. - 1./(1.+r)**n)
    else:
        return 1/n

def _get_generator_dispatch(network):
    """Return dispatch time series for all generators in the model."""
    return network.generators_t.p[network.generators.index]

def plot_dispatch_week(network, week_start, title):
    """Plot one week dispatch with demand for a given start timestamp."""
    week_start = pd.Timestamp(week_start)
    if getattr(week_start, "tz", None) is not None:
        week_start = week_start.tz_convert(None)
    week_end = week_start + pd.Timedelta(days=7)

    dispatch = _get_generator_dispatch(network).loc[week_start:week_end - pd.Timedelta(hours=1)]
    demand = network.loads_t.p["load"].loc[week_start:week_end - pd.Timedelta(hours=1)]

    fig = go.Figure()

    color_map = {
        "onshorewind": "#1f77b4",
        "solar": "#ff7f0e",
        "solar_rooftop": "#f2c14e",
        "run_of_river": "#2a9d8f",
        "hydro_reservoir": "#264653",
        "OCGT": "#8c564b",
    }

    for generator in dispatch.columns:
        fig.add_trace(
            go.Scatter(
                x=dispatch.index,
                y=dispatch[generator],
                mode="lines",
                name=generator,
                stackgroup="generation",
                line=dict(width=0.5, color=color_map.get(generator, None)),
            )
        )

    fig.add_trace(
        go.Scatter(
            x=demand.index,
            y=demand,
            mode="lines",
            name="demand",
            line=dict(color="black", width=2),
        )
    )

    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title="Power (MW)",
        legend=dict(bgcolor="rgba(0,0,0,0)", borderwidth=0),
        margin=dict(l=10, r=10, t=50, b=10),
    )
    fig.show()

def plot_electricity_mix(network):
    """Plot annual electricity mix as energy shares."""
    annual_energy = _get_generator_dispatch(network).sum()
    labels = annual_energy.index.tolist()
    values = annual_energy.values.tolist()

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                textinfo="label+percent",
                hole=0.35,
            )
        ]
    )
    fig.update_layout(title_text="Annual Electricity Mix (MWh)", title_y=0.95)
    fig.show()

def plot_duration_curves(network):
    """Plot duration curves of dispatch for each generator."""
    dispatch = _get_generator_dispatch(network)
    fig = go.Figure()

    for generator in dispatch.columns:
        sorted_dispatch = dispatch[generator].sort_values(ascending=False).reset_index(drop=True)
        fig.add_trace(
            go.Scatter(
                x=sorted_dispatch.index + 1,
                y=sorted_dispatch,
                mode="lines",
                name=generator,
            )
        )

    fig.update_layout(
        title="Generator Duration Curves",
        xaxis_title="Hours (sorted)",
        yaxis_title="Dispatch (MW)",
        legend=dict(bgcolor="rgba(0,0,0,0)", borderwidth=0),
        margin=dict(l=10, r=10, t=50, b=10),
    )
    fig.show()

def calculate_capacity_factors(network):
    """Return capacity factor by generator based on optimal capacities."""
    dispatch = _get_generator_dispatch(network)
    annual_energy = dispatch.sum()  # MWh
    p_nom_opt = network.generators.p_nom_opt.reindex(dispatch.columns)
    hours = len(dispatch.index)
    capacity_factor = annual_energy / (p_nom_opt * hours)
    return capacity_factor.fillna(0.0).sort_values(ascending=False)

def plot_results(network):
    """Backward-compatible quick plot used in early project versions."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        y=network.loads_t.p['load'][0:96],
        mode='lines',
        name='demand',
        line=dict(color='black')
    ))
    fig.add_trace(go.Scatter(
        y=network.generators_t.p['onshorewind'][0:96],
        mode='lines',
        name='onshore wind',
        line=dict(color='blue')
    ))
    fig.add_trace(go.Scatter(
        y=network.generators_t.p['solar'][0:96],
        mode='lines',
        name='solar',
        line=dict(color='orange')
    ))
    fig.add_trace(go.Scatter(
        y=network.generators_t.p['solar_rooftop'][0:96],
        mode='lines',
        name='solar rooftop',
        line=dict(color='#f2c14e')
    ))
    fig.add_trace(go.Scatter(
        y=network.generators_t.p['run_of_river'][0:96],
        mode='lines',
        name='run-of-river',
        line=dict(color='#2a9d8f')
    ))
    fig.add_trace(go.Scatter(
        y=network.generators_t.p['hydro_reservoir'][0:96],
        mode='lines',
        name='hydro reservoir',
        line=dict(color='#264653')
    ))
    fig.add_trace(go.Scatter(
        y=network.generators_t.p['OCGT'][0:96],
        mode='lines',
        name='gas (OCGT)',
        line=dict(color='brown')
    ))
    fig.update_layout(
        legend=dict(
            bgcolor='rgba(0,0,0,0)',
            bordercolor='rgba(0,0,0,0)',
            borderwidth=0
        ),
        margin=dict(l=0, r=0, t=30, b=0)
    )
    fig.show()