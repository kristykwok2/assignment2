import streamlit as st
from openai import OpenAI
from dotenv import load_dotenv

import json

import streamlit as st

from criteria import (
    COMPLEXITY,
    COMPLEXITY_DRIVERS,
    CONTROL,
    EXPERIENCE,
    IMPORTANCE,
    STAKEHOLDER_TYPES,
    ProjectBrief,
    validate,
)

st.set_page_config(page_title="Delivery Method Selector", page_icon="🏗️", layout="centered")

st.title("🏗️ Project Delivery Method Selector")
st.caption(
    "Step 1 of 3: tell us about your project's key objectives. "
    "This tool is an educational aid and is not legal advice."
)

# Keep the submitted answers across Streamlit reruns.
if "brief" not in st.session_state:
    st.session_state.brief = None

with st.form("objectives_form"):
    st.subheader("1. Timing")
    timing_importance = st.select_slider(
        "How important is early or on-time completion?", options=IMPORTANCE, value="Medium"
    )
    fixed_completion_date = st.checkbox("There is a fixed or non-negotiable completion date")
    fast_track_acceptable = st.checkbox(
        "Construction could start before the design is fully complete (fast-tracking)"
    )

    st.subheader("2. Cost")
    cost_certainty_importance = st.select_slider(
        "How important is price certainty before construction starts?",
        options=IMPORTANCE,
        value="Medium",
    )
    budget_fixed = st.checkbox("The budget is fixed (e.g. capped funding)")
    lowest_price_priority = st.checkbox("Achieving the lowest competitive price is a priority")

    st.subheader("3. Control over design")
    design_control_desired = st.select_slider(
        "How much control do you want over design details?", options=CONTROL, value="Some"
    )
    design_changes_expected = st.checkbox("Significant design changes are expected during delivery")

    st.subheader("4. Experience of the principal")
    principal_experience = st.select_slider(
        "How experienced is the principal with construction projects?",
        options=EXPERIENCE,
        value="Limited",
    )
    in_house_project_management = st.checkbox(
        "The principal has in-house project management / technical capability"
    )

    st.subheader("5. Other stakeholders")
    stakeholder_types = st.multiselect(
        "Which other stakeholders have an interest in the project?", STAKEHOLDER_TYPES
    )
    stakeholder_notes = st.text_area(
        "Anything else about stakeholder requirements? (optional)",
        placeholder="e.g. lender requires fixed-price contract; council needs staged handover",
    )

    st.subheader("6. Project complexity")
    complexity_level = st.select_slider(
        "Overall project complexity", options=COMPLEXITY, value="Moderate"
    )
    complexity_drivers = st.multiselect(
        "What contributes to the complexity?", COMPLEXITY_DRIVERS
    )

    submitted = st.form_submit_button("Save my answers", type="primary")

if submitted:
    brief = ProjectBrief(
        timing_importance=timing_importance,
        fixed_completion_date=fixed_completion_date,
        fast_track_acceptable=fast_track_acceptable,
        cost_certainty_importance=cost_certainty_importance,
        budget_fixed=budget_fixed,
        lowest_price_priority=lowest_price_priority,
        design_control_desired=design_control_desired,
        design_changes_expected=design_changes_expected,
        principal_experience=principal_experience,
        in_house_project_management=in_house_project_management,
        stakeholder_types=stakeholder_types,
        stakeholder_notes=stakeholder_notes,
        complexity_level=complexity_level,
        complexity_drivers=complexity_drivers,
    )
    st.session_state.brief = brief

brief = st.session_state.brief
if brief is not None:
    st.success("Answers saved.")
    for problem in validate(brief):
        st.warning(problem)

    with st.expander("Review your answers", expanded=True):
        st.json(brief.to_dict())

    st.download_button(
        "Download answers (JSON)",
        data=json.dumps(brief.to_dict(), indent=2),
        file_name="project_brief.json",
        mime="application/json",
    )

if "openai_api_key" not in st.session_state:
    st.session_state.openai_api_key = None

def render_api_key_input():
    st.sidebar.header("Setup")
    api_key_input = st.sidebar.text_input("Enter your OpenAI API key:", type="password")
    update_button = st.sidebar.button("Update API Key")
    return api_key_input, update_button