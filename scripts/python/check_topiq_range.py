
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

try:
    from modules.topiq import TopiqScore
    scorer = TopiqScore(device='cpu')
    if scorer.model:
        if hasattr(scorer.model, 'score_range'):
            print(f"Score range: {scorer.model.score_range}")
        elif hasattr(scorer.model, 'lower') and hasattr(scorer.model, 'upper'):
             print(f"Score range: {scorer.model.lower} - {scorer.model.upper}")
        else:
            print("No score_range attribute found on pyiqa model object.")
            print(f"Model attributes: {dir(scorer.model)}")
    else:
        print("Model not loaded.")
except Exception as e:
    print(f"Error: {e}")
