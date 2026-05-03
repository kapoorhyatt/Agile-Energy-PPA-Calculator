from calculator.assumptions import DEFAULT_ASSUMPTIONS
import json

# -------------------------
# Term table (b2, b1, a)
# -------------------------
SUPPORTED_TERMS = [7, 10, 12, 15, 20, 25]

TERM_COEFFICIENTS_BY_IRR = {
    "17.5": {
        7:  {"b2": -0.01825648, "b1": 18.74615385, "a": 25.49224895},
        10: {"b2": -0.015500289, "b1": 15.60909091, "a": 22.0608028},
        12: {"b2": -0.014458173, "b1": 14.45244755, "a": 20.68013706},
        15: {"b2": -0.013487565, "b1": 13.43706294, "a": 19.33665734},
        20: {"b2": -0.012652611, "b1": 12.56293706, "a": 18.21008392},
        25: {"b2": -0.012289815, "b1": 12.15174825, "a": 17.73152168},
    },

    "18.5": {
        7:  {"b2": -0.01723119, "b1": 19.26713287, "a": 24.11061259},
        10: {"b2": -0.014789421, "b1": 16.13356643, "a": 21.12520839},
        12: {"b2": -0.013844051, "b1": 15.03776224, "a": 19.83045594},
        15: {"b2": -0.012973342, "b1": 14.02027972, "a": 18.6632951},
        20: {"b2": -0.012235133, "b1": 13.1993007, "a": 17.66223776},
        25: {"b2": -0.011942794, "b1": 12.83706294, "a": 17.24896224},
    }
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

    selected_irr = str(inputs.get("irr", "17.5"))

    if selected_irr not in TERM_COEFFICIENTS_BY_IRR:
        selected_irr = "17.5"

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
        coeffs = TERM_COEFFICIENTS_BY_IRR[selected_irr][term]

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
        print(f"Selected IRR: {selected_irr}")
        for term_info in term_results:
            print(f"  Term {term_info['term']}: "
                  f"{term_info['ppa_rate_cents']} c/kWh "
                  f"({term_info['ppa_rate_dollars']} $/kWh)")
        print("===========================\n")

    return response