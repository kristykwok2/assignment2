
import streamlit as st
import hmac

from advice_view import render_advice
from intake_view import render_intake, render_review
from matrix_view import render_risk_matrix


def check_password():
    """Display a password screen and check the entered password."""

    if st.session_state.get("authenticated", False):
        return True

    st.title("Project Delivery Model Selector")
    st.write("Please enter the password to access the tool.")

    password = st.text_input("Password", type="password")

    if st.button("Log in"):
        correct_password = st.secrets["APP_PASSWORD"]

        if hmac.compare_digest(password, correct_password):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password. Please try again.")

    return False


st.set_page_config(
    page_title="Delivery Method Selector",
    page_icon="🏗️",
    layout="centered"
)

# PASSWORD CHECK
if check_password():

    st.title("🏗️ Project Delivery Method Selector")
    st.caption(
        "Tell us about your project, and an AI model helps you compare "
        "project delivery methods for an Australian construction project. "
        "This tool is an educational aid and is not legal advice."
    )

    if "openai_api_key" not in st.session_state:
        st.session_state.openai_api_key = None

    def render_api_key_input():
        st.sidebar.header("Setup")
        api_key_input = st.sidebar.text_input(
            "Enter your OpenAI API key:",
            type="password"
        )
        update_button = st.sidebar.button("Update API Key")
        return api_key_input, update_button

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

    brief = render_intake()

    if brief is not None:
        st.divider()
        render_review(brief)

        st.divider()
        render_risk_matrix(brief)

        matrix = st.session_state.get("matrix")

        if matrix is not None:
            render_advice(brief, matrix)
