"""Streamlit display for Step 2 (risk matrix)."""

import json

import pandas as pd
import streamlit as st

from risk_matrix import RiskMatrix, build_tables, generate_risk_matrix

_PALETTE = {1: "#c8e6c9", 2: "#e6f2c2", 3: "#fff3b0", 4: "#ffd699", 5: "#f4a6a6"}


def _colour(value: float) -> str:
    if pd.isna(value):
        return ""
    return f"background-color: {_PALETTE[int(round(value))]}; color: #1a1a1a"


def _matrix_table(matrix: RiskMatrix):
    """Build the single colour-coded table: one row per method, one column per objective.

    Returns (styled table, weights, weighted overall risk).
    """
    risk, weights, weighted = build_tables(matrix)

    table = risk.loc[weighted.index].copy()  # lowest overall risk first
    table.columns = [f"{c} (weight {weights[c]})" for c in table.columns]
    table["Overall risk"] = weighted
    table.index.name = "Delivery method"

    formats = {col: "{:.0f}" for col in table.columns[:-1]}
    formats["Overall risk"] = "{:.1f}"
    return table.style.map(_colour).format(formats), weights, weighted


def render_risk_matrix(brief) -> None:
    st.header("Step 2: Risk matrix")

    brief_dict = brief.to_dict()
    brief_key = json.dumps(brief_dict, sort_keys=True)

    # Throw away an old matrix if the user has changed their answers.
    if st.session_state.get("matrix_key") != brief_key:
        st.session_state.pop("matrix", None)

    if st.button("Generate risk matrix", type="primary"):
        api_key = st.session_state.get("openai_api_key")
        if not api_key:
            st.error("Enter your OpenAI API key in the sidebar and click 'Update API Key' first.")
            return
        with st.spinner("Assessing delivery methods..."):
            try:
                st.session_state.matrix = generate_risk_matrix(brief_dict, api_key)
                st.session_state.matrix_key = brief_key
            except Exception as exc:
                st.error(f"Something went wrong generating the matrix: {exc}")
                return

    matrix: RiskMatrix | None = st.session_state.get("matrix")
    if matrix is None:
        return

    styled, weights, weighted = _matrix_table(matrix)

    # --- The matrix (first thing the user sees) ------------------------------
    st.dataframe(styled, width="stretch")
    st.caption(
        "Risk to you as principal: 1 = low (green), 5 = high (red). Lower is better, and methods "
        "are ordered from lowest to highest overall risk. The number next to each objective is "
        "how heavily it counts for your project (1-5)."
    )
    st.markdown(
        f"Lowest overall risk for your answers: **{weighted.index[0]}** ({weighted.iloc[0]:.1f}). "
        f"Highest: **{weighted.index[-1]}** ({weighted.iloc[-1]:.1f})."
    )

    # --- Detail, collapsed ---------------------------------------------------
    with st.expander("Why were the objectives weighted this way?"):
        st.dataframe(
            pd.DataFrame(
                {
                    "Weight (1-5)": weights,
                    "Why": {w.criterion: w.reason for w in matrix.weights},
                }
            ),
            width="stretch",
        )

    with st.expander("Assumptions and limitations"):
        for caveat in matrix.caveats:
            st.markdown(f"- {caveat}")

    st.caption(
        "AI-generated educational analysis. It is not legal advice and should be checked "
        "against the contract documents, current standard forms and applicable law."
    )