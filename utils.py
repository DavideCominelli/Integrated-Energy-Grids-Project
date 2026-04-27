import plotly.graph_objs as go
import pandas as pd
import re
from plotly.subplots import make_subplots
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

def _get_storage_dispatch(network):
    """Return dispatch time series for storage units. Positive = discharging."""
    if network.storage_units.empty:
        return pd.DataFrame(index=network.snapshots)
    return network.storage_units_t.p[network.storage_units.index]

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
    #fig.write_image("electricity_mix.pdf", scale=2)  # Save the figure as a high-resolution PNG
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


# ── Part D: Storage-aware functions ─────────────────────────────────────────

def _get_h2_dispatch(network):
    """Return H2 system signed flows for the Store+Link H2 model.

    PyPSA sign convention for Links:
    - p0 > 0: power consumed FROM bus0 (electrolysis consumes electricity)
    - p1 < 0: power injected INTO bus1 (fuel cell injects electricity, so -p1 > 0)

    Returns a DataFrame with:
    - 'H2 Fuel Cell'    : positive values = electricity supplied to grid
    - 'H2 Electrolysis' : negative values = electricity consumed from grid
    """
    result = {}
    if ("H2 Fuel Cell" in network.links.index
            and "H2 Fuel Cell" in network.links_t.p1.columns):
        result["H2 Fuel Cell"] = -network.links_t.p1["H2 Fuel Cell"]
    if ("H2 Electrolysis" in network.links.index
            and "H2 Electrolysis" in network.links_t.p0.columns):
        result["H2 Electrolysis"] = -network.links_t.p0["H2 Electrolysis"]
    if result:
        return pd.DataFrame(result)
    return pd.DataFrame(index=network.snapshots)


def plot_dispatch_week_storage(network, week_start, title):
    """Week dispatch: generators + StorageUnits (battery, Pumped_Hydro) + H2 Store/Link (Part D)."""
    week_start = pd.Timestamp(week_start)
    if getattr(week_start, "tz", None) is not None:
        week_start = week_start.tz_convert(None)
    week_end = week_start + pd.Timedelta(days=7)

    dispatch = _get_generator_dispatch(network).loc[week_start:week_end - pd.Timedelta(hours=1)]
    storage_dispatch = _get_storage_dispatch(network).loc[week_start:week_end - pd.Timedelta(hours=1)]
    demand = network.loads_t.p["load"].loc[week_start:week_end - pd.Timedelta(hours=1)]

    fig = go.Figure()

    color_map = {
        "onshorewind": "#1f77b4",
        "solar": "#ff7f0e",
        "solar_rooftop": "#f2c14e",
        "run_of_river": "#2a9d8f",
        "hydro_reservoir": "#264653",
        "OCGT": "#8c564b",
        "battery": "#9467bd",
        "Pumped_Hydro": "#2ca02c",
        "H2 Fuel Cell": "#17becf",
        "H2 Electrolysis": "#aec7e8",
    }

    for generator in dispatch.columns:
        fig.add_trace(
            go.Scatter(
                x=dispatch.index,
                y=dispatch[generator],
                mode="lines",
                name=generator,
                stackgroup="supply",
                line=dict(width=0.5, color=color_map.get(generator, None)),
            )
        )

    # StorageUnit discharge (positive p) stacked with supply
    for su in storage_dispatch.columns:
        discharge = storage_dispatch[su].clip(lower=0)
        fig.add_trace(
            go.Scatter(
                x=discharge.index,
                y=discharge,
                mode="lines",
                name=f"{su} (discharge)",
                stackgroup="supply",
                line=dict(width=0.5, color=color_map.get(su, None)),
            )
        )

    # StorageUnit charging (negative p) shown below zero
    for su in storage_dispatch.columns:
        charge = storage_dispatch[su].clip(upper=0)
        if charge.abs().sum() > 0:
            fig.add_trace(
                go.Scatter(
                    x=charge.index,
                    y=charge,
                    mode="lines",
                    name=f"{su} (charging)",
                    stackgroup="charging",
                    line=dict(width=0.5, color=color_map.get(su, None)),
                )
            )

    # H2 Fuel Cell discharge (positive) and Electrolysis charging (negative)
    h2_dispatch = _get_h2_dispatch(network).loc[week_start:week_end - pd.Timedelta(hours=1)]
    for col in h2_dispatch.columns:
        positive = h2_dispatch[col].clip(lower=0)
        negative = h2_dispatch[col].clip(upper=0)
        if positive.sum() > 0:
            fig.add_trace(go.Scatter(
                x=positive.index, y=positive, mode="lines",
                name=col, stackgroup="supply",
                line=dict(width=0.5, color=color_map.get(col, None)),
            ))
        if negative.abs().sum() > 0:
            fig.add_trace(go.Scatter(
                x=negative.index, y=negative, mode="lines",
                name=f"{col} (charging)", stackgroup="charging",
                line=dict(width=0.5, color=color_map.get(col, None)),
            ))

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


def plot_electricity_mix_storage(network):
    """Annual electricity mix: generators + StorageUnit discharge + H2 Fuel Cell"""
    annual_gen = _get_generator_dispatch(network).sum()
    storage_discharge = _get_storage_dispatch(network).clip(lower=0).sum()
    storage_discharge.index = [f"{s} (discharge)" for s in storage_discharge.index]
    h2_supply = _get_h2_dispatch(network).clip(lower=0).sum()
    annual_energy = pd.concat([annual_gen, storage_discharge, h2_supply])
    annual_energy = annual_energy[annual_energy > 0]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=annual_energy.index.tolist(),
                values=annual_energy.values.tolist(),
                textinfo="label+percent",
                hole=0.35,
            )
        ]
    )
    fig.update_layout(title_text="Annual Electricity Mix with Storage (MWh)", title_y=0.95)
    fig.show()


def plot_duration_curves_storage(network):
    """Duration curves: generators + StorageUnit discharge + H2 Fuel Cell (Part D)."""
    dispatch = _get_generator_dispatch(network)
    storage_discharge = _get_storage_dispatch(network).clip(lower=0)
    storage_discharge.columns = [f"{s} (discharge)" for s in storage_discharge.columns]
    h2_supply = _get_h2_dispatch(network).clip(lower=0)
    combined = pd.concat([dispatch, storage_discharge, h2_supply], axis=1)
    fig = go.Figure()

    for col in combined.columns:
        sorted_dispatch = combined[col].sort_values(ascending=False).reset_index(drop=True)
        fig.add_trace(
            go.Scatter(
                x=sorted_dispatch.index + 1,
                y=sorted_dispatch,
                mode="lines",
                name=col,
            )
        )

    fig.update_layout(
        title="Duration Curves with Storage",
        xaxis_title="Hours (sorted)",
        yaxis_title="Dispatch (MW)",
        legend=dict(bgcolor="rgba(0,0,0,0)", borderwidth=0),
        margin=dict(l=10, r=10, t=50, b=10),
    )
    fig.show()


def calculate_capacity_factors_storage(network):
    """Capacity factors for generators, StorageUnits (battery, Pumped_Hydro), and H2 links (Part D)."""
    dispatch = _get_generator_dispatch(network)
    annual_gen = dispatch.sum()
    p_nom_gen = network.generators.p_nom_opt.reindex(dispatch.columns)
    hours = len(dispatch.index)
    cf_gen = annual_gen / (p_nom_gen * hours)

    storage_dispatch = _get_storage_dispatch(network)
    if not storage_dispatch.empty:
        annual_storage = storage_dispatch.clip(lower=0).sum()
        p_nom_storage = network.storage_units.p_nom_opt.reindex(storage_dispatch.columns)
        cf_storage = annual_storage / (p_nom_storage * hours)
    else:
        cf_storage = pd.Series(dtype=float)

    # H2 Fuel Cell: capacity factor based on electricity output
    cf_h2 = pd.Series(dtype=float)
    if ("H2 Fuel Cell" in network.links.index
            and "H2 Fuel Cell" in network.links_t.p1.columns):
        h2_annual = (-network.links_t.p1["H2 Fuel Cell"]).sum()
        p_nom_fc = network.links.p_nom_opt.get("H2 Fuel Cell", 0)
        if p_nom_fc > 0:
            cf_h2["H2 Fuel Cell"] = h2_annual / (p_nom_fc * hours)

    return pd.concat([cf_gen, cf_storage, cf_h2]).fillna(0.0).sort_values(ascending=False)

def plot_storage_soc(network, title="Storage State of Charge – Full Year"):
    """Plot state of charge (%) for all storage units over the full year.

    Two panels are created side-by-side:
    - Left : full-year view  → reveals seasonal charge/discharge cycles
    - Right: a representative winter week → reveals intraday cycles
    """
    h2_ok = ("H2 Tank" in network.stores.index
             and "H2 Tank" in network.stores_t.e.columns
             and network.stores.e_nom_opt.get("H2 Tank", 0) > 1)
    if network.storage_units.empty and not h2_ok:
        return

    soc = network.storage_units_t.state_of_charge
    p_nom_opt = network.storage_units.p_nom_opt

    color_map = {
        "battery": "#9467bd",
        "Pumped_Hydro": "#2ca02c",
        "H2 Tank": "#17becf",
    }

    from plotly.subplots import make_subplots
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=["Full year", "Winter week (12–19 Jan)"],
    )

    winter_start = pd.Timestamp("2015-01-12")
    winter_end   = pd.Timestamp("2015-01-19")

    for su in soc.columns:
        max_energy = p_nom_opt[su] * network.storage_units.loc[su, "max_hours"]
        if max_energy < 1:
            continue  # skip zero-investment storage
        soc_pct = soc[su] / max_energy * 100
        color = color_map.get(su, None)

        # Full-year trace
        fig.add_trace(
            go.Scatter(x=soc_pct.index, y=soc_pct, mode="lines",
                       name=su, line=dict(color=color, width=1)),
            row=1, col=1,
        )
        # Winter-week zoom
        mask = (soc_pct.index >= winter_start) & (soc_pct.index <= winter_end)
        fig.add_trace(
            go.Scatter(x=soc_pct.index[mask], y=soc_pct[mask], mode="lines",
                       name=su, showlegend=False, line=dict(color=color, width=1)),
            row=1, col=2,
        )

    # H2 Tank SoC from Store component (normalized to % of optimal energy capacity)
    if h2_ok:
        e_nom_opt = network.stores.e_nom_opt["H2 Tank"]
        h2_soc_pct = network.stores_t.e["H2 Tank"] / e_nom_opt * 100
        color = color_map["H2 Tank"]
        fig.add_trace(
            go.Scatter(x=h2_soc_pct.index, y=h2_soc_pct, mode="lines",
                       name="H2 Tank", line=dict(color=color, width=1)),
            row=1, col=1,
        )
        mask = (h2_soc_pct.index >= winter_start) & (h2_soc_pct.index <= winter_end)
        fig.add_trace(
            go.Scatter(x=h2_soc_pct.index[mask], y=h2_soc_pct[mask], mode="lines",
                       name="H2 Tank", showlegend=False, line=dict(color=color, width=1)),
            row=1, col=2,
        )

    fig.update_yaxes(title_text="State of charge (%)", row=1, col=1)
    fig.update_yaxes(title_text="State of charge (%)", row=1, col=2)
    fig.update_layout(
        title=title,
        legend=dict(bgcolor="rgba(0,0,0,0)", borderwidth=0),
        margin=dict(l=10, r=10, t=60, b=10),
    )
    fig.show()


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


def plot_dispatch_weeks_side_by_side(network, week1_start, week2_start, title1, title2):
    """Plot two weeks' dispatch side by side as subplots (1 row, 2 columns)."""
    week1_start = pd.Timestamp(week1_start)
    week2_start = pd.Timestamp(week2_start)
    if getattr(week1_start, "tz", None) is not None:
        week1_start = week1_start.tz_convert(None)
    if getattr(week2_start, "tz", None) is not None:
        week2_start = week2_start.tz_convert(None)
    week1_end = week1_start + pd.Timedelta(days=7)
    week2_end = week2_start + pd.Timedelta(days=7)

    dispatch = _get_generator_dispatch(network)
    demand = network.loads_t.p["load"]

    color_map = {
        "onshorewind": "#1f77b4",
        "solar": "#ff7f0e",
        "solar_rooftop": "#f2c14e",
        "run_of_river": "#2a9d8f",
        "hydro_reservoir": "#264653",
        "OCGT": "#8c564b",
    }

    fig = make_subplots(rows=2, cols=1, subplot_titles=(title1, title2), shared_yaxes=True, vertical_spacing=0.1)

    # Week 1
    dispatch1 = dispatch.loc[week1_start:week1_end - pd.Timedelta(hours=1)]
    demand1 = demand.loc[week1_start:week1_end - pd.Timedelta(hours=1)]
    for generator in dispatch1.columns:
        fig.add_trace(
            go.Scatter(
                x=dispatch1.index,
                y=dispatch1[generator],
                mode="lines",
                name=generator if generator else "",
                stackgroup="generation1",
                line=dict(width=0.5, color=color_map.get(generator, None)),
                showlegend=(generator not in fig['data']),
            ),
            row=1, col=1
        )
    fig.add_trace(
        go.Scatter(
            x=demand1.index,
            y=demand1,
            mode="lines",
            name="demand",
            line=dict(color="black", width=2),
            showlegend=False,
        ),
        row=1, col=1
    )

    # Week 2
    dispatch2 = dispatch.loc[week2_start:week2_end - pd.Timedelta(hours=1)]
    demand2 = demand.loc[week2_start:week2_end - pd.Timedelta(hours=1)]
    for generator in dispatch2.columns:
        fig.add_trace(
            go.Scatter(
                x=dispatch2.index,
                y=dispatch2[generator],
                mode="lines",
                name=generator if generator else "",
                stackgroup="generation2",
                line=dict(width=0.5, color=color_map.get(generator, None)),
                showlegend=False,
            ),
            row=2, col=1
        )
    fig.add_trace(
        go.Scatter(
            x=demand2.index,
            y=demand2,
            mode="lines",
            name="demand",
            line=dict(color="black", width=2),
            showlegend=False,
        ),
        row=2, col=1
    )

    fig.update_layout(
        legend=dict(x=1.05, y=1.2,xanchor="right", yanchor="top",bgcolor="rgba(0,0,0,0)", borderwidth=0),
        margin=dict(l=10, r=10, t=50, b=10),
        width=900,
        height=600
    )
    fig.update_xaxes(title_text="Time", row=2, col=1)
    fig.update_yaxes(title_text="Power (MW)", row=1, col=1)
    fig.update_yaxes(title_text="Power (MW)", row=2, col=1)
    fig.write_image("dispatch_comparison.pdf")
    fig.show()

def plot_mix_and_duration_side_by_side(network):
    """Plot electricity mix (pie) and duration curves side by side, duration curve 2/3 width, shared legend."""
    from plotly.subplots import make_subplots
    dispatch = _get_generator_dispatch(network)
    annual_energy = dispatch.sum()
    labels = annual_energy.index.tolist()
    values = annual_energy.values.tolist()

    # Consistent color map
    color_map = {
        "onshorewind": "#1f77b4",
        "solar": "#ff7f0e",
        "solar_rooftop": "#f2c14e",
        "run_of_river": "#2a9d8f",
        "hydro_reservoir": "#264653",
        "OCGT": "#8c564b",
    }

    # Create subplots with width ratios
    fig = make_subplots(
        rows=1, cols=2,
        column_widths=[1/3, 2/3],
        specs=[[{"type": "domain"}, {"type": "xy"}]],
        subplot_titles=["Annual Electricity Mix", "Generator Duration Curves"]
    )

    # Pie chart (left) with consistent colors, no legend
    pie_colors = [color_map.get(label, None) for label in labels]
    fig.add_trace(
        go.Pie(
            labels=labels,
            values=values,
            textinfo="label+percent",
            hole=0.35,
            marker=dict(colors=pie_colors),
            showlegend=False
        ),
        row=1, col=1
    )

    # Duration curves (right), legend only once per technology
    for i, generator in enumerate(dispatch.columns):
        sorted_dispatch = dispatch[generator].sort_values(ascending=False).reset_index(drop=True)
        fig.add_trace(
            go.Scatter(
                x=sorted_dispatch.index + 1,
                y=sorted_dispatch,
                mode="lines",
                name=generator,
                line=dict(color=color_map.get(generator, None)),
                showlegend=True
            ),
            row=1, col=2
        )

    fig.update_xaxes(title_text="Hours (sorted)", row=1, col=2)
    fig.update_yaxes(title_text="Dispatch (MW)", row=1, col=2)
    fig.update_layout(
        legend=dict(bgcolor="rgba(0,0,0,0)", borderwidth=0, x=1.05, y=1),
        margin=dict(l=10, r=10, t=50, b=10),
        width=1100,
        height=500,
    )
    fig.write_image("mix_duration_curves.pdf")

    fig.show()




def _transport_summary(flow_ts, snapshot_weights):
    """
    Returns (total_mwh, avg_mw, peak_mw) for a DataFrame of flows.
    Uses absolute values to capture both flow directions.
    """
    weighted_abs = flow_ts.abs().mul(snapshot_weights, axis=0)
    transported_mwh = weighted_abs.sum()
    avg_mw          = transported_mwh / snapshot_weights.sum()
    peak_mw         = flow_ts.abs().max()
    return transported_mwh, avg_mw, peak_mw


def _elec_pair(line_name):
    """
    Extract sorted country pair from an electricity line name.
    Works for names like 'DEU-CHE', 'DEU-AUT', etc.
    """
    parts = re.findall(r"[A-Z]{3}", line_name)
    if len(parts) >= 2:
        return "-".join(sorted(parts[:2]))
    return line_name


def _gas_pair(link_name):
    """
    Extract sorted country pair from a gas pipeline link name.
    Works for names like 'gas pipeline DEU-CHE' and 'gas pipeline CHE-DEU'.
    Expects exactly two 3-uppercase-letter country codes in the name.
    """
    parts = re.findall(r"[A-Z]{3}", link_name)
    if len(parts) >= 2:
        return "-".join(sorted(parts[:2]))
    return link_name


def print_transport_flows(network, gas_link_prefix="gas pipeline "):
    """
    Print and compare absolute energy flows in the electricity and gas networks.

    Parameters
    ----------
    network : pypsa.Network
    gas_link_prefix : str
        Prefix used when adding gas pipeline links (default matches part_G naming).
    """
    snapshot_weights = network.snapshot_weightings.objective

    # ----------------------------------------------------------------
    # ELECTRICITY NETWORK
    # ----------------------------------------------------------------
    print("\n=== Electricity network transport ===")
    elec_flows = network.lines_t.p0        # signed MW, shape (T, n_lines)

    elec_mwh, elec_avg, elec_peak = _transport_summary(elec_flows, snapshot_weights)

    elec_report = pd.DataFrame({
        "pair":            [_elec_pair(n) for n in network.lines.index],
        "transported_mwh": elec_mwh.values,
        "avg_mw":          elec_avg.values,
        "peak_mw":         elec_peak.values,
    }, index=network.lines.index)

    print(elec_report.sort_values("transported_mwh", ascending=False).round(2).to_string())

    elec_pair = elec_report.groupby("pair").sum(numeric_only=True)
    print("\n--- Electricity by country pair ---")
    print(elec_pair.sort_values("transported_mwh", ascending=False).round(2).to_string())

    # ----------------------------------------------------------------
    # GAS NETWORK
    # Use all gas pipeline links and report both the per-link absolute
    # transported energy and the per-country-pair aggregate.
    # ----------------------------------------------------------------
    print("\n=== Gas pipeline network transport ===")

    gas_mask = network.links.index.str.startswith(gas_link_prefix)

    if gas_mask.sum() == 0:
        print(f"  [WARNING] No gas pipeline links found with prefix '{gas_link_prefix}'.")
        print(f"  Available link names: {list(network.links.index[:10])}")
        gas_total = 0.0
    else:
        gas_flows = network.links_t.p0.loc[:, gas_mask]

        gas_mwh, gas_avg, gas_peak = _transport_summary(gas_flows, snapshot_weights)

        gas_report = pd.DataFrame({
            "pair":            [_gas_pair(n) for n in gas_flows.columns],
            "transported_mwh": gas_mwh.values,
            "avg_mw":          gas_avg.values,
            "peak_mw":         gas_peak.values,
        }, index=gas_flows.columns)

        print(gas_report.sort_values("transported_mwh", ascending=False).round(2).to_string())

        gas_pair = gas_report.groupby("pair").sum(numeric_only=True)
        print("\n--- Gas by country pair ---")
        print(gas_pair.sort_values("transported_mwh", ascending=False).round(2).to_string())
        gas_total = float(gas_pair["transported_mwh"].sum())

    # ----------------------------------------------------------------
    # COMPARISON
    # ----------------------------------------------------------------
    elec_total = float(elec_pair["transported_mwh"].sum())

    print("\n=== Total transported energy comparison ===")
    print(f"  Electricity network : {elec_total:>15,.2f} MWh")
    print(f"  Gas pipeline network : {gas_total:>15,.2f} MWh")

    if elec_total > gas_total:
        ratio = elec_total / gas_total if gas_total > 0 else float("inf")
        print(f"  → Electricity transports MORE energy ({ratio:.1f}x the gas network).")
    elif gas_total > elec_total:
        ratio = gas_total / elec_total if elec_total > 0 else float("inf")
        print(f"  → H2 pipelines transport MORE energy ({ratio:.1f}x the electricity network).")
    else:
        print("  → Both networks transport the same amount of energy.")

    return elec_total, gas_total   # return values for further use (e.g. plots)