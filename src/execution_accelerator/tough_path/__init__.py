"""Tough-path ladder: recipe-first, deterministic-second, decompile-third, LLM-last.

Modules:

* :mod:`recipe_matcher` — step 1, YAML-driven OpenRewrite recipe lookup.
* :mod:`decompiler` — step 3a, Maven JAR download + CFR decompile (sha256-keyed cache).
* :mod:`api_diff` — step 3b, public-API extraction + diff over the decompiled tree.
* :mod:`symbol_mapper` — step 3c, deterministic similarity scoring with optional LLM enrichment.

Steps 2 (JavaParser deterministic structural edits) and 4 (LLM patch generator)
are still planned; the pieces above plug into the complex subgraph composed by
:mod:`execution_accelerator.subgraphs.complex` (see Tier C4).
"""

from .api_diff import (
    CompatibilityDiff,
    PublicApi,
    PublicSymbol,
    diff_public_apis,
    extract_public_api,
)
from .decompiler import (
    DEFAULT_CACHE_ROOT,
    DEFAULT_CFR_JAR_PATH,
    DEFAULT_MAVEN_BASE_URL,
    DecompiledArtifact,
    DecompilerDownloadError,
    DecompilerError,
    DecompilerToolMissing,
    build_artifact_url,
    decompile_jar,
    download_artifact,
)
from .recipe_matcher import (
    RECIPE_REGISTRY_PATH,
    RecipeMatch,
    RecipeMatchInput,
    RecipeRegistry,
    load_recipe_registry,
    match_recipe,
)
from .symbol_mapper import (
    DEFAULT_AUTO_APPLY_THRESHOLD,
    DEFAULT_LLM_THRESHOLD,
    MappingProposal,
    SymbolCandidate,
    map_diff,
    map_symbol,
    reconcile_with_llm_confidence,
)

__all__ = [
    "CompatibilityDiff",
    "DEFAULT_AUTO_APPLY_THRESHOLD",
    "DEFAULT_CACHE_ROOT",
    "DEFAULT_CFR_JAR_PATH",
    "DEFAULT_LLM_THRESHOLD",
    "DEFAULT_MAVEN_BASE_URL",
    "DecompiledArtifact",
    "DecompilerDownloadError",
    "DecompilerError",
    "DecompilerToolMissing",
    "MappingProposal",
    "PublicApi",
    "PublicSymbol",
    "RECIPE_REGISTRY_PATH",
    "RecipeMatch",
    "RecipeMatchInput",
    "RecipeRegistry",
    "SymbolCandidate",
    "build_artifact_url",
    "decompile_jar",
    "diff_public_apis",
    "download_artifact",
    "extract_public_api",
    "load_recipe_registry",
    "map_diff",
    "map_symbol",
    "match_recipe",
    "reconcile_with_llm_confidence",
]
