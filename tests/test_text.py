from job_radar.text import contains_any, count_keyword_hits, is_remote, strip_html


def test_is_remote_true_en():
    assert is_remote("Remote - APAC")
    assert is_remote("", "Fully remote role")
    assert is_remote("Worldwide")


def test_is_remote_false():
    assert not is_remote("Beijing, China")
    assert not is_remote("", "")


def test_strip_html_basic():
    html = "<p>Hello <b>world</b></p><p>Line two</p>"
    out = strip_html(html)
    assert "Hello" in out
    assert "world" in out
    assert "<" not in out


def test_count_keyword_hits_case_insensitive():
    assert count_keyword_hits("Building an LLM agent with RAG", ["llm", "rag", "finetune"]) == 2


def test_contains_any():
    assert contains_any("Senior AI Engineer", ["Junior", "Senior"])
    assert not contains_any("Intern Role", ["Senior"])
