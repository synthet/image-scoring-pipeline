#!/usr/bin/env python3
"""
Batch process all images in a directory with comprehensive logging.
Redirects all output to a log file with current date in the filename.

Wrapper around modules.engine.BatchImageProcessor.
"""

import argparse
import sys
import os
import logging
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from modules.engine import BatchImageProcessor

from scripts.python.run_all_musiq_models import MultiModelMUSIQ

def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Batch process images with MUSIQ models and comprehensive logging",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python batch_process_images.py --input-dir "D:/Photos/Export/2025"
  python batch_process_images.py --input-dir "D:/Photos/Export/2025" --output-dir "D:/Results"
  python batch_process_images.py --input-dir "D:/Photos/Export/2025" --log-file "custom_log.log"
        """
    )
    
    parser.add_argument('--input-dir', required=True, help='Input directory containing images')
    parser.add_argument('--output-dir', help='Output directory for JSON results (default: same as input)')
    parser.add_argument('--log-file', help='Custom log file name (default: auto-generated with timestamp)')
    parser.add_argument('--rate-nef', action='store_true', help='Write ratings to Nikon NEF files based on quality scores')
    parser.add_argument('--skip-existing', action='store_true', help='Skip images that have any existing JSON result file, regardless of version')
    parser.add_argument('--json-stdout', action='store_true', help='Print result JSON to stdout instead of saving files (logs go to stderr)')
    
    args = parser.parse_args()

    # Configure logging
    log_level = logging.INFO
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        stream=sys.stderr if args.json_stdout else sys.stdout
    )
    
    # Add file handler if requested
    if args.log_file:
        file_handler = logging.FileHandler(args.log_file)
        file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s'))
        logging.getLogger().addHandler(file_handler)
    
    # Validate input directory
    if not os.path.exists(args.input_dir):
        print(f"Error: Input directory not found: {args.input_dir}")
        sys.exit(1)
    
    if not os.path.isdir(args.input_dir):
        print(f"Error: Input path is not a directory: {args.input_dir}")
        sys.exit(1)
    
    # Initialize processor
    # Legacy script always writes files unless json-stdout is on (and even then, check logic)
    # The original script default was writing files.
    write_json = not args.json_stdout
    
    # Initialize Scorer
    scorer = MultiModelMUSIQ(skip_gpu=False)
    # Check loading? load_all_models()?
    # BatchImageProcessor uses the scorer instance and calls run_all_models.
    # It might expect models to be loaded?
    # pipeline.ScoringWorker calls self.scorer.run_all_models.
    # run_all_models calls load_model implicitly? No.
    # MultiModelMUSIQ.run_all_models iterates self.models.
    # So we MUST load models.
    scorer.load_all_models()

    processor = BatchImageProcessor(
        # log_file argument removed, handling logging via global config
        output_dir=args.output_dir, 
        skip_existing=args.skip_existing, 
        json_stdout=args.json_stdout,
        write_json=write_json,
        scorer=scorer
    )
    
    # Process directory
    try:
        processor.process_directory(args.input_dir, args.output_dir)
    except KeyboardInterrupt:
        processor.log("Batch processing interrupted by user", "WARNING")
        sys.exit(1)
    except Exception as e:
        processor.log(f"Unexpected error during batch processing: {str(e)}", "ERROR")
        sys.exit(1)


if __name__ == "__main__":
    main()
