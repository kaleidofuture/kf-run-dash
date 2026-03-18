"""i18n module for KF apps — language switching between Japanese and English."""

import json
import os
import streamlit as st


def load_translations(lang: str) -> dict:
    """Load translation file for the given language code."""
    i18n_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "i18n")
    path = os.path.join(i18n_dir, f"{lang}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_lang() -> str:
    """Get the current language from session state."""
    if "lang" not in st.session_state:
        st.session_state.lang = "ja"
    return st.session_state.lang


def t(key: str) -> str:
    """Translate a key using the current language."""
    translations = load_translations(get_lang())
    return translations.get(key, key)


def lang_selector():
    """Render a language toggle in the sidebar."""
    current = get_lang()
    label = "🌐 English" if current == "ja" else "🌐 日本語"
    if st.sidebar.button(label, key="lang_toggle"):
        st.session_state.lang = "en" if current == "ja" else "ja"
        st.rerun()
