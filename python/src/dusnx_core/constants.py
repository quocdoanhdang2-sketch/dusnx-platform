PLATFORMS = ["web", "zalo", "powerpoint"]
EVENT_TYPES = ["message", "click", "accept", "reject", "edit", "search"]
INTENTS = ["chat", "research", "summarize", "presentation_edit", "recommendation", "followup"]
AGENTS = ["conversation", "search_rag", "productivity"]
NEXT_ACTIONS = ["reply", "search", "summarize", "edit_slide", "recommend", "clarify"]

PLATFORM_TO_ID = {v: i for i, v in enumerate(PLATFORMS)}
EVENT_TYPE_TO_ID = {v: i for i, v in enumerate(EVENT_TYPES)}
INTENT_TO_ID = {v: i for i, v in enumerate(INTENTS)}
AGENT_TO_ID = {v: i for i, v in enumerate(AGENTS)}
NEXT_ACTION_TO_ID = {v: i for i, v in enumerate(NEXT_ACTIONS)}
