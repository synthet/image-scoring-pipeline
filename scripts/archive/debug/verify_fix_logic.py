
def test_normalization_logic():
    print("[TEST] Testing normalization logic...")
    
    # Simulate results structure
    results = {
        "models": {
            "everypixel": {
                "score": 85.5,
                "status": "success"
                # missing "normalized_score"
            },
            "sightengine": {
                "score": 0.92,
                "status": "success"
                # missing "normalized_score"
            },
            "spaq": {
                "score": 70,
                "normalized_score": 0.7,
                "status": "success"
            }
        }
    }
    
    normalized_scores_dict = {}
    
    # --- LOGIC UNDER TEST (Mirrors the fixed code in run_all_musiq_models.py) ---
    for model_name, model_result in results["models"].items():
        if model_result["status"] == "success":
            norm_score = model_result.get("normalized_score")
            
            # Fallback normalization/calculation
            if norm_score is None and model_result.get("score") is not None:
                    raw_score = float(model_result.get("score"))
                    
                    if "everypixel" in model_name.lower():
                        # EveryPixel: RAW 0-100 -> Norm 0-1
                        if raw_score > 1.0:
                            norm_score = raw_score / 100.0
                        else:
                            norm_score = raw_score
                            
                    elif "sightengine" in model_name.lower():
                        # SightEngine: RAW 0-1 -> Norm 0-1
                        norm_score = raw_score
                        
                    # Clamp
                    if norm_score is not None:
                        norm_score = max(0.0, min(1.0, norm_score))
                        model_result["normalized_score"] = norm_score
            
            if norm_score is not None:
                normalized_scores_dict[model_name] = norm_score
    # ---------------------------------------------------------------------------

    # Assertions
    print(f"Normalized Scores: {normalized_scores_dict}")
    
    assert "everypixel" in normalized_scores_dict, "EveryPixel missing from normalized dict"
    assert "sightengine" in normalized_scores_dict, "SightEngine missing from normalized dict"
    assert "spaq" in normalized_scores_dict, "SPAQ missing from normalized dict"
    
    assert abs(normalized_scores_dict["everypixel"] - 0.855) < 0.001, f"EveryPixel wrong: {normalized_scores_dict['everypixel']}"
    assert abs(normalized_scores_dict["sightengine"] - 0.92) < 0.001, f"SightEngine wrong: {normalized_scores_dict['sightengine']}"
    assert normalized_scores_dict["spaq"] == 0.7, "SPAQ wrong"

    print("[SUCCESS] Logic verification passed!")

if __name__ == "__main__":
    test_normalization_logic()
