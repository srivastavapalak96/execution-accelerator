"""Unit tests for execution_accelerator.tough_path.symbol_mapper."""

from __future__ import annotations

from execution_accelerator.tough_path.api_diff import PublicApi, PublicSymbol
from execution_accelerator.tough_path.symbol_mapper import (
    map_diff,
    map_symbol,
    reconcile_with_llm_confidence,
)


def _api_with(*symbols: PublicSymbol) -> PublicApi:
    return PublicApi(by_fqn={sym.fqn: sym for sym in symbols})


def test_map_symbol_prefers_token_overlap() -> None:
    legacy = PublicSymbol(
        fqn="org.example.Parser#parseString(String input)",
        kind="method",
        signature="public Object parseString(String input)",
    )
    new_api = _api_with(
        PublicSymbol(
            fqn="org.example.Parser#parseAsString(String text)",
            kind="method",
            signature="public Object parseAsString(String text)",
        ),
        PublicSymbol(
            fqn="org.example.Parser#totallyUnrelated(int)",
            kind="method",
            signature="public Object totallyUnrelated(int)",
        ),
    )

    proposal = map_symbol(legacy, new_api=new_api)
    assert proposal.best is not None
    assert "parseAsString" in proposal.best.candidate.fqn
    # Token overlap (parse, string) gives a strong name score; signature is a
    # 1:1 String match. Confidence should be >= the auto-apply threshold.
    assert proposal.best.confidence > 0.5


def test_map_symbol_returns_empty_when_no_kind_match() -> None:
    legacy = PublicSymbol(fqn="X#m()", kind="method", signature="public void m()")
    new_api = _api_with(
        PublicSymbol(fqn="X", kind="class", signature="public class X"),
    )
    proposal = map_symbol(legacy, new_api=new_api)
    assert proposal.best is None


def test_map_diff_maps_each_removed_symbol() -> None:
    removed = [
        PublicSymbol(fqn="X#a()", kind="method", signature="public void a()"),
        PublicSymbol(fqn="X#b()", kind="method", signature="public void b()"),
    ]
    new_api = _api_with(
        PublicSymbol(fqn="X#aOk()", kind="method", signature="public void aOk()"),
        PublicSymbol(fqn="X#bOk()", kind="method", signature="public void bOk()"),
    )
    proposals = map_diff(removed_symbols=removed, new_api=new_api)
    assert len(proposals) == 2
    assert all(p.best is not None for p in proposals)


def test_reconcile_with_llm_caps_confidence_at_min() -> None:
    legacy = PublicSymbol(
        fqn="org.example.Parser#parseString(String x)",
        kind="method",
        signature="public Object parseString(String x)",
    )
    new_api = _api_with(
        PublicSymbol(
            fqn="org.example.Parser#parseString(String x)",
            kind="method",
            signature="public Object parseString(String x)",
        ),
    )
    proposal = map_symbol(legacy, new_api=new_api)
    deterministic = proposal.best.confidence  # type: ignore[union-attr]
    # An over-confident LLM (0.99) cannot inflate above the deterministic score.
    enriched = reconcile_with_llm_confidence(
        proposal,
        llm_confidence=0.99,
        llm_rationale="LLM says exact match",
    )
    assert enriched.best is not None
    assert enriched.best.confidence == round(min(deterministic, 0.99), 4)
    assert enriched.rationale == "LLM says exact match"


def test_reconcile_with_llm_lowers_confidence_when_llm_disagrees() -> None:
    legacy = PublicSymbol(
        fqn="X#m()",
        kind="method",
        signature="public void m()",
    )
    new_api = _api_with(
        PublicSymbol(fqn="X#m()", kind="method", signature="public void m()"),
    )
    proposal = map_symbol(legacy, new_api=new_api)
    enriched = reconcile_with_llm_confidence(
        proposal,
        llm_confidence=0.30,
        llm_rationale="not actually equivalent due to behavior change",
    )
    assert enriched.best is not None
    assert enriched.best.confidence == 0.30


def test_proposal_to_schema_entry_returns_none_without_candidates() -> None:
    legacy = PublicSymbol(fqn="X#m()", kind="method", signature="public void m()")
    new_api = _api_with()  # empty
    proposal = map_symbol(legacy, new_api=new_api)
    assert proposal.to_schema_entry() is None


def test_proposal_to_schema_entry_renders_default_rationale() -> None:
    legacy = PublicSymbol(
        fqn="org.example.Foo#bar(String x)",
        kind="method",
        signature="public void bar(String x)",
    )
    new_api = _api_with(
        PublicSymbol(
            fqn="org.example.Foo#bar(String x)",
            kind="method",
            signature="public void bar(String x)",
        ),
    )
    proposal = map_symbol(legacy, new_api=new_api)
    entry = proposal.to_schema_entry()
    assert entry is not None
    assert entry.legacy_symbol == "org.example.Foo#bar(String x)"
    assert entry.replacement_symbol == "org.example.Foo#bar(String x)"
    assert "Deterministic similarity" in entry.rationale
