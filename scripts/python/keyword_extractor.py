#!/usr/bin/env python3
"""
AI-powered keyword extraction tool for NEF files and other image formats.
Uses BLIP for image captioning and CLIP for keyword scoring.
"""

import argparse
import json
import os
import sys
import glob
import torch
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from PIL import Image
import numpy as np

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from transformers import BlipProcessor, BlipForConditionalGeneration, CLIPProcessor, CLIPModel
    from keybert import KeyBERT
    import spacy
except ImportError as e:
    print(f"Missing required dependencies: {e}")
    print("Please install with: pip install transformers keybert spacy torch torchvision")
    print("Then download spaCy model: python -m spacy download en_core_web_sm")
    sys.exit(1)


class KeywordExtractor:
    """AI-powered keyword extraction using BLIP + CLIP pipeline."""
    
    def __init__(self, device: str = "auto", confidence_threshold: float = 0.03):
        """
        Initialize the keyword extractor.
        
        Args:
            device: Device to use ('auto', 'cpu', 'cuda')
            confidence_threshold: Minimum confidence for keywords
        """
        self.confidence_threshold = confidence_threshold
        self.device = self._setup_device(device)
        
        # Initialize models
        self.blip_processor = None
        self.blip_model = None
        self.clip_processor = None
        self.clip_model = None
        self.keybert_model = None
        self.nlp = None
        
        self._load_models()
    
    def _setup_device(self, device: str) -> str:
        """Setup the device for model inference."""
        if device == "auto":
            if torch.cuda.is_available():
                return "cuda"
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                return "mps"
            else:
                return "cpu"
        return device
    
    def _load_models(self):
        """Load all required models."""
        print(f"Loading models on device: {self.device}")
        
        try:
            # Load BLIP for image captioning
            print("Loading BLIP model...")
            self.blip_processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
            self.blip_model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
            self.blip_model.to(self.device)
            self.blip_model.eval()
            
            # Load CLIP for keyword scoring
            print("Loading CLIP model...")
            self.clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
            self.clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
            self.clip_model.to(self.device)
            self.clip_model.eval()
            
            # Load KeyBERT for keyword extraction from captions
            print("Loading KeyBERT model...")
            self.keybert_model = KeyBERT()
            
            # Load spaCy for NLP processing
            print("Loading spaCy model...")
            try:
                self.nlp = spacy.load("en_core_web_sm")
            except OSError:
                print("spaCy model not found. Please install with: python -m spacy download en_core_web_sm")
                self.nlp = None
            
            print("All models loaded successfully!")
            
        except Exception as e:
            print(f"Error loading models: {e}")
            raise
    
    def extract_caption(self, image: Image.Image) -> str:
        """Extract caption from image using BLIP."""
        try:
            inputs = self.blip_processor(image, return_tensors="pt").to(self.device)
            
            with torch.no_grad():
                out = self.blip_model.generate(**inputs, max_length=50, num_beams=5)
            
            caption = self.blip_processor.decode(out[0], skip_special_tokens=True)
            return caption
            
        except Exception as e:
            print(f"Error generating caption: {e}")
            return ""
    
    def extract_keywords_from_caption(self, caption: str) -> List[str]:
        """Extract keywords from caption using KeyBERT and spaCy."""
        keywords = set()
        
        # Use KeyBERT for keyword extraction
        if self.keybert_model and caption:
            try:
                keybert_keywords = self.keybert_model.extract_keywords(
                    caption, 
                    keyphrase_ngram_range=(1, 3), 
                    top_n=12,
                    use_mmr=True,
                    diversity=0.5
                )
                keywords.update([kw[0] for kw in keybert_keywords])
            except Exception as e:
                print(f"KeyBERT extraction failed: {e}")
        
        # Use spaCy for additional keyword extraction
        if self.nlp and caption:
            try:
                doc = self.nlp(caption)
                # Extract nouns, adjectives, and named entities
                for token in doc:
                    if token.pos_ in ['NOUN', 'ADJ'] and not token.is_stop and len(token.text) > 2:
                        keywords.add(token.text.lower())
                
                # Add named entities
                for ent in doc.ents:
                    if ent.label_ in ['PERSON', 'ORG', 'GPE', 'EVENT', 'WORK_OF_ART']:
                        keywords.add(ent.text.lower())
            except Exception as e:
                print(f"spaCy extraction failed: {e}")
        
        return list(keywords)
    
    def score_keywords_with_clip(self, image: Image.Image, keywords: List[str]) -> List[Tuple[str, float]]:
        """Score keywords against image using CLIP."""
        if not keywords:
            return []
        
        try:
            # Prepare text prompts
            texts = [f"a photo of {keyword}" for keyword in keywords]
            
            # Process inputs
            inputs = self.clip_processor(
                text=texts, 
                images=image, 
                return_tensors="pt", 
                padding=True
            ).to(self.device)
            
            # Get CLIP scores
            with torch.no_grad():
                outputs = self.clip_model(**inputs)
                scores = outputs.logits_per_image.softmax(dim=-1).squeeze()
            
            # Create keyword-score pairs
            keyword_scores = list(zip(keywords, scores.cpu().tolist()))
            
            # Sort by score (descending)
            keyword_scores.sort(key=lambda x: x[1], reverse=True)
            
            return keyword_scores
            
        except Exception as e:
            print(f"Error scoring keywords with CLIP: {e}")
            return []
    
    def add_domain_keywords(self, keywords: List[str]) -> List[str]:
        """Add domain-specific keywords for photography."""
        domain_keywords = {
            # Photography terms
            'photography', 'photo', 'image', 'picture', 'shot', 'capture',
            'camera', 'lens', 'aperture', 'shutter', 'exposure', 'focus',
            'depth of field', 'bokeh', 'composition', 'lighting', 'contrast',
            'saturation', 'vibrant', 'sharp', 'blur', 'motion blur',
            
            # Common subjects
            'portrait', 'landscape', 'nature', 'wildlife', 'macro', 'street',
            'architecture', 'urban', 'rural', 'forest', 'mountain', 'lake',
            'ocean', 'beach', 'sky', 'clouds', 'sunset', 'sunrise',
            'night', 'day', 'morning', 'evening', 'golden hour',
            
            # Colors and moods
            'colorful', 'monochrome', 'black and white', 'vintage', 'modern',
            'dramatic', 'peaceful', 'serene', 'dynamic', 'static',
            'warm', 'cool', 'bright', 'dark', 'shadow', 'highlight',
            
            # Weather and seasons
            'sunny', 'cloudy', 'rainy', 'snowy', 'foggy', 'misty',
            'spring', 'summer', 'autumn', 'winter', 'seasonal',
            
            # Technical terms
            'high resolution', 'detailed', 'crisp', 'soft', 'grainy',
            'noise', 'artifacts', 'overexposed', 'underexposed', 'balanced'
        }
        
        # Add domain keywords that might be relevant
        extended_keywords = set(keywords)
        for domain_kw in domain_keywords:
            if len(domain_kw.split()) == 1:  # Single words only
                extended_keywords.add(domain_kw)
        
        return list(extended_keywords)
    
    def extract_keywords(self, image_path: str) -> Dict:
        """
        Extract keywords from an image file.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Dictionary with caption, keywords, and metadata
        """
        try:
            # Load and preprocess image
            image = Image.open(image_path).convert("RGB")
            
            # Extract caption
            caption = self.extract_caption(image)
            
            # Extract keywords from caption
            caption_keywords = self.extract_keywords_from_caption(caption)
            
            # Add domain-specific keywords
            all_keywords = self.add_domain_keywords(caption_keywords)
            
            # Score keywords with CLIP
            keyword_scores = self.score_keywords_with_clip(image, all_keywords)
            
            # Filter by confidence threshold
            filtered_keywords = [
                {"keyword": kw, "confidence": float(score), "source": "clip"}
                for kw, score in keyword_scores
                if score >= self.confidence_threshold
            ]
            
            # Limit to top 25 keywords
            filtered_keywords = filtered_keywords[:25]
            
            return {
                "image_path": image_path,
                "caption": caption,
                "keywords": filtered_keywords,
                "total_keywords_found": len(keyword_scores),
                "keywords_above_threshold": len(filtered_keywords),
                "confidence_threshold": self.confidence_threshold,
                "device": self.device,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "image_path": image_path,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def process_batch(self, image_paths: List[str]) -> List[Dict]:
        """Process multiple images and return results."""
        results = []
        
        for i, image_path in enumerate(image_paths, 1):
            print(f"Processing {i}/{len(image_paths)}: {os.path.basename(image_path)}")
            
            result = self.extract_keywords(image_path)
            results.append(result)
            
            if "error" in result:
                print(f"  Error: {result['error']}")
            else:
                print(f"  Caption: {result['caption']}")
                print(f"  Keywords: {len(result['keywords'])} found")
        
        return results


def find_image_files(directory: str) -> List[str]:
    """Find all image files in the specified directory."""
    image_extensions = [
        '*.jpg', '*.jpeg', '*.png', '*.bmp', '*.tiff', '*.tif', '*.webp',
        '*.nef', '*.NEF', '*.nrw', '*.NRW', '*.cr2', '*.CR2', '*.cr3', '*.CR3',
        '*.arw', '*.ARW', '*.dng', '*.DNG', '*.orf', '*.ORF', '*.pef', '*.PEF',
        '*.raf', '*.RAF', '*.rw2', '*.RW2', '*.x3f', '*.X3F'
    ]
    
    image_files = []
    
    for ext in image_extensions:
        pattern = os.path.join(directory, ext)
        image_files.extend(glob.glob(pattern))
        # Also check subdirectories
        pattern = os.path.join(directory, '**', ext)
        image_files.extend(glob.glob(pattern, recursive=True))
    
    return sorted(list(set(image_files)))  # Remove duplicates and sort


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Extract keywords from images using AI models (BLIP + CLIP)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python keyword_extractor.py --input-dir "D:/Photos/NEF_Files"
  python keyword_extractor.py --input-dir "D:/Photos/NEF_Files" --output-dir "D:/Keywords"
  python keyword_extractor.py --input-file "D:/Photos/image.nef"
  python keyword_extractor.py --input-dir "D:/Photos" --confidence-threshold 0.05
        """
    )
    
    parser.add_argument('--input-dir', help='Input directory containing images')
    parser.add_argument('--input-file', help='Single image file to process')
    parser.add_argument('--output-dir', help='Output directory for JSON results')
    parser.add_argument('--confidence-threshold', type=float, default=0.03,
                       help='Minimum confidence threshold for keywords (default: 0.03)')
    parser.add_argument('--device', choices=['auto', 'cpu', 'cuda', 'mps'], default='auto',
                       help='Device to use for inference (default: auto)')
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.input_dir and not args.input_file:
        print("Error: Must specify either --input-dir or --input-file")
        sys.exit(1)
    
    if args.input_dir and not os.path.exists(args.input_dir):
        print(f"Error: Input directory not found: {args.input_dir}")
        sys.exit(1)
    
    if args.input_file and not os.path.exists(args.input_file):
        print(f"Error: Input file not found: {args.input_file}")
        sys.exit(1)
    
    # Setup output directory
    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
    else:
        if args.input_dir:
            args.output_dir = args.input_dir
        else:
            args.output_dir = os.path.dirname(args.input_file)
    
    # Initialize keyword extractor
    try:
        extractor = KeywordExtractor(
            device=args.device,
            confidence_threshold=args.confidence_threshold
        )
    except Exception as e:
        print(f"Failed to initialize keyword extractor: {e}")
        sys.exit(1)
    
    # Get image files to process
    if args.input_file:
        image_files = [args.input_file]
    else:
        image_files = find_image_files(args.input_dir)
    
    if not image_files:
        print("No image files found.")
        sys.exit(1)
    
    print(f"Found {len(image_files)} image files to process")
    
    # Process images
    results = extractor.process_batch(image_files)
    
    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Save individual results
    for result in results:
        if "error" not in result:
            image_name = os.path.splitext(os.path.basename(result["image_path"]))[0]
            output_file = os.path.join(args.output_dir, f"{image_name}_keywords.json")
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            print(f"Saved keywords to: {output_file}")
    
    # Save batch summary
    summary_file = os.path.join(args.output_dir, f"keyword_extraction_summary_{timestamp}.json")
    batch_summary = {
        "processing_date": datetime.now().isoformat(),
        "input_directory": args.input_dir,
        "input_file": args.input_file,
        "output_directory": args.output_dir,
        "confidence_threshold": args.confidence_threshold,
        "device": args.device,
        "total_images": len(image_files),
        "successful": len([r for r in results if "error" not in r]),
        "failed": len([r for r in results if "error" in r]),
        "results": results
    }
    
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(batch_summary, f, indent=2, ensure_ascii=False)
    
    print(f"Batch summary saved to: {summary_file}")
    
    # Print summary
    successful = len([r for r in results if "error" not in r])
    failed = len([r for r in results if "error" in r])
    
    print(f"\nProcessing complete:")
    print(f"  Total images: {len(image_files)}")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")


if __name__ == "__main__":
    main()
