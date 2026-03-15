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
    # ── Storage technologies ───────────────────────────────────────────────
    "Pumped_Hydro":{
        "overnight_cost_power": 150000,  # €/MW
        "overnight_cost_energy": 50000,   # €/MWh
        "max_hours": 12,                  # energy-to-power ratio [h]
        "lifetime": 50,
        "capital_cost_increase": 0.01,
        "efficiency_store": 0.8,          # charging efficiency (η_charge)
        "efficiency_dispatch": 0.8,       # discharging efficiency (η_discharge)
    },
    "battery": {
        "overnight_cost_power": 182000,   # €/MW
        "overnight_cost_energy": 128000,  # €/MWh
        "max_hours": 6,                   # energy-to-power ratio [h]
        "lifetime": 15,
        "capital_cost_increase": 0.02,
        "efficiency_store": 0.9,          # charging efficiency  (η_charge)
        "efficiency_dispatch": 0.9,       # discharging efficiency (η_discharge)
    },
}