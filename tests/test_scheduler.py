import pytest
from unittest.mock import MagicMock, patch
from app.scheduler.scheduler import JobScheduler
from app.services.collection_service import CollectionService

def test_scheduler_registration():
    """
    Tests that JobScheduler registers periodic and startup jobs correctly
    on the underlying APScheduler instance.
    """
    # Create a mock collection service
    mock_service = MagicMock(spec=CollectionService)
    
    # Patch BlockingScheduler so we don't start a real blocking loop
    with patch('app.scheduler.scheduler.BlockingScheduler') as MockBlockingScheduler:
        mock_scheduler_instance = MockBlockingScheduler.return_value
        
        # Instantiate our scheduler
        job_scheduler = JobScheduler(collection_service=mock_service)
        
        # Start the scheduler
        job_scheduler.start()
        
        # Verify scheduler instance started
        mock_scheduler_instance.start.assert_called_once()
        
        # Verify add_job was called twice:
        # 1. Periodic job scheduled with interval trigger
        # 2. Startup execution job scheduled to run immediately
        assert mock_scheduler_instance.add_job.call_count == 2
        
        # Inspect first add_job call (periodic job)
        args_1, kwargs_1 = mock_scheduler_instance.add_job.call_args_list[0]
        assert kwargs_1['id'] == 'periodic_job_sync'
        assert kwargs_1['hours'] == job_scheduler.interval_hours
        
        # Inspect second add_job call (startup run)
        args_2, kwargs_2 = mock_scheduler_instance.add_job.call_args_list[1]
        assert kwargs_2['id'] == 'startup_job_sync'

def test_scheduler_task_execution_handling():
    """
    Tests that the scheduler task calls the collection service
    and catches exceptions without aborting.
    """
    mock_service = MagicMock(spec=CollectionService)
    # Simulate success
    mock_service.run_sync.return_value = {"collected": 10, "inserted": 5}
    
    with patch('app.scheduler.scheduler.BlockingScheduler'):
        job_scheduler = JobScheduler(collection_service=mock_service)
        
        # Execute the task callback directly
        job_scheduler._scheduled_task()
        
        # Verify collection service was invoked
        mock_service.run_sync.assert_called_once()

def test_scheduler_task_execution_resilience():
    """
    Verifies the scheduler task catch all fatal pipeline crashes
    to guarantee the daemon continues running.
    """
    mock_service = MagicMock(spec=CollectionService)
    # Simulate database / connection exception crash
    mock_service.run_sync.side_effect = Exception("Database is locked")
    
    with patch('app.scheduler.scheduler.BlockingScheduler'):
        job_scheduler = JobScheduler(collection_service=mock_service)
        
        # Executing the callback should NOT raise an exception
        try:
            job_scheduler._scheduled_task()
        except Exception as e:
            pytest.fail(f"Scheduler task did not catch internal exception: {e}")
            
        mock_service.run_sync.assert_called_once()
