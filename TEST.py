import os
import csv
import math
import requests
import streamlit as st

# ----------------------------
# Page / App Configuration
# ----------------------------
st.set_page_config(
    page_title="Provider Finder",
    page_icon="🩺",
    layout="wide",
)

# Custom minimal CSS for a more professional look
st.markdown(
    """
    <style>
      .app-title { font-size: 32px; font-weight: 700; margin-bottom: 0.2rem; }
      .app-subtitle { color: #6b7280; margin-bottom: 1.5rem; }
      .result-card {
        padding: 0.9rem 1.1rem;
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        margin-bottom: 0.75rem;
        background: #ffffff;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
      }
      .provider-name { font-weight: 700; font-size: 16px; }
      .muted { color: #6b7280; }
      .pill {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 9999px;
        font-size: 12px;
        background: #f3f4f6;
        color: #374151;
        margin-left: 8px;
      }
    </style>
    """,
    unsafe_allow_html=True
)

# ----------------------------
# Configuration
# ----------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROVIDERS_CSV_PATH = os.path.join(SCRIPT_DIR, "Providers with Coords2.csv")

API_KEY = st.secrets.get("API_KEY")
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

MAX_RESULTS = 20  # Increased from 10 to 20

# ----------------------------
# Helpers
# ----------------------------
def geocode_address(address: str):
    """Return (lat, lng) via Google Geocoding API, or (None, None) on failure."""
    if not API_KEY:
        st.error("API key missing. Please set API_KEY in Streamlit secrets.")
        return None, None
    try:
        resp = requests.get(GEOCODE_URL, params={"address": address, "key": API_KEY}, timeout=15)
        data = resp.json()
        if data.get("status") == "OK":
            loc = data["results"][0]["geometry"]["location"]
            return loc["lat"], loc["lng"]
        else:
            st.error(f"Geocoding failed: {data.get('status')}")
            return None, None
    except Exception as e:
        st.error(f"Exception during geocoding: {e}")
        return None, None

def haversine_distance(lat1, lon1, lat2, lon2):
    """Great-circle distance (miles) between two latitude/longitude points."""
    R = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def load_providers(csv_path: str):
    """Load providers from CSV into a list of dicts."""
    providers = []
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lat = float(row.get("Latitude") or 0.0)
            lng = float(row.get("Longitude") or 0.0)
            providers.append({
                "Providers": row.get("Providers", "").strip(),
                "Address": row.get("Address", "").strip(),
                "Specialty": row.get("Specialty", "").strip(),
                "Latitude": lat,
                "Longitude": lng,
            })
    return providers

def filter_providers(providers, name_query: str = "", specialties=None):
    """Filter by provider name (contains) and specialty (exact match)."""
    if specialties is None:
        specialties = []
    name_query = (name_query or "").strip().lower()

    def _match(p):
        # Name filter (substring)
        if name_query and name_query not in p["Providers"].lower():
            return False
        # Specialty filter
        if specialties:
            return (p["Specialty"] in specialties)
        return True

    return [p for p in providers if _match(p)]

def compute_distances(client_lat: float, client_lng: float, providers):
    """Annotate providers with DistanceMiles (float)."""
    for p in providers:
        p["DistanceMiles"] = haversine_distance(client_lat, client_lng, p["Latitude"], p["Longitude"])
    return providers

# ----------------------------
# UI
# ----------------------------
st.markdown('<div class="app-title">Provider Finder</div>', unsafe_allow_html=True)
st.markdown('<div class="app-subtitle">Find the nearest providers by address and optionally refine by name or specialty.</div>', unsafe_allow_html=True)

# Load data once
providers_all = load_providers(PROVIDERS_CSV_PATH)
all_specialties = sorted({p["Specialty"] for p in providers_all if p["Specialty"]})

with st.sidebar:
    st.header("Filters")
    name_query = st.text_input("Provider name contains", value="", placeholder="e.g., Smith or 'Ortho'")
    selected_specialties = st.multiselect("Specialty", options=all_specialties, default=[])
    st.caption("Leave filters blank to include all providers.")

col_left, col_right = st.columns([1.2, 1])

with col_left:
    st.subheader("Search by Address")
    address = st.text_input("Client's address", value="", placeholder="123 Main St, City, State")
    search_clicked = st.button("Find Providers", type="primary", use_container_width=True)

with col_right:
    st.subheader("Options")
    st.write(f"Max results: **{MAX_RESULTS}**")
    show_addresses = st.checkbox("Show full addresses", value=True)

# Handle searches
if search_clicked and not address.strip() and not (name_query or selected_specialties):
    st.warning("Enter an address, or use Name/Specialty filters, or both.")
else:
    # Filter by name/specialty first (works for both address and non-address flows)
    filtered = filter_providers(providers_all, name_query=name_query, specialties=selected_specialties)

    if search_clicked and address.strip():
        # Distance-based flow
        latlng = geocode_address(address)
        if latlng == (None, None):
            st.stop()
        lat, lng = latlng
        filtered = compute_distances(lat, lng, filtered)
        filtered.sort(key=lambda p: p.get("DistanceMiles", float("inf")))
        results = filtered[:MAX_RESULTS]

        st.success(f"Top {len(results)} provider(s) near **{address}**" + (f" (filtered)" if (name_query or selected_specialties) else ""))
    else:
        # No address, filter-only flow (alphabetical)
        filtered.sort(key=lambda p: p["Providers"])
        results = filtered[:MAX_RESULTS]

        if name_query or selected_specialties:
            st.success(f"Showing {len(results)} provider(s) matching your filters (no address provided).")
        else:
            st.info("Use the filters or enter an address to start.")

    # Render results
    if results:
        for idx, p in enumerate(results, start=1):
            with st.container():
                st.markdown('<div class="result-card">', unsafe_allow_html=True)
                header = f"<span class='provider-name'>{idx}. {p['Providers']}</span>"
                if p.get("Specialty"):
                    header += f"<span class='pill'>{p['Specialty']}</span>"
                st.markdown(header, unsafe_allow_html=True)

                if show_addresses and p.get("Address"):
                    st.markdown(f"<div class='muted'>{p['Address']}</div>", unsafe_allow_html=True)

                if "DistanceMiles" in p:
                    st.markdown(f"<div class='muted'>Distance: {p['DistanceMiles']:.2f} miles</div>", unsafe_allow_html=True)

                st.markdown('</div>', unsafe_allow_html=True)
