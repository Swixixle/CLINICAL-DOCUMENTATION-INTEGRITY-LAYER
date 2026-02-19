"""
Mock AI summarizer endpoint for demo purposes.

This simulates an AI-powered clinical documentation tool.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional

router = APIRouter(prefix="/v1/mock", tags=["mock"])


class MockSummarizeRequest(BaseModel):
    """Request model for mock summarization."""

    clinical_text: str = Field(..., description="Raw clinical text to summarize")
    note_type: Optional[str] = Field(
        default="progress_note", description="Type of clinical note"
    )
    ai_model: Optional[str] = Field(
        default="gpt-4-turbo", description="AI model to use"
    )


class MockSummarizeResponse(BaseModel):
    """Response from mock summarizer."""

    summary: str = Field(..., description="Generated clinical summary")
    model_used: str = Field(..., description="AI model used")
    prompt_version: str = Field(..., description="Prompt version used")
    governance_policy_version: str = Field(..., description="Governance policy version")


@router.post("/summarize", response_model=MockSummarizeResponse)
async def mock_summarize(request: MockSummarizeRequest) -> MockSummarizeResponse:
    """
    Mock AI summarizer endpoint.

    This simulates what an external AI documentation vendor would return.
    In production, this would call a real AI model.

    Returns:
        A mock clinical summary with governance metadata
    """
    # Generate a simple mock summary
    summary = f"CLINICAL SUMMARY ({request.note_type.upper()})\n\n"
    summary += "Chief Complaint: Patient presents with multiple concerns.\n\n"
    summary += "Assessment: Clinical evaluation performed.\n\n"
    summary += "Plan: Treatment plan established.\n\n"
    summary += f"[This is a mock summary generated from {len(request.clinical_text)} characters of clinical text]"

    return MockSummarizeResponse(
        summary=summary,
        model_used=request.ai_model,
        prompt_version="clinical-v1.2",
        governance_policy_version="CDOC-Policy-v1",
    )
