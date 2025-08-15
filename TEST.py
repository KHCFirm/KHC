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

# ----------------------------
# Styles (thinner results, subtle dividers, constrained width)
# ----------------------------
st.markdown(
    """
    <style>
      .app-title { font-size: 32px; font-weight: 700; margin-bottom: 0.25rem; }
      .app-subtitle { color: #6b7280; margin-bottom: 1.25rem; }
      .results-wrap { max-width: 900px; margin: 0 auto; }  /* keep results from spanning full width */
      .result-row {
        padding: 10px 4px;
        border-bottom: 1px solid #e5e7eb; /* thin line divider */
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

DEFAULT_MAX_RESULTS = 20  # default remains 20

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
# Only groups that actually appear in your data will be shown in the UI.
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

    # Build grouped specialty options that actually exist in the dataset
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

# Main controls
col_left, col_right = st.columns([1.2, 1])

with col_left:
    st.subheader("Search by Address")
    address = st.text_input("Client's address", value="", placeholder="123 Main St, City, State")
    # Button kept for UX, but logic below auto-uses the address if it's present.
    st.button("Find Providers", type="primary", use_container_width=True)

with col_right:
    st.subheader("How it works")
    st.write(
        "- Enter an address to sort by distance.\n"
        "- Use **name** and **specialty groups** to refine results.\n"
        "- Adjust **Max results** in the sidebar.\n"
        "- Changes take effect immediately; no need to click again."
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
else:
    if has_address:
        lat, lng, geo_err = geocode_address_cached(address.strip(), API_KEY)
        if geo_err:
            st.error(geo_err)
        if lat is not None and lng is not None:
            filtered = compute_distances(lat, lng, filtered)
            filtered.sort(key=lambda p: p.get("DistanceMiles", float("inf")))
            results = filtered[: int(max_results)]
            st.success(
                f"Top {len(results)} provider(s) near **{address}**"
                + (" (filtered)" if (name_query or selected_groups) else "")
            )
        else:
            # Fallback to filter-only if geocode failed
            filtered.sort(key=lambda p: p["Providers"])
            results = filtered[: int(max_results)]
            st.warning(
                f"Showing {len(results)} provider(s) by name/specialty (address not usable)."
            )
    else:
        # No address, filter-only flow (alphabetical)
        filtered.sort(key=lambda p: p["Providers"])
        results = filtered[: int(max_results)]
        st.success(f"Showing {len(results)} provider(s) matching your filters (no address sorting).")

# ----------------------------
# Render results (thin lines, always show full address)
# ----------------------------
if results:
    st.markdown('<div class="results-wrap">', unsafe_allow_html=True)
    for idx, p in enumerate(results, start=1):
        groups = " / ".join(sorted(specialty_groups_for_text(p.get("Specialty", ""))))
        header = f"<span class='provider-name'>{idx}. {p['Providers']}</span>"
        if groups:
            header += f"<span class='pill'>{groups}</span>"
        st.markdown(f"<div class='result-row'>{header}", unsafe_allow_html=True)

        if p.get("Address"):
            st.markdown(f"<div class='muted'>{p['Address']}</div>", unsafe_allow_html=True)

        if "DistanceMiles" in p:
            st.markdown(f"<div class='muted'>Distance: {p['DistanceMiles']:.2f} miles</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
