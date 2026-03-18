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


def compute_km_splits(metrics: dict) -> list[dict]:
    """Compute per-km splits with pace, HR, elevation, and GAP."""
    if not metrics["paces"]:
        return []

    km_splits = {}
    for p in metrics["paces"]:
        km = int(p["dist"] / 1000)
        if km not in km_splits:
            km_splits[km] = {"paces": [], "hrs": [], "elevations": []}
        km_splits[km]["paces"].append(p["pace"])

    for h in metrics["heart_rates"]:
        km = int(h["dist"] / 1000)
        if km in km_splits:
            km_splits[km]["hrs"].append(h["hr"])

    # Compute elevation change per km for GAP calculation
    points = metrics["points"]
    distances = metrics["distances"]
    for i in range(1, len(points)):
        km = int(distances[i] / 1000)
        if km in km_splits:
            km_splits[km]["elevations"].append(
                (points[i]["elevation"] - points[i - 1]["elevation"],
                 distances[i] - distances[i - 1])
            )

    result = []
    for km in sorted(km_splits.keys()):
        data = km_splits[km]
        avg_pace = sum(data["paces"]) / len(data["paces"])
        avg_hr = sum(data["hrs"]) / len(data["hrs"]) if data["hrs"] else None

        # Calculate grade for GAP
        total_elev_change = sum(e[0] for e in data["elevations"])
        total_horiz_dist = sum(e[1] for e in data["elevations"])
        grade_pct = (total_elev_change / total_horiz_dist * 100) if total_horiz_dist > 0 else 0
        elev_change = total_elev_change

        # GAP = actual_pace / (1 + 0.033 * grade_percent)
        gap_factor = 1 + 0.033 * grade_pct
        gap = avg_pace / gap_factor if gap_factor > 0 else avg_pace

        result.append({
            "km": km + 1,
            "pace": avg_pace,
            "hr": round(avg_hr) if avg_hr else None,
            "elev_change": round(elev_change, 1),
            "grade_pct": round(grade_pct, 1),
            "gap": gap,
        })

    return result


def find_best_splits(metrics: dict) -> dict:
    """Find fastest 1km and 5km segments from the run data."""
    points = metrics["points"]
    distances = metrics["distances"]
    best = {"1km": None, "5km": None}

    if len(points) < 2:
        return best

    # For each target distance, use a sliding window approach
    for target_m, key in [(1000, "1km"), (5000, "5km")]:
        if distances[-1] < target_m:
            continue

        best_time = float("inf")
        best_start_km = None
        best_end_km = None

        j = 0
        for i in range(len(points)):
            # Advance j until we have at least target_m distance from point i
            while j < len(points) - 1 and (distances[j] - distances[i]) < target_m:
                j += 1

            if (distances[j] - distances[i]) >= target_m:
                if points[i]["time"] and points[j]["time"]:
                    elapsed = (points[j]["time"] - points[i]["time"]).total_seconds()
                    if elapsed > 0 and elapsed < best_time:
                        best_time = elapsed
                        best_start_km = distances[i] / 1000
                        best_end_km = distances[j] / 1000

        if best_time < float("inf"):
            pace = best_time / 60 / (target_m / 1000)  # min/km
            best[key] = {
                "time_seconds": best_time,
                "pace": pace,
                "start_km": round(best_start_km, 2),
                "end_km": round(best_end_km, 2),
            }

    return best


def compute_hr_zones(heart_rates: list[dict], max_hr: int) -> list[dict]:
    """Compute time/count in each heart rate zone."""
    zones = [
        {"zone": 1, "min_pct": 50, "max_pct": 60, "count": 0},
        {"zone": 2, "min_pct": 60, "max_pct": 70, "count": 0},
        {"zone": 3, "min_pct": 70, "max_pct": 80, "count": 0},
        {"zone": 4, "min_pct": 80, "max_pct": 90, "count": 0},
        {"zone": 5, "min_pct": 90, "max_pct": 100, "count": 0},
    ]

    below_count = 0
    total_count = 0

    for h in heart_rates:
        hr = h["hr"]
        pct = (hr / max_hr) * 100
        total_count += 1
        assigned = False
        for z in zones:
            if z["min_pct"] <= pct < z["max_pct"]:
                z["count"] += 1
                assigned = True
                break
        if not assigned:
            if pct >= 100:
                zones[4]["count"] += 1  # Zone 5 includes 100%
            else:
                below_count += 1  # Below zone 1

    # Calculate percentages
    for z in zones:
        z["pct"] = round(z["count"] / total_count * 100, 1) if total_count > 0 else 0

    return zones


def format_pace(pace_min_km: float | None) -> str:
    """Format pace as M:SS /km."""
    if pace_min_km is None:
        return "-"
    minutes = int(pace_min_km)
    seconds = int((pace_min_km - minutes) * 60)
    return f"{minutes}:{seconds:02d} /km"


def format_pace_short(pace_min_km: float | None) -> str:
    """Format pace as M:SS (no /km suffix)."""
    if pace_min_km is None:
        return "-"
    minutes = int(pace_min_km)
    seconds = int((pace_min_km - minutes) * 60)
    return f"{minutes}:{seconds:02d}"


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


def generate_csv_report(metrics: dict, km_splits: list[dict]) -> bytes:
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
    writer.writerow(["Split (km)", "Pace (min/km)", "GAP (min/km)", "Heart Rate (bpm)", "Elev Change (m)", "Grade (%)"])

    for split in km_splits:
        writer.writerow([
            f"{split['km']}",
            format_pace_short(split["pace"]),
            format_pace_short(split["gap"]),
            split["hr"] if split["hr"] else "-",
            split["elev_change"],
            split["grade_pct"],
        ])

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

            if len(run_data["points"]) < 2:
                st.error(t("no_gps_data"))
                st.stop()

            metrics = compute_metrics(run_data["points"])
            km_splits = compute_km_splits(metrics)
            best_splits = find_best_splits(metrics)

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

    # --- Best Splits ---
    if best_splits["1km"] or best_splits["5km"]:
        st.markdown(f"#### {t('best_splits_title')}")
        best_cols = st.columns(2)
        if best_splits["1km"]:
            with best_cols[0]:
                bs = best_splits["1km"]
                st.success(
                    f"🏅 {t('best_1km')}: **{format_pace(bs['pace'])}** "
                    f"({format_duration(bs['time_seconds'])}) — "
                    f"km {bs['start_km']:.1f} ~ {bs['end_km']:.1f}"
                )
        if best_splits["5km"]:
            with best_cols[1]:
                bs = best_splits["5km"]
                st.success(
                    f"🏅 {t('best_5km')}: **{format_pace(bs['pace'])}** "
                    f"({format_duration(bs['time_seconds'])}) — "
                    f"km {bs['start_km']:.1f} ~ {bs['end_km']:.1f}"
                )

    st.markdown("---")

    # --- Charts ---
    tab_labels = [
        t("tab_map"), t("tab_pace"), t("tab_elevation"), t("tab_heart_rate"),
        t("tab_splits"),
    ]
    if metrics["heart_rates"]:
        tab_labels.append(t("tab_hr_zones"))
        tab_labels.append(t("tab_pace_vs_hr"))

    tabs = st.tabs(tab_labels)
    tab_idx = 0

    # Map tab
    with tabs[tab_idx]:
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
    tab_idx += 1

    # Pace tab
    with tabs[tab_idx]:
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
    tab_idx += 1

    # Elevation tab
    with tabs[tab_idx]:
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
    tab_idx += 1

    # Heart rate tab
    with tabs[tab_idx]:
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
    tab_idx += 1

    # --- Splits Table tab ---
    with tabs[tab_idx]:
        st.markdown(f"#### {t('splits_table_title')}")
        if km_splits:
            import pandas as pd

            # Determine which km has the best 1km split
            best_1km_kms = set()
            if best_splits["1km"]:
                bs = best_splits["1km"]
                start_km = int(bs["start_km"])
                end_km = int(bs["end_km"])
                for k in range(start_km + 1, end_km + 2):  # +1 because splits are 1-indexed
                    best_1km_kms.add(k)

            table_rows = []
            for split in km_splits:
                row = {
                    "km": split["km"],
                    t("col_pace"): format_pace_short(split["pace"]),
                    t("col_gap"): format_pace_short(split["gap"]),
                    t("col_elev_change"): f"{split['elev_change']:+.1f}",
                    t("col_grade"): f"{split['grade_pct']:.1f}%",
                }
                if split["hr"] is not None:
                    row[t("col_hr")] = split["hr"]
                else:
                    row[t("col_hr")] = "-"
                table_rows.append(row)

            df_splits = pd.DataFrame(table_rows)

            # Highlight best 1km split rows
            def highlight_best(row):
                if row["km"] in best_1km_kms:
                    return ["background-color: #d4edda"] * len(row)
                return [""] * len(row)

            if best_1km_kms:
                styled = df_splits.style.apply(highlight_best, axis=1)
                st.dataframe(styled, use_container_width=True, hide_index=True)
            else:
                st.dataframe(df_splits, use_container_width=True, hide_index=True)
        else:
            st.info(t("no_pace_data"))
    tab_idx += 1

    # --- HR Zones tab (only if HR data exists) ---
    if metrics["heart_rates"]:
        with tabs[tab_idx]:
            st.markdown(f"#### {t('hr_zones_title')}")

            # Max HR input
            st.markdown(t("hr_zones_max_hr_explanation"))
            hr_input_method = st.radio(
                t("hr_zones_input_method"),
                [t("hr_zones_use_age"), t("hr_zones_use_manual")],
                horizontal=True,
            )

            if hr_input_method == t("hr_zones_use_age"):
                age = st.number_input(t("hr_zones_age_label"), min_value=10, max_value=100, value=30)
                user_max_hr = 220 - age
                st.caption(f"{t('hr_zones_estimated_max')}: **{user_max_hr} bpm**")
            else:
                user_max_hr = st.number_input(
                    t("hr_zones_manual_label"), min_value=100, max_value=250,
                    value=metrics["max_hr"] if metrics["max_hr"] else 190,
                )

            zones = compute_hr_zones(metrics["heart_rates"], user_max_hr)

            import pandas as pd

            zone_names = {
                1: t("hr_zone_1_name"),
                2: t("hr_zone_2_name"),
                3: t("hr_zone_3_name"),
                4: t("hr_zone_4_name"),
                5: t("hr_zone_5_name"),
            }
            zone_colors = {1: "#93c5fd", 2: "#86efac", 3: "#fde047", 4: "#fdba74", 5: "#fca5a5"}

            # Percentage breakdown table
            zone_table = []
            for z in zones:
                zone_table.append({
                    t("col_zone"): f"Z{z['zone']}",
                    t("col_zone_name"): zone_names[z["zone"]],
                    t("col_zone_range"): f"{z['min_pct']}–{z['max_pct']}% ({int(user_max_hr * z['min_pct'] / 100)}–{int(user_max_hr * z['max_pct'] / 100)} bpm)",
                    t("col_zone_pct"): f"{z['pct']}%",
                })
            df_zones = pd.DataFrame(zone_table)
            st.dataframe(df_zones, use_container_width=True, hide_index=True)

            # Horizontal stacked bar chart using st.html
            bar_parts = []
            for z in zones:
                if z["pct"] > 0:
                    color = zone_colors[z["zone"]]
                    bar_parts.append(
                        f'<div style="width:{z["pct"]}%;background:{color};height:40px;'
                        f'display:inline-flex;align-items:center;justify-content:center;'
                        f'font-size:12px;font-weight:bold;color:#333;">'
                        f'Z{z["zone"]} {z["pct"]}%</div>'
                    )

            bar_html = (
                '<div style="display:flex;width:100%;border-radius:8px;overflow:hidden;'
                'margin:10px 0;">' + "".join(bar_parts) + '</div>'
            )
            st.markdown(bar_html, unsafe_allow_html=True)

        tab_idx += 1

        # --- Pace vs HR Scatter tab ---
        with tabs[tab_idx]:
            st.markdown(f"#### {t('pace_vs_hr_title')}")
            if metrics["paces"] and metrics["heart_rates"]:
                import pandas as pd

                # Build per-km data with both pace and HR
                km_pace_hr = {}
                for p in metrics["paces"]:
                    km = int(p["dist"] / 1000)
                    if km not in km_pace_hr:
                        km_pace_hr[km] = {"paces": [], "hrs": []}
                    km_pace_hr[km]["paces"].append(p["pace"])

                for h in metrics["heart_rates"]:
                    km = int(h["dist"] / 1000)
                    if km in km_pace_hr:
                        km_pace_hr[km]["hrs"].append(h["hr"])

                scatter_data = []
                for km in sorted(km_pace_hr.keys()):
                    d = km_pace_hr[km]
                    if d["paces"] and d["hrs"]:
                        avg_pace = sum(d["paces"]) / len(d["paces"])
                        avg_hr = sum(d["hrs"]) / len(d["hrs"])
                        scatter_data.append({
                            t("col_hr"): round(avg_hr),
                            t("col_pace"): round(avg_pace, 2),
                            "km": km + 1,
                        })

                if scatter_data:
                    df_scatter = pd.DataFrame(scatter_data)
                    st.scatter_chart(
                        df_scatter,
                        x=t("col_hr"),
                        y=t("col_pace"),
                    )
                    st.caption(t("pace_vs_hr_note"))
                else:
                    st.info(t("no_pace_hr_data"))
            else:
                st.info(t("no_pace_hr_data"))
        tab_idx += 1

    # --- Download CSV ---
    st.markdown("---")
    csv_bytes = generate_csv_report(metrics, km_splits)
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
render_footer(libraries=["fitparse", "gpxpy", "folium", "streamlit-folium"], repo_name="kf-run-dash")
