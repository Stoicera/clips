"""Cutting logic: candidates from the model are validated, never stretched."""

from clips.select import Candidate, cut_points, validate_candidates


def sentences(*spans):
    """spans: (start, end, text)"""
    return [{"id": i, "start": s, "end": e, "text": t} for i, (s, e, t) in enumerate(spans)]


S = sentences(
    (0.0, 10.0, "Zu klein für einen Angriff gibt es nicht."),
    (10.5, 22.0, "2025 waren es 63.459 Anzeigen."),
    (22.4, 35.0, "Das ist mehr als sechsmal so viel."),
    (35.5, 50.0, "Ransomware ist ein arbeitsteiliges Geschäft."),
    (50.2, 70.3, "Fünf Prinzipien machen den Betrieb aufwendig."),
    (70.5, 95.0, "Erstens: Mehrfaktor überall."),
    (95.5, 130.0, "Zweitens: Backups, die man geprobt hat."),
    (130.5, 160.0, "Drittens: Rechte so klein wie möglich."),
    (160.5, 190.0, "Viertens: Updates binnen einer Woche."),
    (190.5, 220.0, "Fünftens: Einmal im Jahr prüfen lassen."),
)


def cand(a, b, title="T"):
    return Candidate(start_sentence=a, end_sentence=b, title=title, hook="h", thesis="t", why="w")


def test_accepts_clip_inside_duration_window():
    clips, rejected = validate_candidates([cand(1, 2)], S)
    assert len(clips) == 1 and rejected == []
    assert clips[0].start == 10.5 and clips[0].end == 35.0
    assert clips[0].text == "2025 waren es 63.459 Anzeigen. Das ist mehr als sechsmal so viel."


def test_too_short_and_too_long_are_dropped_with_reason():
    clips, rejected = validate_candidates([cand(0, 0), cand(0, 5)], S)
    assert clips == []
    reasons = [r for _, r in rejected]
    assert any("short" in r for r in reasons)
    assert any("long" in r for r in reasons)


def test_overlap_keeps_first_in_model_order():
    clips, rejected = validate_candidates([cand(1, 3), cand(2, 4)], S)
    assert [c.start for c in clips] == [10.5]
    assert "overlap" in rejected[0][1]


def test_invalid_indices_are_dropped():
    clips, rejected = validate_candidates([cand(3, 1), cand(0, 99)], S)
    assert clips == [] and len(rejected) == 2


def test_result_is_sorted_by_start_and_capped():
    cands = [cand(9, 9), cand(5, 5), cand(7, 7), cand(8, 8), cand(6, 6), cand(1, 3), cand(4, 4)]
    clips, rejected = validate_candidates(cands, S, max_clips=6)
    assert [c.index for c in clips] == [1, 2, 3, 4, 5, 6]
    assert [c.start for c in clips] == sorted(c.start for c in clips)
    assert len(clips) == 6 and any("maximum" in r for _, r in rejected)


def test_cut_points_add_small_lead_and_tail_without_crossing_neighbours():
    clip, _ = validate_candidates([cand(1, 2)], S)
    start, end = cut_points(clip[0], S, duration=220.0)
    assert 10.0 <= start < 10.5
    assert 35.0 < end <= 35.5
    first, _ = validate_candidates([cand(0, 1)], S)
    assert cut_points(first[0], S, duration=220.0)[0] == 0.0
