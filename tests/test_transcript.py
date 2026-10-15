"""Sentences are rebuilt from word timestamps so every backend yields the same shape."""

from clips.transcript import sentences_from_words, to_srt


def w(text, start, end):
    return {"text": text, "start": start, "end": end}


def test_split_on_sentence_punctuation():
    words = [w("Hallo", 0, 0.3), w("Welt.", 0.3, 0.6), w("Zweiter", 0.7, 1.0), w("Satz!", 1.0, 1.3)]
    s = sentences_from_words(words)
    assert [x["text"] for x in s] == ["Hallo Welt.", "Zweiter Satz!"]
    assert s[1]["start"] == 0.7 and s[1]["end"] == 1.3
    assert s[0]["words"] == words[:2]


def test_split_on_long_pause_without_punctuation():
    words = [w("eins", 0, 0.3), w("zwei", 2.0, 2.3)]
    assert len(sentences_from_words(words, max_gap=1.0)) == 2


def test_abbreviations_and_numbers_do_not_split():
    words = [
        w("2025", 0, 0.3),
        w("waren", 0.3, 0.5),
        w("es", 0.5, 0.6),
        w("63.459", 0.6, 1.0),
        w("Anzeigen,", 1.0, 1.3),
        w("z.B.", 1.3, 1.5),
        w("Phishing.", 1.5, 1.9),
    ]
    assert len(sentences_from_words(words)) == 1


def test_srt_output():
    s = [{"id": 0, "start": 0.0, "end": 1.5, "text": "Hallo Welt."}]
    assert to_srt(s) == "1\n00:00:00,000 --> 00:00:01,500\nHallo Welt.\n\n"
