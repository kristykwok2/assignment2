"""AI calls that happen after the risk matrix exists.

  Call 4 - generate_matrix_check:   independent second-opinion check of the matrix.
  Call 5 - generate_recommendation: ranked recommendation with trade-offs.
  Call 6 - generate_contract_notes: contract/risk-allocation notes for the top method.
  Call 7 - generate_mitigation:     ways to reduce the top method's highest risks.
  Call 9 - answer_question:         follow-up Q&A about the results.
  Call 10 - generate_summary:       one-page plain-English summary for download.

(Calls 1-3 are in intake_ai.py and risk_matrix.py.)

No Streamlit imports here, so this module can be unit-tested on its own.
"""

import json

from pydantic import BaseModel, Field, model_validator

from ai_client import chat_call, structured_call
from methods import CRITERIA, DELIVERY_METHODS
from risk_matrix import RiskMatrix, Score, build_tables

DISCLAIMER = (
    "AI-generated educational analysis. It is not legal advice and should be checked against "
    "the actual contract documents, current standard forms and the law in your jurisdiction."
)

_COMMON_RULES = """General rules:
- This is an educational tool, not legal advice. Write in plain English for a principal who is \
not a lawyer.
- Use ONLY the delivery methods supplied, with exactly the names given.
- Do not cite specific cases, statutes, section numbers or clause numbers.
- Do not invent facts about the user's project. Use their answers.
- The project's jurisdiction within Australia is not specified, so keep legal points general."""

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

class RatingFlag(BaseModel):
    method: str
    criterion: str
    suggested_risk: Score = Field(
        description="The rating you think is more accurate: 1 = very low risk, 5 = very high risk"
    )
    concern: str = Field(description="One sentence on why the current rating looks wrong")


class MatrixCheck(BaseModel):
    verdict: str = Field(
        description="One or two sentences: overall, do the weights and ratings fit the user's answers?"
    )
    flags: list[RatingFlag] = Field(
        description="Zero to four individual ratings that look wrong. Empty if the matrix looks reasonable."
    )

    @model_validator(mode="after")
    def _check_flags(self):
        if len(self.flags) > 4:
            raise ValueError("return at most four flags")
        for flag in self.flags:
            if flag.method not in DELIVERY_METHODS:
                raise ValueError(f"unknown method {flag.method!r}. Use exactly: {list(DELIVERY_METHODS)}")
            if flag.criterion not in CRITERIA:
                raise ValueError(f"unknown criterion {flag.criterion!r}. Use exactly: {list(CRITERIA)}")
        return self


CHECK_SYSTEM = f"""You are an independent reviewer. A different AI produced a risk matrix for a \
principal's Australian construction project, and you are given the matrix with its reasoning. \
Check it against the user's answers. Do not redo it.

Check that:
1. The objective weights follow from the user's answers (for example, a fixed completion date \
should not lead to a low weight for timing).
2. Each risk rating is plausible for that method's general characteristics, and the ratings are \
consistent with each other.
3. Each rationale actually supports its rating (for example, a rationale describing likely cost \
overruns should not sit beside a very low cost risk rating).

Flag only ratings you would change by at least one point and can justify in one sentence. Return \
at most four flags. If the matrix looks reasonable, return no flags and say so in the verdict. \
Do not flag a rating just because you would have chosen differently by a small margin.

{_COMMON_RULES}"""


def generate_matrix_check(brief: dict, matrix: RiskMatrix, api_key: str) -> MatrixCheck:
    """AI call 4: a separate model call that reviews the matrix against the user's answers."""
    user = (
        f"THE USER'S ANSWERS (JSON):\n{json.dumps(brief, indent=2)}\n\n"
        f"DELIVERY METHODS:\n{methods_to_text()}\n\n"
        f"{matrix_to_text(matrix, include_rationale=True)}"
    )
    check = structured_call(api_key, CHECK_SYSTEM, user, MatrixCheck, max_tokens=2500)
    risk, _, _ = build_tables(matrix)
    check.flags = [f for f in check.flags if int(risk.loc[f.method, f.criterion]) != f.suggested_risk]
    return check

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

class MitigationItem(BaseModel):
    criterion: str
    actions: list[str] = Field(description="Two or three practical actions, one short sentence each")


class Mitigation(BaseModel):
    method: str
    items: list[MitigationItem]
    residual_note: str = Field(description="One sentence on the risk that is likely to remain even so")

    @model_validator(mode="after")
    def _check_items(self):
        seen = [i.criterion for i in self.items]
        unknown = [c for c in seen if c not in CRITERIA]
        if unknown or len(seen) != len(set(seen)):
            raise ValueError(f"items must use each of these criteria at most once: {list(CRITERIA)}")
        return self


MITIGATION_SYSTEM = f"""You suggest practical ways for a principal to reduce the biggest risks of \
a chosen project delivery method on an Australian construction project. You are given the method, \
the user's answers, and the objectives where the risk matrix rated this method worst.

Give one entry for each objective listed, using its exact name. Each action must be something \
the principal can do: how the procurement or contract is set up, what to decide early, who to \
involve, or how to govern the project. You may suggest borrowing a feature of another listed \
delivery method, using its exact name. Tie actions to the user's answers where you can.

{_COMMON_RULES}"""


def generate_mitigation(brief: dict, matrix: RiskMatrix, method: str, api_key: str) -> Mitigation:
    """AI call 7: mitigation ideas for the method's highest-risk objectives."""
    focus = highest_risk_criteria(matrix, method, n=3)
    focus_text = "\n".join(f"- {c} (rated {v}/5)" for c, v in focus)
    user = (
        f"METHOD: {method}\n"
        f"METHOD DESCRIPTION: {DELIVERY_METHODS[method]}\n\n"
        f"OBJECTIVES TO ADDRESS (worst first):\n{focus_text}\n\n"
        f"OTHER DELIVERY METHODS:\n{methods_to_text()}\n\n"
        f"THE USER'S ANSWERS (JSON):\n{json.dumps(brief, indent=2)}"
    )
    result = structured_call(api_key, MITIGATION_SYSTEM, user, Mitigation, max_tokens=2500)
    result.method = method
    by_criterion = {i.criterion: i for i in result.items}
    result.items = [by_criterion[c] for c, _ in focus if c in by_criterion]
    if not result.items:
        raise RuntimeError("The AI did not give mitigation ideas for the requested objectives.")
    return result


def mitigation_to_text(mitigation: "Mitigation | None") -> str:
    if mitigation is None:
        return "(not generated)"
    lines = [f"Method: {mitigation.method}"]
    for item in mitigation.items:
        lines.append(f"- {item.criterion}: " + " ".join(item.actions))
    lines.append(mitigation.residual_note)
    return "\n".join(lines)

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

=== RISK MITIGATION IDEAS ===
{mitigation}
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
    mitigation: "Mitigation | None" = None,
) -> str:
    """AI call 9: answer the latest user message in `history`."""
    system = CHAT_SYSTEM_TEMPLATE.format(
        rules=_COMMON_RULES,
        brief=json.dumps(brief, indent=2),
        methods=methods_to_text(),
        matrix=matrix_to_text(matrix, include_rationale=True),
        recommendation=recommendation_to_text(rec),
        notes=notes_to_text(notes),
        mitigation=mitigation_to_text(mitigation),
    )
    return chat_call(api_key, system, history[-MAX_HISTORY_MESSAGES:])

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
    mitigation: "Mitigation | None" = None,
) -> Summary:
    user = (
        f"THE USER'S ANSWERS (JSON):\n{json.dumps(brief, indent=2)}\n\n"
        f"{matrix_to_text(matrix)}\n\n"
        f"RECOMMENDATION:\n{recommendation_to_text(rec)}\n\n"
        f"CONTRACT NOTES:\n{notes_to_text(notes)}\n\n"
        f"RISK MITIGATION IDEAS:\n{mitigation_to_text(mitigation)}"
    )
    summary = structured_call(api_key, SUMMARY_SYSTEM, user, Summary, max_tokens=2500)
    summary.recommended_method = rec.ranked[0].method  # keep consistent with the recommendation
    return summary