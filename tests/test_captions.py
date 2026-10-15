"""Subtitle cues: at most two lines of 38 characters, built from word timestamps."""

from clips.captions_ass import build_cues, format_ass_time, to_ass


def words(text, start=0.0, step=0.4):
    out, t = [], start
    for w in text.split():
        out.append({"text": w, "start": t, "end": t + step})
        t += step
    return out


LONG = (
    "Ransomware ist ein arbeitsteiliges Geschäft. Es sucht nicht den größten Betrieb. "
    "Es sucht den Betrieb mit dem geringsten Aufwand, und das sind oft die kleinen."
)


def test_lines_respect_width_and_count():
    cues = build_cues(words(LONG), max_chars=38, max_lines=2)
    for cue in cues:
        assert 1 <= len(cue.lines) <= 2
        assert all(len(line) <= 38 for line in cue.lines)


def test_all_words_kept_in_order():
    cues = build_cues(words(LONG))
    joined = " ".join(" ".join(c.lines) for c in cues)
    assert joined == LONG


def test_cue_breaks_at_sentence_end():
    cues = build_cues(words("Erster Satz endet hier. Zweiter Satz beginnt neu."))
    assert cues[0].lines == ["Erster Satz endet hier."]


def test_cue_times_follow_words_and_offset():
    cues = build_cues(words("Hallo Welt.", start=12.0), offset=12.0)
    assert cues[0].start == 0.0
    assert abs(cues[0].end - 0.8) < 1e-6


def test_long_pause_starts_new_cue():
    w = words("Erstens zwei") + words("drei vier", start=5.0)
    cues = build_cues(w, max_gap=1.0)
    assert len(cues) == 2


def test_ass_time_format():
    assert format_ass_time(0.0) == "0:00:00.00"
    assert format_ass_time(3725.456) == "1:02:05.46"


def test_ass_document_has_style_and_events():
    cues = build_cues(words("Hallo Welt."))
    doc = to_ass(cues, highlight=False)
    assert "[V4+ Styles]" in doc and "Inter" in doc
    assert "Dialogue: 0,0:00:00.00,0:00:00.80,Clip,,0,0,0,,Hallo Welt." in doc
    assert "MarginV" in doc
