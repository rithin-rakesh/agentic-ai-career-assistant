import pytest
from app.collectors.remoteok import RemoteOKCollector
from app.collectors.arbeitnow import ArbeitnowCollector
from app.collectors.remotive import RemotiveCollector

def test_remoteok_collector_mock():
    collector = RemoteOKCollector(mock_mode=True)
    jobs = collector.collect()
    assert len(jobs) > 0
    assert jobs[0].source == "RemoteOK"
    assert jobs[0].title != ""

def test_arbeitnow_collector_mock():
    collector = ArbeitnowCollector(mock_mode=True)
    jobs = collector.collect()
    assert len(jobs) > 0
    assert jobs[0].source == "Arbeitnow"
    assert jobs[0].company != ""

def test_remotive_collector_mock():
    collector = RemotiveCollector(mock_mode=True)
    jobs = collector.collect()
    assert len(jobs) > 0
    assert jobs[0].source == "Remotive"
    assert jobs[0].description != ""
