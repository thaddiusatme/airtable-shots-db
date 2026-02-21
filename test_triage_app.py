import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


@pytest.fixture
def mock_airtable():
    with patch("triage_app.videos_table") as mock_table:
        mock_table.first.return_value = None
        yield mock_table


@pytest.fixture
def client():
    from triage_app import app
    return TestClient(app, follow_redirects=False)


def test_set_status_done_updates_airtable(client, mock_airtable):
    response = client.post(
        "/set-status",
        data={"record_id": "rec123", "status": "Done"}
    )
    
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    mock_airtable.update.assert_called_once_with("rec123", {"Triage Status": "Done"})


def test_set_status_declined_updates_airtable(client, mock_airtable):
    response = client.post(
        "/set-status",
        data={"record_id": "rec456", "status": "Declined"}
    )
    
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    mock_airtable.update.assert_called_once_with("rec456", {"Triage Status": "Declined"})


def test_set_status_skipped_updates_airtable(client, mock_airtable):
    response = client.post(
        "/set-status",
        data={"record_id": "rec789", "status": "Skipped"}
    )
    
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    mock_airtable.update.assert_called_once_with("rec789", {"Triage Status": "Skipped"})


def test_set_status_invalid_status_redirects_without_update(client, mock_airtable):
    response = client.post(
        "/set-status",
        data={"record_id": "rec999", "status": "InvalidStatus"}
    )
    
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    mock_airtable.update.assert_not_called()
