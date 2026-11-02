"""Streamlit sections for Step 4 (recommendation), Step 5 (ask a question) and Step 6 (download)."""

import streamlit as st

from advice_ai import (
    DISCLAIMER,
    answer_question,
    generate_contract_notes,
    generate_mitigation,
    generate_recommendation,
    generate_summary,
)
from export import build_blocks, to_docx, to_html, to_markdown
from risk_matrix import RiskMatrix, build_tables
from ui_common import cached, get_api_key, make_key, store


def _generate_notes(brief_dict, matrix, method, api_key, rec_key) -> None:
    """AI call 6, run for the top-ranked method."""
    with st.spinner(f"Preparing contract notes for {method}..."):
        try:
            store("contract_notes", rec_key, generate_contract_notes(brief_dict, matrix, method, api_key))
        except Exception as exc:
            st.warning(f"The recommendation worked, but the contract notes failed: {exc}")


def _generate_mitigation(brief_dict, matrix, method, api_key, rec_key) -> None:
    """AI call 7, run for the top-ranked method."""
    with st.spinner(f"Finding ways to reduce the main risks of {method}..."):
        try:
            store("mitigation", rec_key, generate_mitigation(brief_dict, matrix, method, api_key))
        except Exception as exc:
            st.warning(f"The recommendation worked, but the risk mitigation ideas failed: {exc}")


def render_advice(brief, matrix: RiskMatrix) -> None:
    brief_dict = brief.to_dict()
    ctx = make_key(brief_dict, matrix.model_dump())  # changes whenever answers or matrix change

    # ===== Step 4: recommendation + contract notes ==========================
    st.divider()
    st.header("Step 4: Recommendation")

    if st.button("Generate recommendation", type="primary"):
        api_key = get_api_key()
        if api_key:
            with st.spinner("Writing your recommendation..."):
                try:
                    new_rec = generate_recommendation(brief_dict, matrix, api_key)  # AI call 5
                except Exception as exc:
                    new_rec = None
                    st.error(f"Something went wrong generating the recommendation: {exc}")
            if new_rec is not None:
                store("recommendation", ctx, new_rec)
                new_key = make_key(ctx, new_rec.model_dump())
                top = new_rec.ranked[0].method
                _generate_notes(brief_dict, matrix, top, api_key, new_key)  # AI call 6
                _generate_mitigation(brief_dict, matrix, top, api_key, new_key)  # AI call 7

    rec = cached("recommendation", ctx)
    if rec is None:
        st.caption("Click the button to get a ranked recommendation and notes on the contract.")
        return

    rec_key = make_key(ctx, rec.model_dump())  # changes if the recommendation is regenerated
    top_method = rec.ranked[0].method

    mitigation = cached("mitigation", rec_key)

    # Only the headline and the ranking show at first. Everything else opens on click.
    st.markdown(f"### {rec.headline}")
    st.caption("Click a method to see why it suits you and its main drawback.")
    for i, ranked in enumerate(rec.ranked, start=1):
        label = f"{i}. {ranked.method}" + ("  (recommended)" if i == 1 else "")
        with st.expander(label, expanded=False):
            st.write(ranked.why_it_suits)
            st.caption(f"Main drawback: {ranked.main_drawback}")
            if i == 1:  # the deciding factors explain the top pick, so they live in its row
                st.markdown("**What decided it**")
                for factor in rec.deciding_factors:
                    st.markdown(f"- {factor}")
                st.caption(rec.matrix_alignment_note)

                st.markdown("**How to reduce its main risks**")
                if mitigation is None:
                    if st.button("Generate risk mitigation ideas"):  # only if the automatic call failed
                        api_key = get_api_key()
                        if api_key:
                            _generate_mitigation(brief_dict, matrix, top_method, api_key, rec_key)
                            st.rerun()
                else:
                    risk_grid = build_tables(matrix)[0]
                    for item in mitigation.items:
                        rating = int(risk_grid.loc[mitigation.method, item.criterion])
                        st.markdown(f"*{item.criterion}* (rated {rating}/5)")
                        for action in item.actions:
                            st.markdown(f"- {action}")
                    st.caption(mitigation.residual_note)

    notes = cached("contract_notes", rec_key)
    if notes is None:
        if st.button(f"Generate contract notes for {top_method}"):
            api_key = get_api_key()
            if api_key:
                _generate_notes(brief_dict, matrix, top_method, api_key, rec_key)
                st.rerun()
    else:
        with st.expander(f"Contract notes: {notes.method}", expanded=False):
            st.markdown("**Standard forms**")
            for form in notes.standard_forms:
                st.markdown(f"- {form}")
            st.markdown("**How risk is generally allocated**")
            st.write(notes.risk_allocation)
            st.markdown("**Topics to review closely**")
            for topic in notes.topics_to_review:
                st.markdown(f"- **{topic.topic}:** {topic.why_it_matters}")
            st.markdown("**Special conditions to consider**")
            for item in notes.special_conditions:
                st.markdown(f"- {item}")
            st.caption(notes.check_before_relying)
    st.caption(DISCLAIMER)

    # ===== Step 5: follow-up questions =======================================
    st.divider()
    st.header("Step 5: Ask a question")
    st.caption(
        "Ask about your results, for example: Why did design and construct score badly on design "
        "control? What would change if the budget weren't fixed?"
    )

    # Two containers fix the on-screen order: the conversation first, the question box under
    # it. st.chat_input is only pinned to the bottom of the screen when it sits directly on
    # the page; inside a container it stays here, under the Step 5 heading.
    conversation_box = st.container()
    input_box = st.container()
    with input_box:
        question = st.chat_input("Type your question here and press Enter...")

    history = cached("chat", rec_key) or []
    with conversation_box:
        for message in history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        if question:
            api_key = get_api_key()
            if api_key:
                new_history = history + [{"role": "user", "content": question}]
                with st.chat_message("user"):
                    st.markdown(question)
                with st.chat_message("assistant"):
                    with st.spinner("Thinking..."):
                        try:
                            answer = answer_question(  # AI call 9
                                brief_dict, matrix, rec, notes, new_history, api_key,
                                mitigation=mitigation,
                            )
                        except Exception as exc:
                            answer = None
                            st.error(f"Something went wrong answering that: {exc}")
                    if answer:
                        st.markdown(answer)
                        store("chat", rec_key, new_history + [{"role": "assistant", "content": answer}])

    # ===== Step 6: download summary ==========================================
    st.divider()
    st.header("Step 6: Download a summary")

    if st.button("Prepare summary"):
        api_key = get_api_key()
        if api_key:
            with st.spinner("Writing your summary..."):
                try:
                    store(  # AI call 10
                        "summary",
                        rec_key,
                        generate_summary(brief_dict, matrix, rec, notes, api_key, mitigation=mitigation),
                    )
                except Exception as exc:
                    st.error(f"Something went wrong writing the summary: {exc}")

    summary = cached("summary", rec_key)
    if summary is None:
        st.caption("A one-page plain-English summary you can download and share.")
        return

    blocks = build_blocks(summary, matrix, rec, notes)
    markdown = to_markdown(blocks)

    left, middle, right = st.columns(3)
    left.download_button(
        "Download Word (.docx)",
        data=to_docx(blocks),
        file_name="delivery_method_summary.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    middle.download_button(
        "Download web page (.html)",
        data=to_html(blocks),
        file_name="delivery_method_summary.html",
        mime="text/html",
    )
    right.download_button(
        "Download Markdown (.md)",
        data=markdown,
        file_name="delivery_method_summary.md",
        mime="text/markdown",
    )
    with st.expander("Preview", expanded=True):
        st.markdown(markdown)