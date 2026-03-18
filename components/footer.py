"""Shared footer component for KF apps."""

import streamlit as st
from components.i18n import t


def render_footer(libraries: list[str] | None = None, repo_name: str = ""):
    """Render the app footer with about section and library credits.

    Args:
        libraries: List of library names used by this app.
        repo_name: GitHub repository name (e.g. 'kf-meal-rescue').
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

    issue_url = "https://docs.google.com/forms/d/e/1FAIpQLSfAAbh5M_aJAHYCNsFFs4JqvfBx9J3m0YGuO9juxOpdjfHNWA/viewform"

    issue_html = f'<br>🐛 <a href="{issue_url}" target="_blank" style="color:#aaa;">{t("report_issue")}</a>' if issue_url else ""

    st.markdown(
        f"""
        <div style="text-align:center; color:#aaa; font-size:0.8rem; margin-top:24px; padding:12px 0;">
            KaleidoFuture — Built with AI-driven development
            {issue_html}
        </div>
        """,
        unsafe_allow_html=True,
    )
