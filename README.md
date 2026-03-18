---
title: kf-run-dash
emoji: 🚀
colorFrom: green
colorTo: blue
sdk: streamlit
sdk_version: 1.44.1
app_file: app.py
pinned: false
---

# KF-RunDash

> GPX/FITファイルからランニングデータを分析・可視化するアプリ。

## The Problem

Runners want to analyze their data beyond what Strava offers — freely charting pace trends, heart rate zones, and elevation profiles with full control over their own data.

## How It Works

1. Upload a GPX or FIT file (exported from Garmin, Strava, Apple Watch, etc.)
2. View pace, heart rate, and elevation charts
3. See your route on an interactive Folium map
4. Check summary metrics (distance, time, pace, elevation gain, heart rate)
5. Download a CSV report for further analysis

## Libraries Used

- **fitparse** — Parse Garmin FIT files
- **gpxpy** — Parse GPX files
- **folium** — Interactive route map visualization
- **streamlit-folium** — Folium integration for Streamlit

## Development

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deployment

Hosted on [Hugging Face Spaces](https://huggingface.co/spaces/mitoi/kf-run-dash).

---

Part of the [KaleidoFuture AI-Driven Development Research](https://kaleidofuture.com) — proving that everyday problems can be solved with existing libraries, no AI model required.
