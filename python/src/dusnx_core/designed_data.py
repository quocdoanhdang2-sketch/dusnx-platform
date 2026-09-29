"""Authored multi-turn Vietnamese trajectory bank, bounded reuse; no volume-by-renaming claims.

Core labels describe the router task. State annotations support human review,
not model inputs. The runtime's memory_create/update rules are NOT router heads.
"""
from datetime import datetime, timedelta, timezone
import random

CORE = {
    "remember": ("chat", "conversation", "reply"),
    "modify": ("followup", "conversation", "clarify"),
    "confirm": ("followup", "conversation", "reply"),
    "reject": ("followup", "conversation", "reply"),
    "recall": ("chat", "conversation", "reply"),
    "chat": ("chat", "conversation", "reply"),
    "missing": ("followup", "conversation", "clarify"),
    "research": ("research", "search_rag", "search"),
    "summarize": ("summarize", "productivity", "summarize"),
    "slides": ("presentation_edit", "productivity", "edit_slide"),
    "recommendation": ("recommendation", "conversation", "recommend"),
}

PHRASES = {
    "remember": [
        "Hãy nhớ rằng tôi chọn {a} cho {topic}.",
        "Ghi nhớ lựa chọn {a} phục vụ {topic} của tôi nhé.",
        "Lưu lại giúp tôi: {topic} sẽ dùng {a}.",
        "Tôi muốn bạn ghi nhớ {a} là lựa chọn cho {topic}.",
        "Thiết lập {topic} của dự án sang {a} và ghi nhớ nhé.",
        "Chốt {a} cho {topic}, bạn cập nhật vào bộ nhớ giúp tôi.",
        "Từ bây giờ hãy ghi nhận {topic} của tôi là {a}.",
        "Xác lập {a} làm phương án chính thức cho {topic}.",
    ],
    "modify": [
        "Đổi {a} sang {b}",
        "Tôi muốn thay {a} bằng {b} cho {topic}.",
        "Chuyển lựa chọn {topic} từ {a} thành {b} được không?",
        "Sửa quyết định về {topic}: dùng {b} thay {a}.",
        "Cập nhật lại {topic}: thay thế {a} bằng {b} nhé.",
        "Chúng ta chuyển từ {a} qua dùng {b} cho {topic} được không?",
        "Tôi muốn hủy {a} và dùng {b} cho {topic}.",
        "Có sự thay đổi về {topic}: hãy đổi {a} thành {b}.",
    ],
    "confirm": [
        "Đồng ý",
        "Có, tôi xác nhận thay đổi.",
        "Chốt phương án vừa đề xuất nhé.",
        "Hãy thực hiện thay đổi đó.",
        "Xác nhận chuyển đổi.",
        "Đúng vậy, cập nhật luôn giúp tôi.",
        "Tôi đồng ý với điều chỉnh này.",
        "Chính xác, hãy áp dụng ngay.",
    ],
    "reject": [
        "Không, giữ nguyên.",
        "Đừng thay đổi, tôi vẫn chọn phương án cũ.",
        "Hủy đề xuất vừa rồi nhé.",
        "Tôi chưa đồng ý đổi.",
        "Khoan đã, giữ nguyên cấu hình trước đó.",
        "Không, hủy bỏ yêu cầu sửa đổi.",
        "Tôi đổi ý rồi, không thay đổi gì cả.",
        "Từ chối điều chỉnh, quay lại trạng thái cũ.",
    ],
    "recall": [
        "{topic} hiện tại của tôi dùng gì?",
        "Bạn nhắc lại lựa chọn đã chốt cho {topic} được không?",
        "Tôi mở phiên khác rồi, quyết định {topic} của tôi là gì?",
        "Lựa chọn đang hiệu lực về {topic} là gì?",
        "Thông tin đã được xác nhận về {topic} hiện nay là gì?",
        "Dự án của tôi đang thống nhất phương án nào cho {topic}?",
        "Kiểm tra lại giúp tôi quyết định hiện hành đối với {topic}?",
        "Cho tôi biết phương án đang áp dụng cho {topic}.",
    ],
    "chat": [
        "Tôi nghe nói {topic} dùng {c} đúng không?",
        "Có người bảo tôi đã chốt {c}, bạn kiểm tra giúp?",
        "Tôi chỉ hỏi thử về {c}, chưa yêu cầu thay lựa chọn.",
        "Đừng coi thông tin {c} này là quyết định mới nhé.",
        "Liệu có nên xem xét thêm {c} cho {topic} trong tương lai?",
        "Một đồng nghiệp vừa đề xuất thử {c} cho {topic}.",
        "Tôi thấy tài liệu có nhắc đến {c}, đó có phải lựa chọn của tôi?",
        "Trao đổi nhanh: ưu điểm của {c} so với các phương án khác là gì?",
    ],
    "missing": [
        "Nhắc lại điều tôi đã chọn hôm trước?",
        "Chúng ta thống nhất gì ở phiên trước vậy?",
        "Quyết định cũ của tôi là gì?",
        "Tôi chưa kể bối cảnh, bạn biết kế hoạch trước đây không?",
        "Cho tôi biết thông tin đã thảo luận tuần trước?",
        "Có thể nhắc lại nội dung buổi họp gần nhất?",
        "Lựa chọn đã thỏa thuận trước đây là gì?",
        "Bạn còn lưu phương án cũ của tôi không?",
    ],
    "research": [
        "Đối chiếu tài liệu về {topic}, chỉ rõ nguồn.",
        "Tìm bằng chứng đáng tin cậy cho {topic}.",
        "Tra cứu tài liệu gốc liên quan tới {topic} giúp tôi.",
        "Nghiên cứu ưu nhược điểm {topic}, cần nguồn.",
        "Thu thập các bài phân tích kỹ thuật mới nhất về {topic}.",
        "Tìm kiếm tài liệu hướng dẫn và benchmark cho {topic}.",
        "Khảo sát các giải pháp phổ biến cho {topic} hiện nay.",
        "Tra cứu các case study triển khai thực tế về {topic}.",
    ],
    "summarize": [
        "Rút phần vừa tìm thành ba kết luận.",
        "Tổng hợp ngắn các điểm quan trọng trong tài liệu trên.",
        "Nén kết quả này thành bản tóm lược.",
        "Chắt lọc ý chính giúp tôi, chưa cần làm slide.",
        "Tóm tắt các phát hiện chính thành danh sách gạch đầu dòng.",
        "Đúc kết ngắn gọn các ý then chốt từ nghiên cứu trên.",
        "Tổng kết nội dung nghiên cứu trên trong một đoạn văn ngắn.",
        "Rút gọn toàn bộ phân tích trên thành 3 điểm cốt lõi.",
    ],
    "slides": [
        "Chuyển bản tóm lược thành bốn slide.",
        "Sắp xếp nội dung này vào bài trình chiếu.",
        "Sửa bố cục slide theo các kết luận trên.",
        "Tạo dàn ý PowerPoint cho phần vừa tổng hợp.",
        "Xây dựng khung bài thuyết trình 5 slide từ tóm tắt này.",
        "Soạn dàn bài slide báo cáo cho ban giám đốc.",
        "Thiết kế cấu trúc các trang slide theo nội dung vừa phân tích.",
        "Chuyển các luận điểm trên thành outline thuyết trình PowerPoint.",
    ],
    "recommendation": [
        "Gợi ý bước tiếp theo cho {topic}.",
        "Nên ưu tiên hướng nào khi làm {topic}?",
        "Đề xuất ba phương án triển khai {topic}.",
        "Bạn khuyên tôi chọn hướng nào tiếp theo?",
        "Cho tôi lời khuyên về phương án tối ưu cho {topic}.",
        "Dựa trên bối cảnh hiện tại, tôi nên thực hiện bước gì cho {topic}?",
        "Tư vấn giải pháp khả thi nhất đối với {topic}.",
        "Đề xuất kế hoạch hành động tiếp theo cho {topic}.",
    ],
}

TRAJECTORIES = {
    "preference_revision": ["remember", "modify", "confirm", "recall"],
    "decision_rejected_then_changed": ["remember", "modify", "reject", "recall", "modify", "confirm", "recall"],
    "contradiction": ["remember", "chat", "recall"],
    "missing_then_context": ["missing", "remember", "recall"],
    "goal_change": ["remember", "research", "modify", "confirm", "recommendation", "recall"],
    "session_change": ["remember", "recall"],
    "web_ppt_web": ["remember", "research", "slides", "recall"],
    "topic_switch": ["remember", "research", "summarize", "recall"],
    "research_summary_slides": ["research", "summarize", "slides", "recommendation"],
    "clarification_flow": ["missing", "remember", "chat", "recall"],
    "double_revision": ["remember", "modify", "confirm", "modify", "confirm", "recall"],
    "rejection_preserved": ["remember", "modify", "reject", "recall"],
    "research_then_decision": ["research", "summarize", "remember", "recall"],
    "recommendation_then_decision": ["recommendation", "remember", "recall"],
    "cross_session_continuation": ["remember", "research", "recall"],
    "presentation_iteration": ["remember", "slides", "slides", "recall"],
    "deep_research_cycle": ["research", "summarize", "research", "summarize", "recommendation"],
    "decision_with_discussion": ["remember", "chat", "chat", "recall"],
}

TOPICS = [
    "màu giao diện", "công cụ kiểm thử", "mục tiêu quý tới", "hệ thống lưu trữ",
    "phong cách báo cáo", "lịch phát hành", "cơ sở dữ liệu cache", "message broker",
    "cloud provider", "framework backend", "hệ quản trị cơ sở dữ liệu", "giao thức giao tiếp",
    "công cụ CI/CD", "bộ thu thập log", "kiến trúc ứng dụng", "định dạng dữ liệu xuất",
    "phương thức xác thực", "thư viện biểu đồ", "font chữ tài liệu", "bố cục slide",
    "chiến lược sao lưu", "mô hình triển khai", "quản lý cấu hình", "chỉ số độ trễ chính",
]

ENTITIES = [
    ("Lam", "Tím", "Đỏ"),
    ("Playwright", "Cypress", "Selenium"),
    ("giảm độ trễ", "tăng độ tin cậy", "tối ưu chi phí"),
    ("MinIO", "Ceph", "Wasabi"),
    ("ngắn gọn", "trực quan hóa", "kể chuyện"),
    ("thứ hai đầu tuần", "thứ năm", "cuối tháng"),
    ("Redis", "Memcached", "Dragonfly"),
    ("RabbitMQ", "Kafka", "Pulsar"),
    ("DigitalOcean", "Vultr", "Linode"),
    ("FastAPI", "Litestar", "Tornado"),
    ("PostgreSQL", "MySQL", "MariaDB"),
    ("gRPC", "REST JSON", "GraphQL"),
    ("GitHub Actions", "GitLab CI", "Jenkins"),
    ("Vector", "Fluentd", "Logstash"),
    ("Microservices", "Hexagonal", "Clean Architecture"),
    ("Parquet", "Arrow", "JSON Lines"),
    ("Opaque Token", "JWT Token", "Session Cookie"),
    ("Apache ECharts", "Chart.js", "D3.js"),
    ("Inter", "Roboto", "Lora"),
    ("Bauhaus", "Corporate", "Bento grid"),
    ("Snapshot hàng giờ", "Incremental mỗi ngày", "Differential hàng tuần"),
    ("Docker Swarm", "Kubernetes", "Bare Metal"),
    ("Ansible", "Terraform", "Pulumi"),
    ("P99 latency", "Throughput QPS", "Error rate 5xx"),
]


def generate_designed(seed=20260929, per_family=4):
    if not 1 <= per_family <= 8:
        raise ValueError("Diversity cap: at most 8 entity assignments per trajectory/style")
    rng = random.Random(seed)
    result = {"train": [], "validation": []}
    num_styles = 4
    for family, kinds in TRAJECTORIES.items():
        for style in range(num_styles):
            split = "validation" if style == 3 else "train"
            variants_count = max(1, per_family // 2) if split == "validation" else per_family
            for variant in range(variants_count):
                seq = f"designed-{family}-{style}-{variant}"
                choice = rng.randrange(len(TOPICS))
                a, b, c = ENTITIES[choice]
                topic = TOPICS[choice]
                active = []
                obsolete = []
                pending = None
                clock = datetime(2026, 2, 1, tzinfo=timezone.utc) + timedelta(days=variant * 3 + style)
                for step, kind in enumerate(kinds, 1):
                    content = PHRASES[kind][style].format(a=a, b=b, c=c, topic=topic)
                    if kind == "remember":
                        active = [a]
                    elif kind == "modify":
                        pending = b
                    elif kind == "confirm" and pending:
                        obsolete.extend(x for x in active if x not in obsolete)
                        active = [pending]
                        pending = None
                    elif kind == "reject":
                        pending = None
                    route = CORE[kind]
                    clock += timedelta(minutes=rng.choice([2, 5, 25, 120, 1440]))
                    row = dict(
                        event_id=f"{seq}-{step}",
                        global_user_id=seq,
                        sequence_id=seq,
                        session_id=f"{seq}-{'new' if kind == 'recall' and family in ('session_change', 'web_ppt_web', 'cross_session_continuation') else 'initial'}",
                        event_time_utc=clock.isoformat(),
                        platform="powerpoint" if kind == "slides" else "web",
                        event_type="message",
                        content=content,
                        intent_label=route[0],
                        selected_agent=route[1],
                        next_action_label=route[2],
                        feedback_value=0.0,
                        source="synthetic_designed",
                        label_provenance="authored_not_independently_reviewed",
                        layout="multi_turn",
                        template_family=f"{family}-style-{style}",
                        partition=split,
                        state_annotation=dict(active=list(active), obsolete=list(obsolete), pending=pending),
                    )
                    result[split].append(row)
    return result


def make_holdout(seed=914207):
    """Separate authored wording/trajectories for v1. Frozen baseline benchmark.

    Not independently authored or reviewed; only prediction-blind at lock time.
    """
    rng = random.Random(seed)
    mem = ("memory_create", "memory", "create_memory")
    change = ("decision_modify_intent", "memory", "await_confirm")
    yes = ("decision_update", "memory", "update_memory")
    no = ("decision_update_cancelled", "memory", "no_op")
    chat = ("chat", "conversation", "reply")
    bank = {
        "review_claim_vs_commitment": [
            ("Hãy nhớ rằng quyết định của tôi là chọn kiến trúc Hexagonal cho dịch vụ đặt lịch.", mem, ["Hexagonal"], [], False, False, "web", 1),
            ("Một đồng nghiệp bảo dự án đặt lịch đã chốt Layered. Quyết định đã lưu của tôi là gì?", chat, ["Hexagonal"], ["Layered"], False, True, "web", 1),
        ],
        "review_successive_storage": [
            ("Hãy nhớ rằng quyết định của tôi là dùng MinIO để lưu các bản xuất báo cáo.", mem, ["MinIO"], [], False, False, "web", 1),
            ("Đổi MinIO sang Ceph", change, ["MinIO"], [], True, False, "web", 1),
            ("Đồng ý", yes, ["Ceph"], ["MinIO"], False, False, "web", 1),
            ("Đổi Ceph sang Wasabi", change, ["Ceph"], ["MinIO"], True, False, "web", 1),
            ("Có", yes, ["Wasabi"], ["MinIO", "Ceph"], False, False, "web", 1),
            ("Nơi lưu bản xuất báo cáo hiện tại của dự án là gì?", chat, ["Wasabi"], ["MinIO", "Ceph"], False, True, "web", 1),
        ],
        "review_rejection_new_session": [
            ("Hãy nhớ rằng quyết định của tôi là dùng Litestar cho API tra cứu.", mem, ["Litestar"], [], False, False, "web", 1),
            ("Đổi Litestar sang Falcon", change, ["Litestar"], [], True, False, "web", 1),
            ("Không, đừng thay", no, ["Litestar"], [], False, False, "web", 1),
            ("API tra cứu hiện tại của tôi dùng thư viện nào?", chat, ["Litestar"], ["Falcon"], False, True, "web", 2),
        ],
        "review_unknown_then_recall": [
            ("Nhắc lại kế hoạch tháng trước của tôi?", ("clarify_missing_context", "conversation", "clarify"), [], [], True, True, "web", 1),
            ("Hãy nhớ rằng mục tiêu của tôi là giảm thời gian chờ cho khách.", mem, ["giảm thời gian chờ"], [], False, False, "web", 1),
            ("Mục tiêu của tôi đang được ghi nhận là gì?", chat, ["giảm thời gian chờ"], [], False, True, "web", 2),
        ],
        "review_theme_roundtrip": [
            ("Hãy nhớ rằng quyết định của tôi là chọn phong cách Bauhaus cho bài thuyết trình.", mem, ["Bauhaus"], [], False, False, "web", 1),
            ("Đang xem trang mở đầu của bài thuyết trình với bố cục Bauhaus.", chat, ["Bauhaus"], [], False, False, "powerpoint", 1),
            ("Phong cách hiện tại của bài thuyết trình trong dự án là gì?", chat, ["Bauhaus"], [], False, True, "web", 2),
        ],
        "review_preference_reversal": [
            ("Hãy nhớ rằng tôi thích văn bản dùng font Lora.", mem, ["Lora"], [], False, False, "web", 1),
            ("Đổi Lora sang Inter", change, ["Lora"], [], True, False, "web", 1),
            ("Đồng ý", yes, ["Inter"], ["Lora"], False, False, "web", 1),
            ("Font văn bản tôi thích hiện tại là gì?", chat, ["Inter"], ["Lora"], False, True, "web", 2),
        ],
        "review_detour_to_goal": [
            ("Hãy nhớ rằng quyết định của tôi là ưu tiên ổn định dịch vụ trong đợt phát hành này.", mem, ["ổn định dịch vụ"], [], False, False, "web", 1),
            ("Gợi ý một món ăn nhẹ để chuẩn bị buổi họp.", ("recommendation", "conversation", "recommend"), [], [], False, False, "web", 1),
            ("Ưu tiên đã chốt cho đợt phát hành hiện tại của dự án là gì?", chat, ["ổn định dịch vụ"], [], False, True, "web", 1),
        ],
        "review_goal_revision": [
            ("Hãy nhớ rằng quyết định của tôi là ưu tiên tăng tốc xử lý.", mem, ["tăng tốc xử lý"], [], False, False, "web", 1),
            ("Đổi tăng tốc xử lý sang giảm chi phí vận hành", change, ["tăng tốc xử lý"], [], True, False, "web", 1),
            ("Có", yes, ["giảm chi phí vận hành"], ["tăng tốc xử lý"], False, False, "web", 1),
            ("Quyết định ưu tiên hiện tại của dự án là gì?", chat, ["giảm chi phí vận hành"], ["tăng tốc xử lý"], False, True, "web", 2),
        ],
    }
    families = list(bank)
    rng.shuffle(families)
    rows = []
    for family in families:
        seq = f"holdout-{seed}-{family}"
        prior = []
        for step, (text, route, active, obsolete, clarify, target, platform, session) in enumerate(bank[family], 1):
            cid = f"{seq}-{step}"
            rows.append(dict(
                case_id=cid, sequence_id=seq, global_user_id=seq, step=step, platform=platform,
                user_message=text, session_id=f"{seq}-session-{session}", project_id=None, event_type="message",
                prior_event_ids=list(prior), known_feedback_value=0.0, category=family,
                template_family=family, partition="holdout", source="synthetic_designed", label_source="synthetic_designed",
                review_status="not_independently_reviewed", reviewer=None,
                expected_intent=route[0], expected_agent=route[1], expected_next_action=route[2], target_query=target,
                gold_active_facts=active, gold_obsolete_facts=obsolete, requires_clarification=clarify,
                expected_keywords=["bối cảnh", "chưa", "rõ", "muốn"] if clarify else active, forbidden_keywords=[],
            ))
            prior.append(cid)
    return rows


def make_holdout_v2(seed=20261001):
    """Holdout v2 benchmark: 10 distinct sequences, 38 steps.

    Addresses unconfirmed claims (AWS vs Vultr), succession/superseding (PostgreSQL->MySQL,
    Monolith->Microservices->Event-Driven), negative/cancelation (Redis keep, Dark mode keep),
    ambiguity (RabbitMQ and Kafka both active -> clarify), missing context, cross-session,
    and cross-platform (Web <-> PowerPoint).
    Freeze before any new model run on v2.
    """
    rng = random.Random(seed)
    mem = ("memory_create", "memory", "create_memory")
    change = ("decision_modify_intent", "memory", "await_confirm")
    yes = ("decision_update", "memory", "update_memory")
    no = ("decision_update_cancelled", "memory", "no_op")
    chat = ("chat", "conversation", "reply")
    clarify_missing = ("clarify_missing_context", "conversation", "clarify")

    bank = {
        "v2_database_migration": [
            ("Hãy nhớ rằng dự án quyết định lưu trữ dữ liệu chính trên PostgreSQL.", mem, ["PostgreSQL"], [], False, False, "web", 1),
            ("Đổi PostgreSQL sang MySQL", change, ["PostgreSQL"], [], True, False, "web", 1),
            ("Đồng ý", yes, ["MySQL"], ["PostgreSQL"], False, False, "web", 1),
            ("Hệ quản trị dữ liệu chính hiện tại của dự án là gì?", chat, ["MySQL"], ["PostgreSQL"], False, True, "web", 1),
        ],
        "v2_cache_rejection_cross_session": [
            ("Hãy nhớ rằng lựa chọn của tôi là dùng Redis làm bộ nhớ cache.", mem, ["Redis"], [], False, False, "web", 1),
            ("Đổi Redis sang Memcached", change, ["Redis"], [], True, False, "web", 1),
            ("Không, tôi muốn giữ nguyên cấu hình cũ.", no, ["Redis"], [], False, False, "web", 1),
            ("Sau khi khởi động lại phiên làm việc, hệ thống cache đang dùng là gì?", chat, ["Redis"], ["Memcached"], False, True, "web", 2),
        ],
        "v2_cloud_unconfirmed_distraction": [
            ("Hãy nhớ rằng quyết định của tôi là hạ tầng triển khai trên Vultr.", mem, ["Vultr"], [], False, False, "web", 1),
            ("Tôi nghe nói dự án này chuyển sang AWS đúng không?", chat, ["Vultr"], ["AWS"], False, False, "web", 1),
            ("Nền tảng đám mây được chốt của tôi là gì?", chat, ["Vultr"], ["AWS"], False, True, "web", 1),
        ],
        "v2_ambiguous_two_queues": [
            ("Hãy nhớ rằng tôi chọn RabbitMQ cho hàng đợi thanh toán.", mem, ["RabbitMQ"], [], False, False, "web", 1),
            ("Hãy nhớ rằng tôi chọn Kafka cho luồng dữ liệu phân tích.", mem, ["RabbitMQ", "Kafka"], [], False, False, "web", 1),
            ("Quyết định hàng đợi của tôi là gì?", chat, ["RabbitMQ", "Kafka"], [], True, True, "web", 1),
        ],
        "v2_missing_context_recovery": [
            ("Tôi cần kiểm tra lại thỏa thuận ở cuộc họp trước?", clarify_missing, [], [], True, True, "web", 1),
            ("Hãy nhớ rằng mục tiêu quý này là đạt 99.9% uptime.", mem, ["99.9% uptime"], [], False, False, "web", 1),
            ("Mục tiêu quý này của chúng ta là gì?", chat, ["99.9% uptime"], [], False, True, "web", 2),
        ],
        "v2_cross_platform_powerpoint": [
            ("Hãy nhớ rằng định dạng tài liệu xuất chuẩn là PDF bản in.", mem, ["PDF bản in"], [], False, False, "web", 1),
            ("Trang bìa đang trình bày tài liệu theo định dạng PDF bản in.", chat, ["PDF bản in"], [], False, False, "powerpoint", 1),
            ("Định dạng xuất chuẩn đã được xác nhận là gì?", chat, ["PDF bản in"], [], False, True, "web", 2),
        ],
        "v2_successive_architecture_monolith": [
            ("Hãy nhớ rằng tôi chọn kiến trúc Monolith cho giai đoạn thử nghiệm ban đầu.", mem, ["Monolith"], [], False, False, "web", 1),
            ("Đổi Monolith sang Microservices", change, ["Monolith"], [], True, False, "web", 1),
            ("Đồng ý", yes, ["Microservices"], ["Monolith"], False, False, "web", 1),
            ("Đổi Microservices sang Event-Driven", change, ["Microservices"], ["Monolith"], True, False, "web", 1),
            ("Xác nhận", yes, ["Event-Driven"], ["Monolith", "Microservices"], False, False, "web", 1),
            ("Kiến trúc hệ thống đang được lựa chọn là gì?", chat, ["Event-Driven"], ["Monolith", "Microservices"], False, True, "web", 2),
        ],
        "v2_ui_theme_rejection": [
            ("Hãy nhớ rằng phong cách hiển thị tôi chọn là Chế độ tối.", mem, ["Chế độ tối"], [], False, False, "web", 1),
            ("Đổi Chế độ tối sang Chế độ sáng", change, ["Chế độ tối"], [], True, False, "web", 1),
            ("Hủy yêu cầu đổi vừa rồi nhé.", no, ["Chế độ tối"], [], False, False, "web", 1),
            ("Chế độ giao diện tôi đang dùng là gì?", chat, ["Chế độ tối"], ["Chế độ sáng"], False, True, "web", 2),
        ],
        "v2_topic_detour_research_recall": [
            ("Hãy nhớ rằng quyết định của tôi là sử dụng giao thức gRPC cho giao tiếp nội bộ.", mem, ["gRPC"], [], False, False, "web", 1),
            ("Tìm kiếm các bài viết về kỹ thuật tối ưu hóa bộ nhớ.", ("research", "search_rag", "search"), ["gRPC"], [], False, False, "web", 1),
            ("Rút gọn toàn bộ phân tích trên thành 3 điểm cốt lõi.", ("summarize", "productivity", "summarize"), ["gRPC"], [], False, False, "web", 1),
            ("Giao thức giao tiếp nội bộ đã thống nhất là gì?", chat, ["gRPC"], [], False, True, "web", 2),
        ],
        "v2_logging_framework_revision": [
            ("Hãy nhớ rằng quyết định của tôi là dùng Vector để gom log.", mem, ["Vector"], [], False, False, "web", 1),
            ("Đổi Vector sang Fluentd", change, ["Vector"], [], True, False, "web", 1),
            ("Chốt thay đổi này", yes, ["Fluentd"], ["Vector"], False, False, "web", 1),
            ("Công cụ thu thập log hiện tại của dự án là gì?", chat, ["Fluentd"], ["Vector"], False, True, "web", 1),
        ],
    }

    families = list(bank)
    rng.shuffle(families)
    rows = []
    for family in families:
        seq = f"holdout2-{seed}-{family}"
        prior = []
        for step, (text, route, active, obsolete, clarify, target, platform, session) in enumerate(bank[family], 1):
            cid = f"{seq}-{step}"
            expected_kw = ["nhiều", "cụ thể", "nào", "?"] if clarify and active else (
                ["bối cảnh", "chưa", "rõ", "kế hoạch"] if clarify else active
            )
            rows.append(dict(
                case_id=cid,
                sequence_id=seq,
                global_user_id=seq,
                step=step,
                platform=platform,
                user_message=text,
                session_id=f"{seq}-session-{session}",
                project_id=None,
                event_type="message",
                prior_event_ids=list(prior),
                known_feedback_value=0.0,
                category=family,
                template_family=family,
                partition="holdout",
                source="synthetic_designed",
                label_source="synthetic_designed",
                review_status="not_independently_reviewed",
                reviewer=None,
                expected_intent=route[0],
                expected_agent=route[1],
                expected_next_action=route[2],
                target_query=target,
                gold_active_facts=active,
                gold_obsolete_facts=obsolete,
                requires_clarification=clarify,
                expected_keywords=expected_kw,
                forbidden_keywords=[],
            ))
            prior.append(cid)
    return rows
