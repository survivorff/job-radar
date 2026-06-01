from job_radar.sources.lever import LeverSlug, _parse


def test_parse_minimal():
    payload = {
        "id": "abc123",
        "text": "Senior AI Agent Engineer",
        "hostedUrl": "https://jobs.lever.co/okx/abc123",
        "createdAt": 1714200000000,
        "categories": {
            "location": "Singapore",
            "team": "AI",
            "commitment": "Full-time",
        },
        "descriptionPlain": "Build AI agents.",
        "lists": [
            {"text": "Requirements", "content": "<ul><li>5+ years Java</li></ul>"},
        ],
    }
    raw = _parse(LeverSlug("okx", "OKX"), payload)
    assert raw.company == "OKX"
    assert raw.title == "Senior AI Agent Engineer"
    assert raw.location == "Singapore"
    assert raw.source == "lever:okx"
    assert "5+ years Java" in raw.description
    assert raw.apply_url.startswith("https://jobs.lever.co/")
    assert raw.posted_at is not None
