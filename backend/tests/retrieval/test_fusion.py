"""Reciprocal Rank Fusion: rank alone decides, agreement counts, ties are stable."""

from app.retrieval.fusion import fuse


def test_agreement_between_rankings_beats_one_ranking_s_top_place():
    # "b" is second in both; "a" and "c" each top one ranking and miss the other.
    assert fuse([["a", "b"], ["c", "b"]], weights=(1, 1)) == ["b", "a", "c"]


def test_a_smaller_k_lets_one_ranking_s_top_place_win():
    rankings = [["a", "b"], ["c", "d", "e", "b"]]

    assert fuse(rankings, weights=(1, 1))[0] == "b"
    assert fuse(rankings, weights=(1, 1), k=0)[0] == "a"


def test_a_heavier_ranking_wins_a_tie_of_places():
    assert fuse([["a"], ["b"]], weights=(1, 2)) == ["b", "a"]


def test_ties_keep_the_order_items_were_first_seen_in():
    assert fuse([["x", "y"], ["y", "x"]], weights=(1, 1)) == ["x", "y"]


def test_nothing_ranked_fuses_to_nothing():
    assert fuse([[], []], weights=(1, 1)) == []
