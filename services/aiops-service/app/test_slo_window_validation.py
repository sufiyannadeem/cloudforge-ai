import pytest
from .slo_service import window_seconds


@pytest.mark.parametrize('window,seconds',[('5m',300),('6h',21600),('7d',604800),('1h30m',5400),('15ms',0.015)])
def test_supported_duration_values_unchanged(window,seconds):
    assert window_seconds(window)==seconds


@pytest.mark.parametrize('window',['9'*100000,'1h'+'9'*100000,'1x','',None])
def test_unbounded_or_malformed_duration_rejected(window):
    with pytest.raises(ValueError):window_seconds(window)
