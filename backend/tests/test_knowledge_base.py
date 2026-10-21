from app.knowledge_base import retrieve_articles


def test_wifi_article_outranks_unrelated_slow_computer_match():
    articles = retrieve_articles("Campus Wi-Fi is slow and keeps disconnecting")
    titles = [article.title for article in articles]

    assert titles[0] == "Connect to campus Wi-Fi"
    assert "Improve a slow computer" not in titles


def test_hardware_retrieval_still_ranks_slow_computer_article():
    articles = retrieve_articles("My computer is slow and running out of storage")

    assert articles[0].title == "Improve a slow computer"


def test_campus_wifi_article_requires_certificate_verification_and_no_fixed_ssid():
    articles = retrieve_articles("Campus Wi-Fi certificate warning")
    wifi_article = next(article for article in articles if article.title == "Connect to campus Wi-Fi")
    guidance = " ".join(wifi_article.steps).casefold()

    assert "campus-secure" not in guidance
    assert "do not accept" in guidance
    assert "verify any certificate details" in guidance
    assert "independently verified contact information" in guidance
