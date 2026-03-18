"""Shared header component for KF apps."""

import streamlit as st
from components.i18n import t, lang_selector


def render_header():
    """Render the app header with KF branding and language toggle."""
    lang_selector()

    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">
            <span style="font-size:1.6rem; font-weight:700; color:#4A90D9;">KF</span>
            <span style="font-size:1.4rem; font-weight:600;">{t('app_name')}</span>
        </div>
        <p style="color:#666; margin-top:0;">{t('app_tagline')}</p>
        <hr style="margin:12px 0 24px 0; border:none; border-top:1px solid #eee;">
        """,
        unsafe_allow_html=True,
    )
