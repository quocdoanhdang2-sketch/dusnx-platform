"""Holdout v3 benchmark generator: 20 distinct sequences, 310+ steps.

Key characteristics:
- Many long sequences (15-18 turns) to test recurrent state retention across temporal gaps.
- Cross-session continuations.
- Web <-> PowerPoint cross-platform transitions.
- Revisions, successive migrations, rejections.
- Two memories of the same category requiring clarification/disambiguation.
- Unconfirmed rumors/hearsay to test obsolete/leaked elimination.
- Elliptical phrases missing grammatical subjects in natural Vietnamese.
- Queries with zero lexical overlap with target facts (semantic retrieval).
- Strict causal ordering: no future leaks.
"""
import random

def make_holdout_v3(seed=20261002):
    rng = random.Random(seed)
    mem = ("memory_create", "memory", "create_memory")
    change = ("decision_modify_intent", "memory", "await_confirm")
    yes = ("decision_update", "memory", "update_memory")
    no = ("decision_update_cancelled", "memory", "no_op")
    chat = ("chat", "conversation", "reply")
    clarify_missing = ("clarify_missing_context", "conversation", "clarify")
    clarify_ambig = ("clarify_ambiguous_decision", "conversation", "clarify")
    research = ("research", "search_rag", "search")
    summarize = ("summarize", "productivity", "summarize")
    slides = ("presentation_edit", "productivity", "edit_slide")
    recommend = ("recommendation", "conversation", "recommend")

    bank = {
        # 1. Cloud multi-hop recall with rumors and 5-turn temporal gap
        "v3_01_cloud_multi_hop_recall": [
            ("Hãy nhớ rằng hệ thống vi dịch vụ của chúng tôi triển khai trên Azure.", mem, ["Azure"], [], False, False, "web", 1),
            ("Bạn có thể giải thích cơ chế autoscaling của cụm máy chủ không?", chat, ["Azure"], [], False, False, "web", 1),
            ("Một bạn trong nhóm bảo nên chuyển hết sang DigitalOcean cho rẻ.", chat, ["Azure"], [], False, False, "web", 1),
            ("Nhưng tôi thấy DigitalOcean không đủ chứng chỉ cho ngành tài chính.", chat, ["Azure"], [], False, False, "web", 1),
            ("Đổi Azure sang Google Cloud Platform", change, ["Azure"], [], True, False, "web", 1),
            ("Xác nhận đổi sang Google Cloud Platform", yes, ["Google Cloud Platform"], ["Azure"], False, False, "web", 1),
            ("Tìm kiếm tài liệu về chính sách lưu trữ của Google Cloud.", research, ["Google Cloud Platform"], ["Azure"], False, False, "web", 1),
            ("Rút gọn tài liệu trên thành 3 điểm cốt lõi về độ bền dữ liệu.", summarize, ["Google Cloud Platform"], ["Azure"], False, False, "web", 1),
            ("Bên kinh doanh nói đồn rằng dự án sẽ quay lại dùng AWS.", chat, ["Google Cloud Platform"], ["Azure"], False, False, "web", 1),
            ("Đó chỉ là tin đồn thôi, tôi chưa bao giờ đồng ý chọn AWS cả.", chat, ["Google Cloud Platform"], ["Azure"], False, False, "web", 1),
            ("Đổi Google Cloud Platform sang AWS", change, ["Google Cloud Platform"], ["Azure"], True, False, "web", 1),
            ("Không đồng ý, hủy đề xuất đổi sang AWS này ngay.", no, ["Google Cloud Platform"], ["Azure"], False, False, "web", 1),
            ("Thời tiết hôm nay ở văn phòng khá mát mẻ dễ chịu.", chat, ["Google Cloud Platform"], ["Azure"], False, False, "web", 1),
            ("Lát nữa nhóm kỹ thuật có buổi họp bàn giao lúc 3 giờ chiều.", chat, ["Google Cloud Platform"], ["Azure"], False, False, "web", 1),
            ("Mọi thứ đã được chuẩn bị xong xuôi chưa bạn?", chat, ["Google Cloud Platform"], ["Azure"], False, False, "web", 1),
            ("Cụm máy tính lưu trữ và tính toán chính đặt ở đâu?", chat, ["Google Cloud Platform"], ["Azure", "AWS", "DigitalOcean"], False, True, "web", 2),
        ],

        # 2. Web <-> PowerPoint sync with slide edits and title revision
        "v3_02_web_powerpoint_sync": [
            ("Hãy nhớ rằng tiêu đề báo cáo quý này của dự án là Đột phá AI.", mem, ["Đột phá AI"], [], False, False, "web", 1),
            ("Khảo sát các chỉ số tăng trưởng người dùng hàng tuần.", research, ["Đột phá AI"], [], False, False, "web", 1),
            ("Tổng hợp 3 chỉ số then chốt từ báo cáo khảo sát trên.", summarize, ["Đột phá AI"], [], False, False, "web", 1),
            ("Tạo bài trình chiếu 4 trang theo các chỉ số vừa tổng hợp.", slides, ["Đột phá AI"], [], False, False, "powerpoint", 1),
            ("Đổi màu nền của slide 1 sang gam màu xanh thẫm.", slides, ["Đột phá AI"], [], False, False, "powerpoint", 1),
            ("Thêm biểu đồ cột so sánh quý trước ở trang số 2.", slides, ["Đột phá AI"], [], False, False, "powerpoint", 1),
            ("Đổi Đột phá AI sang Tăng trưởng bền vững", change, ["Đột phá AI"], [], True, False, "powerpoint", 1),
            ("Đồng ý áp dụng tiêu đề mới", yes, ["Tăng trưởng bền vững"], ["Đột phá AI"], False, False, "powerpoint", 1),
            ("Cập nhật lại chữ trên trang bìa slide theo tiêu đề vừa đổi.", slides, ["Tăng trưởng bền vững"], ["Đột phá AI"], False, False, "powerpoint", 1),
            ("Sắp xếp lại thứ tự các phần trong bài thuyết trình.", slides, ["Tăng trưởng bền vững"], ["Đột phá AI"], False, False, "powerpoint", 1),
            ("Đổi Tăng trưởng bền vững sang Mở rộng thị phần", change, ["Tăng trưởng bền vững"], ["Đột phá AI"], True, False, "powerpoint", 1),
            ("Thôi đừng đổi nữa, giữ nguyên như vừa chốt.", no, ["Tăng trưởng bền vững"], ["Đột phá AI"], False, False, "powerpoint", 1),
            ("Kiểm tra lại phông chữ trên toàn bộ các trang trình chiếu.", slides, ["Tăng trưởng bền vững"], ["Đột phá AI"], False, False, "powerpoint", 1),
            ("Xuất bản nháp bài thuyết trình ra định dạng trình chiếu.", slides, ["Tăng trưởng bền vững"], ["Đột phá AI"], False, False, "powerpoint", 1),
            ("Tôi vừa rời phòng họp quay trở lại bàn làm việc.", chat, ["Tăng trưởng bền vững"], ["Đột phá AI"], False, False, "web", 2),
            ("Buổi báo cáo với ban lãnh đạo chuẩn bị bắt đầu.", chat, ["Tăng trưởng bền vững"], ["Đột phá AI"], False, False, "web", 2),
            ("Tên chính thức trên trang bìa của bài thuyết trình là gì?", chat, ["Tăng trưởng bền vững"], ["Đột phá AI", "Mở rộng thị phần"], False, True, "web", 2),
        ],

        # 3. Two databases of same category requiring disambiguation
        "v3_03_two_databases_disambiguation": [
            ("Hãy nhớ rằng cơ sở dữ liệu giao dịch của tôi là PostgreSQL.", mem, ["PostgreSQL giao dịch"], [], False, False, "web", 1),
            ("Hãy nhớ rằng cơ sở dữ liệu phân tích nhật ký của tôi là ClickHouse.", mem, ["PostgreSQL giao dịch", "ClickHouse phân tích"], [], False, False, "web", 1),
            ("Hai hệ quản trị này đồng bộ qua đường truyền Kafka CDC.", chat, ["PostgreSQL giao dịch", "ClickHouse phân tích"], [], False, False, "web", 1),
            ("Độ trễ truyền tải dữ liệu hiện duy trì dưới nửa giây.", chat, ["PostgreSQL giao dịch", "ClickHouse phân tích"], [], False, False, "web", 1),
            ("Đổi cơ sở dữ liệu sang bản điện toán đám mây", clarify_ambig, ["PostgreSQL giao dịch", "ClickHouse phân tích"], [], True, False, "web", 1),
            ("Ý tôi là đổi cơ sở dữ liệu giao dịch PostgreSQL sang AWS Aurora.", change, ["PostgreSQL giao dịch", "ClickHouse phân tích"], [], True, False, "web", 1),
            ("Xác nhận chuyển đổi sang AWS Aurora", yes, ["AWS Aurora giao dịch", "ClickHouse phân tích"], ["PostgreSQL giao dịch"], False, False, "web", 1),
            ("Một kỹ sư đề nghị đổi ClickHouse sang Elasticsearch.", chat, ["AWS Aurora giao dịch", "ClickHouse phân tích"], ["PostgreSQL giao dịch"], False, False, "web", 1),
            ("Nhưng Elasticsearch tiêu tốn bộ nhớ quá, tôi không đồng ý.", chat, ["AWS Aurora giao dịch", "ClickHouse phân tích"], ["PostgreSQL giao dịch"], False, False, "web", 1),
            ("Đêm nay đội vận hành sẽ bảo trì hệ thống định kỳ lúc 0 giờ.", chat, ["AWS Aurora giao dịch", "ClickHouse phân tích"], ["PostgreSQL giao dịch"], False, False, "web", 1),
            ("Đã thông báo cho trung tâm hỗ trợ khách hàng đầy đủ.", chat, ["AWS Aurora giao dịch", "ClickHouse phân tích"], ["PostgreSQL giao dịch"], False, False, "web", 1),
            ("Dung lượng đĩa cứng trên các máy chủ còn hơn 60 phần trăm.", chat, ["AWS Aurora giao dịch", "ClickHouse phân tích"], ["PostgreSQL giao dịch"], False, False, "web", 1),
            ("Bản sao lưu hàng ngày đã hoàn tất an toàn.", chat, ["AWS Aurora giao dịch", "ClickHouse phân tích"], ["PostgreSQL giao dịch"], False, False, "web", 1),
            ("Mọi luồng dữ liệu đều đang chạy bình thường.", chat, ["AWS Aurora giao dịch", "ClickHouse phân tích"], ["PostgreSQL giao dịch"], False, False, "web", 1),
            ("Nơi lưu trữ dữ liệu phân tích sự kiện hiện tại là gì?", chat, ["ClickHouse phân tích"], ["Elasticsearch"], False, True, "web", 2),
            ("Hệ thống lưu các bản ghi thanh toán giao dịch đang dùng gì?", chat, ["AWS Aurora giao dịch"], ["PostgreSQL giao dịch"], False, True, "web", 2),
        ],

        # 4. User interface preference pivot & session timeouts
        "v3_04_session_timeout_preference_pivot": [
            ("Hãy nhớ rằng giao diện mặc định tôi muốn hiển thị là Chế độ tối.", mem, ["Chế độ tối"], [], False, False, "web", 1),
            ("Giao diện tối giúp tôi đỡ mỏi mắt khi làm việc buổi tối.", chat, ["Chế độ tối"], [], False, False, "web", 1),
            ("Đổi Chế độ tối sang Chế độ sáng", change, ["Chế độ tối"], [], True, False, "web", 1),
            ("Đồng ý chuyển sang giao diện sáng", yes, ["Chế độ sáng"], ["Chế độ tối"], False, False, "web", 1),
            ("Hãy nhớ rằng thời gian tự động khóa phiên làm việc là 30 phút.", mem, ["Chế độ sáng", "khóa phiên 30 phút"], ["Chế độ tối"], False, False, "web", 1),
            ("Đổi khóa phiên 30 phút sang khóa phiên 60 phút", change, ["Chế độ sáng", "khóa phiên 30 phút"], ["Chế độ tối"], True, False, "web", 1),
            ("Chấp nhận nâng lên 60 phút", yes, ["Chế độ sáng", "khóa phiên 60 phút"], ["Chế độ tối", "khóa phiên 30 phút"], False, False, "web", 1),
            ("Đổi Chế độ sáng sang Tương phản cao", change, ["Chế độ sáng", "khóa phiên 60 phút"], ["Chế độ tối", "khóa phiên 30 phút"], True, False, "web", 1),
            ("Không muốn đổi nữa, giữ nguyên giao diện sáng.", no, ["Chế độ sáng", "khóa phiên 60 phút"], ["Chế độ tối", "khóa phiên 30 phút"], False, False, "web", 1),
            ("Tôi nghe phong phanh trình duyệt sắp bỏ giới hạn cookie.", chat, ["Chế độ sáng", "khóa phiên 60 phút"], ["Chế độ tối"], False, False, "web", 1),
            ("Cái đó chưa được tổ chức tiêu chuẩn xác nhận đâu.", chat, ["Chế độ sáng", "khóa phiên 60 phút"], ["Chế độ tối"], False, False, "web", 1),
            ("Đang chuẩn bị cập nhật bản vá bảo mật cho cổng đăng nhập.", chat, ["Chế độ sáng", "khóa phiên 60 phút"], ["Chế độ tối"], False, False, "web", 1),
            ("Khách hàng phản hồi rất tốt về tốc độ tải trang.", chat, ["Chế độ sáng", "khóa phiên 60 phút"], ["Chế độ tối"], False, False, "web", 1),
            ("Màu sắc giao diện hiện đang được kích hoạt là gì?", chat, ["Chế độ sáng"], ["Chế độ tối", "Tương phản cao"], False, True, "web", 2),
            ("Sau bao lâu không thao tác thì hệ thống sẽ ngắt phiên?", chat, ["khóa phiên 60 phút"], ["khóa phiên 30 phút"], False, True, "web", 2),
        ],

        # 5. Authentication token succession & zero lexical query
        "v3_05_auth_token_succession": [
            ("Hãy nhớ rằng cơ chế xác thực người dùng ban đầu chọn JWT.", mem, ["JWT"], [], False, False, "web", 1),
            ("JWT stateless tiện nhưng khó thu hồi token tức thời.", chat, ["JWT"], [], False, False, "web", 1),
            ("Đổi JWT sang Session Cookie", change, ["JWT"], [], True, False, "web", 1),
            ("Đồng ý đổi sang Session Cookie", yes, ["Session Cookie"], ["JWT"], False, False, "web", 1),
            ("Đổi Session Cookie sang Opaque Token", change, ["Session Cookie"], ["JWT"], True, False, "web", 1),
            ("Chấp nhận chuyển sang Opaque Token", yes, ["Opaque Token"], ["JWT", "Session Cookie"], False, False, "web", 1),
            ("Có đề xuất dùng SAML 2.0 cho khối cơ quan nhà nước.", chat, ["Opaque Token"], ["JWT", "Session Cookie"], False, False, "web", 1),
            ("Đổi Opaque Token sang SAML 2.0", change, ["Opaque Token"], ["JWT", "Session Cookie"], True, False, "web", 1),
            ("Hủy yêu cầu, SAML cấu hình quá cồng kềnh.", no, ["Opaque Token"], ["JWT", "Session Cookie"], False, False, "web", 1),
            ("Đã triển khai Redis để lưu bảng ánh xạ mã phiên bí mật.", chat, ["Opaque Token"], ["JWT", "Session Cookie"], False, False, "web", 1),
            ("Độ dài chuỗi ngẫu nhiên là 32 byte an toàn tuyệt đối.", chat, ["Opaque Token"], ["JWT", "Session Cookie"], False, False, "web", 1),
            ("Cổng kết nối kiểm tra quyền hạn phản hồi trong 2 mili giây.", chat, ["Opaque Token"], ["JWT", "Session Cookie"], False, False, "web", 1),
            ("Kiểm thử tải đồng thời 5000 kết nối không có lỗi nào.", chat, ["Opaque Token"], ["JWT", "Session Cookie"], False, False, "web", 1),
            ("Tất cả bài kiểm tra an ninh mạng đều đã đạt điểm xanh.", chat, ["Opaque Token"], ["JWT", "Session Cookie"], False, False, "web", 1),
            ("Chúng ta chuyển sang tuần làm việc mới rồi.", chat, ["Opaque Token"], ["JWT", "Session Cookie"], False, False, "web", 2),
            ("Phương thức bảo vệ danh tính đăng nhập API hiện tại dùng gì?", chat, ["Opaque Token"], ["JWT", "Session Cookie", "SAML 2.0"], False, True, "web", 2),
        ],

        # 6. Event broker succession with elliptical requests
        "v3_06_microservice_event_broker": [
            ("Hãy nhớ rằng hạ tầng truyền thông điệp của chúng tôi dùng RabbitMQ.", mem, ["RabbitMQ"], [], False, False, "web", 1),
            ("Hàng đợi RabbitMQ chạy ổn với lưu lượng vừa phải.", chat, ["RabbitMQ"], [], False, False, "web", 1),
            ("Đổi RabbitMQ sang Apache Kafka", change, ["RabbitMQ"], [], True, False, "web", 1),
            ("Xác nhận chuyển sang Apache Kafka", yes, ["Apache Kafka"], ["RabbitMQ"], False, False, "web", 1),
            ("Một bạn đề xuất dùng NATS cho nhẹ hơn.", chat, ["Apache Kafka"], ["RabbitMQ"], False, False, "web", 1),
            ("Đổi Apache Kafka sang NATS", change, ["Apache Kafka"], ["RabbitMQ"], True, False, "web", 1),
            ("Không được, Kafka đã cấu hình phân vùng dữ liệu xong rồi.", no, ["Apache Kafka"], ["RabbitMQ"], False, False, "web", 1),
            ("Tra cứu hướng dẫn tối ưu số lượng partition cho cụm.", research, ["Apache Kafka"], ["RabbitMQ"], False, False, "web", 1),
            ("Rút ra 3 nguyên tắc chọn replication factor.", summarize, ["Apache Kafka"], ["RabbitMQ"], False, False, "web", 1),
            ("Hệ thống giám sát Prometheus đã tích hợp xong JMX exporter.", chat, ["Apache Kafka"], ["RabbitMQ"], False, False, "web", 1),
            ("Mức tiêu thụ CPU của các broker đang ở mức 15 phần trăm.", chat, ["Apache Kafka"], ["RabbitMQ"], False, False, "web", 1),
            ("Băng thông mạng nội bộ hoàn toàn đáp ứng tốt tải đỉnh.", chat, ["Apache Kafka"], ["RabbitMQ"], False, False, "web", 1),
            ("Chuẩn bị tài liệu kỹ thuật để bàn giao cho đội vận hành.", chat, ["Apache Kafka"], ["RabbitMQ"], False, False, "web", 1),
            ("Hôm nay làm việc rất hiệu quả, cảm ơn bạn.", chat, ["Apache Kafka"], ["RabbitMQ"], False, False, "web", 1),
            ("Hôm sau bắt đầu phiên mới trên máy tính khác.", chat, ["Apache Kafka"], ["RabbitMQ"], False, False, "web", 2),
            ("Còn cái để truyền sự kiện giữa các dịch vụ đang dùng gì?", chat, ["Apache Kafka"], ["RabbitMQ", "NATS"], False, True, "web", 2),
            ("Hệ thống cũ ban đầu có còn được dùng để truyền tin không?", chat, ["Apache Kafka"], ["RabbitMQ"], False, True, "web", 2),
        ],

        # 7. Heavy elliptical subject omission in Vietnamese dialogue
        "v3_07_elliptical_subject_omission": [
            ("Hãy nhớ rằng màu thương hiệu chính là Màu xanh dương.", mem, ["Màu xanh dương"], [], False, False, "web", 1),
            ("Trông rất chuyên nghiệp và đáng tin cậy.", chat, ["Màu xanh dương"], [], False, False, "web", 1),
            ("Đổi sang màu xanh ngọc bích", change, ["Màu xanh dương"], [], True, False, "web", 1),
            ("Đồng ý luôn đi.", yes, ["Màu xanh ngọc bích"], ["Màu xanh dương"], False, False, "web", 1),
            ("Đổi sang màu đỏ đô", change, ["Màu xanh ngọc bích"], ["Màu xanh dương"], True, False, "web", 1),
            ("Thôi đừng đổi, không thích.", no, ["Màu xanh ngọc bích"], ["Màu xanh dương"], False, False, "web", 1),
            ("Nhìn vẫn ổn định như trước.", chat, ["Màu xanh ngọc bích"], ["Màu xanh dương"], False, False, "web", 1),
            ("Bên in ấn vừa gọi điện hỏi xác nhận lại.", chat, ["Màu xanh ngọc bích"], ["Màu xanh dương"], False, False, "web", 1),
            ("Đang chuẩn bị in đồng phục cho cả công ty.", chat, ["Màu xanh ngọc bích"], ["Màu xanh dương"], False, False, "web", 1),
            ("Số lượng đặt in lần này khoảng hai trăm áo.", chat, ["Màu xanh ngọc bích"], ["Màu xanh dương"], False, False, "web", 1),
            ("Dự kiến tuần sau sẽ giao hàng tận nơi.", chat, ["Màu xanh ngọc bích"], ["Màu xanh dương"], False, False, "web", 1),
            ("Cần kiểm tra kỹ trước khi duyệt thanh toán hợp đồng.", chat, ["Màu xanh ngọc bích"], ["Màu xanh dương"], False, False, "web", 1),
            ("Thời hạn gửi file vector là chiều nay.", chat, ["Màu xanh ngọc bích"], ["Màu xanh dương"], False, False, "web", 1),
            ("Chốt lại thì màu đang áp dụng là màu nào?", chat, ["Màu xanh ngọc bích"], ["Màu xanh dương", "Màu đỏ đô"], False, True, "web", 2),
            ("Cái màu ban đầu lúc mới mở dự án còn dùng không?", chat, ["Màu xanh ngọc bích"], ["Màu xanh dương"], False, True, "web", 2),
        ],

        # 8. Budget allocation reversal and multi-turn corrections
        "v3_08_budget_allocation_reversal": [
            ("Hãy nhớ rằng hạn mức ngân sách quảng cáo tháng này là 50 triệu.", mem, ["ngân sách 50 triệu"], [], False, False, "web", 1),
            ("Chiến dịch tìm kiếm khách hàng mới đang chạy trên Google Ads.", chat, ["ngân sách 50 triệu"], [], False, False, "web", 1),
            ("Đổi ngân sách 50 triệu sang 80 triệu", change, ["ngân sách 50 triệu"], [], True, False, "web", 1),
            ("Xác nhận tăng lên 80 triệu", yes, ["ngân sách 80 triệu"], ["ngân sách 50 triệu"], False, False, "web", 1),
            ("Đổi ngân sách 80 triệu sang 120 triệu", change, ["ngân sách 80 triệu"], ["ngân sách 50 triệu"], True, False, "web", 1),
            ("Hủy đề xuất, dòng tiền chưa về kịp.", no, ["ngân sách 80 triệu"], ["ngân sách 50 triệu"], False, False, "web", 1),
            ("Đội kinh doanh mang về 3 hợp đồng lớn hôm qua.", chat, ["ngân sách 80 triệu"], ["ngân sách 50 triệu"], False, False, "web", 1),
            ("Chi phí chuyển đổi đơn hàng giảm được 15 phần trăm.", chat, ["ngân sách 80 triệu"], ["ngân sách 50 triệu"], False, False, "web", 1),
            ("Kênh mạng xã hội đang mang lại tỷ lệ tương tác cao nhất.", chat, ["ngân sách 80 triệu"], ["ngân sách 50 triệu"], False, False, "web", 1),
            ("Giám đốc tài chính đã phê duyệt phiếu thu chi tuần.", chat, ["ngân sách 80 triệu"], ["ngân sách 50 triệu"], False, False, "web", 1),
            ("Mọi khoản chi đều phải xuất trình hóa đơn đỏ.", chat, ["ngân sách 80 triệu"], ["ngân sách 50 triệu"], False, False, "web", 1),
            ("Cuối tuần này sẽ tổng kết hiệu quả chiến dịch đợt một.", chat, ["ngân sách 80 triệu"], ["ngân sách 50 triệu"], False, False, "web", 1),
            ("Đang chuẩn bị báo cáo số liệu cho nhà đầu tư.", chat, ["ngân sách 80 triệu"], ["ngân sách 50 triệu"], False, False, "web", 1),
            ("Con số tiền quảng cáo chính thức được duyệt hiện tại là bao nhiêu?", chat, ["ngân sách 80 triệu"], ["ngân sách 50 triệu", "120 triệu"], False, True, "web", 2),
            ("Khoản 50 triệu cũ có còn hiệu lực không?", chat, ["ngân sách 80 triệu"], ["ngân sách 50 triệu"], False, True, "web", 2),
        ],

        # 9. CI/CD pipeline migration across multiple revisions
        "v3_09_ci_cd_pipeline_migration": [
            ("Hãy nhớ rằng công cụ tự động hóa bản dựng tôi chọn là GitHub Actions.", mem, ["GitHub Actions"], [], False, False, "web", 1),
            ("Quy trình kiểm thử tự động kích hoạt mỗi khi có pull request mới.", chat, ["GitHub Actions"], [], False, False, "web", 1),
            ("Đổi GitHub Actions sang GitLab CI", change, ["GitHub Actions"], [], True, False, "web", 1),
            ("Đồng ý chuyển sang GitLab CI", yes, ["GitLab CI"], ["GitHub Actions"], False, False, "web", 1),
            ("Đổi GitLab CI sang Jenkins", change, ["GitLab CI"], ["GitHub Actions"], True, False, "web", 1),
            ("Không đổi, Jenkins bảo trì máy chủ tự dựng quá phức tạp.", no, ["GitLab CI"], ["GitHub Actions"], False, False, "web", 1),
            ("Runner của GitLab đang chạy trên cụm máy ảo riêng.", chat, ["GitLab CI"], ["GitHub Actions"], False, False, "web", 1),
            ("Thời gian chạy toàn bộ test giảm từ 15 phút xuống 4 phút.", chat, ["GitLab CI"], ["GitHub Actions"], False, False, "web", 1),
            ("Các container kiểm thử được dọn dẹp sạch sau mỗi lượt chạy.", chat, ["GitLab CI"], ["GitHub Actions"], False, False, "web", 1),
            ("Báo cáo độ phủ code tự động đẩy lên SonarQube.", chat, ["GitLab CI"], ["GitHub Actions"], False, False, "web", 1),
            ("Tất cả tiêu chí chất lượng mã nguồn đều vượt ngưỡng 85 phần trăm.", chat, ["GitLab CI"], ["GitHub Actions"], False, False, "web", 1),
            ("Đội ngũ lập trình viên rất hài lòng với tốc độ phản hồi.", chat, ["GitLab CI"], ["GitHub Actions"], False, False, "web", 1),
            ("Chiều nay sẽ triển khai thử nghiệm tính năng tự động phát hành tag.", chat, ["GitLab CI"], ["GitHub Actions"], False, False, "web", 1),
            ("Hệ sinh thái mã nguồn mở hoạt động rất trơn tru.", chat, ["GitLab CI"], ["GitHub Actions"], False, False, "web", 1),
            ("Công cụ chạy quy trình tự động hóa kiểm thử hiện nay của dự án là gì?", chat, ["GitLab CI"], ["GitHub Actions", "Jenkins"], False, True, "web", 2),
            ("Nền tảng của Microsoft lúc đầu còn dùng để build code không?", chat, ["GitLab CI"], ["GitHub Actions"], False, True, "web", 2),
        ],

        # 10. API Protocol gRPC vs GraphQL vs REST
        "v3_10_api_protocol_grpc_rest": [
            ("Hãy nhớ rằng giao thức truyền dữ liệu nội bộ tôi chọn là gRPC.", mem, ["gRPC"], [], False, False, "web", 1),
            ("Protobuf mã hóa nhị phân giúp giảm dung lượng gói tin đáng kể.", chat, ["gRPC"], [], False, False, "web", 1),
            ("Đổi gRPC sang GraphQL", change, ["gRPC"], [], True, False, "web", 1),
            ("Đồng ý dùng GraphQL", yes, ["GraphQL"], ["gRPC"], False, False, "web", 1),
            ("Đổi GraphQL sang REST truyền thống", change, ["GraphQL"], ["gRPC"], True, False, "web", 1),
            ("Không đồng ý, REST gặp vấn đề over-fetching dữ liệu.", no, ["GraphQL"], ["gRPC"], False, False, "web", 1),
            ("Schema GraphQL đang được kiểm soát phiên bản qua Apollo Studio.", chat, ["GraphQL"], ["gRPC"], False, False, "web", 1),
            ("Các client di động chỉ lấy đúng các trường cần thiết trên màn hình.", chat, ["GraphQL"], ["gRPC"], False, False, "web", 1),
            ("Độ trễ phản hồi trung bình của cổng truy vấn là 45 mili giây.", chat, ["GraphQL"], ["gRPC"], False, False, "web", 1),
            ("Bộ đệm cache tại tầng biên đã giảm tải cho máy chủ gốc 40 phần trăm.", chat, ["GraphQL"], ["gRPC"], False, False, "web", 1),
            ("Tài liệu API tự động sinh thông qua GraphQL Playground.", chat, ["GraphQL"], ["gRPC"], False, False, "web", 1),
            ("Khách hàng đối tác đánh giá cao tính linh hoạt của câu truy vấn.", chat, ["GraphQL"], ["gRPC"], False, False, "web", 1),
            ("Đã hoàn tất cấu hình giới hạn độ sâu truy vấn để chống tấn công.", chat, ["GraphQL"], ["gRPC"], False, False, "web", 1),
            ("Giao thức giao tiếp giữa ứng dụng client và máy chủ hiện là gì?", chat, ["GraphQL"], ["gRPC", "REST"], False, True, "web", 2),
            ("Phương án mã hóa Protobuf ban đầu có còn được sử dụng không?", chat, ["GraphQL"], ["gRPC"], False, True, "web", 2),
        ],

        # 11. Caching layer invalidation
        "v3_11_caching_layer_invalidation": [
            ("Hãy nhớ rằng giải pháp lưu đệm cache tôi chọn là Redis Cluster.", mem, ["Redis Cluster"], [], False, False, "web", 1),
            ("Cụm phân tán 3 node chính và 3 node phụ đảm bảo tính sẵn sàng.", chat, ["Redis Cluster"], [], False, False, "web", 1),
            ("Đổi Redis Cluster sang Memcached", change, ["Redis Cluster"], [], True, False, "web", 1),
            ("Hủy yêu cầu đổi, Memcached không hỗ trợ cấu trúc dữ liệu phức tạp.", no, ["Redis Cluster"], [], False, False, "web", 1),
            ("Chiến lược hết hạn khóa cache là LRU với thời gian sống 2 giờ.", chat, ["Redis Cluster"], [], False, False, "web", 1),
            ("Tỷ lệ truy vấn trúng cache đạt 94 phần trăm trong tuần qua.", chat, ["Redis Cluster"], [], False, False, "web", 1),
            ("Dữ liệu phiên đăng nhập và giỏ hàng đều được lưu đệm tại đây.", chat, ["Redis Cluster"], [], False, False, "web", 1),
            ("Cơ chế giải phóng bộ nhớ tự động vận hành trơn tru.", chat, ["Redis Cluster"], [], False, False, "web", 1),
            ("Không có cảnh báo tràn RAM nào được ghi nhận trong 48 giờ qua.", chat, ["Redis Cluster"], [], False, False, "web", 1),
            ("Băng thông mạng nội bộ dành cho cổng cache hoạt động ổn định.", chat, ["Redis Cluster"], [], False, False, "web", 1),
            ("Tối nay có lịch diễn tập tình huống một node cache bị sập.", chat, ["Redis Cluster"], [], False, False, "web", 1),
            ("Cụm phụ sẵn sàng tự động nhận quyền điều hành trong vòng 3 giây.", chat, ["Redis Cluster"], [], False, False, "web", 1),
            ("Mọi thủ tục kiểm thử chịu lỗi đều đã được lên kịch bản chi tiết.", chat, ["Redis Cluster"], [], False, False, "web", 1),
            ("Hạ tầng bộ nhớ tạm thời tăng tốc truy vấn hiện dùng giải pháp gì?", chat, ["Redis Cluster"], ["Memcached"], False, True, "web", 2),
            ("Đề xuất chuyển qua Memcached hôm trước đã được thông qua chưa?", chat, ["Redis Cluster"], ["Memcached"], False, True, "web", 2),
        ],

        # 12. Logging and observability stack
        "v3_12_logging_observability": [
            ("Hãy nhớ rằng hệ thống thu thập giám sát nhật ký chọn OpenTelemetry.", mem, ["OpenTelemetry"], [], False, False, "web", 1),
            ("Chuẩn mở giúp tránh bị khóa chặt vào một nhà cung cấp thương mại.", chat, ["OpenTelemetry"], [], False, False, "web", 1),
            ("Đổi OpenTelemetry sang Datadog", change, ["OpenTelemetry"], [], True, False, "web", 1),
            ("Chấp thuận chuyển sang Datadog", yes, ["Datadog"], ["OpenTelemetry"], False, False, "web", 1),
            ("Đổi Datadog sang Prometheus kết hợp Grafana", change, ["Datadog"], ["OpenTelemetry"], True, False, "web", 1),
            ("Thôi đừng đổi, Datadog có bảng điều khiển phân tích lỗi rất trực quan.", no, ["Datadog"], ["OpenTelemetry"], False, False, "web", 1),
            ("Agent Datadog đã cài đặt trên toàn bộ các máy chủ vùng sản xuất.", chat, ["Datadog"], ["OpenTelemetry"], False, False, "web", 1),
            ("Cảnh báo lỗi 5xx tự động gửi thông báo về kênh Slack kỹ thuật.", chat, ["Datadog"], ["OpenTelemetry"], False, False, "web", 1),
            ("Thời gian phát hiện sự cố trung bình giảm xuống còn 30 giây.", chat, ["Datadog"], ["OpenTelemetry"], False, False, "web", 1),
            ("Dung lượng log lưu giữ tối đa 30 ngày theo quy định an toàn.", chat, ["Datadog"], ["OpenTelemetry"], False, False, "web", 1),
            ("Đội trực vận hành có thể tra cứu vết sự cố xuyên suốt các dịch vụ.", chat, ["Datadog"], ["OpenTelemetry"], False, False, "web", 1),
            ("Chi phí dịch vụ giám sát hàng tháng nằm trong hạn mức cho phép.", chat, ["Datadog"], ["OpenTelemetry"], False, False, "web", 1),
            ("Hôm nay hệ thống đạt mức thời gian khả dụng 99.99 phần trăm.", chat, ["Datadog"], ["OpenTelemetry"], False, False, "web", 1),
            ("Công cụ giám sát và thu thập thông số vận hành hiện nay là gì?", chat, ["Datadog"], ["OpenTelemetry", "Prometheus"], False, True, "web", 2),
            ("Chuẩn mở ban đầu có còn được áp dụng để theo dõi hệ thống không?", chat, ["Datadog"], ["OpenTelemetry"], False, True, "web", 2),
        ],

        # 13. Frontend framework pivot
        "v3_13_frontend_framework_pivot": [
            ("Hãy nhớ rằng khung phát triển giao diện web tôi chọn là React.", mem, ["React"], [], False, False, "web", 1),
            ("Hệ sinh thái linh kiện và cộng đồng hỗ trợ của React rất phong phú.", chat, ["React"], [], False, False, "web", 1),
            ("Đổi React sang Vue.js", change, ["React"], [], True, False, "web", 1),
            ("Đồng ý chuyển sang Vue.js", yes, ["Vue.js"], ["React"], False, False, "web", 1),
            ("Đổi Vue.js sang Svelte", change, ["Vue.js"], ["React"], True, False, "web", 1),
            ("Hủy yêu cầu, Svelte thiếu nhiều thư viện hiển thị biểu đồ cần thiết.", no, ["Vue.js"], ["React"], False, False, "web", 1),
            ("Ứng dụng xây dựng bằng Vite cho tốc độ biên dịch mã nguồn cực nhanh.", chat, ["Vue.js"], ["React"], False, False, "web", 1),
            ("Pinia đảm nhận việc quản lý trạng thái tập trung rất mạch lạc.", chat, ["Vue.js"], ["React"], False, False, "web", 1),
            ("Dung lượng gói JavaScript xuất xưởng giảm hơn 30 phần trăm.", chat, ["Vue.js"], ["React"], False, False, "web", 1),
            ("Điểm đánh giá trải nghiệm người dùng trên Google Lighthouse đạt 98.", chat, ["Vue.js"], ["React"], False, False, "web", 1),
            ("Giao diện hoạt động mượt mà trên tất cả các trình duyệt phổ biến.", chat, ["Vue.js"], ["React"], False, False, "web", 1),
            ("Lập trình viên mới tiếp cận dự án chỉ mất hai ngày để làm quen.", chat, ["Vue.js"], ["React"], False, False, "web", 1),
            ("Tuần tới chúng ta sẽ bắt đầu thiết kế thêm tính năng đa ngôn ngữ.", chat, ["Vue.js"], ["React"], False, False, "web", 1),
            ("Bộ khung công nghệ dùng để dựng giao diện trang web hiện tại là gì?", chat, ["Vue.js"], ["React", "Svelte"], False, True, "web", 2),
            ("Thư viện giao diện lúc khởi đầu dự án còn được duy trì không?", chat, ["Vue.js"], ["React"], False, True, "web", 2),
        ],

        # 14. Search engine elastic vs meilisearch
        "v3_14_search_engine_elastic": [
            ("Hãy nhớ rằng công cụ tìm kiếm dữ liệu toàn văn tôi chọn là Elasticsearch.", mem, ["Elasticsearch"], [], False, False, "web", 1),
            ("Hỗ trợ tìm kiếm mờ và đánh chỉ mục đa ngôn ngữ rất mạnh mẽ.", chat, ["Elasticsearch"], [], False, False, "web", 1),
            ("Đổi Elasticsearch sang Meilisearch", change, ["Elasticsearch"], [], True, False, "web", 1),
            ("Xác nhận chuyển sang Meilisearch", yes, ["Meilisearch"], ["Elasticsearch"], False, False, "web", 1),
            ("Đổi Meilisearch sang Typesense", change, ["Meilisearch"], ["Elasticsearch"], True, False, "web", 1),
            ("Không đồng ý, Meilisearch xử lý tiếng Việt có dấu rất chuẩn xác rồi.", no, ["Meilisearch"], ["Elasticsearch"], False, False, "web", 1),
            ("Thời gian trả về kết quả tìm kiếm tức thì dưới 10 mili giây.", chat, ["Meilisearch"], ["Elasticsearch"], False, False, "web", 1),
            ("Chỉ mục tìm kiếm tự động cập nhật khi có bài viết hoặc sản phẩm mới.", chat, ["Meilisearch"], ["Elasticsearch"], False, False, "web", 1),
            ("Tính năng gợi ý từ khóa khi người dùng gõ phím hoạt động trơn tru.", chat, ["Meilisearch"], ["Elasticsearch"], False, False, "web", 1),
            ("Mức tiêu thụ bộ nhớ RAM giảm từ 4 Gigabyte xuống còn 600 Megabyte.", chat, ["Meilisearch"], ["Elasticsearch"], False, False, "web", 1),
            ("Đội ngũ biên tập nội dung rất thích giao diện quản trị tìm kiếm.", chat, ["Meilisearch"], ["Elasticsearch"], False, False, "web", 1),
            ("Bộ lọc theo danh mục và khoảng giá phản hồi tức thì không bị giật lag.", chat, ["Meilisearch"], ["Elasticsearch"], False, False, "web", 1),
            ("Chúng ta đã hoàn tất đợt tối ưu hóa công cụ tìm kiếm tháng này.", chat, ["Meilisearch"], ["Elasticsearch"], False, False, "web", 1),
            ("Giải pháp tìm kiếm văn bản và tài liệu hiện tại của hệ thống là gì?", chat, ["Meilisearch"], ["Elasticsearch", "Typesense"], False, True, "web", 2),
            ("Cỗ máy tìm kiếm cồng kềnh ban đầu có còn chạy ngầm không?", chat, ["Meilisearch"], ["Elasticsearch"], False, True, "web", 2),
        ],

        # 15. Mobile cross-platform framework
        "v3_15_mobile_cross_platform": [
            ("Hãy nhớ rằng giải pháp xây dựng ứng dụng di động tôi chọn là Flutter.", mem, ["Flutter"], [], False, False, "web", 1),
            ("Mã nguồn duy nhất chạy mượt trên cả Android và iOS.", chat, ["Flutter"], [], False, False, "web", 1),
            ("Đổi Flutter sang React Native", change, ["Flutter"], [], True, False, "web", 1),
            ("Chấp nhận chuyển sang React Native", yes, ["React Native"], ["Flutter"], False, False, "web", 1),
            ("Đổi React Native sang Native Swift và Kotlin", change, ["React Native"], ["Flutter"], True, False, "web", 1),
            ("Thôi đừng đổi, viết native tách rời tốn gấp đôi nhân sự phát triển.", no, ["React Native"], ["Flutter"], False, False, "web", 1),
            ("Expo giúp việc cập nhật ứng dụng qua mạng diễn ra tức thì.", chat, ["React Native"], ["Flutter"], False, False, "web", 1),
            ("Đội ngũ web có thể tham gia hỗ trợ viết tính năng cho app di động.", chat, ["React Native"], ["Flutter"], False, False, "web", 1),
            ("Thời gian ra mắt phiên bản mới rút ngắn còn một tuần.", chat, ["React Native"], ["Flutter"], False, False, "web", 1),
            ("Tỷ lệ crash trên thiết bị người dùng duy trì dưới 0.1 phần trăm.", chat, ["React Native"], ["Flutter"], False, False, "web", 1),
            ("Giao diện cảm ứng đạt chuẩn thiết kế của Apple và Google.", chat, ["React Native"], ["Flutter"], False, False, "web", 1),
            ("Bản thử nghiệm nội bộ TestFlight đã gửi cho các nhân viên trải nghiệm.", chat, ["React Native"], ["Flutter"], False, False, "web", 1),
            ("Mọi ý kiến đóng góp đầu tiên đều đánh giá trải nghiệm vuốt chạm tốt.", chat, ["React Native"], ["Flutter"], False, False, "web", 1),
            ("Nền tảng công nghệ dùng để phát triển app trên điện thoại là gì?", chat, ["React Native"], ["Flutter", "Native Swift"], False, True, "web", 2),
            ("Khung công nghệ của Google ban đầu còn được sử dụng không?", chat, ["React Native"], ["Flutter"], False, True, "web", 2),
        ],

        # 16. Object storage MinIO vs AWS S3 vs Cloudflare R2
        "v3_16_file_storage_minio_s3": [
            ("Hãy nhớ rằng kho lưu trữ tệp đính kèm tôi chọn là MinIO tự triển khai.", mem, ["MinIO tự triển khai"], [], False, False, "web", 1),
            ("Giao thức tương thích hoàn toàn chuẩn S3 giúp dễ dàng tích hợp.", chat, ["MinIO tự triển khai"], [], False, False, "web", 1),
            ("Đổi MinIO tự triển khai sang Cloudflare R2", change, ["MinIO tự triển khai"], [], True, False, "web", 1),
            ("Đồng ý chuyển sang Cloudflare R2", yes, ["Cloudflare R2"], ["MinIO tự triển khai"], False, False, "web", 1),
            ("Đổi Cloudflare R2 sang Amazon S3", change, ["Cloudflare R2"], ["MinIO tự triển khai"], True, False, "web", 1),
            ("Hủy đề xuất, Amazon S3 tính phí tải dữ liệu ra ngoài rất đắt đỏ.", no, ["Cloudflare R2"], ["MinIO tự triển khai"], False, False, "web", 1),
            ("Cloudflare R2 miễn phí hoàn toàn băng thông tải xuống cho người dùng.", chat, ["Cloudflare R2"], ["MinIO tự triển khai"], False, False, "web", 1),
            ("Tốc độ phân phối ảnh đại diện và tài liệu thông qua mạng CDN rất nhanh.", chat, ["Cloudflare R2"], ["MinIO tự triển khai"], False, False, "web", 1),
            ("Khóa bảo mật truy cập tệp có thời hạn tự hủy sau 15 phút.", chat, ["Cloudflare R2"], ["MinIO tự triển khai"], False, False, "web", 1),
            ("Dung lượng lưu trữ tài nguyên đa phương tiện hiện tại là 500 Gigabyte.", chat, ["Cloudflare R2"], ["MinIO tự triển khai"], False, False, "web", 1),
            ("Chi phí hàng tháng giảm được hơn 70 phần trăm so với phương án cũ.", chat, ["Cloudflare R2"], ["MinIO tự triển khai"], False, False, "web", 1),
            ("Quy trình kiểm tra tính toàn vẹn của tệp tải lên chạy tự động.", chat, ["Cloudflare R2"], ["MinIO tự triển khai"], False, False, "web", 1),
            ("Hôm nay không có báo cáo lỗi hỏng đường dẫn ảnh nào.", chat, ["Cloudflare R2"], ["MinIO tự triển khai"], False, False, "web", 1),
            ("Hệ thống lưu giữ các tệp hình ảnh và tài liệu người dùng ở đâu?", chat, ["Cloudflare R2"], ["MinIO tự triển khai", "Amazon S3"], False, True, "web", 2),
            ("Máy chủ lưu trữ tệp nội bộ ban đầu có còn được duy trì không?", chat, ["Cloudflare R2"], ["MinIO tự triển khai"], False, True, "web", 2),
        ],

        # 17. ML serving TorchServe vs ONNX Runtime
        "v3_17_ml_serving_onnx_torch": [
            ("Hãy nhớ rằng công cụ phục vụ suy luận mô hình AI chọn TorchServe.", mem, ["TorchServe"], [], False, False, "web", 1),
            ("Dễ dàng đóng gói các trọng số mô hình PyTorch nguyên bản.", chat, ["TorchServe"], [], False, False, "web", 1),
            ("Đổi TorchServe sang ONNX Runtime", change, ["TorchServe"], [], True, False, "web", 1),
            ("Xác nhận chuyển sang ONNX Runtime", yes, ["ONNX Runtime"], ["TorchServe"], False, False, "web", 1),
            ("Đổi ONNX Runtime sang Triton Inference Server", change, ["ONNX Runtime"], ["TorchServe"], True, False, "web", 1),
            ("Không đồng ý, Triton quá nặng nề cho cấu hình máy chủ hiện tại.", no, ["ONNX Runtime"], ["TorchServe"], False, False, "web", 1),
            ("ONNX Runtime tối ưu hóa đồ thị tính toán giúp giảm độ trễ 45 phần trăm.", chat, ["ONNX Runtime"], ["TorchServe"], False, False, "web", 1),
            ("Khả năng tăng tốc phần cứng thông qua OpenVINO và DirectML rất tốt.", chat, ["ONNX Runtime"], ["TorchServe"], False, False, "web", 1),
            ("Thời gian suy luận mỗi lượt dự đoán định tuyến chỉ mất 3 mili giây.", chat, ["ONNX Runtime"], ["TorchServe"], False, False, "web", 1),
            ("Tiến trình phục vụ chiếm dụng ít hơn 200 Megabyte bộ nhớ hệ thống.", chat, ["ONNX Runtime"], ["TorchServe"], False, False, "web", 1),
            ("Đã thiết lập kịch bản chạy song song trên 4 luồng xử lý độc lập.", chat, ["ONNX Runtime"], ["TorchServe"], False, False, "web", 1),
            ("Toàn bộ các bài kiểm tra áp lực tải cao đều vượt qua xuất sắc.", chat, ["ONNX Runtime"], ["TorchServe"], False, False, "web", 1),
            ("Sẵn sàng đưa cụm máy chủ dự đoán vào phục vụ người dùng thực tế.", chat, ["ONNX Runtime"], ["TorchServe"], False, False, "web", 1),
            ("Bộ máy thực thi dự đoán mạng nơ-ron hiện tại của dự án là gì?", chat, ["ONNX Runtime"], ["TorchServe", "Triton"], False, True, "web", 2),
            ("Phương án chạy mô hình PyTorch ban đầu có còn được sử dụng không?", chat, ["ONNX Runtime"], ["TorchServe"], False, True, "web", 2),
        ],

        # 18. Rate limiting algorithm
        "v3_18_rate_limiting_algorithm": [
            ("Hãy nhớ rằng thuật toán kiểm soát tần suất gọi API là Token Bucket.", mem, ["Token Bucket"], [], False, False, "web", 1),
            ("Cho phép xử lý linh hoạt các đợt bùng nổ lưu lượng truy cập ngắn.", chat, ["Token Bucket"], [], False, False, "web", 1),
            ("Đổi Token Bucket sang Leaky Bucket", change, ["Token Bucket"], [], True, False, "web", 1),
            ("Hủy yêu cầu đổi, Leaky Bucket giới hạn tốc độ quá cứng nhắc.", no, ["Token Bucket"], [], False, False, "web", 1),
            ("Mỗi tài khoản người dùng được cấp 100 token mỗi phút.", chat, ["Token Bucket"], [], False, False, "web", 1),
            ("Các yêu cầu vượt hạn mức sẽ nhận phản hồi mã lỗi 429 quá tải.", chat, ["Token Bucket"], [], False, False, "web", 1),
            ("Trạng thái số dư token được lưu trên Redis Cluster có độ trễ cực thấp.", chat, ["Token Bucket"], [], False, False, "web", 1),
            ("Đã cấu hình danh sách trắng cho các dịch vụ thanh toán đối tác.", chat, ["Token Bucket"], [], False, False, "web", 1),
            ("Không có cuộc tấn công làm tràn ngập lưu lượng nào vượt qua được cửa ngõ.", chat, ["Token Bucket"], [], False, False, "web", 1),
            ("Khách hàng doanh nghiệp được nâng hạn mức lên gấp mười lần.", chat, ["Token Bucket"], [], False, False, "web", 1),
            ("Báo cáo tuần cho thấy chỉ có 0.05 phần trăm yêu cầu bị chặn lại.", chat, ["Token Bucket"], [], False, False, "web", 1),
            ("Cơ chế phục hồi token theo chu kỳ một giây chạy ổn định liên tục.", chat, ["Token Bucket"], [], False, False, "web", 1),
            ("Hệ thống bảo vệ tầng mạng đã hoàn thiện các bước kiểm thử cuối.", chat, ["Token Bucket"], [], False, False, "web", 1),
            ("Cơ chế tính toán hạn mức ngăn chặn spam yêu cầu API đang áp dụng là gì?", chat, ["Token Bucket"], ["Leaky Bucket"], False, True, "web", 2),
            ("Đề xuất đổi sang thuật toán cái xô rò rỉ hôm trước có được duyệt không?", chat, ["Token Bucket"], ["Leaky Bucket"], False, True, "web", 2),
        ],

        # 19. Export report format
        "v3_19_export_report_format": [
            ("Hãy nhớ rằng định dạng xuất báo cáo phân tích chọn Tập tin PDF.", mem, ["Tập tin PDF"], [], False, False, "web", 1),
            ("Đảm bảo bố cục hiển thị đồng nhất trên mọi máy tính và thiết bị.", chat, ["Tập tin PDF"], [], False, False, "web", 1),
            ("Đổi Tập tin PDF sang Bảng tính Excel", change, ["Tập tin PDF"], [], True, False, "web", 1),
            ("Đồng ý chuyển sang Bảng tính Excel", yes, ["Bảng tính Excel"], ["Tập tin PDF"], False, False, "web", 1),
            ("Đổi Bảng tính Excel sang Bản trình bày PowerPoint", change, ["Bảng tính Excel"], ["Tập tin PDF"], True, False, "web", 1),
            ("Không đồng ý, phòng kế toán cần file bảng tính để tính toán công thức.", no, ["Bảng tính Excel"], ["Tập tin PDF"], False, False, "web", 1),
            ("Mỗi bảng tính tự động gắn sẵn biểu đồ và công thức tổng kết tự động.", chat, ["Bảng tính Excel"], ["Tập tin PDF"], False, False, "web", 1),
            ("Đã thiết lập tính năng khóa các ô dữ liệu nhạy cảm bằng mật khẩu.", chat, ["Bảng tính Excel"], ["Tập tin PDF"], False, False, "web", 1),
            ("Thời gian xuất một báo cáo mười nghìn dòng mất chưa đầy một giây.", chat, ["Bảng tính Excel"], ["Tập tin PDF"], False, False, "web", 1),
            ("Người dùng có thể tải trực tiếp file về từ bảng điều khiển cá nhân.", chat, ["Bảng tính Excel"], ["Tập tin PDF"], False, False, "web", 1),
            ("Đội tài chính đã xác nhận nhận đủ các file tổng kết tháng trước.", chat, ["Bảng tính Excel"], ["Tập tin PDF"], False, False, "web", 1),
            ("Tất cả công thức tính toán thuế và khấu trừ đều chính xác tuyệt đối.", chat, ["Bảng tính Excel"], ["Tập tin PDF"], False, False, "web", 1),
            ("Chúng ta đã hoàn thành xuất sắc đợt đối soát tài chính kỳ này.", chat, ["Bảng tính Excel"], ["Tập tin PDF"], False, False, "web", 1),
            ("Loại tệp tin xuất số liệu chính thức hiện nay là định dạng gì?", chat, ["Bảng tính Excel"], ["Tập tin PDF", "PowerPoint"], False, True, "web", 2),
            ("Định dạng tài liệu văn bản cố định ban đầu còn dùng để gửi số liệu không?", chat, ["Bảng tính Excel"], ["Tập tin PDF"], False, True, "web", 2),
        ],

        # 20. Zero-keyword 10-turn temporal gap detour
        "v3_20_zero_keyword_temporal_gap": [
            ("Hãy nhớ rằng kiến trúc nền tảng chúng tôi thống nhất là Hướng sự kiện phân tán.", mem, ["Hướng sự kiện phân tán"], [], False, False, "web", 1),
            ("Hôm nay trời có vẻ sắp đổ mưa to vào buổi chiều.", chat, ["Hướng sự kiện phân tán"], [], False, False, "web", 1),
            ("Bạn có thích uống cà phê hay trà sữa hơn vào giờ nghỉ trưa?", chat, ["Hướng sự kiện phân tán"], [], False, False, "web", 1),
            ("Quán ăn đối diện công ty vừa đổi món mới trong thực đơn.", chat, ["Hướng sự kiện phân tán"], [], False, False, "web", 1),
            ("Hôm qua tôi quên mang chìa khóa xe phải đi xe buýt về nhà.", chat, ["Hướng sự kiện phân tán"], [], False, False, "web", 1),
            ("Đường phố giờ tan tầm dạo này đông đúc và kẹt xe liên tục.", chat, ["Hướng sự kiện phân tán"], [], False, False, "web", 1),
            ("Ngày mai là thứ sáu cuối tuần rồi, thời gian trôi nhanh thật.", chat, ["Hướng sự kiện phân tán"], [], False, False, "web", 1),
            ("Cuối tuần này tôi dự định đi bơi cùng mấy người bạn thân.", chat, ["Hướng sự kiện phân tán"], [], False, False, "web", 1),
            ("Bộ phim mới chiếu ngoài rạp nhận được rất nhiều lời khen ngợi.", chat, ["Hướng sự kiện phân tán"], [], False, False, "web", 1),
            ("Tôi đang đọc một cuốn sách thú vị về lịch sử thời Phục Hưng.", chat, ["Hướng sự kiện phân tán"], [], False, False, "web", 1),
            ("Âm nhạc không lời giúp tăng sự tập trung đáng kể khi làm việc.", chat, ["Hướng sự kiện phân tán"], [], False, False, "web", 1),
            ("Cây xanh để trên bàn làm việc hôm nay đã bắt đầu nở hoa nhỏ.", chat, ["Hướng sự kiện phân tán"], [], False, False, "web", 1),
            ("Vừa uống xong một cốc nước lọc mát lạnh thấy tỉnh táo hẳn.", chat, ["Hướng sự kiện phân tán"], [], False, False, "web", 1),
            ("Đã đến giờ quay lại với các công việc kỹ thuật chuyên môn rồi.", chat, ["Hướng sự kiện phân tán"], [], False, False, "web", 1),
            ("Bạn còn nhớ các nội dung công việc chúng ta đã bàn không?", chat, ["Hướng sự kiện phân tán"], [], False, False, "web", 1),
            ("Cái nền tảng ban đầu thống nhất đã sẵn sàng chạy chưa?", chat, ["Hướng sự kiện phân tán"], [], False, True, "web", 2),
            ("Mô hình thiết kế hệ thống đã chốt ở lượt đầu tiên là gì?", chat, ["Hướng sự kiện phân tán"], [], False, True, "web", 2),
            ("Có bất kỳ quyết định thay đổi cấu trúc nào khác được đưa ra không?", chat, ["Hướng sự kiện phân tán"], [], False, True, "web", 2),
        ],
    }

    families = list(bank)
    rng.shuffle(families)
    rows = []
    for family in families:
        seq = f"holdout3-{seed}-{family}"
        prior = []
        for step, turn_data in enumerate(bank[family], 1):
            text, route, active, obsolete, clarify, target, platform, session = turn_data[:8]
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
