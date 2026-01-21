import json
import os
from typing import Optional, List, Literal, Iterable, Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langchain.memory import ChatMessageHistory
from pydantic import BaseModel, Field

from app.schema.candidate import CandidateProfile
from app.services.evaluator import TurnEvaluation, TurnEvaluator, FinalReport, FinalReportGenerator
from app.utils.matcher import identify_critical_gaps


class StarAssessment(BaseModel):
    situation: bool = Field(..., description="Mentions situation/context")
    task: bool = Field(..., description="Mentions task/goal")
    action: bool = Field(..., description="Mentions actions taken")
    result: bool = Field(..., description="Mentions results/impact")
    missing_parts: List[str] = Field(default_factory=list)


class ResponseAnalyzer:
    def __init__(self) -> None:
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    def analyze(self, response_text: str) -> StarAssessment:
        system_prompt = (
            "You evaluate interview answers using the STAR method. "
            "Return only JSON that matches the requested schema."
        )
        user_prompt = (
            "Check whether the response clearly includes each STAR component. "
            "Set missing_parts to any missing items from: Situation, Task, Action, Result.\n\n"
            "Schema:\n"
            "{"
            "\"situation\": true|false, "
            "\"task\": true|false, "
            "\"action\": true|false, "
            "\"result\": true|false, "
            "\"missing_parts\": [\"Situation|Task|Action|Result\"]"
            "}\n\n"
            f"Response:\n{response_text}"
        )
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        if hasattr(self.llm, "with_structured_output"):
            structured_llm = self.llm.with_structured_output(StarAssessment)
            assessment = structured_llm.invoke(messages)
        else:
            response = self.llm.invoke(messages)
            assessment = StarAssessment.model_validate_json(response.content)
        return assessment

    @staticmethod
    def needs_followup(assessment: StarAssessment) -> bool:
        return not (assessment.situation and assessment.task and assessment.action and assessment.result)


class InterviewAgent:
    def __init__(self, candidate_profile: CandidateProfile, job_description: str = "") -> None:
        os.environ.pop("OPENAI_BASE_URL", None)
        os.environ.pop("OPENAI_API_BASE", None)
        self.candidate_profile = candidate_profile
        self.job_description = job_description or ""
        self.critical_gaps = identify_critical_gaps(candidate_profile, self.job_description)
        self.history = ChatMessageHistory()
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.7,
            frequency_penalty=0.8,
            presence_penalty=0.6,
        )
        self.validator_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.turn_evaluator = TurnEvaluator()
        self.report_generator = FinalReportGenerator()
        self.turn_evaluations: List[TurnEvaluation] = []
        self.difficulty_score = 3
        self.consecutive_high_quality = 0
        self.final_summary_report: Optional["FinalSummaryReport"] = None

        self.system_prompt = (
            "You are Alex, an elite technical interviewer. Your goal is a fluid, natural "
            "conversation.\n"
            "Listen First: Acknowledge the candidate's last answer specifically before moving on.\n"
            "Follow the Content: If the candidate mentions \"Time series\" or \"LightGBM,\" ask a "
            "deep-dive technical question about that immediately, even if you haven't finished the "
            "behavioral section.\n"
            "No Loops: If you see the prompt \"Could you briefly describe the situation or context?\" "
            "in the chat history, you are FORBIDDEN from asking it again.\n\n"
            "You have the candidate's profile: "
            f"{self._profile_json()}.\n\n"
            f"Job description:\n{self.job_description or 'Not provided'}\n\n"
            f"Critical gaps (JD skills missing or weak on the resume): "
            f"{', '.join(self.critical_gaps) if self.critical_gaps else 'None identified'}.\n\n"
            "Prioritize asking questions about the skills listed in the JD that are missing "
            "or weak on the candidate's resume to verify their actual proficiency.\n\n"
            f"Current interview level is {self.difficulty_score}. Adjust the complexity of "
            "your technical questions to match this level. Level 1 is basic definitions; "
            "Level 5 is complex system design and edge cases."
        )

        self.final_report_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)

    def get_next_response(self, user_input: Optional[str], history: Optional[Iterable[Any]] = None) -> str:
        hint_text = None
        if user_input and user_input.strip():
            cleaned_input = user_input.strip()
            self.history.add_message(HumanMessage(content=cleaned_input))

            evaluation = self.turn_evaluator.evaluate(cleaned_input)
            self.turn_evaluations.append(evaluation)
            hint_text = self.update_difficulty(user_answer_quality=evaluation.technical_accuracy)

        correction_prompt = (
            "Ensure the next question is directly grounded in the candidate's "
            "skills or projects from their profile. Do not invent details."
        )
        response_text = ""
        for attempt in range(3):
            messages = [SystemMessage(content=self.system_prompt)]
            for message in self._normalize_history(self.history.messages):
                messages.append(message)
            if history is not None and history is not self.history.messages:
                for message in self._normalize_history(history):
                    messages.append(message)
            if history is not None and user_input and user_input.strip():
                messages.append(HumanMessage(content=cleaned_input))
            messages.append(SystemMessage(content=self._dynamic_system_prompt(hint_text)))
            if attempt > 0:
                messages.append(SystemMessage(content=correction_prompt))

            response = self.llm.invoke(messages)
            response_text = response.content

            if self._is_grounded(response_text):
                break

        self.history.add_message(AIMessage(content=response_text))
        return response_text

    def _profile_json(self) -> str:
        return json.dumps(self.candidate_profile.model_dump(), ensure_ascii=True)

    def _dynamic_system_prompt(self, hint_text: Optional[str]) -> str:
        prompt = (
            f"Current interview level is {self.difficulty_score}. Adjust the complexity of "
            "your technical questions to match this level. Level 1 is basic definitions; "
            "Level 5 is complex system design and edge cases."
        )
        if hint_text:
            prompt = f"{prompt}\nProvide a brief, actionable hint before the next question: {hint_text}"
        return prompt

    def _normalize_history(self, history: Iterable[Any]) -> List[BaseMessage]:
        normalized: List[BaseMessage] = []
        for item in history:
            if isinstance(item, BaseMessage):
                normalized.append(item)
                continue
            if isinstance(item, dict):
                role = (item.get("role") or "").lower()
                content = item.get("content", "")
                if role == "system":
                    normalized.append(SystemMessage(content=content))
                elif role in {"assistant", "ai"}:
                    normalized.append(AIMessage(content=content))
                else:
                    normalized.append(HumanMessage(content=content))
                continue
            normalized.append(HumanMessage(content=str(item)))
        return normalized

    def update_difficulty(self, user_answer_quality: int) -> Optional[str]:
        if user_answer_quality >= 8:
            self.consecutive_high_quality += 1
        else:
            self.consecutive_high_quality = 0

        if self.consecutive_high_quality >= 2:
            self.difficulty_score = min(5, self.difficulty_score + 1)
            self.consecutive_high_quality = 0

        if user_answer_quality <= 4:
            self.difficulty_score = max(1, self.difficulty_score - 1)
            return (
                "Focus on the core concept, mention assumptions, and briefly discuss "
                "trade-offs or alternatives."
            )
        return None

    def _is_grounded(self, question: str) -> bool:
        if not question.strip():
            return False

        system_prompt = (
            "You are validating whether an interview question is grounded in the "
            "candidate's resume. Respond with only True or False."
        )
        user_prompt = (
            "Candidate profile:\n"
            f"{self._profile_json()}\n\n"
            "Question:\n"
            f"{question}\n\n"
            "Is the question directly related to a skill or project in the profile?"
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = self.validator_llm.invoke(messages)
        return response.content.strip().lower() == "true"

    def generate_final_report(self) -> FinalReport:
        messages = [m.content for m in self.history.messages]
        conversation = "\n".join(messages[-12:])
        avg_tech = self._average_score("technical_accuracy")
        avg_comm = self._average_score("communication_clarity")
        avg_conf = self._average_score("confidence_signal")

        context = (
            f"Candidate profile: {self._profile_json()}\n\n"
            f"Average technical accuracy: {avg_tech}\n"
            f"Average communication clarity: {avg_comm}\n"
            f"Average confidence signal (Low/Med/High): {avg_conf}\n\n"
            f"Recent conversation:\n{conversation}"
        )
        try:
            return self.report_generator.generate(context)
        except Exception:
            return FinalReport(
                strengths=[
                    "Shows willingness to engage with technical prompts.",
                    "Responds to follow-up questions.",
                ],
                areas_for_improvement=[
                    "Provide more structured STAR responses.",
                    "Quantify impact and results more clearly.",
                ],
            )

    def _average_score(self, field: str):
        if not self.turn_evaluations:
            return 0
        if field == "confidence_signal":
            confidence_map = {"Low": 1, "Med": 2, "High": 3}
            avg = sum(confidence_map[ev.confidence_signal] for ev in self.turn_evaluations) / len(
                self.turn_evaluations
            )
            if avg > 2.5:
                return "High"
            if avg >= 1.5:
                return "Med"
            return "Low"
        return round(
            sum(getattr(ev, field) for ev in self.turn_evaluations) / len(self.turn_evaluations),
            2,
        )

    def finalize_interview(self) -> "FinalSummaryReport":
        if self.final_summary_report is not None:
            return self.final_summary_report

        conversation_lines = []
        for message in self.history.messages:
            role = getattr(message, "type", "system")
            if role == "human":
                label = "Candidate"
            elif role == "ai":
                label = "Alex"
            else:
                label = "System"
            conversation_lines.append(f"{label}: {message.content}")
        conversation = "\n".join(conversation_lines)

        avg_tech = self._average_score("technical_accuracy")
        avg_comm = self._average_score("communication_clarity")
        avg_conf = self._average_score("confidence_signal")

        system_prompt = (
            "You are summarizing an interview and must return only JSON "
            "matching the requested schema."
        )
        user_prompt = (
            "Generate a Final Summary Report using the full conversation and metrics.\n\n"
            "Requirements:\n"
            "- overall_verdict: Strong Hire | Hire | No Hire\n"
            "- key_strengths: exactly 3 concise bullet points\n"
            "- critical_gaps: areas the candidate should study\n"
            "- culture_fit_score: integer 1-10 based on tone and communication\n\n"
            "Schema:\n"
            "{"
            "\"overall_verdict\": \"Strong Hire|Hire|No Hire\", "
            "\"key_strengths\": [\"string\", \"string\", \"string\"], "
            "\"critical_gaps\": [\"string\"], "
            "\"culture_fit_score\": 1-10"
            "}\n\n"
            f"Candidate profile:\n{self._profile_json()}\n\n"
            f"Session metrics:\n"
            f"- average_technical_accuracy: {avg_tech}\n"
            f"- average_communication_clarity: {avg_comm}\n"
            f"- average_confidence_signal: {avg_conf}\n\n"
            f"Conversation:\n{conversation}"
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        try:
            if hasattr(self.final_report_llm, "with_structured_output"):
                structured_llm = self.final_report_llm.with_structured_output(FinalSummaryReport)
                report = structured_llm.invoke(messages)
            else:
                response = self.final_report_llm.invoke(messages)
                report = FinalSummaryReport.model_validate_json(response.content)
        except Exception:
            report = FinalSummaryReport(
                overall_verdict="Hire" if avg_tech >= 7 else "No Hire",
                key_strengths=[
                    "Engaged with technical prompts and follow-ups.",
                    "Communicated answers with a clear structure.",
                    "Demonstrated initiative in describing experience.",
                ],
                critical_gaps=self.critical_gaps or ["Deepen core system design fundamentals."],
                culture_fit_score=6 if avg_comm and avg_comm < 6 else 7,
            )

        self.final_summary_report = report
        return report


class FinalSummaryReport(BaseModel):
    overall_verdict: Literal["Strong Hire", "Hire", "No Hire"]
    key_strengths: List[str] = Field(default_factory=list, min_length=3, max_length=3)
    critical_gaps: List[str] = Field(default_factory=list)
    culture_fit_score: int = Field(..., ge=1, le=10)

