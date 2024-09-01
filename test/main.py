from ..main import app
from fastapi.testclient import TestClient
import pytest

client = TestClient(app)


