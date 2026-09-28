from backend.pipeline.spans import locate

BRIEF = ("We sell premium dog food for senior dogs, targeting owners who care about joint "
         "health and longevity. Grain-free, vet-formulated, subscription-based.")


def test_exact():
    s = locate("vet-formulated", BRIEF)
    assert s and BRIEF[s.start:s.end] == "vet-formulated"


def test_case_and_punctuation_insensitive():
    s = locate('"Grain-free."', BRIEF)
    assert s and s.text == "Grain-free"


def test_fuzzy_small_drift():
    s = locate("vet formulated", BRIEF)
    assert s and s.text == "vet-formulated"


def test_invented_quote_rejected():
    assert locate("vet-recommended by experts", BRIEF) is None
    assert locate("clinically proven", BRIEF) is None
    assert locate(None, BRIEF) is None
