from job_radar.pipeline.dedupe import canonical_key, canonical_title


def test_strip_paren_city():
    assert canonical_title("Solutions Architect (Remote)") == "Solutions Architect"
    assert canonical_title("Solutions Architect (Dallas)") == "Solutions Architect"
    assert canonical_title("Solutions Architect (San Francisco)") == "Solutions Architect"


def test_strip_dash_city():
    assert canonical_title("Senior Engineer - Singapore") == "Senior Engineer"


def test_leaves_normal_titles_alone():
    assert canonical_title("Senior AI Agent Engineer") == "Senior AI Agent Engineer"
    assert canonical_title("Staff Software Engineer, Platform") == "Staff Software Engineer, Platform"


def test_canonical_key_case_insensitive():
    a = canonical_key("LangChain", "Solutions Architect (Remote)")
    b = canonical_key("langchain", "Solutions Architect (NYC)")
    assert a == b


def test_okx_multi_location():
    a = canonical_key("OKX", "Senior Staff Engineer, AI Platform")
    b = canonical_key("OKX", "Senior Staff Engineer, AI Platform")  # same title
    assert a == b
