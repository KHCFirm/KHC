import os
import csv
import math
import requests
import pandas as pd
import pydeck as pdk
import streamlit as st

# ----------------------------
# Page / App Configuration
# ----------------------------
st.set_page_config(
    page_title="Provider Finder",
    page_icon="🩺",
    layout="wide",
)

# ----------------------------
# Styles (full-width, tight spacing, 5-col grid)
# ----------------------------
st.markdown(
    """
    <style>
      /* Use the full screen width and reduce padding */
      .block-container { padding: 0.5rem 0.75rem 0.5rem 0.75rem; max-width: 100% !important; }
      /* Sidebar width a bit tighter to give content more room */
      section[data-testid="stSidebar"] { width: 300px !important; }
      .app-title { font-size: 28px; font-weight: 700; margin-bottom: 0.1rem; }
      .app-subtitle { color: #6b7280; margin-bottom: 0.6rem; }
      .results-wrap { width: 100%; margin: 0 auto; }
      .result-card {
        padding: 6px 4px 2px 4px;
        border-bottom: 1px solid #e5e7eb;
        min-height: 78px;
      }
      .provider-name { font-weight: 700; font-size: 15px; }
      .muted { color: #6b7280; font-size: 13px; }
      .pill {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 9999px;
        font-size: 11px;
        background: #f3f4f6;
        color: #374151;
        margin-left: 8px;
      }
      /* Make the address button look like a clean link */
      .stButton>button.addr-btn {
        background: transparent !important;
        border: none !important;
        color: #2563eb !important;
        padding: 0 !important;
        height: auto !important;
        min-height: 0 !important;
        font-size: 13px !important;
        text-align: left !important;
      }
      .stButton>button.addr-btn:hover { text-decoration: underline; }
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
# Optional: if you add MAPBOX_TOKEN to secrets, we’ll use Mapbox; otherwise we use CARTO (no token needed).
MAPBOX_TOKEN = st.secrets.get("MAPBOX_TOKEN")

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
DEFAULT_MAX_RESULTS = 20  # default remains 20

# Keep selection across interactions
if "selected_idx" not in st.session_state:
    st.session_state.selected_idx = None

# ----------------------------
# Helpers
# ----------------------------
@st.cache_data(show_spinner=False, ttl=60 * 60 * 24)
def geocode_address_cached(address: str, api_key: str):
    """Return (lat, lng) via Google Geocoding API, or (None, None) on failure. Cached by address."""
    if not api_key:
        return None, None, "API key missing. Please set API_KEY in Streamlit secrets."
    try:
        resp = requests.get(GEOCODE_URL, params={"address": address, "key": api_key}, timeout=15)
        data = resp.json()
        if data.get("status") == "OK":
            loc = data["results"][0]["geometry"]["location"]
            return loc["lat"], loc["lng"], None
        return None, None, f"Geocoding failed: {data.get('status')}"
    except Exception as e:
        return None, None, f"Exception during geocoding: {e}"

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
            try:
                lat = float(row.get("Latitude") or 0.0)
                lng = float(row.get("Longitude") or 0.0)
            except ValueError:
                lat, lng = 0.0, 0.0
            providers.append({
                "Providers": (row.get("Providers") or "").strip(),
                "Address": (row.get("Address") or "").strip(),
                "Specialty": (row.get("Specialty") or "").strip(),
                "Latitude": lat,
                "Longitude": lng,
            })
    return providers

# Curated specialty grouping (case-insensitive substring match).
SPECIALTY_GROUPS = {
    "Chiro": ["chiro"],
    "PT": ["physical therapy", "physio", " pt ", " pt", "(pt)"],
    "Ortho": ["ortho", "orthop"],
    "Neuro": ["neuro"],
    "Spine": ["spine", "spinal"],
    "Foot/Ankle": ["foot", "ankle", "podiat"],
    "Hand Surgeon": ["hand surgeon", "hand & wrist", "upper extremity", "hand"],
    "Post-Concussion": ["post-concussion", "concuss", "tbi"],
    "Heart": ["cardio", "heart"],
    "Pain Management": ["pain management", "pain med", "interventional pain", "pm&r", "physiat"],
    "MRI/Imaging": ["mri", "radiology", "imaging", "x-ray", "ct"],
    "ENT": ["ent", "otolaryng"],
    "Ophthalmology": ["ophthalm", "eye"],
    "Dental/Oral": ["dental", "oral", "maxillofacial"],
    "Primary Care": ["primary care", "internal medicine", "family medicine"],
    "Urgent Care": ["urgent care"],
    "Neurosurgery": ["neurosurg"],
    "Plastic/Reconstructive": ["plastic", "reconstructive"],
    "Psych/Behavioral": ["psychiat", "psychology", "behavioral"],
}

def specialty_groups_for_text(s: str):
    """Return the set of group labels that match the given specialty text."""
    s_low = f" {s.lower()} "
    matches = set()
    for label, needles in SPECIALTY_GROUPS.items():
        for n in needles:
            if n in s_low:
                matches.add(label)
                break
    return matches

def available_specialty_groups(providers):
    """Return a sorted list of group labels that actually occur in the dataset."""
    found = set()
    for p in providers:
        found |= specialty_groups_for_text(p.get("Specialty", ""))
    return sorted(found)

def filter_by_name(providers, name_query: str = ""):
    nq = (name_query or "").strip().lower()
    if not nq:
        return providers
    return [p for p in providers if nq in p["Providers"].lower()]

def filter_by_groups(providers, selected_groups):
    if not selected_groups:
        return providers
    out = []
    sel = set(selected_groups)
    for p in providers:
        groups = specialty_groups_for_text(p.get("Specialty", ""))
        if groups & sel:
            out.append(p)
    return out

def compute_distances(client_lat: float, client_lng: float, providers):
    """Annotate providers with DistanceMiles (float)."""
    for p in providers:
        p["DistanceMiles"] = haversine_distance(client_lat, client_lng, p["Latitude"], p["Longitude"])
    return providers

def calc_view_state(points, fallback_lat=39.5, fallback_lng=-98.35, selected=None):
    """Center/zoom heuristic; center on selected if provided."""
    if selected is not None:
        return pdk.ViewState(latitude=selected[0], longitude=selected[1], zoom=12, pitch=0)
    if not points:
        return pdk.ViewState(latitude=fallback_lat, longitude=fallback_lng, zoom=4.2, pitch=0)
    lats = [p["lat"] for p in points]
    lngs = [p["lon"] for p in points]
    lat_c = sum(lats) / len(lats)
    lng_c = sum(lngs) / len(lngs)
    lat_span = max(lats) - min(lats) if len(lats) > 1 else 0.05
    lng_span = max(lngs) - min(lngs) if len(lngs) > 1 else 0.05
    span = max(lat_span, lng_span)
    zoom = 11 if span < 0.02 else 10 if span < 0.05 else 9 if span < 0.1 else 8 if span < 0.2 else 7 if span < 0.5 else 6 if span < 1 else 5
    return pdk.ViewState(latitude=lat_c, longitude=lng_c, zoom=zoom, pitch=0)

# ----------------------------
# UI
# ----------------------------
st.markdown('<div class="app-title">Provider Finder</div>', unsafe_allow_html=True)
st.markdown('<div class="app-subtitle">Find nearby providers by address; refine by name and grouped specialty.</div>', unsafe_allow_html=True)

# Load data once
providers_all = load_providers(PROVIDERS_CSV_PATH)

with st.sidebar:
    st.header("Filters")
    name_query = st.text_input("Provider name contains", value="", placeholder="e.g., Smith or 'Ortho'")

    group_options = available_specialty_groups(providers_all)
    selected_groups = st.multiselect(
        "Specialty groups",
        options=group_options,
        default=[],
        help="These groups match any similar specialty text (e.g., 'Ortho' covers Orthopedics)."
    )

    st.header("Results")
    max_results = st.number_input(
        "Max results",
        min_value=1,
        max_value=200,
        value=DEFAULT_MAX_RESULTS,
        step=1,
        help="Change how many providers to show per search."
    )

    show_map = st.checkbox(
        "Show map of results",
        value=True,
        help="Plot the current results as pins (only providers with valid coordinates are shown)."
    )

# Main controls
col_left, col_right = st.columns([1.6, 1])
with col_left:
    st.subheader("Search by Address")
    address = st.text_input("Client's address", value="", placeholder="123 Main St, City, State")
    st.button("Find Providers", type="primary", use_container_width=True)  # kept for UX

with col_right:
    st.subheader("How it works")
    st.write(
        "- Enter an address to sort by distance.\n"
        "- Use **name** and **specialty groups** to refine results.\n"
        "- Adjust **Max results** in the sidebar.\n"
        "- Optionally display the results on a map."
    )

# ----------------------------
# Run search (auto-uses address if present)
# ----------------------------
filtered = filter_by_name(providers_all, name_query)
filtered = filter_by_groups(filtered, selected_groups)

has_address = bool(address.strip())

if not has_address and not (name_query or selected_groups):
    st.info("Use the filters or enter an address to start.")
    results = []
    client_lat = client_lng = None
else:
    if has_address:
        client_lat, client_lng, geo_err = geocode_address_cached(address.strip(), API_KEY)
        if geo_err:
            st.error(geo_err)
        if client_lat is not None and client_lng is not None:
            filtered = compute_distances(client_lat, client_lng, filtered)
            filtered.sort(key=lambda p: p.get("DistanceMiles", float("inf")))
            results = filtered[: int(max_results)]
            st.success(
                f"Top {len(results)} provider(s) near **{address}**"
                + (" (filtered)" if (name_query or selected_groups) else "")
            )
        else:
            filtered.sort(key=lambda p: p["Providers"])
            results = filtered[: int(max_results)]
            st.warning("Showing providers by name/specialty (address not usable).")
    else:
        client_lat = client_lng = None
        filtered.sort(key=lambda p: p["Providers"])
        results = filtered[: int(max_results)]
        st.success(f"Showing {len(results)} provider(s) matching your filters (no address sorting).")

# ----------------------------
# Results grid: 5 columns per row (full-width)
# Clicking the address sets selected_idx to highlight on the map
# ----------------------------
if results:
    st.markdown('<div class="results-wrap">', unsafe_allow_html=True)

    for i in range(0, len(results), 5):
        cols = st.columns(5, gap="small")
        row = results[i:i+5]
        for j, p in enumerate(row):
            idx = i + j + 1
            groups = " / ".join(sorted(specialty_groups_for_text(p.get("Specialty", ""))))
            with cols[j]:
                st.markdown(
                    f"<div class='result-card'><span class='provider-name'>{idx}. {p['Providers']}</span>"
                    + (f"<span class='pill'>{groups}</span>" if groups else "")
                    + "</div>",
                    unsafe_allow_html=True
                )
                clicked = st.button(
                    p.get("Address", "No address listed") or "No address listed",
                    key=f"addr_{idx}",
                    help="Click to highlight this provider on the map",
                    use_container_width=True
                )
                # Style the last-created button as a link
                st.markdown(
                    "<script>var btns = window.parent.document.querySelectorAll('.stButton button');"
                    "if(btns && btns.length) { btns[btns.length-1].classList.add('addr-btn'); }</script>",
                    unsafe_allow_html=True
                )
                if "DistanceMiles" in p:
                    st.markdown(f"<div class='muted'>Distance: {p['DistanceMiles']:.2f} miles</div>", unsafe_allow_html=True)

                if clicked:
                    st.session_state.selected_idx = idx

    st.markdown('</div>', unsafe_allow_html=True)

# ----------------------------
# Map (below the grid) with basemap fix:
# - If MAPBOX_TOKEN is available, use Mapbox
# - Otherwise use CARTO provider (no token required)
# ----------------------------
if results and show_map:
    # Build points for providers with valid coords
    points = []
    selected_point = None
    for k, p in enumerate(results, start=1):
        lat = p.get("Latitude")
        lon = p.get("Longitude")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)) and lat != 0.0 and lon != 0.0:
            is_selected = (st.session_state.selected_idx == k)
            color = [33, 115, 205]  # default blue-ish
            radius = 65
            if is_selected:
                color = [255, 140, 0]   # orange for selected
                radius = 110
                selected_point = (lat, lon)
            points.append({
                "lat": lat,
                "lon": lon,
                "Providers": p.get("Providers", ""),
                "Address": p.get("Address", ""),
                "Distance": f"{p.get('DistanceMiles', float('nan')):.2f} mi" if "DistanceMiles" in p else "",
                "ResultNo": k,
                "color": color,
                "radius": radius,
            })

    df_points = pd.DataFrame(points)

    # Client address layer (if available)
    client_layer = None
    selected_center = selected_point
    if client_lat is not None and client_lng is not None:
        client_df = pd.DataFrame([{"lat": client_lat, "lon": client_lng}])
        client_layer = pdk.Layer(
            "ScatterplotLayer",
            data=client_df,
            get_position="[lon, lat]",
            get_fill_color=[200, 30, 0],  # distinct red-ish color for client
            get_radius=140,
            pickable=False,
            stroked=True,
            get_line_color=[255, 255, 255],
            line_width_min_pixels=1,
        )
        if selected_center is None:
            selected_center = (client_lat, client_lng)

    # Providers layer
    providers_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_points,
        get_position="[lon, lat]",
        get_fill_color="color",
        get_radius="radius",
        pickable=True,
        stroked=True,
        get_line_color=[255, 255, 255],
        line_width_min_pixels=1,
    )

    # Decide basemap provider
    deck_kwargs = {
        "initial_view_state": calc_view_state(
            [{"lat": r["lat"], "lon": r["lon"]} for r in points],
            selected=selected_center
        ),
        "layers": [l for l in [client_layer, providers_layer] if l is not None],
        "tooltip": {
            "html": "<b>{ResultNo}. {Providers}</b><br/>{Address}<br/>{Distance}",
            "style": {"backgroundColor": "white", "color": "black"},
        },
    }

    if MAPBOX_TOKEN:
        # Use Mapbox if token provided
        pdk.settings.mapbox_api_key = MAPBOX_TOKEN
        deck = pdk.Deck(
            map_provider="mapbox",
            map_style="mapbox://styles/mapbox/streets-v12",
            **deck_kwargs,
        )
    else:
        # Tokenless CARTO basemap
        deck = pdk.Deck(
            map_provider="carto",
            map_style="light",
            **deck_kwargs,
        )

    st.pydeck_chart(deck, use_container_width=True, height=520)
