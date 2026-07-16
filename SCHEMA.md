# Mô hình dữ liệu

## Bảng `cases`

Lưu toàn bộ 48 trường của danh sách ca bệnh, cộng thêm:

- `birth_year`: năm sinh được suy ra để thống kê/lọc trùng sau này.
- `source_file`, `source_sheet`, `source_row`: truy vết nguồn.
- `row_hash`: chống nhập lặp tuyệt đối.
- `imported_at`: thời điểm nhập.
- `raw_json`: bản dữ liệu nguồn đã chuẩn hóa dạng chuỗi.

## Bảng `outbreaks`

Lưu 15 trường nguồn và `admin_area` được tách từ chuỗi địa điểm, cùng metadata nguồn và `row_hash`.

## Bảng `import_batches`

Nhật ký từng lần nhập: số dòng đọc, thêm mới, trùng, bỏ qua và số cảnh báo.

## Bảng `data_quality_issues`

Lưu lỗi/cảnh báo gắn với `entity_type` (`case` hoặc `outbreak`) và `entity_id`.

## Quy tắc chống trùng

`row_hash = SHA256(entity_type + JSON chuẩn hóa của toàn bộ nội dung nghiệp vụ)`.

Việc này chỉ ngăn nhập lại đúng cùng một dòng. Lọc trùng cùng một người hoặc gộp các lượt khám là một nghiệp vụ riêng, chưa bật tự động trong bản MVP để tránh gộp nhầm dữ liệu bệnh truyền nhiễm.
