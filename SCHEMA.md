# Mô hình dữ liệu

## `cases`

Lưu 48 trường của danh sách ca bệnh cùng `birth_year`, thông tin file nguồn, `row_hash`, thời điểm nhập và JSON nguồn.

## `outbreaks`

Lưu 15 trường ổ dịch, `admin_area`, thông tin file nguồn, `row_hash`, thời điểm nhập và JSON nguồn.

## `import_batches`

Nhật ký nhập Excel: số dòng đọc, thêm mới, trùng tuyệt đối, bỏ qua và cảnh báo.

## `data_quality_issues`

Các lỗi/cảnh báo chất lượng gắn với loại đối tượng và ID bản ghi.

## `duplicate_actions`

Nhật ký xử lý lọc trùng gồm loại đối tượng, ID giữ lại, danh sách ID đưa vào Thùng rác, giá trị hợp nhất, file sao lưu, thời điểm thao tác và thời điểm khôi phục.

## Hai lớp chống trùng

### 1. Trùng tuyệt đối khi nhập

`row_hash = SHA256(entity_type + JSON chuẩn hóa toàn bộ nội dung nghiệp vụ)`.

Cơ chế này chỉ bỏ qua một dòng giống hệt đã nhập trước đó.

### 2. Lọc trùng nghiệp vụ

`find_duplicate_groups()` tạo các cặp ứng viên theo khóa chặn rồi chấm điểm:

- Ca bệnh: mã ca/CCCD cho điểm tuyệt đối; các trường họ tên, điện thoại, năm sinh, giới, xã/phường, chẩn đoán, địa chỉ và khoảng cách ngày khởi phát bổ sung điểm.
- Ổ dịch: tên bệnh, độ tương đồng địa điểm, địa bàn, khoảng cách ngày khởi phát và đơn vị báo cáo.

Ngưỡng và trọng số được lưu trong `duplicate_rules.json`. Không tự động xử lý. `merge_duplicate_records()` sao lưu CSDL, cập nhật bản ghi chính theo giá trị người dùng chọn và chuyển các bản còn lại vào `duplicate_trash`. `restore_duplicate_action()` có thể khôi phục các bản ghi này.

## Triển khai LAN

- Máy chủ và máy đơn lẻ sử dụng SQLite cục bộ.
- Máy chủ mở HTTP API; mỗi request dùng một kết nối SQLite riêng và WAL.
- Máy trạm gọi API, không truy cập file `.db` qua thư mục chia sẻ mạng.
- Mật khẩu là tùy chọn; để trống thì API không yêu cầu header xác thực.


## `duplicate_trash`

Lưu JSON đầy đủ của bản ghi bị loại trùng, ID gốc, thao tác nguồn, thời điểm xóa và thông tin khôi phục. Đây là Thùng rác nghiệp vụ, không phải dữ liệu phát hành kèm ứng dụng.

## Sao lưu và phục hồi

Chính sách nằm trong `backup_policy.json`, không nằm trong CSDL. Mỗi bản sao SQLite được kiểm tra `PRAGMA integrity_check`; trước khi phục hồi, hệ thống tạo thêm bản `before_restore`. Cơ chế lưu giữ chọn các mốc ngày, tuần, tháng và một số bản thủ công gần nhất.
