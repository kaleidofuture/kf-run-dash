"""Shared footer component for KF apps."""

import streamlit as st
from pathlib import Path
from components.i18n import t


def render_footer(libraries: list[str] | None = None):
    """Render the app footer with about section and library credits.

    Args:
        libraries: List of library names used by this app.
    """
    st.markdown("---")

    with st.expander(t("about_title")):
        st.markdown(t("about_description"))

        st.markdown(f"**{t('pain_point_title')}**")
        st.markdown(t("pain_point_description"))

    if libraries:
        with st.expander(t("libraries_title")):
            for lib in libraries:
                st.markdown(f"- `{lib}`")

    app_name = Path(__file__).resolve().parent.parent.name
    issue_url = f"https://github.com/kaleidofuture/{app_name}/issues"

    st.markdown(
        f"""
        <div style="text-align:center; color:#aaa; font-size:0.8rem; margin-top:24px; padding:12px 0;">
            KaleidoFuture — Built with AI-driven development, powered by existing libraries
            <br>
            🐛 <a href="{issue_url}" target="_blank" style="color:#aaa;">{t('report_issue')}</a>
        </div>
        """,
        unsafe_allow_html=True,
    )
