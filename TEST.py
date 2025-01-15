import streamlit as st
import csv
import requests
import math
import os

# --- Configuration ---

# Dynamically get the directory of the current script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Build the path to the CSV in the same directory
PROVIDERS_CSV_PATH = os.path.join(SCRIPT_DIR, "Providers with Coords.csv")

API_KEY = "AIzaSyAmyHPY1AnV6loDOdbf_O6Xkg6fr3ziZiE"  # Replace with your actual key
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


# --- Helper Functions ---

def geocode_address(address):
    """
    Returns (latitude, longitude) of the given address using the Google Geocoding API.
    Returns (None, None) if geocoding fails.
    """
    params = {
        "address": address,
        "key": API_KEY
    }
    try:
        resp = requests.get(GEOCODE_URL, params=params)
        data = resp.json()
        if data["status"] == "OK":
            location = data["results"][0]["geometry"]["location"]
            return location["lat"], location["lng"]
        else:
            st.error(f"Geocoding failed: {data['status']}")
            return None, None
    except Exception as e:
        st.error(f"Exception during geocoding: {e}")
        return None, None


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance in miles between two points
    on the Earth (specified in decimal degrees).
    """
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c
    return distance


def load_providers(csv_path):
    """
    Read the CSV and return a list of dictionaries:
    [
      {"Provider": ..., "Address": ..., "Latitude": ..., "Longitude": ...},
      ...
    ]
    """
    providers_data = []
    with open(csv_path, mode="r", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            lat = float(row["Latitude"]) if row["Latitude"] else 0.0
            lng = float(row["Longitude"]) if row["Longitude"] else 0.0
            providers_data.append({
                "Provider": row["Provider"],   # Column name must match CSV
                "Address": row["Address"],
                "Latitude": lat,
                "Longitude": lng
            })
    return providers_data


def find_top_5_closest_providers(client_lat, client_lng, providers_list):
    """
    Given a client's lat/lng and a list of providers with lat/lng,
    returns the top 5 closest providers by Haversine distance.
    """
    # Calculate distance to each provider in miles
    for provider in providers_list:
        dist_miles = haversine_distance(
            client_lat,
            client_lng,
            provider["Latitude"],
            provider["Longitude"]
        )
        provider["DistanceMiles"] = dist_miles

    # Sort by distance ascending
    sorted_providers = sorted(providers_list, key=lambda p: p["DistanceMiles"])

    # Return top 5
    return sorted_providers[:5]


# --- Streamlit UI ---

def main():
    st.title("Find Closest Providers")
    st.write("Enter a client's address, and we'll find the 5 closest providers (in miles).")

    # Input form
    address_input = st.text_input("Client's Address:", "")

    if st.button("Find Providers"):
        if not address_input.strip():
            st.warning("Please enter an address.")
            return

        # 1. Geocode the client address
        client_lat, client_lng = geocode_address(address_input)

        if client_lat is None or client_lng is None:
            st.error("Could not geocode the provided address.")
            return

        # 2. Load providers from CSV
        providers_list = load_providers(PROVIDERS_CSV_PATH)

        # 3. Find top 5 closest
        top_5 = find_top_5_closest_providers(client_lat, client_lng, providers_list)

        # 4. Display results
        st.success(f"Top 5 closest providers to '{address_input}':")
        for idx, provider in enumerate(top_5, start=1):
            st.write(
                f"**{idx}. {provider['Provider']}**\n"
                f"Address: {provider['Address']}\n"
                f"Distance: {provider['DistanceMiles']:.2f} miles"
            )


if __name__ == "__main__":
    main()
