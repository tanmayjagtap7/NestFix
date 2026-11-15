from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Employer(Base):
    __tablename__ = "employers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)

    employees: Mapped[List["Employee"]] = relationship(back_populates="employer")


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (UniqueConstraint("employer_id", "employee_id_external", name="uq_employee_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employer_id: Mapped[int] = mapped_column(ForeignKey("employers.id"), nullable=False, index=True)
    employee_id_external: Mapped[str] = mapped_column(String(80), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    annual_salary: Mapped[float] = mapped_column(Float, nullable=False)
    family_size: Mapped[int] = mapped_column(Integer, nullable=False)
    num_children: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    preferred_city: Mapped[str] = mapped_column(String(200), nullable=False)
    max_commute_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    min_bedrooms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    contribution_type: Mapped[str] = mapped_column(String(40), nullable=False)
    contribution_amount: Mapped[float] = mapped_column(Float, nullable=False)
    contribution_duration_months: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    other_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    employer: Mapped["Employer"] = relationship(back_populates="employees")

    @property
    def contribution_label(self) -> str:
        from app.services.affordability import contribution_label as label_for

        return label_for(self)
    housing_options: Mapped[List["HousingOption"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )
    selection: Mapped[Optional["EmployeeSelection"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan", uselist=False
    )


class HousingOption(Base):
    __tablename__ = "housing_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address: Mapped[str] = mapped_column(String(400), nullable=False)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bedrooms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bathrooms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sqft: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    listing_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    amenities_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    gemini_analysis: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    net_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    employee: Mapped["Employee"] = relationship(back_populates="housing_options")
    selection: Mapped[Optional["EmployeeSelection"]] = relationship(back_populates="housing_option")


class EmployeeSelection(Base):
    __tablename__ = "employee_selections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, unique=True)
    housing_option_id: Mapped[int] = mapped_column(ForeignKey("housing_options.id"), nullable=False)
    selected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    employee_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    employee: Mapped["Employee"] = relationship(back_populates="selection")
    housing_option: Mapped["HousingOption"] = relationship(back_populates="selection")


class HousingQuestion(Base):
    __tablename__ = "housing_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    housing_option_id: Mapped[int] = mapped_column(ForeignKey("housing_options.id"), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    housing_option: Mapped["HousingOption"] = relationship()


class AnalysisLog(Base):
    __tablename__ = "analysis_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True, index=True)
    service: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    request_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
