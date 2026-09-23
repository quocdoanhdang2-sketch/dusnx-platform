from dusnx_core.routing_policy import match_explicit_route


def test_summarize_wins_over_research_word():
    route = match_explicit_route("web", "Tóm tắt nội dung AI Agent tôi đang nghiên cứu")
    assert route is not None
    assert (route.intent, route.agent, route.next_action) == (
        "summarize", "productivity", "summarize"
    )


def test_presentation_wins_for_explicit_slide_request():
    route = match_explicit_route(
        "powerpoint", "Tạo 5 slide từ chủ đề AI Agent tôi vừa nghiên cứu"
    )
    assert route is not None
    assert (route.intent, route.agent, route.next_action) == (
        "presentation_edit", "productivity", "edit_slide"
    )


def test_ambiguous_chat_is_left_to_model():
    assert match_explicit_route("web", "Xin chào, hôm nay thế nào?") is None
