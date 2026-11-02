"""Streamlit display for Step 3 (risk matrix)."""

import json

import pandas as pd
import streamlit as st

from advice_ai import generate_matrix_check
from export import RISK_PALETTE as _PALETTE
from risk_matrix import RiskMatrix, build_tables, generate_risk_matrix
from ui_common import cached, get_api_key, make_key, store


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


def _run_check(brief_dict: dict, matrix: RiskMatrix, api_key: str, check_key: str) -> None:
    """AI call 4. A failure only produces a warning: the matrix itself stays usable."""
    with st.spinner("Double-checking the ratings..."):
        try:
            store("matrix_check", check_key, generate_matrix_check(brief_dict, matrix, api_key))
        except Exception as exc:
            st.warning(f"The matrix was created, but the second-opinion check failed: {exc}")


def render_risk_matrix(brief) -> None:
    st.header("Step 3: Risk matrix")

    brief_dict = brief.to_dict()
    brief_key = json.dumps(brief_dict, sort_keys=True)

    if st.session_state.get("matrix_key") != brief_key:
        st.session_state.pop("matrix", None)

    if st.button("Generate risk matrix", type="primary"):
        api_key = st.session_state.get("openai_api_key")
        if not api_key:
            st.error("Enter your OpenAI API key in the sidebar and click 'Update API Key' first.")
            return
        with st.spinner("Assessing delivery methods..."):
            try:
                new_matrix = generate_risk_matrix(brief_dict, api_key)  # AI call 3
            except Exception as exc:
                st.error(f"Something went wrong generating the matrix: {exc}")
                return
        st.session_state.matrix = new_matrix
        st.session_state.matrix_key = brief_key
        _run_check(  # AI call 4, runs straight away
            brief_dict, new_matrix, api_key, make_key(brief_dict, new_matrix.model_dump())
        )

    matrix: RiskMatrix | None = st.session_state.get("matrix")
    if matrix is None:
        return

    styled, weights, weighted = _matrix_table(matrix)
    check_key = make_key(brief_dict, matrix.model_dump())

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

    check = cached("matrix_check", check_key)
    if check is None:
        if st.button("Run the second-opinion check"):  # only appears if the automatic check failed
            api_key = get_api_key()
            if api_key:
                _run_check(brief_dict, matrix, api_key, check_key)
                st.rerun()
    else:
        count = len(check.flags)
        label = (
            "Second-opinion check: no ratings flagged"
            if count == 0
            else f"Second-opinion check: {count} rating{'s' if count != 1 else ''} flagged"
        )
        with st.expander(label):
            st.write(check.verdict)
            risk_grid = build_tables(matrix)[0]
            for flag in check.flags:
                current = int(risk_grid.loc[flag.method, flag.criterion])
                st.markdown(
                    f"- **{flag.method}, {flag.criterion}:** rated {current}, "
                    f"the reviewer suggests {flag.suggested_risk}. {flag.concern}"
                )
            st.caption(
                "A second AI call reviewed the matrix. The table above is unchanged, so you can "
                "decide whether to agree with any flag."
            )

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