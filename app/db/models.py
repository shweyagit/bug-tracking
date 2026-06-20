from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class TestRun(Base):
    __tablename__ = "test_runs"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    github_run_id = Column(BigInteger, unique=True, nullable=False)
    github_repo = Column(String(255), nullable=False)
    branch = Column(String(255))
    commit_sha = Column(String(40))
    commit_message = Column(Text)
    pr_number = Column(Integer)
    pr_title = Column(Text)
    triggered_by = Column(String(255))
    workflow_name = Column(String(255))
    status = Column(String(50))
    conclusion = Column(String(50))
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    results = relationship("TestResult", back_populates="run", cascade="all, delete-orphan")
    bugs = relationship("Bug", back_populates="run", cascade="all, delete-orphan")


class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(Text, nullable=False)
    classname = Column(Text)
    feature_area = Column(String(255))
    suite_name = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("name", "classname"),)

    results = relationship("TestResult", back_populates="case")
    failure_stat = relationship("FailureStat", back_populates="case", uselist=False)


class TestResult(Base):
    __tablename__ = "test_results"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id = Column(PGUUID(as_uuid=True), ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(PGUUID(as_uuid=True), ForeignKey("test_cases.id"), nullable=False)
    status = Column(String(20), nullable=False)
    duration_seconds = Column(Float)
    error_message = Column(Text)
    error_type = Column(String(255))
    stack_trace = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    run = relationship("TestRun", back_populates="results")
    case = relationship("TestCase", back_populates="results")


class Bug(Base):
    __tablename__ = "bugs"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id = Column(PGUUID(as_uuid=True), ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    summary = Column(Text)
    root_cause = Column(Text)
    affected_feature = Column(String(255))
    severity = Column(String(20))
    failing_test_ids = Column(JSONB, default=list)
    jira_ticket_key = Column(String(50))
    jira_ticket_url = Column(Text)
    status = Column(String(30), default="draft")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    run = relationship("TestRun", back_populates="bugs")


class FailureStat(Base):
    __tablename__ = "failure_stats"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    case_id = Column(PGUUID(as_uuid=True), ForeignKey("test_cases.id", ondelete="CASCADE"), unique=True, nullable=False)
    feature_area = Column(String(255))
    total_runs = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    last_failed_at = Column(DateTime(timezone=True))
    last_passed_at = Column(DateTime(timezone=True))
    consecutive_failures = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    case = relationship("TestCase", back_populates="failure_stat")


class Release(Base):
    __tablename__ = "releases"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    version = Column(String(100), unique=True, nullable=False)
    release_date = Column(DateTime(timezone=True))
    snapshot_bug_ids = Column(JSONB, default=list)
    unfixed_bug_ids = Column(JSONB, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
