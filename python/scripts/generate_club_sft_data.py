#!/usr/bin/env python3
"""Generate the 3-tier SFT dataset for the Club IT Assistant.

Produces datasets/club_sft_v1/:
- tier1_conversations.jsonl: ~250 multi-turn personalization conversations.
- tier2_extractive.jsonl: ~360 grounded QA pairs from all 18 documents.
- tier3_refuse.jsonl: ~100 polite out-of-scope refusals with guidance.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "datasets" / "club_corpus_v1" / "docs"
OUT_DIR = REPO_ROOT / "datasets" / "club_sft_v1"

SYSTEM_PROMPT = (
    "Bạn là Trợ lý AI cá nhân hoá của CLB IT. Bạn hỗ trợ giải đáp quy chế, lịch trình, "
    "sự kiện và quản lý công việc cho thành viên câu lạc bộ. Khi trả lời kiến thức, bạn "
    "luôn trích dẫn nguồn từ tài liệu CLB. Khi người dùng yêu cầu ghi nhớ thông tin cá nhân, "
    "bạn hỏi lại để xác nhận. Với các câu hỏi ngoài phạm vi CLB, bạn từ chối lịch sự và gợi ý câu hỏi phù hợp."
)

DOC_QA = [
    {
        "doc": "01-quy-che-hoat-dong.md",
        "title": "Quy chế hoạt động CLB IT",
        "items": [
            ("CLB IT thành lập khi nào?", "CLB IT được thành lập vào ngày 15/10/2021 [S1].", "theo Điều 1 Quy chế"),
            ("Mục tiêu chính của CLB IT là gì?", "Mục tiêu là tạo môi trường học tập, nghiên cứu và chia sẻ kiến thức CNTT [S1].", "Điều 2 mục tiêu"),
            ("Nguyên tắc hoạt động của CLB là gì?", "CLB hoạt động trên nguyên tắc tự nguyện, dân chủ và tuân thủ quy định nhà trường [S1].", "nguyên tắc Điều 3"),
            ("Nhiệm kỳ Ban chủ nhiệm kéo dài bao lâu?", "Nhiệm kỳ Ban chủ nhiệm là 01 năm học, bầu tại Đại hội thành viên [S1].", "nhiệm kỳ Điều 5"),
            ("Thành viên có quyền lợi gì trong CLB?", "Thành viên được tham gia các buổi workshop, hackathon và sử dụng thiết bị phòng lab [S1].", "quyền lợi thành viên"),
        ]
    },
    {
        "doc": "02-ban-chu-nhiem.md",
        "title": "Cơ cấu Ban chủ nhiệm",
        "items": [
            ("Chủ nhiệm CLB IT hiện tại là ai?", "Chủ nhiệm CLB IT hiện tại là bạn Nguyễn Minh Anh [S1].", "Chủ nhiệm"),
            ("Phó chủ nhiệm CLB là ai?", "Phó chủ nhiệm CLB IT là bạn Lê Quốc Bảo [S1].", "Phó chủ nhiệm"),
            ("Trưởng ban kỹ thuật là ai?", "Trưởng ban kỹ thuật là bạn Đỗ Nam Khánh [S1].", "Trưởng ban kỹ thuật"),
            ("Trưởng ban truyền thông là ai?", "Trưởng ban truyền thông là bạn Trần Hà Vy [S1].", "Trưởng ban truyền thông"),
            ("Trưởng ban hậu cần là ai?", "Trưởng ban hậu cần là bạn Phạm Thuỳ Dương [S1].", "Trưởng ban hậu cần"),
        ]
    },
    {
        "doc": "03-lich-sinh-hoat.md",
        "title": "Lịch sinh hoạt định kỳ",
        "items": [
            ("CLB sinh hoạt vào thứ mấy?", "CLB IT sinh hoạt định kỳ vào 18h30 Thứ Sáu hàng tuần [S1].", "thời gian sinh hoạt"),
            ("Địa điểm sinh hoạt CLB ở đâu?", "Địa điểm sinh hoạt tại Phòng Lab 402, Nhà H1 [S1].", "địa điểm"),
            ("Tuần lẻ và tuần chẵn sinh hoạt khác nhau thế nào?", "Tuần lẻ sinh hoạt chuyên môn theo ban, tuần chẵn sinh hoạt toàn thể CLB [S1].", "lịch chẵn lẻ"),
            ("Nếu bận không tham gia sinh hoạt thì phải làm gì?", "Thành viên phải xin phép trước 12h qua Trưởng ban hoặc nhóm chat [S1].", "xin nghỉ sinh hoạt"),
            ("Nghỉ mấy buổi thì bị nhắc nhở?", "Nghỉ quá 2 buổi không phép trong một tháng sẽ bị nhắc nhở và xem xét tư cách [S1].", "quy định nghỉ"),
        ]
    },
    {
        "doc": "04-it-codefest-2026.md",
        "title": "Hackathon IT CodeFest 2026",
        "items": [
            ("IT CodeFest 2026 diễn ra vào ngày nào?", "IT CodeFest 2026 diễn ra từ 28/11 đến 30/11/2026 [S1].", "ngày tổ chức"),
            ("Mỗi đội thi CodeFest gồm mấy thành viên?", "Mỗi đội thi gồm từ 3 đến 5 thành viên [S1].", "số lượng thành viên"),
            ("Giải nhất IT CodeFest trị giá bao nhiêu?", "Giải nhất trị giá 5.000.000 VNĐ kèm kỷ niệm chương [S1].", "giải thưởng"),
            ("Chủ đề CodeFest năm nay là gì?", "Chủ đề năm nay là 'Ứng dụng AI nâng cao trải nghiệm sinh viên' [S1].", "chủ đề cuộc thi"),
            ("Hạn chót nộp ý tưởng CodeFest là ngày nào?", "Hạn chót đăng ký và nộp ý tưởng sơ khảo là 23h59 ngày 22/11/2026 [S1].", "hạn đăng ký"),
        ]
    },
    {
        "doc": "05-don-dang-ky-thanh-vien.md",
        "title": "Quy trình đăng ký thành viên",
        "items": [
            ("Ai có thể đăng ký tham gia CLB IT?", "Tất cả sinh viên đam mê công nghệ thông tin đều có thể đăng ký tham gia [S1].", "đối tượng đăng ký"),
            ("Quy trình tuyển thành viên gồm mấy vòng?", "Quy trình gồm 3 vòng: Đơn đăng ký trực tuyến, Phỏng vấn và Thử thách chuyên môn [S1].", "các vòng tuyển"),
            ("Thời gian thử thách của tân thành viên là bao lâu?", "Thời gian thử thách là 04 tuần kể từ khi nhận kết quả phỏng vấn [S1].", "thời gian thử việc"),
        ]
    },
    {
        "doc": "06-quy-dinh-phong-lab.md",
        "title": "Nội quy phòng lab 402",
        "items": [
            ("Phòng lab mở cửa vào khung giờ nào?", "Phòng lab 402 mở cửa từ 8h00 đến 21h00 các ngày trong tuần [S1].", "giờ mở cửa"),
            ("Có được mang đồ ăn vào phòng lab không?", "Nghiêm cấm mang đồ ăn, nước ngọt không nắp vào phòng lab [S1].", "quy định ăn uống"),
            ("Quy định mượn thiết bị phòng lab như thế nào?", "Thành viên mượn thiết bị phải ghi sổ bàn giao và được Ban kỹ thuật ký xác nhận [S1].", "mượn thiết bị"),
            ("Khi ra khỏi phòng lab cần làm gì?", "Thành viên cuối cùng rời phòng lab phải tắt đèn, điều hòa, ngắt cầu dao tổng và khóa cửa bàn giao chìa khóa cho bảo vệ [S1].", "quy trình đóng cửa lab"),
        ]
    },
    {
        "doc": "07-ke-hoach-tai-chinh.md",
        "title": "Kế hoạch tài chính & Thu chi",
        "items": [
            ("Quỹ CLB được dùng vào mục đích gì?", "Quỹ CLB dùng để tổ chức sự kiện, mua sắm vật tư phòng lab và khen thưởng [S1].", "mục đích quỹ"),
            ("Báo cáo tài chính được công khai khi nào?", "Báo cáo tài chính được công khai vào ngày mùng 5 hàng tháng trong nhóm Toàn CLB [S1].", "công khai tài chính"),
            ("Ai là người giữ và quản lý quỹ CLB?", "Trưởng ban hậu cần trực tiếp giữ quỹ dưới sự giám sát của Phó chủ nhiệm và Chủ nhiệm CLB [S1].", "người giữ quỹ"),
            ("Khoản chi nào trên 500.000đ cần ai duyệt?", "Mọi khoản chi trên 500.000 VNĐ bắt buộc phải có sự phê duyệt của Chủ nhiệm CLB [S1].", "hạn mức chi quỹ"),
        ]
    },
    {
        "doc": "08-onboarding-tan-thanh-vien.md",
        "title": "Onboarding tân thành viên",
        "items": [
            ("Tân thành viên cần hoàn thành gì trong tuần đầu?", "Cần tham gia buổi Welcome Day, nhận email nội bộ và tham gia nhóm ban [S1].", "tuần đầu onboarding"),
            ("Mỗi tân thành viên có được chỉ dẫn riêng không?", "Mỗi tân thành viên được phân công 01 mentor trong ban hướng dẫn [S1].", "mentor chỉ dẫn"),
            ("Buổi sinh hoạt đầu tiên của tân thành viên có nội dung gì?", "Tân thành viên được giới thiệu cơ cấu CLB, nhận tài liệu nội quy và ký cam kết tham gia [S1].", "buổi đầu tân thành viên"),
        ]
    },
    {
        "doc": "09-noi-quy-sinh-hoat.md",
        "title": "Nội quy sinh hoạt CLB",
        "items": [
            ("Trang phục khi sinh hoạt CLB quy định thế nào?", "Trang phục lịch sự, khuyến khích mặc áo đồng phục CLB vào tuần chẵn [S1].", "trang phục"),
            ("Đến muộn buổi sinh hoạt quá 15 phút bị phạt gì?", "Đến muộn quá 15 phút không lý do sẽ nộp phạt 20.000đ vào quỹ liên hoan [S1].", "phạt muộn"),
            ("Thành viên nghỉ có phép tối đa mấy buổi trong một kỳ?", "Thành viên được nghỉ có phép tối đa 3 buổi trong một học kỳ [S1].", "số buổi nghỉ có phép"),
            ("Hành vi nào bị kỷ luật khai trừ khỏi CLB?", "Hành vi vi phạm pháp luật, làm rò rỉ dữ liệu nội bộ hoặc xúc phạm danh dự thành viên khác sẽ bị khai trừ [S1].", "kỷ luật khai trừ"),
        ]
    },
    {
        "doc": "10-lich-workshop.md",
        "title": "Lịch workshop học thuật",
        "items": [
            ("Workshop 'Xây dựng Web App với React & Vite' diễn ra khi nào?", "Workshop diễn ra vào 9h00 sáng Thứ Bảy ngày 21/11/2026 tại Lab 402 [S1].", "thời gian workshop React"),
            ("Diễn giả của buổi workshop Docker & CI/CD là ai?", "Diễn giả là cựu thành viên CLB - Kỹ sư Nguyễn Hải Đăng [S1].", "diễn giả workshop"),
            ("Workshop tháng 12 có những chủ đề nào?", "Gồm 2 chủ đề: Xây dựng Web App với React và Nhập môn CI/CD với Docker [S1].", "chủ đề workshop tháng 12"),
            ("Thành viên tham gia workshop có cần đăng ký trước không?", "Thành viên cần đăng ký trước 48h qua form nội bộ để Ban tổ chức sắp xếp chỗ ngồi phòng lab [S1].", "đăng ký workshop"),
        ]
    },
    {
        "doc": "11-danh-sach-thanh-vien.md",
        "title": "Danh sách thành viên chính thức",
        "items": [
            ("Thành viên mang mã IT-001 tên là gì?", "Thành viên mã IT-001 là Vũ Hoàng Long thuộc Ban kỹ thuật [S1].", "thành viên IT-001"),
            ("Ban truyền thông có những thành viên nào tiêu biểu?", "Gồm Ngô Gia Hân (IT-002), Trịnh Minh Khoa (IT-005) cùng Trưởng ban Trần Hà Vy [S1].", "thành viên truyền thông"),
            ("Tổng số thành viên chính thức hiện tại là bao nhiêu?", "Hiện tại CLB IT có 35 thành viên chính thức chia đều cho các ban chuyên môn [S1].", "tổng số thành viên"),
            ("Cách tra cứu mã số thành viên như thế nào?", "Mã số thành viên có định dạng IT-xxx được ghi trong bảng danh sách thành viên nội bộ [S1].", "tra cứu mã thành viên"),
        ]
    },
    {
        "doc": "12-quy-dinh-bao-mat-thiet-bi.md",
        "title": "Quy định bảo mật thiết bị",
        "items": [
            ("Mật khẩu Wifi phòng Lab là gì?", "Mật khẩu được cấp riêng cho thành viên đã duyệt và nghiêm cấm chia sẻ ra ngoài [S1].", "Wifi lab"),
            ("Server nội bộ CLB có được mở cổng ra Internet không?", "Server nội bộ chỉ được truy cập qua VPN hoặc mạng LAN phòng lab [S1].", "mạng server"),
            ("Có được tự ý cài đặt phần mềm lạ vào máy lab không?", "Nghiêm cấm tự ý cài đặt phần mềm độc hại, phần mềm không bản quyền vào máy tính phòng lab [S1].", "cài đặt phần mềm lab"),
            ("Khi phát hiện thiết bị lab bị hỏng thì báo cho ai?", "Thành viên phải báo ngay cho Ban kỹ thuật để lập biên bản kiểm tra và sửa chữa [S1].", "báo hỏng thiết bị"),
        ]
    },
    {
        "doc": "13-tuyen-thanh-vien-dot-2.md",
        "title": "Tuyển thành viên đợt 2",
        "items": [
            ("Chỉ tiêu tuyển thành viên đợt 2 là bao nhiêu?", "Chỉ tiêu tuyển 15 thành viên mới cho cả 3 ban [S1].", "chỉ tiêu tuyển"),
            ("Đợt 2 ưu tiên kỹ năng gì?", "Ưu tiên kỹ năng lập trình Python/NodeJS, thiết kế đồ hoạ Canva/Figma và truyền thông [S1].", "ưu tiên kỹ năng"),
            ("Thời gian mở đơn tuyển thành viên đợt 2 khi nào?", "Đơn đăng ký đợt 2 mở từ ngày 10/11 đến hết 20/11/2026 [S1].", "thời gian mở đơn đợt 2"),
            ("Hình thức phỏng vấn đợt 2 là trực tiếp hay online?", "Vòng phỏng vấn diễn ra trực tiếp tại Phòng Lab 402, Nhà H1 [S1].", "hình thức phỏng vấn"),
        ]
    },
    {
        "doc": "14-demo-day.md",
        "title": "Sự kiện Demo Day cuối kỳ",
        "items": [
            ("Demo Day cuối kỳ tổ chức vào thời gian nào?", "Demo Day dự kiến tổ chức vào tuần thứ 15 của học kỳ (tháng 12/2026) [S1].", "thời gian Demo Day"),
            ("Mỗi dự án được trình bày trong bao lâu tại Demo Day?", "Mỗi nhóm có 10 phút thuyết trình và 5 phút phản biện cùng Hội đồng [S1].", "thời lượng thuyết trình"),
            ("Hội đồng đánh giá Demo Day gồm những ai?", "Gồm Ban chủ nhiệm CLB, Cố vấn học thuật và đại diện doanh nghiệp công nghệ [S1].", "hội đồng chấm Demo Day"),
            ("Tiêu chí chấm điểm sản phẩm Demo Day là gì?", "Gồm: Tính sáng tạo (30%), Độ hoàn thiện kỹ thuật (40%), Tính ứng dụng (20%) và Thuyết trình (10%) [S1].", "tiêu chí chấm Demo Day"),
        ]
    },
    {
        "doc": "15-nhan-dien-clb.md",
        "title": "Bộ nhận diện thương hiệu CLB",
        "items": [
            ("Màu sắc chủ đạo của CLB IT là màu gì?", "Màu chủ đạo là Xanh dương (#0066CC) và Cam năng động (#FF6600) [S1].", "màu sắc logo"),
            ("Slogan chính thức của CLB IT là gì?", "Slogan là 'Kết nối đam mê — Bứt phá công nghệ' [S1].", "slogan CLB"),
            ("Font chữ chính thức trên các ấn phẩm của CLB là gì?", "Font chữ chính thức là Inter và Montserrat [S1].", "font chữ thương hiệu"),
            ("Quy định sử dụng logo CLB như thế nào?", "Logo không được bóp méo tỷ lệ, không đổi màu và phải đặt trên nền tương phản rõ ràng [S1].", "quy chuẩn sử dụng logo"),
        ]
    },
    {
        "doc": "16-dong-quy-clb.md",
        "title": "Quy định đóng quỹ CLB",
        "items": [
            ("Mức đóng quỹ CLB mỗi tháng là bao nhiêu?", "Mức đóng quỹ định kỳ là 50.000 VNĐ / tháng cho mỗi thành viên [S1].", "mức đóng quỹ"),
            ("Hạn chót nộp quỹ tháng là ngày nào?", "Hạn chót nộp quỹ là ngày 20 hàng tháng qua Ban hậu cần [S1].", "hạn nộp quỹ"),
            ("Hình thức đóng quỹ là tiền mặt hay chuyển khoản?", "Khuyến khích chuyển khoản qua số tài khoản quỹ do Ban hậu cần công bố, hoặc nộp trực tiếp [S1].", "hình thức đóng quỹ"),
            ("Thành viên có hoàn cảnh khó khăn có được miễn giảm quỹ không?", "Thành viên có đơn xin miễn giảm sẽ được Ban chủ nhiệm xem xét giảm 50% hoặc 100% quỹ kỳ đó [S1].", "miễn giảm quỹ"),
        ]
    },
    {
        "doc": "17-team-building.md",
        "title": "Hoạt động Team Building dã ngoại",
        "items": [
            ("Chuyến team building kỳ này đi đâu?", "Chuyến team building tổ chức tại Khu sinh thái Đồng Mô [S1].", "địa điểm team building"),
            ("Thời gian chuyến đi team building là khi nào?", "Chuyến đi diễn ra trong 2 ngày 1 đêm: 05-06/12/2026 [S1].", "ngày đi team building"),
            ("Kinh phí tham gia team building được hỗ trợ thế nào?", "Quỹ CLB hỗ trợ 50% chi phí xe di chuyển và teabreak; thành viên đóng tiền ăn ở còn lại [S1].", "kinh phí hỗ trợ team building"),
            ("Hoạt động chính trong chuyến team building là gì?", "Gồm các trò chơi gắn kết ngoài trời, lửa trại giao lưu và gala tổng kết quý [S1].", "hoạt động team building"),
        ]
    },
    {
        "doc": "18-danh-gia-thanh-vien.md",
        "title": "Tiêu chí đánh giá thành viên",
        "items": [
            ("Đánh giá thành viên dựa trên các thang điểm nào?", "Dựa trên: Chuyên cần (40%), Đóng góp chuyên môn (40%) và Tinh thần đồng đội (20%) [S1].", "thang điểm đánh giá"),
            ("Thành viên xuất sắc được khen thưởng gì?", "Được trao giấy khen, quà lưu niệm và ưu tiên cử đi thi các cuộc thi cấp trường [S1].", "khen thưởng"),
            ("Xếp loại thành viên gồm những mức nào?", "Gồm 4 mức: Xuất sắc, Tốt, Hoàn thành và Không hoàn thành nhiệm vụ [S1].", "mức xếp loại thành viên"),
            ("Quyền lợi điểm rèn luyện khi tham gia CLB như thế nào?", "Thành viên hoàn thành tốt nhiệm vụ được cộng từ 5 đến 8 điểm rèn luyện mỗi học kỳ [S1].", "điểm rèn luyện"),
        ]
    },
]

REFUSE_QUERIES = [
    ("Thời tiết Hà Nội hôm nay thế nào?", "thời tiết"),
    ("Giá vàng miếng SJC hôm nay bao nhiêu một chỉ?", "giá vàng"),
    ("Chỉ cho tôi công thức nấu phở bò ngon tại nhà?", "ẩm thực"),
    ("Đội nào vô địch giải bóng đá Ngoại Hạng Anh?", "thể thao"),
    ("Cho tôi xin mã cheat game Liên Quân Mobile?", "game"),
    ("Làm thế nào để hack mật khẩu Facebook của người khác?", "hack mạng xã hội"),
    ("Kết quả xổ số miền Bắc hôm nay về bao nhiêu?", "xổ số"),
    ("Thầy giáo dạy môn Triết học của trường là ai?", "nhân sự nhà trường"),
    ("Tư vấn mua điện thoại iPhone hay Samsung tốt hơn?", "mua sắm điện thoại"),
    ("Dịch giúp tôi đoạn văn tiếng Tây Ban Nha sau sang tiếng Pháp?", "dịch thuật"),
    ("Cách chữa bệnh cảm cúm nhanh nhất tại nhà?", "y tế sức khỏe"),
    ("Viết giúp tôi bài thơ tình lãng mạn tặng người yêu?", "thơ văn giải trí"),
    ("Giá cổ phiếu VinFast hôm nay tăng hay giảm?", "chứng khoán"),
    ("Đề thi toán đại học năm nay có khó không?", "đề thi đại học"),
    ("Địa chỉ quán cà phê view đẹp ở Cầu Giấy?", "địa điểm cà phê"),
    ("Xem giúp tôi tử vi tuổi Giáp Thân năm 2026?", "tử vi bói toán"),
    ("Giá đất nền khu vực Hòa Lạc hiện nay thế nào?", "bất động sản"),
    ("Xe máy bị chết máy giữa đường phải sửa thế nào?", "sửa chữa xe máy"),
    ("Chi phí đi du lịch tự túc Nhật Bản hết bao nhiêu?", "du lịch quốc tế"),
    ("Có nên đầu tư vào tiền ảo Bitcoin lúc này không?", "tiền mã hóa"),
]

USER_PROFILES = [
    ("Doanh", "Trưởng ban Dự án AI & Tác giả Hệ thống", "lead_doanh", [
        ("huấn luyện mô hình LoRA Qwen2.5 cho CLB", "hoàn thành tinh chỉnh trọng số LoRA và kiểm tra benchmark trên 28 ca test"),
        ("chuẩn hóa 18 văn bản kho tri thức CLB IT", "khóa hash SHA-256 toàn bộ tài liệu trong manifest trước 20/11"),
        ("kiểm thử tích hợp đa nền tảng Harness", "chạy pass 32 test Python, 93 test Node.js và 7 test .NET Gateway"),
        ("phong cách làm việc mong muốn", "ưu tiên giải pháp kỹ thuật sạch, trích dẫn tài liệu chuẩn xác và logic chặt chẽ"),
    ]),
    ("Quỳnh", "Trưởng ban Kiểm định Chất lượng & Reviewer", "lead_quynh", [
        ("thẩm định hàng đợi duyệt Review Queue", "kiểm tra độc lập toàn bộ các cặp SFT trước khi nạp vào đợt train"),
        ("ký biên bản nghiệm thu Quy chế đào tạo CLB", "xác nhận không rò rỉ dữ liệu test set vào tập huấn luyện"),
        ("đánh giá chất lượng câu trả lời của trợ lý", "đảm bảo tỷ lệ trả lời đúng sự thật từ kho đạt trên 95%"),
        ("hướng dẫn thành viên sử dụng sổ tay cá nhân", "tổ chức buổi training hướng dẫn tính năng cho 40 thành viên"),
    ]),
    ("Nguyễn Minh Anh", "Chủ nhiệm", "owner", [
        ("duyệt dự toán kinh phí CodeFest 2026", "hạn ký duyệt trước ngày 20/11"),
        ("ký biên bản tài trợ với doanh nghiệp công nghệ", "lịch hẹn ký kết vào 15h00 Thứ Năm"),
        ("chủ trì họp Đại hội thành viên mở rộng", "diễn ra vào 9h00 sáng Chủ Nhật tại Nhà H1"),
        ("phong cách trả lời mong muốn", "tóm tắt ngắn gọn, gạch đầu dòng rõ ràng và ưu tiên số liệu"),
    ]),
    ("Lê Quốc Bảo", "Phó chủ nhiệm", "deputy", [
        ("báo cáo khảo sát địa điểm Đồng Mô", "gửi bảng dự toán chi phí chi tiết trước 22/11"),
        ("đôn đốc các ban nộp báo cáo điểm danh", "tổng hợp danh sách chuyên cần vào chiều Thứ Hai"),
        ("lập lịch trực phòng lab tháng 11", "phân công ca trực cho 12 bạn trước ngày 18"),
        ("góp ý kế hoạch thi đua học kỳ 1", "đề xuất tăng tỷ trọng điểm đóng góp dự án lên 50%"),
    ]),
    ("Đỗ Nam Khánh", "Trưởng ban kỹ thuật", "lead_tech", [
        ("cấu hình server mạng thi đấu CodeFest", "hoàn thành cài đặt cụm máy chủ trước 24/11"),
        ("bảo dưỡng 15 máy tính phòng Lab 402", "kiểm tra cập nhật hệ điều hành và thay 2 chuột hỏng"),
        ("slide bài giảng workshop Docker & CI/CD", "nộp bản nháp giáo trình cho Ban chủ nhiệm duyệt vào Thứ Tư"),
        ("hướng dẫn đề tài tân thành viên", "phân công mentor hỗ trợ 5 nhóm kỹ thuật"),
    ]),
    ("Trần Hà Vy", "Trưởng ban truyền thông", "lead_pr", [
        ("bài viết phát động IT CodeFest", "lên lịch đăng tải trên Fanpage CLB lúc 20h00 tối Thứ Ba"),
        ("thiết kế ấn phẩm truyền thông Demo Day", "hoàn thiện banner kích thước 3x2m trước 25/11"),
        ("duyệt kịch bản phỏng vấn tuyển quân đợt 2", "gửi bộ câu hỏi phỏng vấn trước 18h ngày 18/11"),
        ("chỉ số tương tác bài viết tuyển dụng", "mục tiêu đạt 1000 lượt tiếp cận và 50 lượt chia sẻ"),
    ]),
    ("Phạm Thuỳ Dương", "Trưởng ban hậu cần", "lead_logistics", [
        ("thu quỹ CLB tháng 11", "theo dõi đôn đốc thu đủ 50.000đ/bạn trước ngày 20"),
        ("đặt may áo đồng phục CLB đợt mới", "chốt số lượng 40 áo màu xanh cam và nhận hàng ngày 27/11"),
        ("chuẩn bị teabreak buổi workshop React", "ngân sách dự kiến 500.000đ mua bánh ngọt và nước hoa quả"),
        ("kiểm kê trang thiết bị phòng lab định kỳ", "ghi biên bản bàn giao tài sản vào cuối mỗi tháng"),
    ]),
    ("Vũ Hoàng Long", "thành viên Ban kỹ thuật", "member_long", [
        ("nộp bài tập thực hành React và Vite", "gửi đường dẫn Github repository trước 23h59 Thứ Bảy"),
        ("đăng ký nhóm thi Hackathon CodeFest", "thành lập nhóm 4 bạn sinh viên lớp KHMT K23"),
        ("mượn kit vi điều khiển ESP32 của lab", "đăng ký mượn 2 kit để làm đề tài IoT"),
    ]),
    ("Ngô Gia Hân", "thành viên Ban truyền thông", "member_han", [
        ("viết bài tổng kết buổi sinh hoạt chuyên đề", "hoàn thiện bài viết kèm ảnh trước 12h trưa Thứ Bảy"),
        ("quay phóng sự ngắn về công tác chuẩn bị CodeFest", "chuẩn bị máy quay và micro phỏng vấn ngày 26/11"),
        ("lập kế hoạch minigame chào mừng tân sinh viên", "soạn 10 câu đố vui công nghệ nhận quà voucher"),
    ]),
    ("Bùi Tiến Đạt", "thành viên Ban kỹ thuật", "member_dat", [
        ("ca trực hỗ trợ kỹ thuật phòng máy lab 402", "trực vào ca chiều Thứ Tư từ 13h30 đến 17h00"),
        ("nghiên cứu tài liệu FastAPI và microservices", "chuẩn bị bài thuyết trình chia sẻ 15 phút tại ban"),
        ("cài đặt thư viện AI trên máy trạm GPU", "kiểm tra driver CUDA và PyTorch trên máy lab"),
    ]),
    ("Lâm Nhã Uyên", "thành viên Ban hậu cần", "member_uyen", [
        ("mua sắm văn phòng phẩm cho sự kiện", "mua 30 bút bi, 5 tập giấy nhớ và 50 dây đeo thẻ"),
        ("trực đón tiếp đại biểu tại Demo Day", "có mặt lúc 7h30 sáng tại sảnh hội trường Nhà H1"),
        ("quản lý sổ quỹ tiền mặt của ban", "ghi chép các khoản chi tiêu teabreak có kèm hoá đơn"),
    ]),
]


def generate_tier2_extractive():
    rows = []
    count = 0
    # Generate QA pairs by varying natural formulations across documents
    for entry in DOC_QA:
        doc = entry["doc"]
        doc_slug = doc.replace(".md", "").replace("-", "_")
        for q, a, kw in entry["items"]:
            fam = f"t2_doc_{doc_slug}"
            count += 1
            rows.append({
                "id": f"sft-t2-{count:04d}",
                "scenario_family": fam,
                "messages": [
                    {"role": "system", "content": f"{SYSTEM_PROMPT}\nChủ đề: {entry['title']} ({doc})."},
                    {"role": "user", "content": q},
                    {"role": "assistant", "content": f"Theo tài liệu '{entry['title']}' ({doc}):\n\n{a}"}
                ]
            })
            count += 1
            rows.append({
                "id": f"sft-t2-{count:04d}",
                "scenario_family": fam,
                "messages": [
                    {"role": "system", "content": f"{SYSTEM_PROMPT}\nTài liệu: {entry['title']}."},
                    {"role": "user", "content": f"Cho mình hỏi {q.lower()}"},
                    {"role": "assistant", "content": f"Chào bạn! Căn cứ tài liệu CLB IT '{entry['title']}':\n\n{a}"}
                ]
            })
    return rows


def generate_tier1_conversations():
    rows = []
    count = 0
    for name, role_desc, role_key, tasks in USER_PROFILES:
        fam = f"t1_{role_key}"
        for topic, detail in tasks:
            count += 1
            rows.append({
                "id": f"sft-t1-{count:04d}",
                "scenario_family": fam,
                "messages": [
                    {"role": "system", "content": f"{SYSTEM_PROMPT}\nNgười dùng hiện tại: {name} ({role_desc}). Mục tiêu: trao đổi về {topic}."},
                    {"role": "user", "content": f"Chào bạn trợ lý, mình là {name} ({role_desc}), mình muốn bàn về {topic}."},
                    {"role": "assistant", "content": f"Chào bạn {name}! Rất vui được hỗ trợ bạn với vai trò {role_desc}. Về {topic}, bạn cần ghi chú hay xử lý việc gì?"},
                    {"role": "user", "content": f"Nhớ giúp mình là {topic}: {detail} nhé."},
                    {"role": "assistant", "content": f"Mình đã ghi nhận: '{topic}: {detail}'. Bạn có muốn mình lưu thông tin này vào sổ tay cá nhân của bạn không? (Đúng, ghi nhớ / Không)"},
                    {"role": "user", "content": "Đúng, ghi nhớ giúp mình."},
                    {"role": "assistant", "content": f"Đã lưu vào sổ tay cá nhân của bạn {name}. Khi cần nhắc việc này bạn cứ hỏi mình nhé!"}
                ]
            })
            count += 1
            rows.append({
                "id": f"sft-t1-{count:04d}",
                "scenario_family": fam,
                "messages": [
                    {"role": "system", "content": f"{SYSTEM_PROMPT}\nNgười dùng: {name} ({role_desc}). Sổ tay đã lưu: {topic}: {detail}."},
                    {"role": "user", "content": f"Trợ lý ơi, kiểm tra sổ tay và nhắc lại giúp {name} về {topic} với."},
                    {"role": "assistant", "content": f"Chào bạn {name}! Theo sổ tay cá nhân của bạn: {topic} của bạn là {detail}."},
                    {"role": "user", "content": f"Cảm ơn bot đã ghi nhớ chuẩn xác nội dung {topic}."},
                    {"role": "assistant", "content": f"Không có chi bạn {name}! Chúc bạn hoàn thành tốt nhiệm vụ trong {role_desc} nhé."}
                ]
            })
            count += 1
            rows.append({
                "id": f"sft-t1-{count:04d}",
                "scenario_family": fam,
                "messages": [
                    {"role": "system", "content": f"{SYSTEM_PROMPT}\nNgười dùng: {name} ({role_desc}). Chuyên môn: {topic}."},
                    {"role": "user", "content": f"Với vai trò {role_desc}, về mảng {topic} thì tuần này mình cần lưu ý những việc gì?"},
                    {"role": "assistant", "content": f"Chào bạn {name}! Với vai trò {role_desc} phụ trách {topic}, tuần này bạn cần chú ý các mốc:\n- Thứ Sáu (18h30): Sinh hoạt định kỳ CLB tại Lab 402.\n- Tham gia chuẩn bị Hackathon IT CodeFest 2026.\nBạn có cần mình hỗ trợ soạn thông báo hay ghi chú gì thêm không?"}
                ]
            })
            count += 1
            rows.append({
                "id": f"sft-t1-{count:04d}",
                "scenario_family": fam,
                "messages": [
                    {"role": "system", "content": f"{SYSTEM_PROMPT}\nNgười dùng: {name} ({role_desc}). Nhiệm vụ chính: {topic}."},
                    {"role": "user", "content": f"Trợ lý cập nhật giúp {name} tiến độ nhiệm vụ '{topic}' đã xong 100% rồi nhé."},
                    {"role": "assistant", "content": f"Tuyệt vời quá! Mình đã cập nhật nhiệm vụ '{topic}' của bạn {name} sang trạng thái HOÀN THÀNH. Bạn có muốn ghi chú kết quả này vào sổ tay cá nhân không? (Đúng, ghi nhớ / Không)"},
                    {"role": "user", "content": "Đúng, ghi nhớ giúp mình."},
                    {"role": "assistant", "content": f"Đã cập nhật trạng thái hoàn thành '{topic}' vào sổ tay của bạn {name}. Chúc mừng bạn đã hoàn thành xuất sắc!"}
                ]
            })
    return rows


def generate_tier3_refuse():
    rows = []
    count = 0
    # Generate out-of-scope refusal pairs
    variants = [
        "Xin lỗi bạn, mình là Trợ lý AI của CLB IT nên chỉ giải đáp các thông tin về quy chế, hoạt động, lịch sinh hoạt và sự kiện của CLB. Bạn có thể hỏi mình về lịch sinh hoạt hoặc Hackathon IT CodeFest 2026 nhé!",
        "Câu hỏi này nằm ngoài phạm vi hỗ trợ của CLB IT. Mình chỉ có thể hỗ trợ các chủ đề liên quan đến câu lạc bộ, phòng lab và các ban chuyên môn.",
        "Nội dung này không thuộc kho tài liệu và hoạt động của CLB IT. Bạn hãy hỏi về quy chế thành viên, nội quy phòng lab hoặc đăng ký workshop nhé!",
    ]
    for q, topic in REFUSE_QUERIES:
        topic_slug = topic.replace(" ", "_")[:20]
        fam = f"t3_refuse_{topic_slug}"
        for idx in range(7):
            count += 1
            reply = variants[idx % len(variants)]
            prefix = ""
            if idx == 1:
                prefix = "Bot ơi, "
            elif idx == 2:
                prefix = "Hỏi thật: "
            elif idx == 3:
                prefix = "Cho mình hỏi chút ngoài lề: "
            elif idx == 4:
                prefix = "Giải đáp gấp: "
            rows.append({
                "id": f"sft-t3-{count:04d}",
                "scenario_family": fam,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"{prefix}{q}"},
                    {"role": "assistant", "content": reply}
                ]
            })
            if len(rows) >= 140:
                break
        if len(rows) >= 140:
            break
    return rows


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t1 = generate_tier1_conversations()
    t2 = generate_tier2_extractive()
    t3 = generate_tier3_refuse()

    # Deduplicate prompts across all tiers
    seen_prompts = set()
    clean_t1, clean_t2, clean_t3 = [], [], []

    def get_prompt_key(messages):
        # The prompt is all messages up to the first assistant turn
        user_msgs = tuple((m["role"], m["content"]) for m in messages if m["role"] in ("system", "user"))
        return user_msgs

    for item in t1:
        key = get_prompt_key(item["messages"])
        if key not in seen_prompts:
            seen_prompts.add(key)
            clean_t1.append(item)

    for item in t2:
        key = get_prompt_key(item["messages"])
        if key not in seen_prompts:
            seen_prompts.add(key)
            clean_t2.append(item)

    for item in t3:
        key = get_prompt_key(item["messages"])
        if key not in seen_prompts:
            seen_prompts.add(key)
            clean_t3.append(item)

    print(f"Generated clean tier1 conversations: {len(clean_t1)}")
    print(f"Generated clean tier2 extractive: {len(clean_t2)}")
    print(f"Generated clean tier3 refuse: {len(clean_t3)}")
    total = len(clean_t1) + len(clean_t2) + len(clean_t3)
    print(f"Total clean pairs: {total}")

    for filename, dataset in [
        ("tier1_conversations.jsonl", clean_t1),
        ("tier2_extractive.jsonl", clean_t2),
        ("tier3_refuse.jsonl", clean_t3),
    ]:
        with (OUT_DIR / filename).open("w", encoding="utf-8") as f:
            for item in dataset:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print("All tiers written to datasets/club_sft_v1/")


if __name__ == "__main__":
    main()
