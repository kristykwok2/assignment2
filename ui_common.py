import hashlib
import json

import streamlit as st


def get_api_key() -> str | None:
    """Return the OpenAI key saved from the sidebar, or show an error and return None."""
    key = st.session_state.get("openai_api_key")
    if not key:
        st.error("Enter your OpenAI API key in the sidebar and click 'Update API Key' first.")
    return key


def make_key(*parts) -> str:
    """A short fingerprint of some data. Used to tell whether stored results are still current."""
    raw = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def cached(name: str, key: str):
    """Return the stored result called `name` if it was made for `key`, otherwise None."""
    stored = st.session_state.get(name)
    if stored and stored["key"] == key:
        return stored["value"]
    return None


def store(name: str, key: str, value) -> None:
    st.session_state[name] = {"key": key, "value": value}