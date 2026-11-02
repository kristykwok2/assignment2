from dataclasses import dataclass, field, asdict

IMPORTANCE = ["Low", "Medium", "High", "Critical"]
CONTROL = ["Minimal", "Some", "Substantial", "Full"]
EXPERIENCE = ["None", "Limited", "Moderate", "Extensive"]
COMPLEXITY = ["Low", "Moderate", "High", "Very high"]

STAKEHOLDER_TYPES = [
    "Funding body / lender",
    "Government agency / regulator",
    "Tenants or end users",
    "Community / local residents",
    "Joint venture partners",
    "Heritage or environmental bodies",
    "Other",
]

COMPLEXITY_DRIVERS = [
    "Novel or specialised technology",
    "Difficult or uncertain site conditions",
    "Many interfaces between trades/contractors",
    "Staged or occupied-site works",
    "Heavy regulatory approvals",
    "Design likely to change during delivery",
]

@dataclass
class ProjectBrief:
    timing_importance: str = "Medium"
    fixed_completion_date: bool = False
    fast_track_acceptable: bool = False  # can construction start before design is finished?

    cost_certainty_importance: str = "Medium"
    budget_fixed: bool = False
    lowest_price_priority: bool = False

    design_control_desired: str = "Some"
    design_changes_expected: bool = False

    principal_experience: str = "Limited"
    in_house_project_management: bool = False

    stakeholder_types: list = field(default_factory=list)
    stakeholder_notes: str = ""

    complexity_level: str = "Moderate"
    complexity_drivers: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def validate(brief: ProjectBrief) -> list[str]:
    """Return a list of human-readable problems (empty list = valid)."""
    problems = []
    if brief.fast_track_acceptable and brief.design_control_desired == "Full":
        problems.append(
            "You want full design control but are happy to start construction "
            "before design is finished. Check these two answers are consistent."
        )
    if brief.fixed_completion_date and brief.timing_importance == "Low":
        problems.append(
            "You have a fixed completion date but rated timing importance as Low."
        )
    if brief.budget_fixed and brief.cost_certainty_importance == "Low":
        problems.append(
            "You have a fixed budget but rated cost certainty importance as Low."
        )
    return problems

QUESTION_LABELS = {
    "timing_importance": "Timing",
    "fixed_completion_date": "Timing",
    "fast_track_acceptable": "Timing",

    "cost_certainty_importance": "Cost",
    "budget_fixed": "Cost",
    "lowest_price_priority": "Cost",

    "design_control_desired": "Control over design",
    "design_changes_expected": "Control over design",

    "principal_experience": "Experience of the principal",
    "in_house_project_management": "Experience of the principal",

    "stakeholder_types": "Other stakeholders",
    "stakeholder_notes": "Other stakeholders",

    "complexity_level": "Project complexity",
    "complexity_drivers": "Project complexity",
}