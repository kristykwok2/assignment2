import json
from dataclasses import fields
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ai_client import structured_call
from criteria import (
    COMPLEXITY,
    COMPLEXITY_DRIVERS,
    CONTROL,
    EXPERIENCE,
    IMPORTANCE,
    STAKEHOLDER_TYPES,
    QUESTION_LABELS,
    ProjectBrief,
)
ImportanceT = Literal[tuple(IMPORTANCE)]  # type: ignore[valid-type]
ControlT = Literal[tuple(CONTROL)]  # type: ignore[valid-type]
ExperienceT = Literal[tuple(EXPERIENCE)]  # type: ignore[valid-type]
ComplexityT = Literal[tuple(COMPLEXITY)]  # type: ignore[valid-type]
StakeholderT = Literal[tuple(STAKEHOLDER_TYPES)]  # type: ignore[valid-type]
DriverT = Literal[tuple(COMPLEXITY_DRIVERS)]  # type: ignore[valid-type]

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

class Inconsistency(BaseModel):
    conflict: str = Field(description="One short sentence naming the two answers that conflict")
    why_it_matters: str = Field(
        description="One or two sentences on why this matters when choosing a delivery method"
    )
    potential_fix: str = Field(
        description="One sentence on how the user could resolve it, by deciding which matters more "
        "or changing one of the two answers"
    )


class AnswerReview(BaseModel):
    inconsistencies: list[Inconsistency] = Field(
        description="Zero to five items, most important first. Empty if the answers are consistent."
    )

    @model_validator(mode="after")
    def _check_items(self):
        if len(self.inconsistencies) > 5:
            raise ValueError("return at most five inconsistencies")
        self.inconsistencies = [i for i in self.inconsistencies if i.conflict.strip()]
        return self


REVIEW_SYSTEM = """You check the answers a user gave on an intake form about an Australian \
construction project, before a tool compares project delivery methods for them. You are not \
giving legal advice and you must not recommend a delivery method.

Your only job is to list inconsistencies: pairs of answers that pull against each other. For \
example, wanting full design control while accepting fast-tracking, or a fixed budget while \
expecting significant design changes. Also include anything in the free-text stakeholder notes \
that contradicts the other answers.

Rules:
- For each item, 'conflict' is one short sentence naming the two answers that conflict,
  in plain English.
- 'why_it_matters' is one or two sentences (about 35 words at most) on why the
  conflict matters when choosing a delivery method.
- 'potential_fix' must be one short, practical sentence (maximum 25 words).
- Speak directly to the person completing the form. Always use "you" and "your",
  never "the user", "the principal" or third-person language.
- Use simple, everyday English. Avoid academic, legalistic or overly formal language.
- Make suggestions sound natural and helpful, not like instructions or criticism.
- Refer to the relevant section using its exact heading from QUESTION_LABELS.
- Avoid unnecessarily repeating section headings or using phrases like
  "in the [section] section".
- Do not use technical terms unless absolutely necessary.
- When suggesting an answer to change, ALWAYS refer to one of
  the six user-facing section names supplied in QUESTION_LABELS.
- Use only these names: Timing, Cost, Control over design,
  Experience of the principal, Other stakeholders, and Project complexity.
- NEVER use internal Python field names, JSON keys, variable names
  or technical identifiers in any user-facing response.
- Refer to the relevant section by its heading, rather than its
  individual question or stored field name.
- Do not list gaps or missing information, and do not ask questions.
- Do not invent facts about the project, and do not flag a combination that is
  merely unusual.
- Maximum five items, most important first. If the answers are consistent,
  return an empty list."""

def review_brief(brief: dict, api_key: str) -> AnswerReview:
    user = (
        f"USER-FACING QUESTION LABELS:\n"
        f"{json.dumps(QUESTION_LABELS, indent=2)}\n\n"
        f"THE USER'S ANSWERS (JSON):\n"
        f"{json.dumps(brief, indent=2)}"
    )

    return structured_call(
        api_key,
        REVIEW_SYSTEM,
        user,
        AnswerReview,
        max_tokens=2500
    )