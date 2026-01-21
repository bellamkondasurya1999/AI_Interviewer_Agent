import re
from typing import List, Set

from app.schema.candidate import CandidateProfile


STOP_WORDS = {
    "and", "or", "the", "a", "an", "to", "of", "in", "for", "on", "with", "by",
    "from", "as", "at", "into", "over", "under", "is", "are", "was", "were",
    "be", "been", "being", "this", "that", "these", "those", "it", "its",
    "experience", "years", "year", "skills", "skill", "knowledge", "ability",
    "responsibilities", "requirements", "preferred", "nice", "plus", "role",
    "team", "work", "working", "develop", "build", "design", "implement",
    "maintain", "using", "use", "strong", "excellent",
}


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9+#\./-]*", text)


def _normalize(token: str) -> str:
    return token.lower().strip()


def _candidate_terms(profile: CandidateProfile) -> Set[str]:
    terms: Set[str] = set()
    for skill in profile.technical_stack:
        if skill:
            terms.add(_normalize(skill))
    for line in profile.key_achievements + profile.education:
        for token in _tokenize(line):
            normalized = _normalize(token)
            if len(normalized) > 2 and normalized not in STOP_WORDS:
                terms.add(normalized)
    return terms


def identify_critical_gaps(
    candidate_profile: CandidateProfile,
    job_description: str,
    max_gaps: int = 12,
) -> List[str]:
    if not job_description or not job_description.strip():
        return []

    candidate_terms = _candidate_terms(candidate_profile)
    seen = set()
    gaps: List[str] = []

    for token in _tokenize(job_description):
        normalized = _normalize(token)
        if len(normalized) <= 2 or normalized in STOP_WORDS:
            continue
        if normalized in candidate_terms or normalized in seen:
            continue
        seen.add(normalized)
        gaps.append(token)
        if len(gaps) >= max_gaps:
            break

    return gaps
