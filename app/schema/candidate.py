from typing import List, Optional, Literal

from pydantic import BaseModel, Field


class CandidateProfile(BaseModel):
    full_name: str = Field(..., description="Candidate full name")
    email: Optional[str] = Field(default=None, description="Email address")
    experience_years: int = Field(..., description="Total years of experience")
    technical_stack: List[str] = Field(default_factory=list)
    education: List[str] = Field(default_factory=list)
    key_achievements: List[str] = Field(
        default_factory=list,
        description="3-4 major bullet points"
    )
    seniority_level: Literal["Junior", "Mid", "Senior", "Lead"]

