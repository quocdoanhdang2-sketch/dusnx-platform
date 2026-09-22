from apps.ai_api.main import bootstrap_state_update, detect_route
from dusnx_core.schema import ProcessRequest


def test_detect_powerpoint_route():
    intent, agent, action, confidence = detect_route("Tạo 5 slide về DUSN-X")
    assert intent == "presentation_edit"
    assert agent == "productivity"
    assert action == "edit_slide"
    assert confidence > 0.5


def test_bootstrap_state_version_increases():
    request = ProcessRequest(
        global_user_id="user-1",
        platform="web",
        content="nghiên cứu AI Agent",
    )
    first = bootstrap_state_update(request, "research")
    request.previous_state = first
    second = bootstrap_state_update(request, "research")
    assert first.state_version == 1
    assert second.state_version == 2
    assert len(second.platform_states) == 3
