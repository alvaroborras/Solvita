from src.oracle.catalog import build_oracle_catalog


def test_catalog_exposes_family_ids_and_metadata():
    catalog = build_oracle_catalog()
    item = catalog["oracle.dp.topdown"]
    assert item["family_id"] == "oracle.dp.topdown"
    assert item["route_hint"] == "exact_single_answer"
    assert "tags" in item
