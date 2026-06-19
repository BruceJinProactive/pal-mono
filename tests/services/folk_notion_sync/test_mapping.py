from __future__ import annotations

from services.folk_notion_sync._mapping import (
    build_notion_properties,
    project_company_sync,
)

EXPECTED_TARGET_DATA_SOURCE_PROPERTY_TYPES = {
    "AE": "people",
    "FDE": "people",
    "Folk Active Status": "rich_text",
    "Folk Assign": "rich_text",
    "Folk Billing Details": "rich_text",
    "Folk Billing Method": "rich_text",
    "Folk Billing Status": "rich_text",
    "Folk Brand Structure": "rich_text",
    "Folk CARR": "number",
    "Folk Company Addresses": "rich_text",
    "Folk Company Description": "rich_text",
    "Folk Company Emails": "rich_text",
    "Folk Company IDs": "rich_text",
    "Folk Company Phones": "rich_text",
    "Folk Company URLs": "rich_text",
    "Folk Contract Signed Date": "date",
    "Folk Cuisine Type": "rich_text",
    "Folk Deal IDs": "rich_text",
    "Folk Deal Locations": "number",
    "Folk Deal Summary": "rich_text",
    "Folk Deal URLs": "rich_text",
    "Folk Go-live Date": "date",
    "Folk Industry": "rich_text",
    "Folk Key Account": "rich_text",
    "Folk Lead Source": "rich_text",
    "Folk Live Locations": "number",
    "Folk Price Per Month Per Location": "number",
    "Folk Primary Contacts": "rich_text",
    "Folk Stages": "rich_text",
    "Folk Sync Error": "rich_text",
    "Folk Tier": "rich_text",
    "Folk Total Locations": "number",
    "Last Folk Sync At": "date",
    "Last Folk Sync Source": "select",
    "Name": "title",
    "Products": "multi_select",
    "Stage": "status",
    "Vendors": "multi_select",
}


def test_build_notion_properties_maps_deal_and_company_fields() -> None:
    deal = {
        "id": "obj_123",
        "name": "Houston TX Hot Chicken - Voice AI",
        "companies": [{"id": "com_123", "name": "Houston TX Hot Chicken"}],
        "customFieldValues": {
            "Stage": "2. Meeting set (Sales)",
            "AE": [
                {
                    "id": "usr_54a1621e-141a-4fb8-a372-f4103ee89664",
                    "fullName": "Ashley Hart",
                    "email": "ashley@proactiveailab.com",
                }
            ],
            "FDE": [
                {
                    "id": "usr_93d81c01-abb9-42b9-9f7f-9e8e281fdae8",
                    "fullName": "Andrew Li",
                    "email": "andrew.li@proactiveailab.com",
                }
            ],
            "Product(s)": "Voice AI - Integration (Any)",
            "Vendors": ["Toast"],
            "Total Locations": "5",
            "Deal Locations": "5",
            "Lead Source": ["Demo Call (Inbound)"],
            "Price Per Month Per Location": "$125.50",
        },
    }
    second_deal = {
        "id": "obj_456",
        "name": "Houston TX Hot Chicken - Catering AI",
        "companies": [{"id": "com_123", "name": "Houston TX Hot Chicken"}],
        "customFieldValues": {
            "Stage": "6. Contract signed (Post-Sale)",
            "Product(s)": "Catering AI",
            "Vendors": [{"name": "Toast"}],
            "Total Locations": "12",
        },
    }
    unrelated_deal = {
        "id": "obj_999",
        "name": "Other Restaurant - Voice AI",
        "companies": [{"id": "com_999", "name": "Other Restaurant"}],
        "customFieldValues": {
            "Stage": "9. Retention (Post-Sale)",
            "Product(s)": "Vision AI - Analytics/Operation",
        },
    }
    company = {
        "id": "com_123",
        "name": "Houston TX Hot Chicken",
        "description": "Restaurant group",
        "industry": "Restaurants",
        "emails": ["info@hhc.ooo"],
        "phones": ["+12814828820"],
        "urls": ["https://hhc.ooo"],
        "addresses": [],
        "customFieldValues": {"grp_test": {"Cuisine Type": ["Chicken/Burger"]}},
    }
    projection = project_company_sync(
        deal,
        [deal, second_deal, unrelated_deal],
        company,
        "grp_test",
    )

    props = build_notion_properties(projection, source="webhook", include_title=True)
    deal_ids = props["Folk Deal IDs"]["rich_text"][0]["text"]["content"].split("\n")

    assert props["Name"]["title"][0]["text"]["content"] == "Houston TX Hot Chicken"
    assert set(deal_ids) == {"obj_123", "obj_456"}
    assert "obj_999" not in deal_ids
    assert props["Folk Company IDs"]["rich_text"][0]["text"]["content"] == "com_123"
    assert props["Stage"]["status"]["name"] == "S6 Onboarding"
    assert props["Folk Total Locations"]["number"] is None
    assert props["Folk Deal Locations"]["number"] == 5.0
    assert props["Folk Price Per Month Per Location"]["number"] == 125.50
    assert (
        props["Folk Company Emails"]["rich_text"][0]["text"]["content"]
        == "info@hhc.ooo"
    )
    assert props["AE"]["people"] == [{"id": "321d872b-594c-8138-9328-0002cb20bec6"}]
    assert props["FDE"]["people"] == [{"id": "2b6d872b-594c-817f-a134-00020c633368"}]
    assert props["Products"]["multi_select"] == [
        {"name": "Catering AI"},
        {"name": "Voice AI - Integration (Any)"},
    ]
    assert props["Vendors"]["multi_select"] == [{"name": "Toast"}]


def test_build_notion_properties_matches_target_data_source_property_types() -> None:
    deal = {
        "id": "obj_123",
        "name": "Acme - Voice AI",
        "companies": [{"id": "com_123", "name": "Acme"}],
        "customFieldValues": {
            "Stage": "6. Contract signed (Post-Sale)",
            "AE": [{"fullName": "Ashley Hart"}],
            "FDE": [{"fullName": "Andrew Li"}],
            "Product(s)": "Voice AI - Integration (Any)",
            "Vendors": ["Toast"],
            "Total Locations": "5",
            "Deal Locations": "5",
            "Live locations": "3",
            "Price Per Month Per Location": "$125.50",
            "CARR": "$7,530",
            "Contract Signed Date": "2026-06-19",
            "Go-live Date": "2026-07-01",
        },
    }
    company = {
        "id": "com_123",
        "name": "Acme",
        "customFieldValues": {},
    }
    projection = project_company_sync(deal, [deal], company, "grp_test")

    props = build_notion_properties(projection, source="webhook", include_title=True)

    assert set(props) == set(EXPECTED_TARGET_DATA_SOURCE_PROPERTY_TYPES)
    for (
        property_name,
        expected_type,
    ) in EXPECTED_TARGET_DATA_SOURCE_PROPERTY_TYPES.items():
        assert set(props[property_name]) == {expected_type}, property_name


def test_build_notion_properties_clears_empty_owned_people_and_select_fields() -> None:
    deal = {
        "id": "obj_123",
        "name": "Acme - Voice AI",
        "companies": [{"id": "com_123", "name": "Acme"}],
        "customFieldValues": {},
    }
    company = {
        "id": "com_123",
        "name": "Acme",
        "customFieldValues": {},
    }
    projection = project_company_sync(deal, [deal], company, "grp_test")

    props = build_notion_properties(projection, source="webhook", include_title=False)

    assert props["AE"]["people"] == []
    assert props["FDE"]["people"] == []
    assert props["Products"]["multi_select"] == []
    assert props["Vendors"]["multi_select"] == []
