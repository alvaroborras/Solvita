from src.heuristic.knowledge import StrategyCard, StrategyStore


def test_strategy_promotion_requires_two_families_or_human(tmp_path):
    store = StrategyStore(tmp_path / "strategies.sqlite3")
    card = StrategyCard("lns", "destroy and repair", domains=("packing",))
    store.put(card)
    store.add_evidence("lns", "ogc", "scheduling", 1.0)
    store.add_evidence("lns", "ogc-2", "scheduling", -2.0)
    assert [row["delta"] for row in store.evidence("lns")] == [1.0, -2.0]
    assert all(row["causal"] == 0 for row in store.evidence("lns"))
    assert store.promote_eligible() == []
    store.add_evidence("lns", "binpack", "packing", 0.5)
    assert store.promote_eligible() == ["lns"]
    assert store.retrieve(domain="packing")[0].card_id == "lns"

    second = StrategyCard("restart", "adaptive restart")
    store.put(second)
    store.approve_global("restart", approved_by="tester")
    assert {card.card_id for card in store.retrieve()} == {"lns", "restart"}


def test_incubator_cards_remain_owner_problem_local(tmp_path):
    store = StrategyStore(tmp_path / "strategies.sqlite3")
    store.put(
        StrategyCard(
            "local",
            "local scheduling trick",
            domains=("scheduling",),
            owner_problem="ogc",
        )
    )
    assert store.retrieve(domain="scheduling", include_incubator=True, problem_id="ogc")
    assert not store.retrieve(
        domain="scheduling", include_incubator=True, problem_id="other"
    )
