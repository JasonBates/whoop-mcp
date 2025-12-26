"""Pydantic models for WHOOP API responses."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class RecoveryScore(BaseModel):
    """WHOOP recovery score data."""

    recovery_score: float = Field(description="Recovery percentage (0-100)")
    resting_heart_rate: float = Field(description="Resting heart rate in bpm")
    hrv_rmssd_milli: float = Field(description="HRV in milliseconds")
    spo2_percentage: Optional[float] = Field(None, description="Blood oxygen % (WHOOP 4.0+)")
    skin_temp_celsius: Optional[float] = Field(None, description="Skin temperature in Celsius")
    user_calibrating: bool = Field(False, description="Whether user is still calibrating")


class Recovery(BaseModel):
    """WHOOP recovery record."""

    cycle_id: int
    sleep_id: Optional[str] = None
    user_id: int
    created_at: datetime
    updated_at: datetime
    score_state: str = Field(description="SCORED, PENDING_SCORE, or UNSCORABLE")
    score: Optional[RecoveryScore] = None


class SleepStageSummary(BaseModel):
    """Summary of sleep stages."""

    total_in_bed_time_milli: int
    total_awake_time_milli: int
    total_no_data_time_milli: int = 0
    total_light_sleep_time_milli: int
    total_slow_wave_sleep_time_milli: int
    total_rem_sleep_time_milli: int
    sleep_cycle_count: int
    disturbance_count: int

    @property
    def total_sleep_milli(self) -> int:
        """Total sleep time (excluding awake time)."""
        return (
            self.total_light_sleep_time_milli
            + self.total_slow_wave_sleep_time_milli
            + self.total_rem_sleep_time_milli
        )

    @property
    def total_sleep_hours(self) -> float:
        """Total sleep time in hours."""
        return self.total_sleep_milli / (1000 * 60 * 60)

    @property
    def deep_sleep_hours(self) -> float:
        """Deep (slow wave) sleep in hours."""
        return self.total_slow_wave_sleep_time_milli / (1000 * 60 * 60)

    @property
    def rem_sleep_hours(self) -> float:
        """REM sleep in hours."""
        return self.total_rem_sleep_time_milli / (1000 * 60 * 60)

    @property
    def light_sleep_hours(self) -> float:
        """Light sleep in hours."""
        return self.total_light_sleep_time_milli / (1000 * 60 * 60)


class SleepNeeded(BaseModel):
    """Breakdown of sleep need."""

    baseline_milli: int
    need_from_sleep_debt_milli: int
    need_from_recent_strain_milli: int
    need_from_recent_nap_milli: int = 0


class SleepScore(BaseModel):
    """WHOOP sleep score data."""

    stage_summary: SleepStageSummary
    sleep_needed: SleepNeeded
    respiratory_rate: Optional[float] = None
    sleep_performance_percentage: Optional[float] = None
    sleep_consistency_percentage: Optional[float] = None
    sleep_efficiency_percentage: Optional[float] = None


class Sleep(BaseModel):
    """WHOOP sleep record."""

    id: str
    cycle_id: Optional[int] = None
    user_id: int
    created_at: datetime
    updated_at: datetime
    start: datetime
    end: datetime
    timezone_offset: str
    nap: bool = Field(description="True if this is a nap, not main sleep")
    score_state: str
    score: Optional[SleepScore] = None


class CycleScore(BaseModel):
    """WHOOP cycle (daily strain) score."""

    strain: float = Field(description="Strain score 0-21")
    kilojoule: float = Field(description="Energy expenditure in kJ")
    average_heart_rate: int
    max_heart_rate: int


class Cycle(BaseModel):
    """WHOOP physiological cycle record."""

    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    start: datetime
    end: Optional[datetime] = None
    timezone_offset: str
    score_state: str
    score: Optional[CycleScore] = None
