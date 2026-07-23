# Việc còn lại / Backlog

Kiến trúc & schema hiện tại xem [`CLAUDE.md`](CLAUDE.md). File này chỉ theo dõi **việc đã xong
gần đây** (để không làm lại) và **việc còn mở**.

## Đã xong (tính đến v0.6.0)

1. Lọc trùng theo tiêu chí chọn (bỏ chấm điểm), hiển thị `case_code` gốc để tra ngược.
2. Xuất Excel chia theo xã (mỗi xã 1 sheet + sheet `Tong_hop`), quy tắc chọn xã khi trùng khác
   xã (xã của bản ghi `admission_date` mới nhất).
3. Web nộp dữ liệu + hàng đợi 2 tầng (`/xa`, `/cdc/hang-doi`), tài khoản riêng theo xã
   (`commune_accounts`) + audit log, rate-limit theo (IP, xã).
4. GAS máy chủ phụ: chuyển tiếp trực tiếp khi có `MAIN_SERVER_URL`, đệm Sheet/Drive khi lỗi
   mạng, đồng bộ bù idempotent.
5. Trang GitHub Pages iframe GAS (`docs/index.html`) làm link cố định cho xã + tab "tình hình
   nộp" lọc theo xã trong `Code.gs`.
6. Danh mục chính thức 114 xã/phường/đặc khu Hải Phòng (sau sáp nhập), thay ô nhập tự do.
7. Tính năng **"Chuyển máy chủ"**: đồng bộ toàn bộ dữ liệu sang máy chủ mới qua
   `/admin/receive-full-backup`, tự chuyển máy chủ cũ sang chế độ "đã đóng"/redirect
   (`_retired_response`) thay vì tắt đột ngột.
8. **Tài khoản quản trị viên riêng từng người** (`cdc_accounts`, `/cdc/login`) thay mật khẩu
   máy chủ dùng chung cho thao tác quản trị.
9. Tách 2 bản release riêng: `setup-server.iss` (chỉ Máy chủ) và `setup-admin.iss` (chỉ máy
   trạm quản trị). `setup.iss` gốc (3 chế độ) vẫn giữ cho máy đơn lẻ/máy trạm thường.
10. 4 file hướng dẫn PDF (`docs/huong-dan/`): xã/phường, máy chủ, máy trạm quản trị, Google
    Apps Script.
11. Di chuyển toàn bộ phát triển từ `Monsterph6/GSBTN` sang `cdc-hp/bcbtn` (repo chính thức).
12. Gộp tài liệu: `CLAUDE.md` (cốt lõi) + `TASKS.md` (file này) thay cho `SCHEMA.md`,
    `WEB_DEDUP_DESIGN.md`, `google_apps_script/README.md` (đã xoá, nội dung gộp vào
    `CLAUDE.md`).
13. **Cấu hình cột hiển thị danh sách ca bệnh** (`case_view_config.py`): chọn/đổi tên cột, thêm
    cột tính toán (tuổi, số ngày giữa 2 mốc, nối cột) — xem CLAUDE.md mục "Cấu hình cột hiển thị
    danh sách ca bệnh". `query_records`/`CASE_TABLE_COLUMNS` mở rộng để SELECT đủ 48 trường +
    `birth_year` thay vì 12 cột cố định như trước.

## Backlog — chưa cài đặt

Thứ tự không nhất thiết phản ánh độ ưu tiên; đánh giá lại theo nhu cầu triển khai thật.

- [ ] **HTTPS cho `lan_server.py`** — hiện dùng `http.server` thuần, mật khẩu/token truyền qua
      HTTP nếu chưa có TLS. Bắt buộc phải có trước khi mở máy chủ chính ra Internet lâu dài
      (không chỉ dựa vào reverse proxy tạm thời).
- [ ] **Mã hoá `national_id`/`phone` lúc lưu trữ** (Nghị định 13/2023/NĐ-CP) — cần thiết kế
      riêng vì ảnh hưởng trực tiếp thuật toán so khớp trùng hiện dựa trên so sánh giá trị
      thuần (mã hoá sẽ cần so khớp trên giá trị đã băm/mã hoá xác định — deterministic).
- [ ] **Khoá tài khoản sau nhiều lần đăng nhập sai** — hiện chỉ ghi `login_failed` vào
      `audit_log`, chưa tự khoá tài khoản (`commune_accounts` và `cdc_accounts`).
- [ ] **Bảng `communes` chuẩn hoá** — đã có danh mục 114 xã/phường/đặc khu nhưng chưa tách
      thành bảng riêng có mã chuẩn; `commune` trên mỗi bản ghi/tài khoản vẫn là chuỗi tự do.
- [ ] **Theo dõi tiến độ nộp báo cáo tuần** — dashboard CDC hiển thị ma trận Xã × Tuần (đã
      nộp/chưa nộp/trễ hạn), có thể nhắc email/SMS tự động vào ngày cố định mỗi tuần.
- [ ] **Đối soát ngược sau khi xã lọc trùng trên phần mềm Bộ Y tế** — xã nộp lại kết quả/mã ca
      đã xác nhận, hệ thống so khớp với `commune_export_batches` (bảng này chưa tồn tại) để
      biết ca nào xử lý xong, ca nào xã chưa phản hồi.
- [ ] **Giám sát vận hành** — cảnh báo khi máy chủ chính rớt mạng quá X phút, khi hàng đợi máy
      chủ phụ tồn đọng quá lâu chưa đồng bộ.
- [ ] **Lịch tự động cho đồng bộ máy chủ phụ** — hiện phải bấm tay "Đồng bộ máy chủ phụ"; GAS
      chưa tự lập lịch việc này.

## Câu hỏi còn mở (cần CDC xác nhận trước khi code hoá tiếp)

- Cách hiểu "ca vào viện gần nhất" khi chọn xã đại diện cho nhóm trùng khác xã: đang code theo
  nghĩa *ngày nhập viện mới nhất/gần hiện tại nhất* (nearest-to-now) — nếu ý đúng là "khoảng
  cách ngày nhập viện giữa 2 ca gần nhau nhất" thì quy tắc chọn xã cần sửa lại khác đi.
  (`core.py`, phần xuất Excel chia xã — xem mục "Xuất Excel chia theo xã" trong `CLAUDE.md`.)
- Tần suất/độ trễ chấp nhận được cho đồng bộ máy chủ phụ → máy chủ chính khi có lịch tự động
  (đề xuất tham khảo trước đây: 5 phút — chưa triển khai, xem mục "Lịch tự động" ở trên).
