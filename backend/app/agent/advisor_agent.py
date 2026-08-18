from __future__ import annotations

import json

from app.agent.advisor_tools import AdvisorToolExecutor, ToolEvidence
from app.agent.llm_provider import AdvisorLLMProvider, create_llm_provider
from app.agent.specialists import (
    COST_PRESSURE_ACTION_SPECIALIST,
    SCENARIO_SPECIALIST,
    SUPERVISOR_NAME,
    TREND_FORECAST_SPECIALIST,
    CostPressureActionSpecialist,
    ScenarioSpecialist,
    SpecialistResult,
    SpecialistTask,
    TrendForecastSpecialist,
)
from app.core.config import get_settings
from app.schemas.advisor import AdvisorResponse


SYSTEM_INSTRUCTIONS = """You are the Medical Economics Advisor for a healthcare-finance application.
Use only the structured evidence supplied in the input. Do not invent values, forecasts, savings,
alerts, recommendations, or causal claims. This is not clinical decision support: never diagnose,
recommend treatment, prescribe, or discuss patient-level information. Be concise and business-oriented.
When useful, use headings: Finding, Evidence, Why it matters, Recommended action, Scenario impact.
Explicitly label observed facts as ACTUAL, model outputs as FORECAST, and scenario output as HYPOTHETICAL.
Never describe a scenario estimate as guaranteed savings. If a tool reports unavailable data, state that clearly."""

CLINICAL_TERMS = ("diagnos", "diagnosis", "prescrib", "treatment", "medication", "patient care", "clinical")
BUSINESS_TERMS = ("cost", "expense", "spend", "medical", "utilization", "patient", "forecast", "trend", "pressure", "driver", "department", "recommend", "priorit", "leadership", "scenario", "projected", "summary", "oncology", "pharmacy", "site of care", "service mix", "unit cost")
UNSUPPORTED_QUESTION_MESSAGE = "I can help analyze medical cost trends, forecast cost pressure, identify cost drivers, evaluate cost-containment recommendations, and run what-if scenarios for the selected dataset."


class MedicalEconomicsSupervisorAgent:
    """Routes questions to thin specialists and optionally synthesizes their deterministic evidence."""

    def __init__(self, *, llm_provider: AdvisorLLMProvider | None = None) -> None:
        self.llm_provider = llm_provider or create_llm_provider(get_settings())
        self._specialists = {
            TREND_FORECAST_SPECIALIST: TrendForecastSpecialist(),
            COST_PRESSURE_ACTION_SPECIALIST: CostPressureActionSpecialist(),
            SCENARIO_SPECIALIST: ScenarioSpecialist(),
        }

    def answer(self, *, executor: AdvisorToolExecutor, dataset_id: int, question: str) -> AdvisorResponse:
        normalized_question = question.lower()
        if any(term in normalized_question for term in CLINICAL_TERMS):
            return self._unsupported(dataset_id, question, f"The advisor does not provide clinical guidance. {UNSUPPORTED_QUESTION_MESSAGE}")
        if not any(term in normalized_question for term in BUSINESS_TERMS):
            return self._unsupported(dataset_id, question, UNSUPPORTED_QUESTION_MESSAGE)

        tasks = self.select_specialists(question)
        specialist_results = [self._specialists[task.specialist].analyze(executor, dataset_id=dataset_id, question=question, tools=task.tools) for task in tasks]
        evidence = [item for result in specialist_results for item in result.evidence]
        response = AdvisorResponse(
            dataset_id=dataset_id,
            question=question,
            status="provider_unavailable",
            answer=_deterministic_answer(evidence),
            message="Deterministic evidence response. Configure an optional LLM provider for additional synthesis.",
            supervisor=SUPERVISOR_NAME,
            specialists_invoked=[result.specialist for result in specialist_results],
            tools_used=[item.tool for item in evidence],
            evidence=evidence,
            provider=self.llm_provider.name,
            model=self.llm_provider.model,
        )
        if not self.llm_provider.available():
            return response
        try:
            response.answer = self.llm_provider.generate(
                instructions=SYSTEM_INSTRUCTIONS,
                input_text=json.dumps({"question": question, "dataset_id": dataset_id, "supervisor": SUPERVISOR_NAME, "specialists": [_specialist_dump(result) for result in specialist_results], "tool_evidence": [_evidence_dump(item) for item in evidence]}, default=str),
            )
            response.status = "completed"
            response.message = None
        except RuntimeError as err:
            response.status = "provider_error"
            response.answer = _deterministic_answer(evidence)
            response.message = f"LLM Provider Error: {err}"
        return response

    def _unsupported(self, dataset_id: int, question: str, message: str) -> AdvisorResponse:
        return AdvisorResponse(dataset_id=dataset_id, question=question, status="unsupported_question", answer=None, message=message, supervisor=SUPERVISOR_NAME, specialists_invoked=[], tools_used=[], evidence=[], provider=self.llm_provider.name, model=self.llm_provider.model)

    @staticmethod
    def select_specialists(question: str) -> list[SpecialistTask]:
        normalized = question.lower()
        if any(phrase in normalized for phrase in ("what happens if", "what if", "reduced by", "reduction", "falls by", "fall by", "decreased by", "decrease by", "drops by", "drop by")):
            return [SpecialistTask(SCENARIO_SPECIALIST, ("scenario",))]
        if any(phrase in normalized for phrase in ("biggest cost pressures", "most pressure", "most cost pressure")):
            return [SpecialistTask(COST_PRESSURE_ACTION_SPECIALIST, ("cost_pressures",))]
        if any(phrase in normalized for phrase in ("executive summary", "summarize this dataset", "summary of this dataset")):
            return [SpecialistTask(TREND_FORECAST_SPECIALIST, ("analytics", "forecast")), SpecialistTask(COST_PRESSURE_ACTION_SPECIALIST, ("cost_pressures", "recommendations"))]
        if any(phrase in normalized for phrase in ("prioritize", "priority", "what should", "leadership focus", "should leadership")):
            return [SpecialistTask(COST_PRESSURE_ACTION_SPECIALIST, ("cost_pressures", "recommendations"))]
        if any(phrase in normalized for phrase in ("cost pressure", "pressure", "why are", "why is", "why did")):
            return [SpecialistTask(TREND_FORECAST_SPECIALIST, ("analytics",)), SpecialistTask(COST_PRESSURE_ACTION_SPECIALIST, ("cost_pressures",))]
        if any(phrase in normalized for phrase in ("expected cost trend", "forecast", "expected trend", "cost trend", "expected to rise", "expected to fall", "next few months")):
            return [SpecialistTask(TREND_FORECAST_SPECIALIST, ("forecast",))]
        return [SpecialistTask(TREND_FORECAST_SPECIALIST, ("analytics",))]


MedicalEconomicsAdvisorAgent = MedicalEconomicsSupervisorAgent


def _evidence_dump(evidence: ToolEvidence) -> dict[str, object]:
    return {"tool": evidence.tool, "result": evidence.result, "error": evidence.error}


def _specialist_dump(result: SpecialistResult) -> dict[str, object]:
    return {"specialist": result.specialist, "evidence": [_evidence_dump(item) for item in result.evidence]}


medical_economics_advisor = MedicalEconomicsSupervisorAgent()


def _deterministic_answer(evidence: list[ToolEvidence]) -> str:
    """Format existing specialist output for people without adding calculations or claims."""
    results = {item.tool: item.result or {} for item in evidence if item.error is None}
    analytics = results.get("analytics", {})
    forecast = results.get("forecast", {})
    pressures = results.get("cost_pressures", {})
    recommendations = results.get("recommendations", {})
    scenario = results.get("scenario", {})
    lines: list[str] = []

    if scenario:
        lines.extend(["HYPOTHETICAL SCENARIO", f"Baseline projected cost: {_currency(scenario.get('baseline_projected_cost'))}", f"Estimated reduction: {_currency(scenario.get('estimated_reduction_amount'))}", f"Scenario projected cost: {_currency(scenario.get('scenario_projected_cost'))}", "This is a hypothetical estimate, not guaranteed savings."])
    else:
        metrics = analytics.get("metrics", {}) if isinstance(analytics.get("metrics"), dict) else {}
        change = metrics.get("month_over_month_cost_change_pct")
        if isinstance(change, (int, float)):
            direction = "upward" if change >= 0 else "downward"
            summary = f"Medical costs are showing {direction} pressure ({_percent(change)} month over month)."
        elif forecast:
            summary = "A stored forecast is available for the selected dataset."
        elif pressures:
            summary = "Existing driver and alert evidence identifies current cost pressure."
        else:
            summary = "No complete evidence is currently available for the selected dataset."
        lines.extend(["SUMMARY", summary, "", "KEY EVIDENCE"])
        if isinstance(change, (int, float)):
            lines.append(f"- ACTUAL: Latest monthly cost changed {_percent(change)} versus the previous month.")
        highest = analytics.get("highest_cost_department") if isinstance(analytics.get("highest_cost_department"), dict) else None
        if highest and isinstance(highest.get("contribution_pct"), (int, float)):
            lines.append(f"- ACTUAL: {highest.get('department')} represents {_percent(highest['contribution_pct'])} of total medical cost.")
        if forecast:
            horizon = forecast.get("horizon_months")
            expected = forecast.get("expected_change_pct")
            if isinstance(expected, (int, float)):
                lines.append(f"- FORECAST: {forecast.get('model_name', 'Stored model')} projects {_percent(expected)} over the {horizon}-month outlook.")
            else:
                lines.append(f"- FORECAST: A {horizon}-month stored forecast is available using {forecast.get('model_name', 'the recorded model')}.")
        drivers = pressures.get("drivers", []) if isinstance(pressures.get("drivers"), list) else []
        alerts = pressures.get("alerts", []) if isinstance(pressures.get("alerts"), list) else []
        for item in drivers[:2]:
            if isinstance(item, dict) and item.get("explanation"):
                lines.append(f"- ACTUAL: {item['explanation']}")
        for item in alerts[:1]:
            if isinstance(item, dict) and item.get("explanation"):
                lines.append(f"- ACTUAL ALERT: {item['explanation']}")
        recommendations_list = recommendations.get("recommendations", []) if isinstance(recommendations.get("recommendations"), list) else []
        if highest or drivers or alerts:
            lines.extend(["", "WHAT THIS MEANS"])
            if highest:
                lines.append(f"Observed pressure is concentrated in {highest.get('department')}; review the evidence alongside the overall trend.")
            elif drivers:
                lines.append("The current drivers indicate operational cost pressure that should be reviewed with the supporting evidence.")
        if recommendations_list and isinstance(recommendations_list[0], dict):
            recommendation = recommendations_list[0]
            lines.extend(["", "RECOMMENDED FOCUS", f"{recommendation.get('title')}: {recommendation.get('rationale')}"])

    dataset = analytics.get("dataset") if isinstance(analytics.get("dataset"), dict) else forecast.get("dataset") if isinstance(forecast.get("dataset"), dict) else None
    trend = analytics.get("monthly_trend", []) if isinstance(analytics.get("monthly_trend"), list) else []
    if dataset or trend:
        lines.extend(["", "SOURCE"])
        if dataset:
            label = "Synthetic demo data — not real medical data" if dataset.get("is_synthetic") else "Uploaded aggregated medical-cost data"
            lines.append(f"{dataset.get('name', 'Selected dataset')} · {label}")
        months = [item.get("month") for item in trend if isinstance(item, dict) and item.get("month")]
        if months:
            lines.append(f"Historical period: {months[0]} to {months[-1]}")
    return "\n".join(lines)


def _currency(value: object) -> str:
    return f"${value:,.0f}" if isinstance(value, (int, float)) else "Not available"


def _percent(value: float) -> str:
    return f"{value:+.1f}%"
