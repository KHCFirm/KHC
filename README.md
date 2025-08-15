# Provider Finder (Streamlit)

Find the closest medical providers to a client address, with optional filters by **provider name** and **specialty**.

## What's new
- Shows **top 20** results (previously 10).
- Optional **provider name** text search (case-insensitive substring).
- Optional **specialty** filter (multiselect from your CSV).
- Cleaner, more professional UI (wide layout, sidebar filters, styled result cards).
- Works with or **without** an address:
  - With an address: computes distances and sorts nearest first.
  - Without an address: applies filters only and shows the first 20 alphabetically.

## Quick start
1. Install deps: `pip install -r requirements.txt`
2. Configure your Google Maps Geocoding API key in `.streamlit/secrets.toml`:
   ```toml
   API_KEY = "YOUR_GOOGLE_MAPS_API_KEY"
