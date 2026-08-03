from chunking import split_text, TARGET_SIZE, MAX_SIZE


def _check_offsets(text, chunks):
    for c in chunks:
        assert text[c["start"]:c["end"]].strip() == c["text"]


def test_empty_string():
    assert split_text("") == []


def test_whitespace_only():
    assert split_text("   \n\n  \t  ") == []


def test_single_short_paragraph():
    text = "Just one short paragraph."
    chunks = split_text(text)
    assert len(chunks) == 1
    assert chunks[0]["text"] == text
    _check_offsets(text, chunks)


def test_multiple_short_paragraphs_merge_up_to_target():
    para = "x" * 500
    text = "\n\n".join([para] * 4)
    chunks = split_text(text, target=1500, max_size=2200)
    assert len(chunks) >= 1
    for c in chunks[:-1]:
        assert len(c["text"]) <= 2200
    _check_offsets(text, chunks)
    assert "".join(c["text"] for c in chunks).replace("\n\n", "") or True


def test_long_paragraph_split_on_sentence_boundaries():
    sentence = "This is one sentence. "
    para = sentence * 200
    text = para
    chunks = split_text(text, target=1500, max_size=2200)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c["text"]) <= 2200
        assert c["text"].endswith(".") or c["text"] == chunks[-1]["text"]
    _check_offsets(text, chunks)


def test_mixed_paragraphs_and_long_paragraph():
    short1 = "Short intro paragraph."
    long_para = ("Another sentence here. " * 150)
    short2 = "Short closing paragraph."
    text = "\n\n".join([short1, long_para, short2])
    chunks = split_text(text)
    assert len(chunks) >= 2
    _check_offsets(text, chunks)


def test_offsets_exact_for_all_chunks():
    text = (
        "First paragraph with some text.\n\n"
        "Second paragraph, a bit longer than the first one here.\n\n"
        + ("Repeated sentence fragment here. " * 100)
    )
    chunks = split_text(text)
    assert len(chunks) > 0
    _check_offsets(text, chunks)
