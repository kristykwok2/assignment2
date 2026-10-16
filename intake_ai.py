"""AI calls that happen around the intake form.

  Call 1 - extract_brief: turn a free-text project description into form answers.
  Call 2 - review_brief:  check the saved answers for tensions, gaps and open questions.

No Streamlit imports here, so this module can be unit-tested on its own.
"""

import json
from dataclasses import fields
from typing import Literal

from pydantic import BaseModel, Field

from ai_client import structured_call
from criteria import (
    COMPLEXITY,
    COMPLEXITY_DRIVERS,
    CONTROL,
    EXPERIENCE,
    IMPORTANCE,
    STAKEHOLDER_TYPES,
    ProjectBrief,
)

# The option lists in criteria.py are the single source of truth. Turning them into
# Literal types means the model can only return values the form actually offers.
ImportanceT = Literal[tuple(IMPORTANCE)]  # type: ignore[valid-type]
ControlT = Literal[tuple(CONTROL)]  # type: ignore[valid-type]
ExperienceT = Literal[tuple(EXPERIENCE)]  # type: ignore[valid-type]
ComplexityT = Literal[tuple(COMPLEXITY)]  # type: ignore[valid-type]
StakeholderT = Literal[tuple(STAKEHOLDER_TYPES)]  # type: ignore[valid-type]
DriverT = Literal[tuple(COMPLEXITY_DRIVERS)]  # type: ignore[valid-type]


# ---------------------------------------------------------------------------
# Call 1: free text -> form answers
# ---------------------------------------------------------------------------
class IntakeResult(BaseModel):
    """Mirrors ProjectBrief field-for-field, plus a list of assumptions."""

    timing_importance: ImportanceT
    fixed_completion_date: bool
    fast_track_acceptable: bool = Field(
        description="True only if the description says construction can start before design is complete"
    )

    cost_certainty_importance: ImportanceT
    budget_fixed: bool
    lowest_price_priority: bool

    design_control_desired: ControlT
    design_changes_expected: bool

    principal_experience: ExperienceT
    in_house_project_management: bool

    stakeholder_types: list[StakeholderT]
    stakeholder_notes: str = Field(
        description="Very short note on specific stakeholder requirements mentioned, or an empty string"
    )

    complexity_level: ComplexityT
    complexity_drivers: list[DriverT]

    assumptions: list[str] = Field(
        description="Up to 5 short notes on answers you had to guess or leave at a neutral default"
    )


EXTRACT_SYSTEM = """You help a student-built educational tool pre-fill an intake form about an \
Australian construction project. Read the project description and complete the form.

Rules:
- Use only what the description says or clearly implies. Do not invent facts.
- The 'principal' is the client or owner commissioning the project.
- Where the description says nothing, use these neutral defaults: importance fields "Medium", \
design control "Some", principal experience "Limited", complexity "Moderate", every yes/no \
field false, and empty lists.
- In 'assumptions', list the most important answers you guessed or left at a default, in plain \
English (for example "Assumed the principal is only moderately experienced because the \
description doesn't say"). Maximum 5.
- Keep stakeholder_notes to one short sentence, or an empty string."""


def extract_brief(description: str, api_key: str) -> IntakeResult:
    """AI call 1: fill in the intake form from a free-text description."""
    user = f"PROJECT DESCRIPTION:\n{description.strip()}"
    return structured_call(api_key, EXTRACT_SYSTEM, user, IntakeResult)


def intake_to_brief(result: IntakeResult) -> ProjectBrief:
    """Copy the form-answer fields of an IntakeResult into a ProjectBrief."""
    return ProjectBrief(**{f.name: getattr(result, f.name) for f in fields(ProjectBrief)})


# ---------------------------------------------------------------------------
# Call 2: review of the saved answers
# ---------------------------------------------------------------------------
class AnswerIssue(BaseModel):
    kind: Literal["Inconsistency", "Gap", "Note"]
    message: str = Field(description="One or two sentences in plain English")
    suggestion: str = Field(description="What the user could change or clarify")


class AnswerReview(BaseModel):
    summary: str = Field(
        description="One or two sentences: are the answers coherent and complete enough for the analysis?"
    )
    issues: list[AnswerIssue] = Field(
        description="Zero to five issues, most important first. Empty if there are none."
    )
    clarifying_questions: list[str] = Field(
        description="Zero to three questions whose answers would most improve the analysis"
    )


REVIEW_SYSTEM = """You review the answers a user gave on an intake form about an Australian \
construction project, before a tool compares project delivery methods for them. You are not \
giving legal advice and you must not recommend a delivery method yet.

Look for:
- Inconsistencies between answers (for example wanting full design control while accepting \
fast-tracking, or a fixed budget while expecting significant design changes).
- Gaps: things that matter for choosing a delivery method but are missing or look like untouched \
defaults (for example complexity drivers selected while overall complexity is Low).
- Anything in the free-text stakeholder notes that the other answers don't reflect.

Be specific and brief. Do not invent facts about the project. If the answers are coherent, say so \
and return an empty list of issues."""


def review_brief(brief: dict, api_key: str) -> AnswerReview:
    """AI call 2: sanity-check the user's answers."""
    user = f"THE USER'S ANSWERS (JSON):\n{json.dumps(brief, indent=2)}"
    return structured_call(api_key, REVIEW_SYSTEM, user, AnswerReview, max_tokens=2500)