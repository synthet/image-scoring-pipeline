# Proposed WebUI Improvements

Based on the analysis of the current `webui.py` and backend modules, here are three high-impact features proposed to elevate the application from a simple scorer to a functional Digital Asset Management (DAM) tool.

## 1. Interactive Metadata Editor
**Current State**: The Gallery is read-only (except for deletion).
**Problem**: Users cannot correct AI-generated tags or adjust ratings within the tool.
**Solution**: Transform the "Image Details" panel into an editable workspace.
- **Editable Fields**: Keywords, Title, Description, Rating, Color Label.
- **Action**: "Save Metadata" button that triggers `exiftool` (via `tagging.py`) to write changes back to the NEF/JPG/Sidecar.
**Value**: Enables **human-in-the-loop verification**, allowing users to refine the AI's output.

## 2. Deep-Dive Score Visualization
**Current State**: The "Image Details" view shows raw JSON data, which is difficult to parse quickly.
**Problem**: It is hard to intuitively understand *why* an image received a specific score.
**Solution**: Replace the JSON view (or augment it) with visual elements.
- **Visuals**: Progress bars or a Radar Chart for individual scores (Technical, Aesthetic, Quality, Sharpness, Noise).
- **Layout**: Clean summary of the top contributing factors.
**Value**: Provides **instant visual insight** into image quality metrics without reading code-like text.

## 3. "Smart Filter" & Export Workflow
**Current State**: Filtering is limited to exact matches on Rating/Label. There is no export functionality.
**Problem**: Users cannot easily find "top 10%" images or move them to a deliverable folder.
**Solution**: Enhance the Gallery with advanced filtering and actions.
- **Filters**: Range sliders for scores (e.g., "Aesthetic Score > 0.75").
- **Date Filter**: Filter by creation date range.
- **Export**: An "Export Filtered" or "Move to Best" button to copy/move selected images to a separate directory.
**Value**: Completes the **curation workflow** (Score -> Filter -> Deliver).
