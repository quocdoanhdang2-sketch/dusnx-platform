"""Small authored trajectory bank, bounded reuse; no volume-by-renaming claims.

Core labels describe the router task. State annotations support human review,
not model inputs. The runtime's memory_create/update rules are NOT router heads.
"""
from datetime import datetime, timedelta, timezone
import random

CORE={
    "remember":("chat","conversation","reply"),"modify":("followup","conversation","clarify"),
    "confirm":("followup","conversation","reply"),"reject":("followup","conversation","reply"),
    "recall":("chat","conversation","reply"),"chat":("chat","conversation","reply"),
    "missing":("followup","conversation","clarify"),"research":("research","search_rag","search"),
    "summarize":("summarize","productivity","summarize"),
    "slides":("presentation_edit","productivity","edit_slide"),
    "recommendation":("recommendation","conversation","recommend"),
}
PHRASES={
 "remember":["Hãy nhớ rằng tôi chọn {a} cho {topic}.","Ghi nhớ lựa chọn {a} phục vụ {topic} của tôi nhé.",
             "Lưu lại giúp tôi: {topic} sẽ dùng {a}.","Tôi muốn bạn ghi nhớ {a} là lựa chọn cho {topic}."],
 "modify":["Đổi {a} sang {b}","Tôi muốn thay {a} bằng {b} cho {topic}.",
           "Chuyển lựa chọn {topic} từ {a} thành {b} được không?","Sửa quyết định về {topic}: dùng {b} thay {a}."],
 "confirm":["Đồng ý","Có, tôi xác nhận thay đổi.","Chốt phương án vừa đề xuất nhé.","Hãy thực hiện thay đổi đó."],
 "reject":["Không, giữ nguyên.","Đừng thay đổi, tôi vẫn chọn phương án cũ.","Hủy đề xuất vừa rồi nhé.","Tôi chưa đồng ý đổi."],
 "recall":["{topic} hiện tại của tôi dùng gì?","Bạn nhắc lại lựa chọn đã chốt cho {topic} được không?",
           "Tôi mở phiên khác rồi, quyết định {topic} của tôi là gì?","Lựa chọn đang hiệu lực về {topic} là gì?"],
 "chat":["Tôi nghe nói {topic} dùng {c} đúng không?","Có người bảo tôi đã chốt {c}, bạn kiểm tra giúp?",
         "Tôi chỉ hỏi thử về {c}, chưa yêu cầu thay lựa chọn.","Đừng coi thông tin {c} này là quyết định mới nhé."],
 "missing":["Nhắc lại điều tôi đã chọn hôm trước?","Chúng ta thống nhất gì ở phiên trước vậy?",
            "Quyết định cũ của tôi là gì?","Tôi chưa kể bối cảnh, bạn biết kế hoạch trước đây không?"],
 "research":["Đối chiếu tài liệu về {topic}, chỉ rõ nguồn.","Tìm bằng chứng đáng tin cậy cho {topic}.",
             "Tra cứu tài liệu gốc liên quan tới {topic} giúp tôi.","Nghiên cứu ưu nhược điểm {topic}, cần nguồn."],
 "summarize":["Rút phần vừa tìm thành ba kết luận.","Tổng hợp ngắn các điểm quan trọng trong tài liệu trên.",
              "Nén kết quả này thành bản tóm lược.","Chắt lọc ý chính giúp tôi, chưa cần làm slide."],
 "slides":["Chuyển bản tóm lược thành bốn slide.","Sắp xếp nội dung này vào bài trình chiếu.",
           "Sửa bố cục slide theo các kết luận trên.","Tạo dàn ý PowerPoint cho phần vừa tổng hợp."],
 "recommendation":["Gợi ý bước tiếp theo cho {topic}.","Nên ưu tiên hướng nào khi làm {topic}?",
                   "Đề xuất ba phương án triển khai {topic}.","Bạn khuyên tôi chọn hướng nào tiếp theo?"],
}
TRAJECTORIES={
 "preference_revision":["remember","modify","confirm","recall"],
 "decision_rejected_then_changed":["remember","modify","reject","recall","modify","confirm","recall"],
 "contradiction":["remember","chat","recall"],
 "missing_then_context":["missing","remember","recall"],
 "goal_change":["remember","research","modify","confirm","recommendation","recall"],
 "session_change":["remember","recall"],
 "web_ppt_web":["remember","research","slides","recall"],
 "topic_switch":["remember","research","summarize","recall"],
 "research_summary_slides":["research","summarize","slides","recommendation"],
}
TOPICS=["màu giao diện","công cụ kiểm thử","mục tiêu quý tới","hệ thống lưu trữ","phong cách báo cáo","lịch phát hành"]
ENTITIES=[("Lam","Tím","Đỏ"),("Cypress","Playwright","Selenium"),("giảm độ trễ","tăng độ tin cậy","thêm chức năng"),
          ("MinIO","Ceph","S3"),("ngắn gọn","chi tiết","kể chuyện"),("thứ hai","thứ sáu","chủ nhật")]


def generate_designed(seed=20260929,per_family=4):
    if not 1<=per_family<=8:raise ValueError("Diversity cap: at most 8 entity assignments per trajectory/style")
    rng=random.Random(seed);result={"train":[],"validation":[]}
    for family,kinds in TRAJECTORIES.items():
        for style in range(4):
            split="validation" if style==3 else "train"
            for variant in range(1 if split=="validation" else per_family):
                seq=f"designed-{family}-{style}-{variant}"
                choice=rng.randrange(len(TOPICS));a,b,c=ENTITIES[choice];topic=TOPICS[choice]
                active=[];obsolete=[];pending=None
                # Vary the spacing/session boundary as well as event order between trajectories.
                clock=datetime(2026,2,1,tzinfo=timezone.utc)+timedelta(days=variant)
                for step,kind in enumerate(kinds,1):
                    content=PHRASES[kind][style].format(a=a,b=b,c=c,topic=topic)
                    if kind=="remember":active=[a]
                    if kind=="modify":pending=b
                    if kind=="confirm" and pending:
                        obsolete.extend(x for x in active if x not in obsolete);active=[pending];pending=None
                    if kind=="reject":pending=None
                    route=CORE[kind]
                    clock+=timedelta(minutes=rng.choice([1,3,30,180,1440]))
                    row=dict(event_id=f"{seq}-{step}",global_user_id=seq,sequence_id=seq,
                             session_id=f"{seq}-{'new' if kind=='recall' and family in ('session_change','web_ppt_web') else 'initial'}",
                             event_time_utc=clock.isoformat(),platform="powerpoint" if kind=="slides" else "web",
                             event_type="message",content=content,intent_label=route[0],selected_agent=route[1],
                             next_action_label=route[2],feedback_value=0.0,source="synthetic_designed",
                             label_provenance="authored_not_independently_reviewed",layout="multi_turn",
                             template_family=f"{family}-style-{style}",partition=split,
                             state_annotation=dict(active=list(active),obsolete=list(obsolete),pending=pending))
                    result[split].append(row)
    return result


def make_holdout(seed=914207):
    """Separate authored wording/trajectories. Freeze before any new-model run.

    Not independently authored or reviewed; only prediction-blind at lock time.
    """
    rng=random.Random(seed)
    # Each tuple: message, API route, active facts, obsolete facts, clarification,
    # target query, platform, session. No product entities from the development failures.
    mem=("memory_create","memory","create_memory")
    change=("decision_modify_intent","memory","await_confirm")
    yes=("decision_update","memory","update_memory")
    no=("decision_update_cancelled","memory","no_op")
    chat=("chat","conversation","reply")
    bank={
      "review_claim_vs_commitment":[
        ("Hãy nhớ rằng quyết định của tôi là chọn kiến trúc Hexagonal cho dịch vụ đặt lịch.",mem,["Hexagonal"],[],False,False,"web",1),
        ("Một đồng nghiệp bảo dự án đặt lịch đã chốt Layered. Quyết định đã lưu của tôi là gì?",chat,["Hexagonal"],["Layered"],False,True,"web",1)],
      "review_successive_storage":[
        ("Hãy nhớ rằng quyết định của tôi là dùng MinIO để lưu các bản xuất báo cáo.",mem,["MinIO"],[],False,False,"web",1),
        ("Đổi MinIO sang Ceph",change,["MinIO"],[],True,False,"web",1),
        ("Đồng ý",yes,["Ceph"],["MinIO"],False,False,"web",1),
        ("Đổi Ceph sang Wasabi",change,["Ceph"],["MinIO"],True,False,"web",1),
        ("Có",yes,["Wasabi"],["MinIO","Ceph"],False,False,"web",1),
        ("Nơi lưu bản xuất báo cáo hiện tại của dự án là gì?",chat,["Wasabi"],["MinIO","Ceph"],False,True,"web",1)],
      "review_rejection_new_session":[
        ("Hãy nhớ rằng quyết định của tôi là dùng Litestar cho API tra cứu.",mem,["Litestar"],[],False,False,"web",1),
        ("Đổi Litestar sang Falcon",change,["Litestar"],[],True,False,"web",1),
        ("Không, đừng thay",no,["Litestar"],[],False,False,"web",1),
        ("API tra cứu hiện tại của tôi dùng thư viện nào?",chat,["Litestar"],["Falcon"],False,True,"web",2)],
      "review_unknown_then_recall":[
        ("Nhắc lại kế hoạch tháng trước của tôi?",("clarify_missing_context","conversation","clarify"),[],[],True,True,"web",1),
        ("Hãy nhớ rằng mục tiêu của tôi là giảm thời gian chờ cho khách.",mem,["giảm thời gian chờ"],[],False,False,"web",1),
        ("Mục tiêu của tôi đang được ghi nhận là gì?",chat,["giảm thời gian chờ"],[],False,True,"web",2)],
      "review_theme_roundtrip":[
        ("Hãy nhớ rằng quyết định của tôi là chọn phong cách Bauhaus cho bài thuyết trình.",mem,["Bauhaus"],[],False,False,"web",1),
        ("Đang xem trang mở đầu của bài thuyết trình với bố cục Bauhaus.",chat,["Bauhaus"],[],False,False,"powerpoint",1),
        ("Phong cách hiện tại của bài thuyết trình trong dự án là gì?",chat,["Bauhaus"],[],False,True,"web",2)],
      "review_preference_reversal":[
        ("Hãy nhớ rằng tôi thích văn bản dùng font Lora.",mem,["Lora"],[],False,False,"web",1),
        ("Đổi Lora sang Inter",change,["Lora"],[],True,False,"web",1),
        ("Đồng ý",yes,["Inter"],["Lora"],False,False,"web",1),
        ("Font văn bản tôi thích hiện tại là gì?",chat,["Inter"],["Lora"],False,True,"web",2)],
      "review_detour_to_goal":[
        ("Hãy nhớ rằng quyết định của tôi là ưu tiên ổn định dịch vụ trong đợt phát hành này.",mem,["ổn định dịch vụ"],[],False,False,"web",1),
        ("Gợi ý một món ăn nhẹ để chuẩn bị buổi họp.",("recommendation","conversation","recommend"),[],[],False,False,"web",1),
        ("Ưu tiên đã chốt cho đợt phát hành hiện tại của dự án là gì?",chat,["ổn định dịch vụ"],[],False,True,"web",1)],
      "review_goal_revision":[
        ("Hãy nhớ rằng quyết định của tôi là ưu tiên tăng tốc xử lý.",mem,["tăng tốc xử lý"],[],False,False,"web",1),
        ("Đổi tăng tốc xử lý sang giảm chi phí vận hành",change,["tăng tốc xử lý"],[],True,False,"web",1),
        ("Có",yes,["giảm chi phí vận hành"],["tăng tốc xử lý"],False,False,"web",1),
        ("Quyết định ưu tiên hiện tại của dự án là gì?",chat,["giảm chi phí vận hành"],["tăng tốc xử lý"],False,True,"web",2)],
    }
    families=list(bank);rng.shuffle(families);rows=[]
    for family in families:
        seq=f"holdout-{seed}-{family}";prior=[]
        for step,(text,route,active,obsolete,clarify,target,platform,session) in enumerate(bank[family],1):
            cid=f"{seq}-{step}"
            rows.append(dict(case_id=cid,sequence_id=seq,global_user_id=seq,step=step,platform=platform,
                user_message=text,session_id=f"{seq}-session-{session}",project_id=None,event_type="message",
                prior_event_ids=list(prior),known_feedback_value=0.0,category=family,
                template_family=family,partition="holdout",source="synthetic_designed",label_source="synthetic_designed",
                review_status="not_independently_reviewed",reviewer=None,
                expected_intent=route[0],expected_agent=route[1],expected_next_action=route[2],target_query=target,
                gold_active_facts=active,gold_obsolete_facts=obsolete,requires_clarification=clarify,
                expected_keywords=["bối cảnh","chưa","rõ","muốn"] if clarify else active,forbidden_keywords=[]))
            prior.append(cid)
    return rows
