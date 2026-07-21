from langchain_langgraph import build_support_response, classify_question, route_by_classification


def test_classifies_greeting_questions() -> None:
    assert classify_question("Hello, can you help me?") == "greeting"


def test_classifies_billing_questions() -> None:
    assert classify_question("Can I get a refund for my invoice?") == "billing"


def test_billing_terms_take_priority_over_greeting() -> None:
    assert classify_question("Hello, I need help with my latest invoice") == "billing"


def test_classifies_technical_questions() -> None:
    assert classify_question("The login page throws an error") == "technical"


def test_routes_to_node_for_classification() -> None:
    assert route_by_classification({"classification": "billing"}) == "handle_billing"


def test_builds_response_from_classification() -> None:
    result = build_support_response(
        {
            "question": "Can I get a refund?",
            "classification": "billing",
        }
    )

    assert result["response"].startswith("Billing:")
