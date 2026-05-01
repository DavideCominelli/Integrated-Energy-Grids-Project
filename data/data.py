tech_data = {
    "solar": {
        "overnight_cost": 425000,
        "lifetime": 25,
        "capital_cost_increase": 0.03,
    },
    "solar_rooftop": {
        "overnight_cost": 725000,
        "lifetime": 25,
        "capital_cost_increase": 0.02,
    },
    "onshorewind": {
        "overnight_cost": 910000,
        "lifetime": 30,
        "capital_cost_increase": 0.033,
    },
    "run_of_river": {
        "overnight_cost": 3000000,
        "lifetime": 80,
        "capital_cost_increase": 0.02,
        "fixed_capacity": 4000,
        "availability": 0.45,
    },
    "hydro_reservoir": {
        "overnight_cost": 2000000,
        "lifetime": 80,
        "capital_cost_increase": 0.01,
        "fixed_capacity": 1800,
        "availability": 0.18,
    },
    "OCGT": {
        "overnight_cost": 560000,
        "lifetime": 25,
        "capital_cost_increase": 0.033,
        "fuel_cost": 21.6,
        "efficiency": 0.39,
    },
    "gas_pipeline": {
        "D": 1,         # m Diameter of the pipeline (average value found in SNAM report)
        "u": 12,          # m/s Average flow velocity of natural gas in pipelines (range: 10-15 m/s found in different reports)
        "P": 50 * 100000, # Pa
        "Z": 0.93,      # Compressibility factor (value for 290K and 50 bar, research gate)   
        "R": 8.314,       # J/molK
        "M": 0.016,       # kg/mol
        "T": 273 + 25,    # K
        "e": 50,          # GJ/tonne or MJ/kg
    },
    # ── Storage technologies ───────────────────────────────────────────────
    "Pumped_Hydro":{
        "overnight_cost_power": 0.8e6,  # €/MW 
        "max_power_capacity": 5900,         # maximum power capacity (MW)
        "max_energy_capacity": 64000,          # maximum energy capacity (MWh)
        "lifetime": 80,
        "capital_cost_increase": 0.01,
        "efficiency_store": 0.87,          # charging efficiency (η_charge)
        "efficiency_dispatch": 0.87,       # discharging efficiency (η_discharge)
    },
    "battery": {
        "overnight_cost_power": 80000,   # €/MW
        "overnight_cost_energy": 90000,  # €/MWh 
        "lifetime": 15,
        "capital_cost_increase": 0.03,
        "efficiency_store": 0.9,          # charging efficiency  (η_charge)
        "efficiency_dispatch": 0.9,       # discharging efficiency (η_discharge)
        "max_hours": 6,                   # maximum storage duration (hours)
    },
    "hydrogen_electrolysis": {
        "overnight_cost_power": 350000,   # €/MW 
        "lifetime": 18,
        "capital_cost_increase": 0.04,   
        "efficiency": 0.8,               # η_in
    },
    "hydrogen_fuel_cell": {
        "overnight_cost_power": 339000,   # €/MW 
        "lifetime": 20,
        "capital_cost_increase": 0.03,   
        "efficiency": 0.58,              # η_out
    },
    "hydrogen_storage": {
        "overnight_cost_energy": 8400,    # €/MWh 
        "lifetime": 20,
        "capital_cost_increase": 0.00, 
          
    },
}