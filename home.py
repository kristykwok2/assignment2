"""Project Delivery Method Selector (Australian construction law).

Run locally with:  streamlit run home.py

Flow (each step builds on the one before):
  1. Your project        - describe it for an AI form fill (AI call 1), then save your answers
  2. Check your answers  - AI review for contradictions and gaps (AI call 2)
  3. Risk matrix         - AI weights the objectives and rates each method (AI call 3)
  4. Recommendation      - ranked recommendation (AI call 5) + contract notes (AI call 6)
  5. Ask a question      - follow-up Q&A about the results (AI call 9)
  6. Download a summary  - one-page summary as Word/HTML/Markdown (AI call 10)
"""

import streamlit as st

from advice_view import render_advice
from intake_view import render_intake, render_review
from matrix_view import render_risk_matrix

st.set_page_config(page_title="Delivery Method Selector", page_icon="🏗️", layout="centered")

st.title("🏗️ Project Delivery Method Selector")
st.caption(
    "Tell us about your project, and an AI model helps you compare project delivery methods "
    "for an Australian construction project. This tool is an educational aid and is not legal advice."
)

# --- API key (required assignment snippet) ----------------------------------
if "openai_api_key" not in st.session_state:
    st.session_state.openai_api_key = None

def render_api_key_input():
    st.sidebar.header("Setup")
    api_key_input = st.sidebar.text_input("Enter your OpenAI API key:", type="password")
    update_button = st.sidebar.button("Update API Key")
    return api_key_input, update_button

# Save the key when the button is clicked. It is kept only in this browser session's
# memory (never written to disk or committed to GitHub).
api_key_input, update_button = render_api_key_input()
if update_button:
    if api_key_input.strip():
        st.session_state.openai_api_key = api_key_input.strip()
    else:
        st.sidebar.error("Please enter an API key first.")
if st.session_state.openai_api_key:
    st.sidebar.success("API key set for this session.")
else:
    st.sidebar.info("Your key is needed for the AI steps.")
# ---------------------------------------------------------------------------

brief = render_intake()  # Step 1 (AI call 1)

if brief is not None:
    st.divider()
    render_review(brief)  # Step 2 (AI call 2)

    st.divider()
    render_risk_matrix(brief)  # Step 3 (AI call 3)

    matrix = st.session_state.get("matrix")
    if matrix is not None:
        render_advice(brief, matrix)  # Steps 4-6 (AI calls 5, 6, 9, 10)