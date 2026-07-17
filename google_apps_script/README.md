# Máy chủ phụ (Google Apps Script)

Xem `WEB_DEDUP_DESIGN.md` mục 7 và `secondary_sync.py`.

**Đây là link mà Trạm Y tế xã dùng thường xuyên.** Nếu máy chủ chính (`lan_server.py`) chỉ
nghe trong LAN nội bộ CDC, các xã ở xa không cùng mạng LAN **không bao giờ** vào thẳng được
trang `/xa`. URL Web App của Google Apps Script (luôn chạy trên hạ tầng công cộng của Google)
mới là link ổn định mà CDC gửi cho mỗi xã để họ lưu lại và dùng nộp hằng tuần.

Google Apps Script hoạt động như **"cửa sổ online" của chính máy chủ chính**, không phải một
hệ thống dữ liệu độc lập:

- Nếu CDC đã cấu hình cho máy chủ chính có địa chỉ Internet thật (mục "Mở máy chủ chính ra
  Internet" bên dưới), mỗi lần xã nộp, script **chuyển tiếp thẳng** (server-to-server) tới
  `/queue/submit` của máy chủ chính — dữ liệu vào ngay hàng đợi chính, không có độ trễ đồng bộ.
- Nếu máy chủ chính tạm thời không phản hồi được (mất mạng, đang bảo trì, chưa cấu hình địa chỉ
  Internet), script tự lưu tạm vào Google Sheet/Drive để CDC đồng bộ bù sau — không mất dữ liệu.
- Xác thực vẫn đơn giản: mọi xã dùng chung một khóa `SHARED_KEY` với Apps Script (không có tài
  khoản riêng từng xã như tài khoản `/xa` trên máy chủ chính — đây là lựa chọn có chủ đích để
  giữ đơn giản, xem mục "Giới hạn đã biết").
- CSDL chính vẫn luôn là SQLite trên máy chủ chính; Google Sheet/Drive chỉ là bộ đệm khi không
  chuyển tiếp trực tiếp được.

## Mở máy chủ chính ra Internet (để chuyển tiếp trực tiếp)

Đây là thay đổi khác với khuyến cáo LAN-only ban đầu — cân nhắc kỹ trước khi bật vì máy chủ sẽ
nhận request từ Internet công khai:

1. Máy chủ chính cần một địa chỉ Internet ổn định: domain riêng trỏ về IP của mạng CDC (khuyến
   nghị, nhất là nếu IP động thì dùng Dynamic DNS như DuckDNS/No-IP), hoặc chấp nhận dùng thẳng
   IP công khai nếu cố định.
2. Trên router/tường lửa của CDC: chuyển tiếp cổng (port forward) cổng LAN của máy chủ (mặc
   định `8765`) ra Internet, trỏ về máy đang chạy chế độ Máy chủ.
3. **Đặt mật khẩu máy chủ** (tab Server trên app desktop) nếu chưa đặt — bắt buộc khi máy chủ
   có thể nhận request từ Internet, đây là lớp xác thực duy nhất `/queue/submit` dùng khi không
   có token đăng nhập xã.
4. Hiện `lan_server.py` chưa hỗ trợ HTTPS (xem `WEB_DEDUP_DESIGN.md` mục 9, "Chưa cài đặt") —
   dữ liệu giữa Apps Script và máy chủ chính đi qua HTTP thuần nếu chưa có TLS. Nếu cần HTTPS
   ngay, đặt máy chủ chính sau một reverse proxy có chứng chỉ (ví dụ Caddy/Nginx với Let's
   Encrypt) rồi trỏ `MAIN_SERVER_URL` (bước dưới) vào địa chỉ HTTPS đó thay vì gọi thẳng cổng
   `8765`.

## Triển khai (thao tác thủ công trên Google, không tự động hoá được từ repo)

1. Tạo một Google Sheet mới (ví dụ đặt tên "GSBTN - Hàng đợi phụ"). Sheet dữ liệu
   (`HangDoiPhu`) và các cột sẽ tự tạo khi script chạy lần đầu — không cần tạo tay.
2. Trong Sheet đó: **Tiện ích mở rộng → Apps Script**. Xoá nội dung mặc định, dán toàn bộ
   nội dung file `Code.gs` vào.
3. **Project Settings (biểu tượng bánh răng) → Script Properties → Add script property**, thêm
   lần lượt:
   - `SHARED_KEY`: một chuỗi bí mật tự đặt (không dùng chung với mật khẩu máy chủ chính). Đây
     là khóa mà Trạm Y tế xã và `secondary_sync.py` phải cung cấp để ghi/đọc hàng đợi phụ.
   - `MAIN_SERVER_URL` *(tùy chọn — chỉ đặt nếu đã làm mục "Mở máy chủ chính ra Internet" ở
     trên)*: địa chỉ Internet của máy chủ chính, ví dụ `https://cdc-haiphong.example.com:8765`
     hoặc `http://<ip-cong-khai>:8765`. Nếu để trống, script luôn đệm qua Sheet/Drive như trước
     (không chuyển tiếp trực tiếp).
   - `MAIN_SERVER_PASSWORD` *(tùy chọn, đi kèm `MAIN_SERVER_URL`)*: mật khẩu máy chủ chính
     (giống giá trị đã đặt ở tab Server trên app desktop) — script gửi kèm khi chuyển tiếp.
4. **Triển khai → Triển khai mới (Deploy → New deployment)**:
   - Loại: **Web app**.
   - Execute as: **Me** (tài khoản CDC sở hữu Sheet/Drive).
   - Who has access: **Anyone** (để Trạm Y tế xã truy cập được mà không cần đăng nhập Google) —
     bảo mật dựa vào `SHARED_KEY`, không dựa vào quyền Google.
   - Bấm Deploy, cấp quyền khi được hỏi, sao chép **Web app URL** (dạng
     `https://script.google.com/macros/s/XXXXXXXX/exec`).
5. Cấu hình máy chủ chính (mở app desktop ở chế độ Máy chủ, tab Server): điền
   `secondary_webapp_url` = URL vừa sao chép và `secondary_shared_key` = giá trị `SHARED_KEY`
   ở bước 3 — dùng để CDC **kéo bù** dữ liệu đã đệm (khi không chuyển tiếp trực tiếp được), độc
   lập với việc có bật `MAIN_SERVER_URL` hay không.
6. Gửi cho các Trạm Y tế xã: **URL Web app** và **khóa `SHARED_KEY`** — đây là link chính mà
   xã lưu lại và dùng hằng tuần.

## Vận hành

- Xã mở URL Web app (link đã lưu sẵn), điền form, nộp mỗi tuần.
- **Nếu đã cấu hình `MAIN_SERVER_URL`**: dữ liệu vào thẳng hàng đợi máy chủ chính ngay khi nộp
  (`source = 'server_chinh'`... thực chất script tự đánh dấu `forwarded: true`, hàng đợi ghi
  nhận như nộp trực tiếp) — CDC thấy ngay trên `/cdc/hang-doi`/tab Hàng đợi, không cần đồng bộ.
- **Nếu máy chủ chính không phản hồi được lúc đó** (hoặc chưa cấu hình `MAIN_SERVER_URL`): file
  lưu vào Google Drive (thư mục `MayChuPhu_GSBTN/<xã>/<tuần>/`) và ghi một dòng trạng thái
  `cho_dong_bo` vào sheet `HangDoiPhu`. CDC đồng bộ bù bằng cách bấm **"Đồng bộ máy chủ phụ"**
  trên `/cdc/hang-doi`, tab **Hàng đợi** của ứng dụng desktop, hoặc gọi thẳng
  `secondary_sync.pull_secondary_queue(...)` — kéo các dòng `cho_dong_bo` vào hàng đợi chính
  (`import_queue`, nguồn `server_phu`), rồi báo lại cho Apps Script đánh dấu `da_dong_bo`.
- Dù đã bật chuyển tiếp trực tiếp, vẫn nên đồng bộ định kỳ (vài lần/ngày) để vét các lần chuyển
  tiếp thất bại — script trong repo chưa tự lập lịch việc này (xem mục 10.7
  `WEB_DEDUP_DESIGN.md`, "giám sát vận hành", vẫn ở dạng thiết kế).

## Bảo mật

- Mọi hành động (`submit`, `list_pending`, `mark_synced`) đều qua **POST**, khóa `SHARED_KEY`
  luôn nằm trong phần thân request — không bao giờ xuất hiện trong query string (tránh lộ qua
  log truy cập/lịch sử trình duyệt/Referer). So khớp khóa dùng so sánh không phụ thuộc thời
  gian sớm dừng (constant-time), hạn chế dò khóa qua độ trễ phản hồi.
- `handleSubmit` giới hạn file tối đa 20 MB (chặt hơn giới hạn 100 MB phía máy chủ chính, vì đây
  chỉ là bộ đệm tạm) và kiểm tra chữ ký đầu file (`PK\x03\x04`, đặc trưng định dạng ZIP mà
  `.xlsx`/`.xlsm` dựa trên) trước khi lưu vào Drive — chặn việc nạp file không phải Excel.
- Khi chuyển tiếp thất bại vì máy chủ chính **từ chối thật** (sai `MAIN_SERVER_PASSWORD`, dữ
  liệu không hợp lệ...) — không phải lỗi mạng — script báo lỗi thẳng cho xã thay vì âm thầm đệm
  vào Sheet/Drive (đệm trong trường hợp đó chỉ trì hoãn và lặp lại đúng lỗi khi CDC đồng bộ
  sau).
- `MAIN_SERVER_PASSWORD` lưu trong Script Properties của Apps Script (không hiện trong mã
  nguồn `Code.gs`, không đồng bộ qua Git) — chỉ người có quyền chỉnh sửa project Apps Script
  mới xem được.

## Giới hạn đã biết

- File càng lớn thì thời gian mã hoá base64/tải qua Apps Script càng lâu; Apps Script giới hạn
  thời gian chạy mỗi lần gọi khoảng 6 phút — phù hợp với quy mô danh sách ca bệnh hằng tuần của
  một xã, không phù hợp để chuyển file rất lớn.
- `Who has access: Anyone` nghĩa là ai có URL + khóa đều gọi được — khóa cần được xem như một
  mật khẩu, thay định kỳ nếu nghi lộ, và không nên gửi qua kênh không an toàn.
- Chưa có tài khoản riêng từng xã trên GAS (chỉ một `SHARED_KEY` dùng chung) — nếu cần, đây là
  việc mở rộng riêng, chưa làm vì Apps Script không tự nhiên hỗ trợ tốt việc đồng bộ danh sách
  tài khoản `commune_accounts` từ máy chủ chính sang.
- Khi `MAIN_SERVER_URL` trỏ tới cổng HTTP thuần (chưa có TLS), dữ liệu ca bệnh đi qua Internet
  giữa Google và máy chủ chính không được mã hoá trên đường truyền — nên dùng HTTPS (reverse
  proxy) nếu triển khai thật cho dữ liệu y tế.
