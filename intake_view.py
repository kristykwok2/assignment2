import json
from dataclasses import fields

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
from intake_ai import extract_brief, intake_to_brief, review_brief
from ui_common import cached, get_api_key, make_key, store

BRIEF_FIELDS = [f.name for f in fields(ProjectBrief)]


def _key(name: str) -> str:
    """Session-state key of the form widget for a ProjectBrief field."""
    return f"in_{name}"


def _init_defaults() -> None:
    for name, value in ProjectBrief().to_dict().items():
        st.session_state.setdefault(_key(name), value)


def _fill_from_description() -> None:
    """AI call 1: read the free-text description and set the form widgets."""
    description = st.session_state.get("project_description", "").strip()
    if not description:
        st.warning("Write a short description of your project first.")
        return
    api_key = get_api_key()
    if not api_key:
        return
    with st.spinner("Reading your description..."):
        try:
            result = extract_brief(description, api_key)
        except Exception as exc:
            st.error(f"Something went wrong filling in the form: {exc}")
            return

    for name, value in intake_to_brief(result).to_dict().items():
        st.session_state[_key(name)] = value
    st.session_state.brief = None  
    st.session_state.intake_notes = list(result.assumptions)


def render_intake() -> ProjectBrief | None:
    """Step 1. Returns the saved ProjectBrief, or None if the user hasn't saved answers yet."""
    st.header("Step 1: Your project")
    _init_defaults()
    if "brief" not in st.session_state:
        st.session_state.brief = None

    with st.expander("Shortcut: describe your project and let AI fill in the form", expanded=True):
        st.text_area(
            "Describe your project in a few sentences",
            key="project_description",
            height=130,
            placeholder=(
                "e.g. A council wants a new $25m community aquatic centre. It must open before "
                "summer 2028, the budget is capped by a state grant, and residents and the "
                "funding body will both want a say. The council has built little before."
            ),
        )
        if st.button("Fill in the form for me"):
            _fill_from_description()

    notes = st.session_state.get("intake_notes")
    if notes is not None:
        if notes:
            st.info(
                "The AI filled in the form below. **Please check it before saving.** "
                "It had to assume:\n" + "\n".join(f"- {n}" for n in notes)
            )
        else:
            st.info("The AI filled in the form below. Please check the answers before saving.")

    with st.form("objectives_form"):
        st.subheader("1. Timing")
        st.select_slider(
            "How important is early or on-time completion?",
            options=IMPORTANCE,
            key=_key("timing_importance"),
        )
        st.checkbox(
            "There is a fixed or non-negotiable completion date", key=_key("fixed_completion_date")
        )
        st.checkbox(
            "Construction could start before the design is fully complete (fast-tracking)",
            key=_key("fast_track_acceptable"),
        )

        st.subheader("2. Cost")
        st.select_slider(
            "How important is price certainty before construction starts?",
            options=IMPORTANCE,
            key=_key("cost_certainty_importance"),
        )
        st.checkbox("The budget is fixed (e.g. capped funding)", key=_key("budget_fixed"))
        st.checkbox(
            "Achieving the lowest competitive price is a priority", key=_key("lowest_price_priority")
        )

        st.subheader("3. Control over design")
        st.select_slider(
            "How much control do you want over design details?",
            options=CONTROL,
            key=_key("design_control_desired"),
        )
        st.checkbox(
            "Significant design changes are expected during delivery",
            key=_key("design_changes_expected"),
        )

        st.subheader("4. Experience of the principal")
        st.select_slider(
            "How experienced is the principal with construction projects?",
            options=EXPERIENCE,
            key=_key("principal_experience"),
        )
        st.checkbox(
            "The principal has in-house project management / technical capability",
            key=_key("in_house_project_management"),
        )

        st.subheader("5. Other stakeholders")
        st.multiselect(
            "Which other stakeholders have an interest in the project?",
            STAKEHOLDER_TYPES,
            key=_key("stakeholder_types"),
        )
        st.text_area(
            "Anything else about stakeholder requirements? (optional)",
            placeholder="e.g. lender requires fixed-price contract; council needs staged handover",
            key=_key("stakeholder_notes"),
        )

        st.subheader("6. Project complexity")
        st.select_slider("Overall project complexity", options=COMPLEXITY, key=_key("complexity_level"))
        st.multiselect(
            "What contributes to the complexity?",
            COMPLEXITY_DRIVERS,
            key=_key("complexity_drivers"),
        )

        submitted = st.form_submit_button("Save my answers", type="primary")

    if submitted:
        values = {}
        for name in BRIEF_FIELDS:
            value = st.session_state[_key(name)]
            values[name] = list(value) if isinstance(value, list) else value
        st.session_state.brief = ProjectBrief(**values)

    brief = st.session_state.brief
    if brief is not None:
        st.success("Answers saved.")
        with st.expander("Your saved answers", expanded=False):
            st.json(brief.to_dict())
            st.download_button(
                "Download answers (JSON)",
                data=json.dumps(brief.to_dict(), indent=2),
                file_name="project_brief.json",
                mime="application/json",
            )
    return brief


def render_review(brief: ProjectBrief) -> None:
    """Step 2. Rule-based warnings, plus an AI review (AI call 2) on request."""
    st.header("Step 2: Check your answers")

    for problem in validate(brief):  
        st.markdown(f"⚠️ {problem}")

    brief_dict = brief.to_dict()
    key = make_key(brief_dict)

    review = cached("review", key)
    failure = cached("review_error", key)
    retry = st.button("Try the AI review again") if failure else False

    if review is None and (failure is None or retry):
        api_key = st.session_state.get("openai_api_key")
        if not api_key:
            st.info("Add your OpenAI API key in the sidebar and the AI will review your answers here.")
            return
        with st.spinner("Reviewing your answers..."):
            try:
                review = review_brief(brief_dict, api_key)
                store("review", key, review)
            except Exception as exc:
                failure = str(exc)
                store("review_error", key, failure)
        if retry and review is not None:
            st.rerun()  

    if review is None:
        st.warning(
            f"The AI review didn't work this time ({failure}). You can still continue to Step 3."
        )
        return

    for item in review.inconsistencies:
        st.markdown(f"⚠️ {item}")
    if review.inconsistencies:
        st.caption("To change an answer, edit the form in Step 1 and save again.")
    elif not validate(brief):
        st.success("No inconsistencies found.")