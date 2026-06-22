import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from services.candidate_matching_service import CandidateMatchingService

@pytest.fixture
def mock_job():
    job = MagicMock()
    job.min_experience = 5
    job.max_experience = 10
    job.location = "Mumbai"
    job.is_remote = False
    job.max_salary = Decimal('2000000')
    job.skills.values_list.return_value = ['Python', 'Django', 'PostgreSQL']
    return job

@pytest.fixture
def mock_candidate():
    candidate = MagicMock()
    candidate.id = "test-uuid"
    candidate.total_experience = Decimal('6.0')
    candidate.location = "Mumbai"
    candidate.expected_salary = Decimal('1800000')
    candidate.notice_period = 15
    candidate.is_immediate_joiner = False
    candidate.skills.values_list.return_value = ['Python', 'Django', 'PostgreSQL', 'Docker']
    return candidate

def test_calculate_match_score_perfect_match(mock_job, mock_candidate):
    result = CandidateMatchingService.calculate_match_score(mock_job, mock_candidate)
    
    assert result['match_score'] == 100.0
    assert result['skill_score'] == 70.0
    assert result['experience_score'] == 20.0
    assert result['location_score'] == 5.0
    assert result['notice_score'] == 5.0
    assert result['is_qualified'] is True

def test_calculate_skill_score_partial_match(mock_job, mock_candidate):
    # Only 2 out of 3 skills match (66.67%), which is below 70% threshold, so score should be 0.0
    mock_candidate.skills.values_list.return_value = ['Python', 'Django']
    
    score = CandidateMatchingService._calculate_skill_score(mock_job, mock_candidate)
    assert float(score) == 0.0

def test_calculate_skill_score_passing_partial_match(mock_job, mock_candidate):
    # If job has 4 skills, and 3 match (75%), which is above 70% threshold
    mock_job.skills.values_list.return_value = ['Python', 'Django', 'PostgreSQL', 'Docker']
    mock_candidate.skills.values_list.return_value = ['Python', 'Django', 'PostgreSQL']
    
    score = CandidateMatchingService._calculate_skill_score(mock_job, mock_candidate)
    # (3/4) * 70 = 52.5
    assert float(score) == 52.5
