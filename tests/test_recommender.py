"""Recommender: NIST algorithm selection, level scoring, and context handling."""

from __future__ import annotations

import json

from pqc_migrator.context.context import AppContext, load_context
from pqc_migrator.models import Finding
from pqc_migrator.recommender.recommend import algorithms_used, recommend, recommend_all


def make_finding(purpose="kem", algorithm="rsa", matched="rsa.generate_private_key",
                 snippet="") -> Finding:
    return Finding(
        file="app.py",
        line=1,
        algorithm=algorithm,
        purpose=purpose,
        matched=matched,
        library="cryptography",
        snippet=snippet,
    )


def test_kem_purpose_maps_to_ml_kem_per_level():
    for level, expected in [(1, "ML-KEM-512"), (3, "ML-KEM-768"), (5, "ML-KEM-1024")]:
        recommendation = recommend(make_finding(), AppContext(security_level=level))
        assert recommendation.pqc_algorithm == expected
        assert recommendation.nist_standard == "FIPS 203"
        assert recommendation.nist_level == level


def test_key_exchange_also_maps_to_ml_kem():
    recommendation = recommend(
        make_finding(purpose="key_exchange", algorithm="dh", matched="dh.generate_parameters"),
        AppContext(security_level=3),
    )
    assert recommendation.pqc_algorithm == "ML-KEM-768"


def test_signature_purpose_maps_to_ml_dsa_per_level():
    for level, expected in [(2, "ML-DSA-44"), (3, "ML-DSA-65"), (5, "ML-DSA-87")]:
        recommendation = recommend(
            make_finding(purpose="signature", algorithm="ecc", matched="ec.ECDSA"),
            AppContext(security_level=level),
        )
        assert recommendation.pqc_algorithm == expected
        assert recommendation.nist_standard == "FIPS 204"


def test_hash_based_preference_selects_slh_dsa():
    recommendation = recommend(
        make_finding(purpose="signature", algorithm="ecc", matched="ec.ECDSA"),
        AppContext(security_level=5, prefer_signature_scheme="SLH-DSA"),
    )
    assert recommendation.pqc_algorithm == "SLH-DSA-SHA2-256s"
    assert recommendation.nist_standard == "FIPS 205"


def test_scoring_raises_level_for_stronger_classical_parameters():
    weak = recommend(
        make_finding(snippet="rsa.generate_private_key(key_size=2048)"),
        AppContext(security_level=1),
    )
    strong = recommend(
        make_finding(snippet="rsa.generate_private_key(key_size=4096)"),
        AppContext(security_level=1),
    )
    assert weak.pqc_algorithm == "ML-KEM-512"
    assert strong.pqc_algorithm == "ML-KEM-1024"
    assert "4096" in strong.rationale


def test_scoring_never_lowers_the_configured_level():
    recommendation = recommend(
        make_finding(purpose="signature", algorithm="ecc", matched="ec.SECP256R1",
                     snippet="ec.generate_private_key(ec.SECP256R1())"),
        AppContext(security_level=5),
    )
    assert recommendation.nist_level == 5


def test_rationale_mentions_the_construct_and_target():
    recommendation = recommend(make_finding(), AppContext())
    assert "rsa.generate_private_key" in recommendation.rationale
    assert "ML-KEM-768" in recommendation.rationale


def test_algorithms_used_is_deduplicated_in_order():
    recommendations = recommend_all(
        [make_finding(), make_finding(purpose="signature", matched="ec.ECDSA"), make_finding()],
        AppContext(security_level=3),
    )
    assert algorithms_used(recommendations) == ["ML-KEM-768", "ML-DSA-65"]


def test_context_defaults_when_no_config(tmp_path):
    context = load_context(tmp_path)
    assert context.security_level == 3
    assert context.prefer_signature_scheme == "ML-DSA"
    assert context.source == "defaults"


def test_context_is_read_from_config_file(tmp_path):
    (tmp_path / "pqc.config.json").write_text(
        json.dumps({"security_level": 5, "prefer_signature_scheme": "SLH-DSA"}),
        encoding="utf-8",
    )
    context = load_context(tmp_path)
    assert context.security_level == 5
    assert context.prefer_signature_scheme == "SLH-DSA"
    assert context.source.endswith("pqc.config.json")


def test_invalid_config_values_fall_back_safely(tmp_path):
    (tmp_path / "pqc.config.json").write_text(
        json.dumps({"security_level": 99, "prefer_signature_scheme": "RSA"}),
        encoding="utf-8",
    )
    context = load_context(tmp_path)
    assert context.security_level == 5
    assert context.prefer_signature_scheme == "ML-DSA"
