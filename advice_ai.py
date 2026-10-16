"""AI calls that happen after the risk matrix exists.

  Call 5 - generate_recommendation: ranked recommendation with trade-offs.
  Call 6 - generate_contract_notes: contract/risk-allocation notes for the top method.
  Call 9 - answer_question:         follow-up Q&A about the results.
  Call 10 - generate_summary:       one-page plain-English summary for download.

(Calls 1-3 are in intake_ai.py and risk_matrix.py.)

No Streamlit imports here, so this module can be unit-tested on its own.
"""

import json

from pydantic import BaseModel, Field, model_validator

from ai_client import chat_call, structured_call
from methods import DELIVERY_METHODS
from risk_matrix import RiskMatrix, build_tables

DISCLAIMER = (
    "AI-generated educational analysis. It is not legal advice and should be checked against "
    "the actual contract documents, current standard forms and the law in your jurisdiction."
)

# Rules repeated in every system prompt so the model stays within what the tool can support.
_COMMON_RULES = """General rules:
- This is an educational tool, not legal advice. Write in plain English for a principal who is \
not a lawyer.
- Use ONLY the delivery methods supplied, with exactly the names given.
- Do not cite specific cases, statutes, section numbers or clause numbers.
- Do not invent facts about the user's project. Use their answers.
- The project's jurisdiction within Australia is not specified, so keep legal points general."""


# ---------------------------------------------------------------------------
# Helpers that turn the matrix into text for prompts (pure Python, no AI)
# ---------------------------------------------------------------------------
def matrix_to_text(matrix: RiskMatrix, include_rationale: bool = False) -> str:
    risk, weights, weighted = build_tables(matrix)
    reasons = {w.criterion: w.reason for w in matrix.weights}

    lines = ["OBJECTIVE WEIGHTS (1 = minor, 5 = critical for this project):"]
    for criterion in weights.index:
        lines.append(f"- {criterion}: {weights[criterion]} ({reasons[criterion]})")

    lines += ["", "RISK RATINGS (1 = low risk, 5 = high risk), methods ordered lowest to highest overall risk:"]
    for method in weighted.index:
        cells = ", ".join(f"{c} {int(risk.loc[method, c])}" for c in risk.columns)
        lines.append(f"- {method} | overall {weighted[method]:.1f} | {cells}")

    if include_rationale:
        lines += ["", "RATIONALE BEHIND EACH RATING:"]
        for cell in matrix.cells:
            lines.append(f"- {cell.method} / {cell.criterion} (risk {cell.risk}): {cell.rationale}")

    if matrix.caveats:
        lines += ["", "CAVEATS FROM THE MATRIX:"] + [f"- {c}" for c in matrix.caveats]
    return "\n".join(lines)


def methods_to_text() -> str:
    return "\n".join(f"- {name}: {desc}" for name, desc in DELIVERY_METHODS.items())


def highest_risk_criteria(matrix: RiskMatrix, method: str, n: int = 2) -> list[tuple[str, int]]:
    """The n criteria where `method` has the highest risk rating (ties keep matrix order)."""
    risk, _, _ = build_tables(matrix)
    row = risk.loc[method].sort_values(ascending=False, kind="stable")
    return [(criterion, int(value)) for criterion, value in row.head(n).items()]


# ---------------------------------------------------------------------------
# Call 5: recommendation
# ---------------------------------------------------------------------------
class RankedMethod(BaseModel):
    method: str
    why_it_suits: str = Field(description="2-3 sentences in plain English, tied to the user's answers")
    main_drawback: str = Field(description="1-2 sentences on the biggest trade-off or risk")


class Recommendation(BaseModel):
    headline: str = Field(description="One sentence stating which method is recommended and the main reason")
    ranked: list[RankedMethod] = Field(description="Exactly three different methods, best first")
    deciding_factors: list[str] = Field(
        description="3-4 short points naming the user's answers that most influenced the ranking"
    )
    matrix_alignment_note: str = Field(
        description="One or two sentences: does this ranking match the risk matrix order? If not, why not?"
    )

    @model_validator(mode="after")
    def _check_ranked(self):
        names = [r.method for r in self.ranked]
        if len(names) != 3 or len(set(names)) != 3:
            raise ValueError("ranked must contain exactly three different methods")
        unknown = [n for n in names if n not in DELIVERY_METHODS]
        if unknown:
            raise ValueError(f"unknown delivery methods: {unknown}. Use exactly: {list(DELIVERY_METHODS)}")
        return self


RECOMMEND_SYSTEM = f"""You are advising a principal on which project delivery method best suits \
their Australian construction project. You are given their answers and a risk matrix that was \
already produced (lower risk is better).

Rank the three best-suited methods. Base the ranking on the user's answers and the matrix. You may \
depart from the matrix order if the user's answers justify it, but then you must say so and explain \
why in matrix_alignment_note.

{_COMMON_RULES}"""


def generate_recommendation(brief: dict, matrix: RiskMatrix, api_key: str) -> Recommendation:
    """AI call 5: ranked recommendation."""
    user = (
        f"THE USER'S ANSWERS (JSON):\n{json.dumps(brief, indent=2)}\n\n"
        f"DELIVERY METHODS:\n{methods_to_text()}\n\n"
        f"{matrix_to_text(matrix)}"
    )
    return structured_call(api_key, RECOMMEND_SYSTEM, user, Recommendation, max_tokens=3000)


# ---------------------------------------------------------------------------
# Call 6: contract notes for the top method
# ---------------------------------------------------------------------------
class ClauseTopic(BaseModel):
    topic: str = Field(description="Short name of the contract topic, e.g. 'Latent conditions'")
    why_it_matters: str = Field(description="1-2 sentences on why it matters under this delivery method")


class ContractNotes(BaseModel):
    method: str
    standard_forms: list[str] = Field(
        description="Standard forms named in the method description, or one entry saying there is no "
        "widely used Australian standard form and agreements are usually bespoke"
    )
    risk_allocation: str = Field(
        description="3-5 sentences on how design, cost, time and ground/site risk is generally allocated "
        "between principal and contractor under this method"
    )
    topics_to_review: list[ClauseTopic] = Field(description="4-6 contract topics the principal should look at closely")
    special_conditions: list[str] = Field(
        description="3-5 short suggestions for special conditions or drafting points to consider"
    )
    check_before_relying: str = Field(
        description="One or two sentences telling the reader what to verify before relying on these notes"
    )


NOTES_SYSTEM = f"""You write short general notes about how contracts for a chosen project delivery \
method usually allocate risk in Australia, to help a principal prepare for a conversation with \
their lawyer. You are given the method, the user's answers, and the areas where the risk matrix \
rated this method as highest risk for them.

Tie the topics to those high-risk areas and to the user's answers where you can.

Standard forms: name a form ONLY if it appears in the method description you are given. If none \
is named there, say there is no widely used Australian standard form and agreements are usually \
bespoke. Never guess form numbers or clause numbers.

{_COMMON_RULES}"""


def generate_contract_notes(brief: dict, matrix: RiskMatrix, method: str, api_key: str) -> ContractNotes:
    """AI call 6: contract and risk-allocation notes for `method`."""
    focus = ", ".join(f"{c} (rated {v}/5)" for c, v in highest_risk_criteria(matrix, method))
    user = (
        f"METHOD: {method}\n"
        f"METHOD DESCRIPTION: {DELIVERY_METHODS[method]}\n\n"
        f"HIGHEST-RISK AREAS FOR THIS METHOD ACCORDING TO THE MATRIX: {focus}\n\n"
        f"THE USER'S ANSWERS (JSON):\n{json.dumps(brief, indent=2)}"
    )
    notes = structured_call(api_key, NOTES_SYSTEM, user, ContractNotes, max_tokens=3000)
    notes.method = method  # make sure the label always matches what we asked about
    return notes


# ---------------------------------------------------------------------------
# Call 9: follow-up questions
# ---------------------------------------------------------------------------
CHAT_SYSTEM_TEMPLATE = """You answer follow-up questions from a principal about the results of an \
educational tool that compares project delivery methods for an Australian construction project. \
Everything the tool produced is below. Ground your answers in it.

How to answer:
- Be concise: usually 2-5 sentences, longer only if the question needs it.
- If asked why something was rated or ranked a certain way, use the ratings and rationale below.
- If asked about something the results don't cover, you may give brief general background, but \
say it goes beyond the tool's results.
- If the question needs jurisdiction-specific or case-specific legal advice, say so and suggest \
speaking to a construction lawyer.
- If the user wants different results, tell them to change their answers in Step 1 and regenerate.
- Stay on the topic of project delivery methods and this project.

{rules}

=== THE USER'S ANSWERS ===
{brief}

=== DELIVERY METHODS ===
{methods}

=== RISK MATRIX ===
{matrix}

=== RECOMMENDATION ===
{recommendation}

=== CONTRACT NOTES ===
{notes}
"""

MAX_HISTORY_MESSAGES = 12


def recommendation_to_text(rec: Recommendation) -> str:
    lines = [rec.headline]
    for i, r in enumerate(rec.ranked, 1):
        lines.append(f"{i}. {r.method}: {r.why_it_suits} Main drawback: {r.main_drawback}")
    lines.append("Deciding factors: " + "; ".join(rec.deciding_factors))
    lines.append(rec.matrix_alignment_note)
    return "\n".join(lines)


def notes_to_text(notes: ContractNotes | None) -> str:
    if notes is None:
        return "(not generated)"
    lines = [f"Method: {notes.method}", "Standard forms: " + "; ".join(notes.standard_forms), notes.risk_allocation]
    lines += [f"- {t.topic}: {t.why_it_matters}" for t in notes.topics_to_review]
    lines += ["Special conditions: " + "; ".join(notes.special_conditions)]
    return "\n".join(lines)


def answer_question(
    brief: dict,
    matrix: RiskMatrix,
    rec: Recommendation,
    notes: ContractNotes | None,
    history: list[dict],
    api_key: str,
) -> str:
    """AI call 9: answer the latest user message in `history`."""
    system = CHAT_SYSTEM_TEMPLATE.format(
        rules=_COMMON_RULES,
        brief=json.dumps(brief, indent=2),
        methods=methods_to_text(),
        matrix=matrix_to_text(matrix, include_rationale=True),
        recommendation=recommendation_to_text(rec),
        notes=notes_to_text(notes),
    )
    return chat_call(api_key, system, history[-MAX_HISTORY_MESSAGES:])


# ---------------------------------------------------------------------------
# Call 10: downloadable summary
# ---------------------------------------------------------------------------
class Summary(BaseModel):
    title: str = Field(description="A short title such as 'Delivery method summary: <project type>'")
    project_overview: str = Field(description="2-3 sentences describing the project and its priorities")
    recommended_method: str
    reasons: list[str] = Field(description="3-4 short bullet points on why this method is recommended")
    runner_up_note: str = Field(description="1-2 sentences on the second-ranked method and when it might be better")
    risks_to_manage: list[str] = Field(description="3-5 short bullet points on the main risks to manage")
    contract_points: list[str] = Field(description="3-5 short bullet points from the contract notes")
    next_steps: list[str] = Field(description="3-5 practical next steps for the principal")


SUMMARY_SYSTEM = f"""You write a one-page plain-English summary of the results of an educational \
tool that compares project delivery methods for an Australian construction project. The reader is \
the principal, who may share it with colleagues or a lawyer. Use ONLY the material provided: do \
not add new analysis or change the recommendation.

{_COMMON_RULES}"""


def generate_summary(
    brief: dict,
    matrix: RiskMatrix,
    rec: Recommendation,
    notes: ContractNotes | None,
    api_key: str,
) -> Summary:
    """AI call 10: structured one-page summary."""
    user = (
        f"THE USER'S ANSWERS (JSON):\n{json.dumps(brief, indent=2)}\n\n"
        f"{matrix_to_text(matrix)}\n\n"
        f"RECOMMENDATION:\n{recommendation_to_text(rec)}\n\n"
        f"CONTRACT NOTES:\n{notes_to_text(notes)}"
    )
    summary = structured_call(api_key, SUMMARY_SYSTEM, user, Summary, max_tokens=2500)
    summary.recommended_method = rec.ranked[0].method  # keep consistent with the recommendation
    return summary