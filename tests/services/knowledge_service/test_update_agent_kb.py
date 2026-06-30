from datetime import datetime

import pytest

from db.tables.types import IntegrationProvider
from services.knowledge_service import _implementation


def test_update_agent_kb_olo_returns_q_and_a_artifacts_with_manage_app_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeOloMenuProcessor:
        def __init__(self, debug: bool = False) -> None:
            self.debug = debug

        def process_and_index_menu_from_api(
            self,
            store_id: str,
            client_id: str,
            client_secret: str,
            pinecone_index_name: str,
            pinecone_namespace: str,
            general_api_endpoint: str,
        ) -> dict[str, object]:
            assert store_id == "restaurant-123"
            assert client_id == "client-id"
            assert client_secret == "client-secret"
            assert pinecone_index_name == "menu-index"
            assert pinecone_namespace == "menu-namespace"
            assert general_api_endpoint == "https://api.olo.com"
            return {
                "system_prompt_menu": "Menu prompt",
                "pinecone_namespace": pinecone_namespace,
                "pinecone_index_name": pinecone_index_name,
                "processed_items": 3,
                "restaurant_id": store_id,
            }

    monkeypatch.setattr(
        "services.knowledge_service.olo.OloMenuProcessor",
        FakeOloMenuProcessor,
    )

    result = _implementation.update_agent_kb(
        pos_provider=IntegrationProvider.olo,
        store_id="restaurant-123",
        client_id="client-id",
        client_secret="client-secret",
        token_api_endpoint="",
        general_api_endpoint="https://api.olo.com",
        pinecone_namespace="menu-namespace",
        pinecone_index_name="menu-index",
    )

    assert result["system_prompt_menu"] == "Menu prompt"
    assert result["pinecone_namespace"] == "menu-namespace"
    assert result["pinecone_index_name"] == "menu-index"
    assert result["processed_items"] == 3
    assert result["restaurant_id"] == "restaurant-123"
    assert result["menu_last_updated_source"] == "manage_app"
    datetime.fromisoformat(result["menu_last_updated"])
