from calculator.assumptions import DEFAULT_ASSUMPTIONS
import json

# -------------------------
# Term table (b2, b1, a)
# -------------------------
SUPPORTED_TERMS = [7, 10, 12, 15, 20, 25]

TERM_COEFFICIENTS = {
    7:  {"b2": -0.016400442, "b1": 18.25454545, "a": 23.00933706},
    10: {"b2": -0.013899784, "b1": 15.05314685, "a": 19.9657958},
    12: {"b2": -0.012903938, "b1": 13.90559441, "a": 18.60481119},
    15: {"b2": -0.011958568, "b1": 12.83426573, "a": 17.3289958},
    20: {"b2": -0.011188811, "b1": 11.92237762, "a": 16.27588252},
    25: {"b2": -0.010799727, "b1": 11.48321678, "a": 15.75513846},
}

def run_model(submission_file='submissions.json', assumptions=None, inputs=None, debug=True):
    """
    Calculates applied yield, specific yield, net $/W installed, and PPA rates for all terms.

    FIXED:
    - net_dollar_per_watt is used directly in the PPA formula
    - NO conversion to cents per watt
    """

    assumptions = assumptions or DEFAULT_ASSUMPTIONS

    def safe_float(val, default=0.0):
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    if inputs is None:
        with open(submission_file, 'r') as f:
            submissions = json.load(f)
        if not submissions:
            raise ValueError("No submissions found in submissions.json")
        latest_key = max(submissions.keys())
        latest = submissions[latest_key]
        inputs = latest.get("inputs", {})

    # -------------------------
    # Parse inputs
    # -------------------------
    solar_kw = safe_float(inputs.get("solar_kw"), 0.0)
    annual_generation_mwh = safe_float(inputs.get("annual_generation_mwh"), 0.0)
    total_capex = safe_float(inputs.get("total_capex"), solar_kw * 600)
    ppa_meter_cost = safe_float(inputs.get("ppa_meter_cost"), 0.0)

    # -------------------------
    # Assumptions
    # -------------------------
    generation_derate = assumptions.get("generation_derate", 0)

    # -------------------------
    # Core calculations
    # -------------------------
    applied_yield_mwh = annual_generation_mwh * (1 - generation_derate)
    applied_price = total_capex + ppa_meter_cost

    # ✅ KEEP IN DOLLARS PER WATT (NO *100)
    net_dollar_per_watt = applied_price / solar_kw / 1000 if solar_kw != 0 else 0

    specific_yield = (
        applied_yield_mwh * 1000 / solar_kw if solar_kw != 0 else 0
    )

    # -------------------------
    # PPA rates
    # -------------------------
    term_results = []

    for term in SUPPORTED_TERMS:
        coeffs = TERM_COEFFICIENTS[term]

        # ✅ Use net_dollar_per_watt directly
        rate_cents = (
            coeffs["b2"] * specific_yield +
            coeffs["b1"] * net_dollar_per_watt +
            coeffs["a"]
        )

        rate_dollars = rate_cents

        term_results.append({
            "term": term,
            "ppa_rate_cents": round(rate_cents, 1),
            "ppa_rate_dollars": round(rate_dollars, 1),
            "b2": coeffs["b2"],
            "b1": coeffs["b1"],
            "a": coeffs["a"]
        })

    # -------------------------
    # Response
    # -------------------------
    results = [{
        "install_price": total_capex,
        "applied_price": round(applied_price, 2),
        "terms": term_results
    }]

    response = {
        "solar_kw": solar_kw,
        "annual_generation_mwh": round(annual_generation_mwh, 3),
        "applied_yield_mwh": round(applied_yield_mwh, 3),
        "specific_yield": round(specific_yield, 2),
        "net_dollar_per_watt": round(net_dollar_per_watt, 4),  # stays like 0.612
        "results": results
    }

    # -------------------------
    # Debug
    # -------------------------
    if debug:
        print("\n===== BACKEND DEBUG =====")
        print(f"Inputs: solar_kw={solar_kw}, annual_generation_mwh={annual_generation_mwh}")
        print(f"Total CAPEX={total_capex}, PPA meter cost={ppa_meter_cost}")
        print(f"Applied yield MWh: {applied_yield_mwh}")
        print(f"Applied price: {applied_price}")
        print(f"Net $/W installed (NO cents conversion): {net_dollar_per_watt}")
        print(f"Specific yield kWh/kW: {specific_yield}")
        print("Calculated PPA rates per term:")
        for term_info in term_results:
            print(f"  Term {term_info['term']}: "
                  f"{term_info['ppa_rate_cents']} c/kWh "
                  f"({term_info['ppa_rate_dollars']} $/kWh)")
        print("===========================\n")

    return response