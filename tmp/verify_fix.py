
import os
import sys
from unittest.mock import MagicMock, patch

# Mock EVERYTHING that could cause issues
mock_modules = [
    'tensorflow',
    'tensorflow.python',
    'tensorflow.python.pywrap_tensorflow',
    'torch',
    'transformers',
    'PIL',
    'numpy',
    'modules.db',
    'modules.events',
    'modules.version',
    'modules.phases',
    'modules.phases_policy',
    'modules.config',
    'modules.thumbnails',
    'modules.xmp',
    'scripts.python.run_all_musiq_models'
]

for m in mock_modules:
    sys.modules[m] = MagicMock()

# Import the class after mocking
from modules.scoring import ScoringRunner

def test_scoring_runner_no_name_error():
    """
    Test that ScoringRunner.start_batch doesn't raise NameError for target_phases.
    """
    runner = ScoringRunner()
    
    # Mock BatchImageProcessor and other internal components
    with patch('modules.scoring.BatchImageProcessor') as MockProcessor, \
         patch('modules.scoring.MultiModelMUSIQ') as MockScorer, \
         patch('modules.scoring.threading.Thread') as MockThread, \
         patch('os.path.isdir', return_value=True), \
         patch('os.path.exists', return_value=True):
        
        # We don't want to actually start the thread, just call the internal method
        def mock_start():
            # Trigger the internal run method which had the bug
            print("Calling _run_batch_internal...")
            # signature: _run_batch_internal(input_path, skip_existing, job_id=None, target_phases=None)
            runner._run_batch_internal("test_path", skip_existing=False, job_id=123, target_phases=["scoring"])
            print("Successfully called _run_batch_internal.")
            
        MockThread.return_value.start = mock_start
        
        # This shouldn't raise NameError
        # signature: start_batch(input_path, job_id=None, skip_existing=False, target_phases=None)
        result = runner.start_batch("test_path", job_id=123, skip_existing=False, target_phases=["scoring"])
        
        print(f"Result: {result}")
        
        # Check if BatchImageProcessor was called at least once
        if MockProcessor.call_args:
            args, kwargs = MockProcessor.call_args
            print(f"BatchImageProcessor call kwargs: {kwargs}")
            
            if kwargs.get('target_phases') == ["scoring"]:
                print("SUCCESS: target_phases was correctly passed to BatchImageProcessor.")
            else:
                print(f"FAILURE: target_phases was NOT passed correctly. Got: {kwargs.get('target_phases')}")
                sys.exit(1)
        else:
            print("FAILURE: BatchImageProcessor was NOT called.")
            sys.exit(1)

if __name__ == "__main__":
    try:
        test_scoring_runner_no_name_error()
    except NameError as e:
        print(f"VERIFICATION FAILED: NameError: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred during verification: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    else:
        print("VERIFICATION SUCCESSFUL: No NameError encountered.")
        sys.exit(0)
