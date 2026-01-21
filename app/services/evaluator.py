from typing import Literal, List

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field


class TurnEvaluation(BaseModel):
    technical_accuracy: int = Field(..., ge=1, le=10)
    communication_clarity: int = Field(..., ge=1, le=10)
    confidence_signal: Literal["Low", "Med", "High"]


class TurnEvaluator:
    def __init__(self) -> None:
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    def evaluate(self, response_text: str) -> TurnEvaluation:
        system_prompt = (
            "You are evaluating a candidate's interview response. "
            "Return only JSON that matches the requested schema."
        )
        user_prompt = (
            "Score the response.\n"
            "- technical_accuracy: 1-10\n"
            "- communication_clarity: 1-10\n"
            "- confidence_signal: Low/Med/High\n\n"
            "Schema:\n"
            "{"
            "\"technical_accuracy\": 1-10, "
            "\"communication_clarity\": 1-10, "
            "\"confidence_signal\": \"Low|Med|High\""
            "}\n\n"
            f"Response:\n{response_text}"
        )
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        if hasattr(self.llm, "with_structured_output"):
            structured_llm = self.llm.with_structured_output(TurnEvaluation)
            evaluation = structured_llm.invoke(messages)
        else:
            response = self.llm.invoke(messages)
            evaluation = TurnEvaluation.model_validate_json(response.content)
        return evaluation


class FinalReport(BaseModel):
    strengths: List[str] = Field(default_factory=list)
    areas_for_improvement: List[str] = Field(default_factory=list)


class FinalReportGenerator:
    def __init__(self) -> None:
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)

    def generate(self, context: str) -> FinalReport:
        system_prompt = (
            "You summarize interview performance into concise bullets. "
            "Return only JSON that matches the requested schema."
        )
        user_prompt = (
            "Create 2-4 strengths and 2-4 areas for improvement based on the context.\n\n"
            "Schema:\n"
            "{"
            "\"strengths\": [\"string\"], "
            "\"areas_for_improvement\": [\"string\"]"
            "}\n\n"
            f"Context:\n{context}"
        )
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        if hasattr(self.llm, "with_structured_output"):
            structured_llm = self.llm.with_structured_output(FinalReport)
            return structured_llm.invoke(messages)
        response = self.llm.invoke(messages)
        return FinalReport.model_validate_json(response.content)
