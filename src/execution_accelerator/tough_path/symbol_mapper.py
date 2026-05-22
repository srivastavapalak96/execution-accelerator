"""Step 3c of the tough-path ladder: map removed symbols to likely replacements.

For each removed/changed symbol from :class:`CompatibilityDiff`, we score
candidates from the new public API and pick the best deterministic match.
The scoring is a deliberately simple combination of:

* token Jaccard similarity over the symbol's identifier (``parseString`` vs
  ``parseAsString`` is a near-1.0 match);
* signature compatibility (param count + parameter type tokens);
* package proximity (matching the same parent package counts).

If the deterministic confidence is below ``DEFAULT_LLM_THRESHOLD`` (0.85), the
caller can optionally invoke an LLM via
:func:`execution_accelerator.llm.structured.structured_call` to enrich the
mapping with a rationale and a confidence override; the final stored confidence
is ``min(deterministic, llm)`` so an LLM cannot inflate trust in something it
made up.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final

from execution_accelerator.schemas import SymbolMappingEntry

from .api_diff import PublicApi, PublicSymbol

DEFAULT_LLM_THRESHOLD: Final[float] = 0.85
DEFAULT_AUTO_APPLY_THRESHOLD: Final[float] = 0.70
_TOKEN_PATTERN = re.compile(r"[A-Za-z][a-z]*|[A-Z]+(?=[A-Z]|$)|\d+")


@dataclass(frozen=True)
class SymbolCandidate:
    """One candidate replacement with its component score breakdown."""

    candidate: PublicSymbol
    name_score: float
    signature_score: float
    package_score: float
    confidence: float


@dataclass
class MappingProposal:
    """Mapper output for a single removed/changed symbol."""

    legacy_symbol: PublicSymbol
    top_candidates: list[SymbolCandidate] = field(default_factory=list)
    rationale: str = ""

    @property
    def best(self) -> SymbolCandidate | None:
        return self.top_candidates[0] if self.top_candidates else None

    def to_schema_entry(self) -> SymbolMappingEntry | None:
        """Render as the persisted :class:`SymbolMappingEntry` schema, or None if no candidate."""

        best = self.best
        if best is None:
            return None
        return SymbolMappingEntry(
            legacy_symbol=self.legacy_symbol.fqn,
            replacement_symbol=best.candidate.fqn,
            confidence=best.confidence,
            rationale=self.rationale or _default_rationale(self.legacy_symbol, best),
        )


def map_symbol(
    legacy: PublicSymbol,
    *,
    new_api: PublicApi,
    top_k: int = 3,
) -> MappingProposal:
    """Score every new-API symbol against ``legacy`` and return the top-K candidates.

    The proposal is returned even if no good candidate exists; callers should
    inspect ``.best.confidence`` against :data:`DEFAULT_AUTO_APPLY_THRESHOLD`
    before applying.
    """

    legacy_tokens = _tokenize(legacy.fqn.split("#")[-1].split("(")[0])
    legacy_params = _parse_param_types(legacy.signature)
    legacy_package = _package_of(legacy)

    scored: list[SymbolCandidate] = []
    for candidate_symbol in new_api.by_fqn.values():
        if candidate_symbol.kind != legacy.kind:
            continue
        candidate_tokens = _tokenize(candidate_symbol.fqn.split("#")[-1].split("(")[0])
        candidate_params = _parse_param_types(candidate_symbol.signature)
        candidate_package = _package_of(candidate_symbol)

        name_score = _jaccard(legacy_tokens, candidate_tokens)
        signature_score = _signature_score(legacy_params, candidate_params)
        package_score = _package_score(legacy_package, candidate_package)
        confidence = round(0.6 * name_score + 0.3 * signature_score + 0.1 * package_score, 4)
        if confidence <= 0.0:
            continue
        scored.append(
            SymbolCandidate(
                candidate=candidate_symbol,
                name_score=name_score,
                signature_score=signature_score,
                package_score=package_score,
                confidence=confidence,
            )
        )

    scored.sort(key=lambda s: s.confidence, reverse=True)
    return MappingProposal(legacy_symbol=legacy, top_candidates=scored[:top_k])


def map_diff(
    *,
    removed_symbols: list[PublicSymbol],
    new_api: PublicApi,
    top_k: int = 3,
) -> list[MappingProposal]:
    """Run :func:`map_symbol` for every removed legacy symbol."""

    return [map_symbol(symbol, new_api=new_api, top_k=top_k) for symbol in removed_symbols]


def reconcile_with_llm_confidence(
    proposal: MappingProposal,
    *,
    llm_confidence: float,
    llm_rationale: str,
) -> MappingProposal:
    """Combine the deterministic candidate score with an LLM-provided confidence.

    Final confidence is ``min(deterministic, llm)`` -- never let the LLM inflate
    trust above what similarity scoring justifies.
    """

    best = proposal.best
    if best is None:
        return proposal
    capped = min(best.confidence, max(0.0, min(1.0, llm_confidence)))
    new_best = SymbolCandidate(
        candidate=best.candidate,
        name_score=best.name_score,
        signature_score=best.signature_score,
        package_score=best.package_score,
        confidence=round(capped, 4),
    )
    return MappingProposal(
        legacy_symbol=proposal.legacy_symbol,
        top_candidates=[new_best, *proposal.top_candidates[1:]],
        rationale=llm_rationale or proposal.rationale,
    )


# --- internals ---------------------------------------------------------------


def _tokenize(name: str) -> set[str]:
    return {token.lower() for token in _TOKEN_PATTERN.findall(name)}


def _parse_param_types(signature: str) -> tuple[str, ...]:
    """Best-effort extraction of comma-separated parameter type tokens."""

    paren = re.search(r"\(([^)]*)\)", signature)
    if paren is None:
        return ()
    body = paren.group(1).strip()
    if not body:
        return ()
    types: list[str] = []
    for piece in _split_top_level(body, separator=","):
        clean = piece.strip()
        if not clean:
            continue
        # Trim parameter names: `String name` -> `String`.
        first_token = clean.split()[0]
        types.append(first_token)
    return tuple(types)


def _split_top_level(body: str, *, separator: str) -> list[str]:
    """Split ``body`` on ``separator`` ignoring nested generics ``<...>``."""

    pieces: list[str] = []
    depth = 0
    current: list[str] = []
    for char in body:
        if char == "<":
            depth += 1
        elif char == ">" and depth > 0:
            depth -= 1
        if char == separator and depth == 0:
            pieces.append("".join(current))
            current = []
            continue
        current.append(char)
    if current:
        pieces.append("".join(current))
    return pieces


def _package_of(symbol: PublicSymbol) -> str:
    fqn = symbol.fqn.split("#")[0]
    if "." not in fqn:
        return ""
    return fqn.rsplit(".", 1)[0]


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _signature_score(left_params: tuple[str, ...], right_params: tuple[str, ...]) -> float:
    if not left_params and not right_params:
        return 1.0
    if len(left_params) != len(right_params):
        return 0.0
    matches = sum(1 for a, b in zip(left_params, right_params, strict=False) if a == b)
    return matches / len(left_params)


def _package_score(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    left_parts = left.split(".")
    right_parts = right.split(".")
    common = 0
    for left_segment, right_segment in zip(left_parts, right_parts, strict=False):
        if left_segment != right_segment:
            break
        common += 1
    if common == 0:
        return 0.0
    return common / max(len(left_parts), len(right_parts))


def _default_rationale(legacy: PublicSymbol, best: SymbolCandidate) -> str:
    return (
        f"Deterministic similarity: name={best.name_score:.2f}, "
        f"signature={best.signature_score:.2f}, package={best.package_score:.2f}; "
        f"legacy {legacy.fqn} -> {best.candidate.fqn}."
    )
