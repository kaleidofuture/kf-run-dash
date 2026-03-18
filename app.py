"""KF-RunDash — GPX/FITファイルからランニングデータを分析・可視化するアプリ。"""

import streamlit as st

st.set_page_config(
    page_title="KF-RunDash",
    page_icon="🏃",
    layout="wide",
)

from components.header import render_header
from components.footer import render_footer
from components.i18n import t

import io
import csv
import math
from datetime import datetime, timedelta

# --- Header ---
render_header()


def parse_gpx(file_bytes: bytes) -> dict:
    """Parse a GPX file and return structured run data."""
    import gpxpy

    gpx = gpxpy.parse(file_bytes.decode("utf-8"))

    points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                points.append({
                    "lat": point.latitude,
                    "lon": point.longitude,
                    "elevation": point.elevation or 0,
                    "time": point.time,
                    "heart_rate": None,  # GPX extensions may have HR
                })
                # Try to extract heart rate from extensions
                if point.extensions:
                    for ext in point.extensions:
                        # Look for heart rate in Garmin TrackPointExtension
                        hr_elem = ext.find(".//{http://www.garmin.com/xmlschemas/TrackPointExtension/v1}hr")
                        if hr_elem is not None and hr_elem.text:
                            points[-1]["heart_rate"] = int(hr_elem.text)

    return {"points": points, "name": gpx.tracks[0].name if gpx.tracks and gpx.tracks[0].name else "Run"}


def parse_fit(file_bytes: bytes) -> dict:
    """Parse a FIT file and return structured run data."""
    from fitparse import FitFile

    fitfile = FitFile(io.BytesIO(file_bytes))

    points = []
    for record in fitfile.get_messages("record"):
        point = {
            "lat": None,
            "lon": None,
            "elevation": None,
            "time": None,
            "heart_rate": None,
        }
        for field in record:
            if field.name == "position_lat" and field.value is not None:
                point["lat"] = field.value * (180 / 2**31)  # semicircles to degrees
            elif field.name == "position_long" and field.value is not None:
                point["lon"] = field.value * (180 / 2**31)
            elif field.name == "altitude" and field.value is not None:
                point["elevation"] = field.value
            elif field.name == "enhanced_altitude" and field.value is not None:
                point["elevation"] = field.value
            elif field.name == "timestamp" and field.value is not None:
                point["time"] = field.value
            elif field.name == "heart_rate" and field.value is not None:
                point["heart_rate"] = field.value

        if point["lat"] is not None and point["lon"] is not None:
            if point["elevation"] is None:
                point["elevation"] = 0
            points.append(point)

    return {"points": points, "name": "Run"}


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two GPS coordinates in meters."""
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def compute_metrics(points: list[dict]) -> dict:
    """Compute running metrics from GPS points."""
    if len(points) < 2:
        return {}

    distances = [0.0]
    paces = []
    elevations = []
    heart_rates = []
    times = []
    cumulative_dist = 0.0
    total_ascent = 0.0
    total_descent = 0.0

    for i in range(1, len(points)):
        p1, p2 = points[i - 1], points[i]

        # Distance
        d = haversine(p1["lat"], p1["lon"], p2["lat"], p2["lon"])
        cumulative_dist += d
        distances.append(cumulative_dist)

        # Elevation
        elev = p2["elevation"]
        elevations.append(elev)
        elev_diff = p2["elevation"] - p1["elevation"]
        if elev_diff > 0:
            total_ascent += elev_diff
        else:
            total_descent += abs(elev_diff)

        # Pace (min/km)
        if p1["time"] and p2["time"]:
            dt = (p2["time"] - p1["time"]).total_seconds()
            if d > 0 and dt > 0:
                pace = (dt / d) * 1000 / 60  # min/km
                if pace < 30:  # Filter out pauses (> 30 min/km)
                    paces.append({"dist": cumulative_dist, "pace": pace, "time": p2["time"]})

        # Heart rate
        if p2["heart_rate"] is not None:
            heart_rates.append({"dist": cumulative_dist, "hr": p2["heart_rate"], "time": p2["time"]})

        if p2["time"]:
            times.append(p2["time"])

    # Total time
    total_time = None
    if points[0]["time"] and points[-1]["time"]:
        total_time = (points[-1]["time"] - points[0]["time"]).total_seconds()

    total_dist_km = cumulative_dist / 1000

    # Average pace
    avg_pace = None
    if total_time and total_dist_km > 0:
        avg_pace = total_time / 60 / total_dist_km  # min/km

    # Average heart rate
    avg_hr = None
    max_hr = None
    if heart_rates:
        hrs = [h["hr"] for h in heart_rates]
        avg_hr = sum(hrs) / len(hrs)
        max_hr = max(hrs)

    return {
        "total_distance_km": round(total_dist_km, 2),
        "total_time_seconds": total_time,
        "avg_pace_min_km": round(avg_pace, 2) if avg_pace else None,
        "total_ascent_m": round(total_ascent, 1),
        "total_descent_m": round(total_descent, 1),
        "avg_hr": round(avg_hr) if avg_hr else None,
        "max_hr": max_hr,
        "distances": distances,
        "paces": paces,
        "heart_rates": heart_rates,
        "elevations": elevations,
        "points": points,
    }


def format_pace(pace_min_km: float | None) -> str:
    """Format pace as M:SS /km."""
    if pace_min_km is None:
        return "-"
    minutes = int(pace_min_km)
    seconds = int((pace_min_km - minutes) * 60)
    return f"{minutes}:{seconds:02d} /km"


def format_duration(seconds: float | None) -> str:
    """Format duration as H:MM:SS."""
    if seconds is None:
        return "-"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def generate_csv_report(metrics: dict) -> bytes:
    """Generate a CSV summary report."""
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Metric", "Value"])
    writer.writerow(["Total Distance (km)", metrics["total_distance_km"]])
    writer.writerow(["Total Time", format_duration(metrics["total_time_seconds"])])
    writer.writerow(["Average Pace", format_pace(metrics["avg_pace_min_km"])])
    writer.writerow(["Total Ascent (m)", metrics["total_ascent_m"]])
    writer.writerow(["Total Descent (m)", metrics["total_descent_m"]])
    writer.writerow(["Average Heart Rate (bpm)", metrics["avg_hr"] or "-"])
    writer.writerow(["Max Heart Rate (bpm)", metrics["max_hr"] or "-"])

    # Detailed per-km splits
    writer.writerow([])
    writer.writerow(["Split (km)", "Pace (min/km)", "Heart Rate (bpm)"])

    if metrics["paces"]:
        km_splits = {}
        for p in metrics["paces"]:
            km = int(p["dist"] / 1000)
            if km not in km_splits:
                km_splits[km] = {"paces": [], "hrs": []}
            km_splits[km]["paces"].append(p["pace"])

        for h in metrics["heart_rates"]:
            km = int(h["dist"] / 1000)
            if km in km_splits:
                km_splits[km]["hrs"].append(h["hr"])

        for km in sorted(km_splits.keys()):
            avg_p = sum(km_splits[km]["paces"]) / len(km_splits[km]["paces"])
            avg_h = sum(km_splits[km]["hrs"]) / len(km_splits[km]["hrs"]) if km_splits[km]["hrs"] else None
            writer.writerow([f"{km + 1}", format_pace(avg_p), round(avg_h) if avg_h else "-"])

    return output.getvalue().encode("utf-8-sig")


# --- Main Content ---
st.markdown(f"### {t('upload_title')}")

uploaded_file = st.file_uploader(
    t("upload_prompt"),
    type=["gpx", "fit"],
    help=t("upload_help"),
)

if uploaded_file is not None:
    file_bytes = uploaded_file.read()
    file_ext = uploaded_file.name.rsplit(".", 1)[-1].lower()

    with st.spinner(t("processing")):
        try:
            if file_ext == "gpx":
                run_data = parse_gpx(file_bytes)
            elif file_ext == "fit":
                run_data = parse_fit(file_bytes)
            else:
                st.error(t("unsupported_format"))
                st.stop()

            if not run_data["points"]:
                st.error(t("no_gps_data"))
                st.stop()

            metrics = compute_metrics(run_data["points"])

        except Exception as e:
            st.error(f"{t('parse_error')}: {e}")
            st.stop()

    # --- Summary Metrics ---
    st.markdown(f"### {t('summary_title')}")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(t("metric_distance"), f"{metrics['total_distance_km']} km")
    with col2:
        st.metric(t("metric_time"), format_duration(metrics["total_time_seconds"]))
    with col3:
        st.metric(t("metric_pace"), format_pace(metrics["avg_pace_min_km"]))
    with col4:
        st.metric(t("metric_ascent"), f"{metrics['total_ascent_m']} m")

    if metrics["avg_hr"]:
        col5, col6 = st.columns(2)
        with col5:
            st.metric(t("metric_avg_hr"), f"{metrics['avg_hr']} bpm")
        with col6:
            st.metric(t("metric_max_hr"), f"{metrics['max_hr']} bpm")

    st.markdown("---")

    # --- Charts ---
    tab_map, tab_pace, tab_elev, tab_hr = st.tabs([
        t("tab_map"), t("tab_pace"), t("tab_elevation"), t("tab_heart_rate")
    ])

    # Map tab
    with tab_map:
        st.markdown(f"#### {t('route_map')}")
        try:
            import folium
            from streamlit_folium import st_folium

            points_with_coords = [p for p in run_data["points"] if p["lat"] and p["lon"]]
            if points_with_coords:
                center_lat = sum(p["lat"] for p in points_with_coords) / len(points_with_coords)
                center_lon = sum(p["lon"] for p in points_with_coords) / len(points_with_coords)

                m = folium.Map(location=[center_lat, center_lon], zoom_start=14)

                # Route line
                coords = [[p["lat"], p["lon"]] for p in points_with_coords]
                folium.PolyLine(coords, weight=4, color="#4A90D9", opacity=0.8).add_to(m)

                # Start/End markers
                folium.Marker(
                    coords[0],
                    popup=t("marker_start"),
                    icon=folium.Icon(color="green", icon="play", prefix="fa"),
                ).add_to(m)
                folium.Marker(
                    coords[-1],
                    popup=t("marker_finish"),
                    icon=folium.Icon(color="red", icon="flag-checkered", prefix="fa"),
                ).add_to(m)

                st_folium(m, width=None, height=500, use_container_width=True)
        except ImportError:
            st.warning(t("folium_not_available"))
            # Fallback: show as st.map
            import pandas as pd
            map_df = pd.DataFrame([{"lat": p["lat"], "lon": p["lon"]} for p in points_with_coords])
            st.map(map_df)

    # Pace tab
    with tab_pace:
        st.markdown(f"#### {t('pace_chart')}")
        if metrics["paces"]:
            import pandas as pd
            # Per-km splits
            km_paces = {}
            for p in metrics["paces"]:
                km = int(p["dist"] / 1000) + 1
                if km not in km_paces:
                    km_paces[km] = []
                km_paces[km].append(p["pace"])

            pace_data = []
            for km in sorted(km_paces.keys()):
                avg_pace = sum(km_paces[km]) / len(km_paces[km])
                pace_data.append({"km": km, t("col_pace"): round(avg_pace, 2)})

            if pace_data:
                df_pace = pd.DataFrame(pace_data)
                st.bar_chart(df_pace, x="km", y=t("col_pace"))
        else:
            st.info(t("no_pace_data"))

    # Elevation tab
    with tab_elev:
        st.markdown(f"#### {t('elevation_chart')}")
        if metrics["elevations"]:
            import pandas as pd
            elev_data = []
            for i, elev in enumerate(metrics["elevations"]):
                dist_km = metrics["distances"][i + 1] / 1000
                elev_data.append({"km": round(dist_km, 2), t("col_elevation"): round(elev, 1)})

            # Sample for performance (max 500 points)
            if len(elev_data) > 500:
                step = len(elev_data) // 500
                elev_data = elev_data[::step]

            df_elev = pd.DataFrame(elev_data)
            st.area_chart(df_elev, x="km", y=t("col_elevation"))

            col1, col2 = st.columns(2)
            with col1:
                st.metric(t("metric_ascent"), f"{metrics['total_ascent_m']} m")
            with col2:
                st.metric(t("metric_descent"), f"{metrics['total_descent_m']} m")
        else:
            st.info(t("no_elevation_data"))

    # Heart rate tab
    with tab_hr:
        st.markdown(f"#### {t('hr_chart')}")
        if metrics["heart_rates"]:
            import pandas as pd
            hr_data = []
            for h in metrics["heart_rates"]:
                dist_km = h["dist"] / 1000
                hr_data.append({"km": round(dist_km, 2), t("col_hr"): h["hr"]})

            # Sample for performance
            if len(hr_data) > 500:
                step = len(hr_data) // 500
                hr_data = hr_data[::step]

            df_hr = pd.DataFrame(hr_data)
            st.line_chart(df_hr, x="km", y=t("col_hr"))
        else:
            st.info(t("no_hr_data"))

    # --- Download CSV ---
    st.markdown("---")
    csv_bytes = generate_csv_report(metrics)
    st.download_button(
        label=t("download_csv"),
        data=csv_bytes,
        file_name=f"run_report_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        type="primary",
    )

else:
    st.info(t("no_file"))

# --- Footer ---
render_footer(libraries=["fitparse", "gpxpy", "folium", "streamlit-folium"])
