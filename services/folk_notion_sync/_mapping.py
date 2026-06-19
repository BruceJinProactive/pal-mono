from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

NOTION_USER_IDS_BY_NAME = {
    "Ali Templin": "2d9d872b-594c-816c-87f7-000267db431f",
    "Andrew Li": "2b6d872b-594c-817f-a134-00020c633368",
    "Ashley Hart": "321d872b-594c-8138-9328-0002cb20bec6",
    "Audrey Lee": "28cd872b-594c-81b3-8aa7-0002c5a63b81",
    "Auston Baker": "2bcd872b-594c-812e-9eb1-0002b2a11c94",
    "Bruce Jin": "ff017984-993b-4712-a8fc-5d7cd6fd4ac0",
    "Gray Wong": "173d872b-594c-8112-8a3f-0002f6a0cc04",
    "Jeffrey Crooks": "229d872b-594c-81a1-8f1e-0002851f5b6f",
    "Jeffrey Weisinger": "2e3d872b-594c-81e7-b8ca-0002a5a0e9aa",
    "Maria Zhang": "142cb688-3e8d-4cc2-ab9a-05ef31354fd1",
    "Rena Ogura": "304d872b-594c-81c8-b52b-0002388d690d",
    "Rui Wang": "2a5d872b-594c-818a-9fbf-00025be9172b",
    "Thy Tran": "2e3d872b-594c-8123-8b65-000223f154c8",
}


@dataclass(frozen=True)
class DealProjection:
    id: str
    name: str
    company_id: str
    company_name: str
    stage: str
    ae: str
    fde: str
    product: str
    vendors: str
    total_locations: str
    deal_locations: str
    live_locations: str
    contract_signed_date: str
    go_live_date: str
    lead_source: str
    billing_details: str
    billing_method: str
    billing_status: str
    brand_structure: str
    key_account: str
    carr: str
    price_per_month_per_location: str


@dataclass(frozen=True)
class CompanyProjection:
    key: str
    name: str
    company_id: str
    deals: list[DealProjection]
    industry: str
    cuisine_type: str
    description: str
    addresses: str
    emails: str
    phones: str
    urls: str
    primary_contacts: str


def project_company_sync(
    target_deal: dict[str, Any],
    group_deals: list[dict[str, Any]],
    company: dict[str, Any],
    group_id: str,
) -> CompanyProjection:
    company_id = str(company.get("id") or "")
    relevant_deals = [
        deal
        for deal in group_deals
        if _first_company_id(deal) == company_id
        or (not company_id and deal.get("id") == target_deal.get("id"))
    ]
    if not relevant_deals:
        relevant_deals = [target_deal]

    company_fields = custom_fields(company, group_id)
    name = str(
        company.get("name")
        or company_fields.get("Account Name")
        or _first_company_name(target_deal)
        or target_deal.get("name")
        or "Untitled"
    )

    deals = [
        project_deal(deal, company, group_id)
        for deal in sorted(relevant_deals, key=lambda item: str(item.get("name", "")))
    ]
    return CompanyProjection(
        key=company_id or str(target_deal.get("id", "")),
        name=name,
        company_id=company_id,
        deals=deals,
        industry=format_value(company.get("industry")),
        cuisine_type=format_value(company_fields.get("Cuisine Type")),
        description=format_value(company.get("description")),
        addresses=format_value(company.get("addresses")),
        emails=format_value(company.get("emails")),
        phones=format_value(company.get("phones")),
        urls=format_value(company.get("urls")),
        primary_contacts=format_value(company_fields.get("Primary Contact(s)")),
    )


def project_deal(
    deal: dict[str, Any],
    company: dict[str, Any],
    group_id: str,
) -> DealProjection:
    deal_fields = custom_fields(deal, group_id)
    company_fields = custom_fields(company, group_id)
    company_id = _first_company_id(deal) or str(company.get("id") or "")
    company_name = _first_company_name(deal) or str(company.get("name") or "")
    return DealProjection(
        id=str(deal.get("id") or ""),
        name=str(deal.get("name") or company_name or "Untitled deal"),
        company_id=company_id,
        company_name=company_name,
        stage=format_value(deal_fields.get("Stage")),
        ae=format_value(deal_fields.get("AE") or company_fields.get("AE")),
        fde=format_value(deal_fields.get("FDE") or company_fields.get("FDE")),
        product=format_value(
            deal_fields.get("Product(s)") or company_fields.get("Product(s)")
        ),
        vendors=format_value(
            deal_fields.get("Vendors") or company_fields.get("Vendors")
        ),
        total_locations=format_value(
            deal_fields.get("Total Locations") or company_fields.get("Total Locations")
        ),
        deal_locations=format_value(deal_fields.get("Deal Locations")),
        live_locations=format_value(deal_fields.get("Live locations")),
        contract_signed_date=format_value(deal_fields.get("Contract Signed Date")),
        go_live_date=format_value(deal_fields.get("Go-live Date")),
        lead_source=format_value(deal_fields.get("Lead Source")),
        billing_details=format_value(deal_fields.get("Billing Details")),
        billing_method=format_value(deal_fields.get("Billing Method")),
        billing_status=format_value(deal_fields.get("Billing Status")),
        brand_structure=format_value(deal_fields.get("Brand Structure")),
        key_account=format_value(deal_fields.get("Key Account")),
        carr=format_value(deal_fields.get("CARR")),
        price_per_month_per_location=format_value(
            deal_fields.get("Price Per Month Per Location")
        ),
    )


def build_notion_properties(
    company: CompanyProjection,
    *,
    source: str,
    include_title: bool,
) -> dict[str, Any]:
    deal_ids = [deal.id for deal in company.deals if deal.id]
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    stages = combine_values(company.deals, "stage")
    products = combine_values(company.deals, "product")
    vendors = combine_values(company.deals, "vendors")
    props: dict[str, Any] = {
        "Folk Deal IDs": text_property(text_join(deal_ids)),
        "Folk Deal URLs": text_property(
            text_join([deal_url(deal.id) for deal in company.deals])
        ),
        "Folk Company IDs": text_property(company.company_id),
        "Folk Company URLs": text_property(company_url(company.company_id)),
        "Folk Deal Summary": text_property(
            "\n".join(f"{deal.name} ({deal.id})" for deal in company.deals)
        ),
        "Folk Stages": text_property(stages),
        "Folk Active Status": text_property(""),
        "Folk Tier": text_property(""),
        "Folk Brand Structure": text_property(
            combine_values(company.deals, "brand_structure")
        ),
        "Folk Key Account": text_property(combine_values(company.deals, "key_account")),
        "Folk Total Locations": number_property(
            combine_values(company.deals, "total_locations")
        ),
        "Folk Deal Locations": number_property(
            combine_values(company.deals, "deal_locations")
        ),
        "Folk Live Locations": number_property(
            combine_values(company.deals, "live_locations")
        ),
        "Folk Price Per Month Per Location": text_property(
            combine_values(company.deals, "price_per_month_per_location")
        ),
        "Folk CARR": number_property(combine_values(company.deals, "carr")),
        "Folk Industry": text_property(company.industry),
        "Folk Cuisine Type": text_property(company.cuisine_type),
        "Folk Lead Source": text_property(combine_values(company.deals, "lead_source")),
        "Folk Primary Contacts": text_property(company.primary_contacts),
        "Folk Company Addresses": text_property(company.addresses),
        "Folk Company Emails": text_property(company.emails),
        "Folk Company Phones": text_property(company.phones),
        "Folk Company Description": text_property(company.description),
        "Folk Contract Signed Date": date_property(
            combine_values(company.deals, "contract_signed_date")
        ),
        "Folk Go-live Date": date_property(
            combine_values(company.deals, "go_live_date")
        ),
        "Folk Billing Details": text_property(
            combine_values(company.deals, "billing_details")
        ),
        "Folk Billing Method": text_property(
            combine_values(company.deals, "billing_method")
        ),
        "Folk Billing Status": text_property(
            combine_values(company.deals, "billing_status")
        ),
        "Folk Assign": text_property(
            text_join(
                [
                    combine_values(company.deals, "ae"),
                    combine_values(company.deals, "fde"),
                ]
            )
        ),
        "Last Folk Sync At": {"date": {"start": now}},
        "Last Folk Sync Source": select_property(source),
        "Folk Sync Error": text_property(""),
        "Stage": status_property(stage_option(stages)),
    }
    if include_title:
        props["Name"] = title_property(company.name)
    ae = combine_values(company.deals, "ae")
    fde = combine_values(company.deals, "fde")
    props["AE"] = people_property(ae)
    props["FDE"] = people_property(fde)
    props["Products"] = multi_select_property(product_options(products))
    props["Vendors"] = multi_select_property(split_values(vendors))
    return props


def custom_fields(item: dict[str, Any], group_id: str) -> dict[str, Any]:
    custom_values = item.get("customFieldValues")
    if not isinstance(custom_values, dict):
        return {}
    group_values = custom_values.get(group_id)
    if isinstance(group_values, dict):
        return group_values
    return custom_values


def format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        parts = [format_value(item) for item in value if item is not None]
        return "; ".join(part for part in parts if part)
    if isinstance(value, dict):
        return str(
            value.get("fullName")
            or value.get("name")
            or value.get("label")
            or value.get("email")
            or value.get("id")
            or ""
        )
    return str(value)


def combine_values(deals: list[DealProjection], attr: str) -> str:
    values: list[str] = []
    for deal in deals:
        value = getattr(deal, attr)
        if value and value not in values:
            values.append(value)
    return "; ".join(values)


def text_property(value: str) -> dict[str, Any]:
    content = value[:2000]
    if not content:
        return {"rich_text": []}
    return {"rich_text": [{"text": {"content": content}}]}


def title_property(value: str) -> dict[str, Any]:
    return {"title": [{"text": {"content": value[:2000] or "Untitled"}}]}


def select_property(value: str) -> dict[str, Any]:
    return {"select": {"name": value}} if value else {"select": None}


def status_property(value: str) -> dict[str, Any]:
    return {"status": {"name": value}} if value else {"status": None}


def multi_select_property(values: list[str]) -> dict[str, Any]:
    return {"multi_select": [{"name": value[:100]} for value in values if value]}


def number_property(value: str) -> dict[str, Any]:
    scalar_value = _single_combined_value(value)
    if not scalar_value:
        return {"number": None}
    match = re.search(r"-?\d+(?:\.\d+)?", scalar_value.replace(",", ""))
    return {"number": float(match.group(0)) if match else None}


def date_property(value: str) -> dict[str, Any]:
    scalar_value = _single_combined_value(value)
    if not scalar_value:
        return {"date": None}
    match = re.search(r"\d{4}-\d{2}-\d{2}", scalar_value)
    if not match:
        return {"date": None}
    return {"date": {"start": match.group(0)}}


def _single_combined_value(value: str) -> str:
    parts = [part.strip() for part in value.split(";") if part.strip()]
    return parts[0] if len(parts) == 1 else ""


def people_property(names_text: str) -> dict[str, Any]:
    people = []
    for name in split_values(names_text):
        user_id = NOTION_USER_IDS_BY_NAME.get(name)
        if user_id:
            people.append({"id": user_id})
    return {"people": people}


def split_values(value: str) -> list[str]:
    seen: list[str] = []
    for part in re.split(r";|,", value or ""):
        cleaned = part.strip()
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def text_join(values: list[str]) -> str:
    seen: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return "\n".join(seen)


def product_options(value: str) -> list[str]:
    options: list[str] = []
    for product in split_values(value):
        if product == "Voice AI - Answering Only":
            mapped = ["Answering"]
        elif product in {"Voice AI - Integration (Any)", "Voice AI Premium 1000 Calls"}:
            mapped = ["Voice AI - Integration (Any)"]
        elif product == "Vision AI - Analytics/Operation":
            mapped = ["Vision"]
        elif product == "Catering AI":
            mapped = ["Catering AI"]
        elif product == "Voice AI + Vision AI":
            mapped = ["Voice AI - Integration (Any)", "Vision"]
        elif product == "Voice AI + Vision AI + Catering AI":
            mapped = ["Voice + Vision + Catering AI"]
        elif product == "Vision AI + Catering AI":
            mapped = ["Vision AI + Catering AI"]
        else:
            mapped = [product]
        for item in mapped:
            if item not in options:
                options.append(item)
    return options


def stage_option(stages_text: str) -> str:
    stages = split_values(stages_text)
    ranks = [
        ("9.", "S9 Retention"),
        ("8a.", "S8 Expansion"),
        ("8b.", "S8 Expansion"),
        ("7a.", "S7 Piloting"),
        ("7b.", "S7 Piloting"),
        ("6.", "S6 Onboarding"),
        ("5.", "S6 Onboarding"),
        ("4.", "Pre-sales"),
        ("3.", "Pre-sales"),
        ("2.", "Pre-sales"),
        ("1.", "Pre-sales"),
        ("0.", "Pre-sales"),
    ]
    if any(
        stage in {"Closed Lost", "Disqualified", "Onboarding Failed"}
        for stage in stages
    ):
        return "Lost"
    for prefix, notion_stage in ranks:
        if any(stage.startswith(prefix) for stage in stages):
            return notion_stage
    return "Pre-sales"


def normalize_name(value: str) -> str:
    normalized = value.casefold()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(
        r"\b(inc|llc|ltd|co|company|corp|corporation|restaurant|restaurants|group|hospitality)\b",
        " ",
        normalized,
    )
    return re.sub(r"\s+", " ", normalized).strip()


def deal_url(deal_id: str) -> str:
    return f"https://app.folk.app/apps/contacts/deals/{deal_id}" if deal_id else ""


def company_url(company_id: str) -> str:
    return (
        f"https://app.folk.app/apps/contacts/companies/{company_id}"
        if company_id
        else ""
    )


def _first_company_id(deal: dict[str, Any]) -> str:
    company = _first_company(deal)
    return str(company.get("id") or "") if company else ""


def _first_company_name(deal: dict[str, Any]) -> str:
    company = _first_company(deal)
    return str(company.get("name") or "") if company else ""


def _first_company(deal: dict[str, Any]) -> dict[str, Any] | None:
    value = deal.get("companies")
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    value = deal.get("company")
    if isinstance(value, dict):
        return value
    return None
