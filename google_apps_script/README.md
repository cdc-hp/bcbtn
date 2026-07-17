# Máy chủ phụ (Google Apps Script)

Xem `WEB_DEDUP_DESIGN.md` mục 7 và `secondary_sync.py`.

**Đây là link mà Trạm Y tế xã dùng thường xuyên, không phải chỉ khi "khẩn cấp".** Máy chủ
chính (`lan_server.py`) chỉ nghe trong LAN nội bộ CDC và README gốc khuyến cáo **không** đưa
cổng server ra Internet — nghĩa là các xã ở xa, không cùng mạng LAN với CDC, **không bao giờ**
vào thẳng được trang `/xa` của máy chủ chính. URL Web App của Google Apps Script (luôn chạy
trên hạ tầng công cộng của Google) mới là link mà đa số xã thực sự dùng để nộp — CDC chỉ cần
gửi cho mỗi xã **một link duy nhất** để họ lưu lại. Trang `/xa` trên máy chủ chính vẫn tồn
tại song song, chủ yếu hữu ích khi ai đó đang có mặt/kết nối ngay trong LAN của CDC.

Google Apps Script chỉ đóng vai trò "cửa sổ online" giúp máy chủ chính có một địa chỉ Internet
ổn định để nhận dữ liệu — **không phải một hệ thống độc lập với tài khoản riêng**: mọi xã dùng
chung một khóa `SHARED_KEY` (không có tài khoản riêng từng xã như tài khoản `/xa` trên máy chủ
chính). CSDL chính vẫn luôn là SQLite trên máy chủ chính; dữ liệu qua GAS chỉ nằm tạm trong
Google Sheet/Drive cho tới khi CDC đồng bộ về.

## Triển khai (thao tác thủ công trên Google, không tự động hoá được từ repo)

1. Tạo một Google Sheet mới (ví dụ đặt tên "GSBTN - Hàng đợi phụ"). Sheet dữ liệu
   (`HangDoiPhu`) và các cột sẽ tự tạo khi script chạy lần đầu — không cần tạo tay.
2. Trong Sheet đó: **Tiện ích mở rộng → Apps Script**. Xoá nội dung mặc định, dán toàn bộ
   nội dung file `Code.gs` vào.
3. **Project Settings (biểu tượng bánh răng) → Script Properties → Add script property**:
   - Key: `SHARED_KEY`
   - Value: một chuỗi bí mật tự đặt (không dùng chung với mật khẩu LAN của máy chủ chính).
     Đây là khóa mà Trạm Y tế xã và `secondary_sync.py` phải cung cấp để ghi/đọc hàng đợi phụ.
4. **Triển khai → Triển khai mới (Deploy → New deployment)**:
   - Loại: **Web app**.
   - Execute as: **Me** (tài khoản CDC sở hữu Sheet/Drive).
   - Who has access: **Anyone** (để Trạm Y tế xã truy cập được mà không cần đăng nhập Google) —
     bảo mật dựa vào `SHARED_KEY`, không dựa vào quyền Google.
   - Bấm Deploy, cấp quyền khi được hỏi, sao chép **Web app URL** (dạng
     `https://script.google.com/macros/s/XXXXXXXX/exec`).
5. Cấu hình máy chủ chính: mở app desktop ở chế độ Máy chủ, điền `secondary_webapp_url` =
   URL vừa sao chép và `secondary_shared_key` = giá trị `SHARED_KEY` ở bước 3 (lưu trong
   `deployment.json` qua màn hình cấu hình máy chủ).
6. Gửi cho các Trạm Y tế xã: **URL Web app** và **khóa `SHARED_KEY`** — đây là link chính mà
   xã lưu lại và dùng hằng tuần (không phải chỉ dùng khi máy chủ chính offline).

## Vận hành

- Xã mở URL Web app (link đã lưu sẵn), điền form, nộp mỗi tuần — file được lưu vào
  Google Drive (thư mục `MayChuPhu_GSBTN/<xã>/<tuần>/`) và ghi một dòng trạng thái
  `cho_dong_bo` vào sheet `HangDoiPhu`.
- Vì đây là kênh nộp chính chứ không chỉ dùng khi mất kết nối, CDC nên đồng bộ **thường xuyên**
  (không đợi "khi online lại"): bấm **"Đồng bộ máy chủ phụ"** trên trang `/cdc/hang-doi`, tab
  **Hàng đợi** của ứng dụng desktop (chạy được cả ở chế độ Máy chủ và Máy trạm), hoặc gọi thẳng
  `secondary_sync.pull_secondary_queue(...)`. Mỗi lần đồng bộ kéo các dòng `cho_dong_bo` vào
  hàng đợi chính (`import_queue`, nguồn `server_phu`), rồi báo lại cho Apps Script đánh dấu
  `da_dong_bo` để không kéo trùng lần sau.
- Nên chạy đồng bộ theo lịch cố định (ví dụ vài lần mỗi ngày) thay vì chỉ bấm tay khi nhớ ra —
  script trong repo chưa tự lập lịch việc này (xem mục 10.7 `WEB_DEDUP_DESIGN.md`, "giám sát
  vận hành", vẫn ở dạng thiết kế).

## Bảo mật

- Mọi hành động (`submit`, `list_pending`, `mark_synced`) đều qua **POST**, khóa `SHARED_KEY`
  luôn nằm trong phần thân request — không bao giờ xuất hiện trong query string (tránh lộ qua
  log truy cập/lịch sử trình duyệt/Referer). So khớp khóa dùng so sánh không phụ thuộc thời
  gian sớm dừng (constant-time), hạn chế dò khóa qua độ trễ phản hồi.
- `handleSubmit` giới hạn file tối đa 20 MB (chặt hơn giới hạn 100 MB phía máy chủ chính, vì đây
  chỉ là bộ đệm tạm) và kiểm tra chữ ký đầu file (`PK\x03\x04`, đặc trưng định dạng ZIP mà
  `.xlsx`/`.xlsm` dựa trên) trước khi lưu vào Drive — chặn việc nạp file không phải Excel.

## Giới hạn đã biết

- File càng lớn thì thời gian mã hoá base64/tải qua Apps Script càng lâu; Apps Script giới hạn
  thời gian chạy mỗi lần gọi khoảng 6 phút — phù hợp với quy mô danh sách ca bệnh hằng tuần của
  một xã, không phù hợp để chuyển file rất lớn.
- `Who has access: Anyone` nghĩa là ai có URL + khóa đều gọi được — khóa cần được xem như một
  mật khẩu, thay định kỳ nếu nghi lộ, và không nên gửi qua kênh không an toàn.
