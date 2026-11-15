from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class EmployerCreate(BaseModel):
    company_name: str = Field(min_length=2, max_length=200)
    contact_email: str
    work_location: str = Field(min_length=3, max_length=300)


class EmployerUpdate(BaseModel):
    work_location: str = Field(min_length=3, max_length=300)


class EmployerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_name: str
    contact_email: str
    work_location: Optional[str] = None
    work_latitude: Optional[float] = None
    work_longitude: Optional[float] = None


class EmployeeIn(BaseModel):
    employee_id: str = Field(min_length=1, max_length=80)
    full_name: str
    email: str
    annual_salary: float
    family_size: int
    num_children: int = 0
    preferred_city: Optional[str] = None
    work_location: Optional[str] = None
    max_commute_minutes: Optional[int] = None
    min_bedrooms: Optional[int] = None
    other_notes: Optional[str] = None
    contribution_type: Optional[str] = None
    contribution_amount: Optional[float] = None
    contribution_duration_months: Optional[int] = None


class EmployeeUpdate(BaseModel):
    contribution_type: Optional[str] = None
    contribution_amount: Optional[float] = Field(default=None, ge=0)
    contribution_duration_months: Optional[int] = Field(default=None, ge=1)
    other_notes: Optional[str] = None
    min_bedrooms: Optional[int] = Field(default=None, ge=0)
    max_commute_minutes: Optional[int] = Field(default=None, ge=0)
    preferred_city: Optional[str] = None
    family_size: Optional[int] = Field(default=None, ge=1)
    num_children: Optional[int] = Field(default=None, ge=0)


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employer_id: int
    employee_id_external: str
    full_name: str
    email: str
    annual_salary: float
    family_size: int
    num_children: int
    preferred_city: str
    max_commute_minutes: Optional[int] = None
    min_bedrooms: Optional[int] = None
    contribution_type: str
    contribution_amount: float
    contribution_duration_months: Optional[int] = None
    other_notes: Optional[str] = None
    contribution_label: str = ""
    options_count: int = 0
    selected_option_id: Optional[int] = None
    selected_address: Optional[str] = None
    employer_name: Optional[str] = None
    work_location: Optional[str] = None


class UploadResult(BaseModel):
    employer_id: int
    created: int
    updated: int
    employees: List[EmployeeOut]


class HousingOptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    source_url: Optional[str] = None
    address: str
    price: Optional[float] = None
    bedrooms: Optional[float] = None
    bathrooms: Optional[float] = None
    sqft: Optional[float] = None
    listing_data: Optional[Dict[str, Any]] = None
    amenities_data: Optional[Dict[str, Any]] = None
    gemini_analysis: Optional[Dict[str, Any]] = None
    net_price: Optional[float] = None
    employer_monthly_cover: Optional[float] = None
    created_at: datetime


class OptionsResponse(BaseModel):
    employee: EmployeeOut
    monthly_gross: float
    housing_budget: float
    contribution_label: str
    selected_option_id: Optional[int] = None
    analysis_source: Optional[str] = None
    gemini_error: Optional[str] = None
    data_note: Optional[str] = None
    options: List[HousingOptionOut]


class GenerateResponse(OptionsResponse):
    options_created: int
    bright_data_note: str


class SelectIn(BaseModel):
    housing_option_id: int
    employee_notes: Optional[str] = None


class SelectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    housing_option_id: int
    selected_at: datetime
    employee_notes: Optional[str] = None


class AffordabilityIn(BaseModel):
    other_monthly_expenses: float = Field(ge=0)
    desired_savings: float = Field(ge=0)
    take_home_ratio: float = Field(default=0.75, gt=0, le=1)


class RankedOption(BaseModel):
    housing_option_id: int
    address: str
    net_price: Optional[float] = None
    sticker_price: Optional[float] = None
    bedrooms: Optional[float] = None
    score: Optional[float] = None
    fits_budget: bool
    monthly_cushion: Optional[float] = None
    rent_to_income_ratio: Optional[float] = None
    rank: int
    original_rank: int
    note: str


class AffordabilityOut(BaseModel):
    monthly_gross: float
    estimated_take_home: float
    other_monthly_expenses: float
    desired_savings: float
    housing_budget: float
    narrative: str
    narrative_source: str
    options: List[RankedOption]


class SelectionSummaryItem(BaseModel):
    employee_id: int
    employee_id_external: str
    full_name: str
    email: str
    preferred_city: str
    contribution_label: str
    housing_option_id: Optional[int] = None
    address: Optional[str] = None
    sticker_price: Optional[float] = None
    net_price: Optional[float] = None
    employer_monthly_cover: Optional[float] = None
    selected_at: Optional[datetime] = None
    employee_notes: Optional[str] = None
    status: str


class SelectionsSummary(BaseModel):
    employer: EmployerOut
    total_employees: int
    selections_count: int
    pending_count: int
    options_ready_count: int
    selections: List[SelectionSummaryItem]


class QuestionIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question: str
    answer: str
    created_at: datetime


class AnalysisLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: Optional[int] = None
    service: str
    action: str
    status: str
    request_summary: Optional[str] = None
    response_summary: Optional[str] = None
    detail: Optional[str] = None
    created_at: datetime
