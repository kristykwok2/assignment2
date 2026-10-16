"""Step 2: use an OpenAI model to weight the criteria and score each delivery method, then
compute the weighted risk totals in plain Python.

Design choice: the AI makes the *judgements* (weights, per-cell risk ratings and
reasons). The *arithmetic* (weighted totals, ranking) is done in code so it is
reproducible and checkable.

No Streamlit imports here, so this module can be unit-tested on its own.
"""

import json
from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field, model_validator

from ai_client import structured_call
from methods import CRITERIA, DELIVERY_METHODS

# Structured Outputs doesn't accept min/max constraints, so 1-5 is expressed as a Literal.
Score = Literal[1, 2, 3, 4, 5]


# ---------------------------------------------------------------------------
# Schema the AI must return (also used to validate its output)
# ---------------------------------------------------------------------------
class CriterionWeight(BaseModel):
    criterion: str
    weight: Score = Field(description="1 = minor importance, 5 = critical to this project")
    reason: str = Field(description="One sentence linking the weight to the user's answers")


class RiskCell(BaseModel):
    method: str
    criterion: str
    risk: Score = Field(
        description="Risk to the principal if this method is used: 1 = very low, 5 = very high",
    )
    rationale: str = Field(description="One or two sentences, maximum 40 words")


class RiskMatrix(BaseModel):
    weights: list[CriterionWeight]
    cells: list[RiskCell]
    caveats: list[str] = Field(description="2-4 assumptions or limitations the user should know")

    @model_validator(mode="after")
    def _check_complete(self):
        expected_w = set(CRITERIA)
        got_w = {w.criterion for w in self.weights}
        if got_w != expected_w or len(self.weights) != len(expected_w):
            raise ValueError(f"weights must cover exactly these criteria once each: {sorted(expected_w)}")

        expected_cells = {(m, c) for m in DELIVERY_METHODS for c in CRITERIA}
        got_cells = [(x.method, x.criterion) for x in self.cells]
        if set(got_cells) != expected_cells or len(got_cells) != len(expected_cells):
            raise ValueError("cells must contain exactly one entry for every method x criterion pair")
        return self


# ---------------------------------------------------------------------------
# Prompting
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are assisting with an educational tool that helps choose a project \
delivery method for an Australian construction project. You are not giving legal advice.

Your job:
1. WEIGHT each criterion from 1 (minor) to 5 (critical) based on the user's answers. \
Higher importance ratings, fixed dates/budgets and similar constraints should push weights up.
2. RATE the risk to the principal of using each delivery method against each criterion, \
from 1 (very low risk) to 5 (very high risk), assuming the method is well administered.
3. Give a short rationale for every rating that refers to the user's actual answers where relevant.

Rules:
- Use ONLY the delivery methods and criteria supplied, with exactly the names given.
- Return one weight per criterion and one risk cell for EVERY method x criterion pair.
- Do not cite specific cases or statutory provisions. General references to standard forms \
named in the method descriptions are fine.
- Rate each method on its general characteristics in the Australian market; the weights are \
what personalise the result to the user.
- If the user's answers are in tension, say so in the caveats.
"""


def build_user_message(brief: dict) -> str:
    return (
        "USER'S PROJECT BRIEF (JSON):\n"
        f"{json.dumps(brief, indent=2)}\n\n"
        "DELIVERY METHODS:\n"
        + "\n".join(f"- {name}: {desc}" for name, desc in DELIVERY_METHODS.items())
        + "\n\nCRITERIA:\n"
        + "\n".join(f"- {name}: {desc}" for name, desc in CRITERIA.items())
        + "\n\nReturn the weights, one risk cell per method x criterion pair, and the caveats."
    )


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------
def generate_risk_matrix(brief: dict, api_key: str) -> RiskMatrix:
    """Ask the model for weights + scores (AI call 3).

    The schema forces the reply into a RiskMatrix, and our validator checks that every
    method x criterion pair is present exactly once. A bad reply is retried once.
    """
    return structured_call(
        api_key, SYSTEM_PROMPT, build_user_message(brief), RiskMatrix, max_tokens=8000
    )


# ---------------------------------------------------------------------------
# Scoring (pure Python/pandas - no AI)
# ---------------------------------------------------------------------------
def build_tables(matrix: RiskMatrix) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Return (risk grid, weights, weighted risk per method sorted best->worst).

    Weighted risk = sum(weight * risk) / sum(weights), so it stays on the 1-5 scale.
    LOWER is better.
    """
    risk = pd.DataFrame(index=list(DELIVERY_METHODS), columns=list(CRITERIA), dtype=float)
    for cell in matrix.cells:
        risk.loc[cell.method, cell.criterion] = cell.risk

    weights = pd.Series({w.criterion: w.weight for w in matrix.weights})[list(CRITERIA)]
    weighted = ((risk * weights).sum(axis=1) / weights.sum()).sort_values()
    return risk, weights, weighted