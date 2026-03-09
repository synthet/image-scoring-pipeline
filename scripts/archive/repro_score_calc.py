
def calc(liqe, ava, spaq):
    print(f"Inputs: LIQE={liqe}, AVA={ava}, SPAQ={spaq}")
    
    # Logic from recalc_scores.py
    norm_liqe = max(0.0, min(1.0, (liqe - 1.0) / 4.0))
    print(f"Norm LIQE: {norm_liqe}")
    
    norm_ava = max(0.0, min(1.0, (ava - 1.0) / 9.0))
    print(f"Norm AVA: {norm_ava}")
    
    norm_spaq = max(0.0, min(1.0, spaq / 100.0))
    print(f"Norm SPAQ: {norm_spaq}")
    
    gen = (0.50 * norm_liqe) + (0.30 * norm_ava) + (0.20 * norm_spaq)
    print(f"Result General: {gen}")

# Values from screenshot (approx)
# Row 38354
# LIQE (Technical) = 0.729
# AVA = 0.405
# SPAQ = 0.428

calc(0.729, 0.405, 0.428)
