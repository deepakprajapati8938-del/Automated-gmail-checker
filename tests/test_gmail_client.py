import pytest
from pathlib import Path
from app.email.gmail import GmailClient, GmailAuthError

def test_missing_oauth_token(tmp_path):
    token_path = tmp_path / "missing.json"
    state_path = tmp_path / "state.json"
    
    with pytest.raises(GmailAuthError, match="No Gmail token found"):
        GmailClient(token_path, state_path)

def test_invalid_oauth_token(tmp_path):
    token_path = tmp_path / "invalid.json"
    state_path = tmp_path / "state.json"
    
    token_path.write_text("not real json")
    
    with pytest.raises(Exception):
        # We expect it to raise either GmailAuthError or a JSON decoding error 
        # from google.oauth2.credentials (which translates into a failed startup)
        GmailClient(token_path, state_path)
