# Ứng dụng Giám sát dịch bệnh — CDC Hải Phòng

Tài liệu **cốt lõi** của dự án: kiến trúc, schema, vận hành. Việc còn phải làm/backlog xem
[`TASKS.md`](TASKS.md). Hướng dẫn cài đặt/build cho người dùng cuối xem [`README.md`](README.md).

Web App tập trung (**FastAPI/Uvicorn + SQLite**, `webapp/`) chạy như 1 dịch vụ Windows duy nhất
để quản lý ca bệnh/ổ dịch, lọc trùng — quản trị viên chỉ cần trình duyệt, không cài/mở gì thêm.
Xã nộp báo cáo qua trang tĩnh GitHub Pages, gọi thẳng máy chủ chính, dự phòng Google Apps Script
khi máy chủ chính không phản hồi được. Phiên bản hiện tại: xem `VERSION.txt`.

Bản desktop PyQt6 cũ (`app.py`/`lan_server.py`/`remote_core.py`, các chế độ Máy đơn
lẻ/Trạm/Chủ) **đã gỡ bỏ hoàn toàn** kể từ v0.17.0 — Web App tập trung nay là bản DUY NHẤT.

## Repo chính thức — đọc kỹ trước khi làm gì

- **`cdc-hp/bcbtn`** — nơi phát triển chính thức, nhánh `main`. Đây là repo duy nhất còn được
  cập nhật.
- **`Monsterph6/GSBTN`** (public) — repo cũ, đã dừng phát triển, chỉ giữ lại để tra cứu lịch sử
  commit trước khi chuyển sang `cdc-hp/bcbtn` (commit `37980e5` trở về trước).
- **Bẫy khi push**: nhánh local đang checkout tên là `claude/disease-case-dedup-workflow-6mjzjx`
  và **upstream mặc định của nó vẫn là `origin` = `Monsterph6/GSBTN`** (di sản từ lúc migrate).
  `git push` trơn sẽ đẩy nhầm vào repo cũ. Luôn push tường minh vào repo chính thức:
  ```
  git push bcbtn claude/disease-case-dedup-workflow-6mjzjx:main
  ```
  (remote `bcbtn` trỏ `https://github.com/cdc-hp/bcbtn.git`). Cân nhắc đổi tên nhánh local
  thành `main` và sửa lại upstream cho đỡ nhầm về sau.

## Kiến trúc tổng thể

```
Xã/phường  ──►  GitHub Pages (docs/index.html — form thật, không còn iframe)
                 link cố định: cdc-hp.github.io/bcbtn
                        │ 1. thử POST thẳng /queue/submit-xa (CORS, khoá public_submit_key)
                        ▼    — nếu lỗi mạng/hết giờ (8s) mới rơi xuống bước 2
                 Máy chủ chính (webapp/, FastAPI, SQLite) ◄──────────────────────┐
                        ▲                                                       │
                        │ 2. (dự phòng) POST tới Google Apps Script (Code.gs)   │ chuyển tiếp
                        │    action="submit" — chuyển tiếp thẳng nếu             │ thẳng nếu
                        │    MAIN_SERVER_URL cấu hình, không thì đệm Sheet/Drive │ MAIN_SERVER_URL
                        └────────────────────────────────────────────────────────┘ cấu hình
                                    ▲
              Quản trị viên (trình duyệt, không cài gì) ── đăng nhập /cdc/login,
                                                            tài khoản trong cdc_accounts
```

- `core.py` là **lõi nghiệp vụ** dùng chung cho toàn bộ hệ thống — `webapp/` chỉ bọc thêm quanh
  các hàm có sẵn (`import_excel`, `find_duplicate_groups`, `merge_duplicate_records`,
  `export_rows`...), không viết lại logic import/dedup/export.
- `docs/index.html` là **form nộp báo cáo thật** (HTML/CSS/JS tĩnh, không còn iframe nhúng
  trang Apps Script) — xem mục "Web nộp báo cáo trực tiếp từ GitHub Pages" bên dưới.
- `docs/config.js` chứa `GAS_URL` (đường dự phòng) và `MAIN_SERVER_URL` (đường ưu tiên, để trống
  nếu máy chủ chính chưa mở ra Internet). Chỉ cần sửa `GAS_URL` khi tạo **deployment GAS mới**
  (đổi ID); nếu chỉ "New version" trên deployment cũ thì URL không đổi, không cần sửa gì ở đây.
- `gas_deploy/` (bị `.gitignore`) là thư mục làm việc với `clasp` để đẩy `Code.gs` lên project
  GAS thật (`scriptId` trong `gas_deploy/.clasp.json`) — không commit vào git.

### Web nộp báo cáo trực tiếp từ GitHub Pages

Trước đây `docs/index.html` chỉ là khung `<iframe>` nhúng thẳng trang HTML do `Code.gs: doGet`
tự phục vụ (cùng origin script.google.com, tránh vướng CORS) — mọi request nộp báo cáo đều đi
qua Apps Script trước, kể cả khi máy chủ chính đang online. Nay `docs/index.html` là **trang
tĩnh độc lập** (form/JS thật, không còn iframe), tự quyết định gọi thẳng máy chủ chính trước:

- **Ưu tiên gọi thẳng** `POST {MAIN_SERVER_URL}/queue/submit-xa` (CORS, `webapp/main.py` chỉ mở
  cho đúng origin `https://cdc-hp.github.io`, xem `PUBLIC_FRONTEND_ORIGIN`) — xác thực bằng
  header `X-GSBTN-Password` so khớp `public_submit_key` (`/cdc/cau-hinh`), **KHÁC** `gas_api_key`
  vì khoá này bị lộ ra trình duyệt công khai của mọi xã (gõ vào ô "Khóa nộp báo cáo" mỗi lần
  nộp) — không còn là bí mật server-to-server. CDC nên đặt `public_submit_key` TRÙNG
  `SHARED_KEY` bên Apps Script để xã chỉ cần nhớ một khoá cho cả 2 đường nộp. Bỏ trống
  `public_submit_key` hoặc `MAIN_SERVER_URL` = tắt hẳn đường gọi thẳng, xã luôn nộp qua Apps
  Script như trước (không có gì thay đổi hành vi cho tới khi CDC chủ động bật).
  `webapp/routers/submission_api.py: submit_xa` tự kiểm tra lại xã (`core.OFFICIAL_COMMUNES`),
  định dạng/không được ở tương lai của tuần báo cáo, và chữ ký file `.xlsx` (`PK\x03\x04`) —
  những điều `Code.gs` từng làm hộ trước khi chuyển tiếp, nay phải tự làm vì trình duyệt gọi
  thẳng, không còn qua Apps Script chặn giữa nữa.
- **Rơi xuống Apps Script CHỈ khi lỗi mạng/hết thời gian chờ** (8 giây) khi gọi thẳng — một phản
  hồi thật từ máy chủ chính (kể cả lỗi nghiệp vụ như sai khoá/xã không hợp lệ) được hiển thị
  thẳng cho xã, không âm thầm rơi xuống Apps Script (giống hệt logic
  `Code.gs: tryForwardToMainServer` vốn đã áp dụng nguyên tắc này ở chặng kế tiếp).
  `docs/index.html: trySubmitGas` gửi y hệt request cũ (`action:"submit"`, không đặt
  `Content-Type` tường minh để tránh preflight OPTIONS mà Apps Script không xử lý được) — phía
  `Code.gs` **không đổi gì**, vẫn hoạt động nếu ai đó mở thẳng URL Apps Script.
- **Giữ đúng tab "Tình hình nộp"** (thực chất là dòng cảnh báo "Chưa nộp báo cáo các tuần" trên
  form): khi nộp thẳng thành công, `docs/index.html: logStatusToGas` gọi thêm (cố gắng, không
  chặn UI) action mới `log_status` trên `Code.gs` để ghi 1 dòng vào Sheet `HangDoiPhu` — không
  kèm file — để Sheet này vẫn là nguồn dữ liệu đầy đủ cho `listStatus`, không bị thiếu các lượt
  nộp thẳng bỏ qua Apps Script hoàn toàn.
- **Máy chủ chính lấy dữ liệu buffer ngược lại từ Apps Script** vẫn dùng cơ chế có sẵn, không
  đổi gì: `secondary_sync.pull_secondary_queue` gọi `action:"list_pending"`/`"mark_synced"` trên
  `Code.gs` — đây chính là "API đầu ra" của máy chủ phụ mà máy chủ chính dùng để đồng bộ bù, đã
  có từ trước (xem mục "Máy chủ phụ Google Apps Script — vận hành" bên dưới).
- 3 nơi lặp lại danh mục 114 xã/phường/đặc khu (`core.OFFICIAL_COMMUNES`, `Code.gs: COMMUNES`,
  `docs/index.html: COMMUNES`) — JS tĩnh/Apps Script/Python không chia sẻ được nguồn chung, phải
  sửa cả 3 nơi nếu danh mục hành chính thay đổi (xem TASKS.md mục "communes chuẩn hoá").

### File chính

```text
core.py                SQLite, nhập/xuất, chất lượng, thuật toán lọc trùng, cdc_accounts
deployment_config.py   Cấu hình triển khai (cổng, khoá GAS, máy chủ phụ, tên miền công khai...)
backup_manager.py      Chính sách, kiểm tra, lưu giữ và phục hồi sao lưu
duplicate_config.py    Trọng số và ngưỡng lọc trùng
case_view_config.py    Cấu hình cột hiển thị danh sách ca bệnh (chọn/đổi tên/cột tính toán)
update_manager.py      Cập nhật ứng dụng
secondary_sync.py      Đồng bộ hàng đợi từ máy chủ phụ (Google Apps Script) khi online lại
webapp/                Web App tập trung (FastAPI/Uvicorn) — xem mục riêng bên dưới
service_windows.py     Entry point dịch vụ Windows chạy webapp/ (pywin32)
service_tray.py        Chạy webapp/ thủ công + icon khay hệ thống — thay cho dịch vụ Windows khi
                        chưa muốn/chưa thể đăng ký dịch vụ (xem `Chay_May_Chu.bat`)
setup-webapp-server.iss Bộ cài DUY NHẤT, cài Web App làm dịch vụ Windows
docs/                  GitHub Pages (index.html + config.js) + docs/huong-dan (nguồn HTML + PDF)
tests/                 Kiểm thử lõi, lọc trùng, cấu hình, cdc_accounts, webapp/ (test_webapp_*.py),
                        scheduler, service_windows
```

## Web App tập trung (`webapp/`) — xem TASKS.md

Kiến trúc **duy nhất** của hệ thống (bản desktop PyQt6 cũ đã gỡ bỏ hoàn toàn, xem TASKS.md mục
"Đang làm: chuyển sang Web App tập trung" cho lịch sử 11 giai đoạn chuyển đổi). Chạy trên đúng 1
máy chủ, dưới dạng **dịch vụ Windows** (`service_windows.py`, tên dịch vụ `CDCGiamSatDichBenh`)
— quản trị viên chỉ cần trình duyệt tại `/cdc/login`, không cài/mở gì thêm.

- Chạy dev: `uvicorn webapp.main:app --reload`. Chạy như dịch vụ thật:
  `python service_windows.py install|start|stop|remove|debug`; chạy tay không qua khung dịch vụ
  (để phát triển/kiểm thử nhanh, không đăng ký gì với Windows): `python service_windows.py run`;
  chạy tay kèm icon khay hệ thống (thay dịch vụ Windows khi chưa muốn đăng ký):
  `python service_tray.py` (hoặc bấm đúp `Chay_May_Chu.bat`).
- `webapp/config.py` đọc `deployment.json` qua `deployment_config.py` — `web_token_secret` dùng
  để ký cookie phiên.
- `webapp/auth.py`: đăng nhập **tái dùng** `core.issue_admin_token`/`verify_admin_token` đã có
  sẵn (không thêm thư viện session) — chỉ khác chỗ lưu: cookie `cdc_session` (HttpOnly,
  `Secure` khi request có `X-Forwarded-Proto: https` — Cloudflare Tunnel gắn header này) thay
  vì header `X-GSBTN-Admin-Token`. CSRF theo mẫu double-submit-cookie (cookie `csrf_token`
  không HttpOnly + form phải gửi kèm đúng giá trị) — không thêm thư viện, không cần bảng
  session.
- `webapp/dependencies.py`: nơi tập trung mọi quy tắc phân quyền — `require_login` (chưa đăng
  nhập → redirect `/cdc/login`), `require_password_current` (chặn thao tác khác cho tới khi đổi
  xong mật khẩu buộc đổi), `require_role(*roles)` (factory kiểm tra vai trò, 403 nếu không đủ
  quyền), `require_setup_done` (chưa có tài khoản nào → redirect `/cdc/setup`).
- `cdc_accounts` mở rộng thêm `role` (`super_admin`/`admin`/`data_operator`/`viewer`, hằng số
  `core.CDC_ROLE_*`), `must_change_password`, `failed_login_count`, `locked_until` — khoá 15
  phút (`core.ACCOUNT_LOCKOUT_MINUTES`) sau 5 lần sai liên tiếp (`core.ACCOUNT_LOCKOUT_THRESHOLD`).
  `audit_log` thêm cột `ip` (ghi từ `Cf-Connecting-Ip`/`X-Forwarded-For` khi có Cloudflare
  Tunnel, fallback IP kết nối TCP trực tiếp) để `/cdc/nhat-ky` lọc được theo IP.
- Bootstrap 5 + HTMX **vendor cục bộ** trong `webapp/static/vendor/` (tải sẵn, không gọi CDN
  lúc chạy) — tránh phụ thuộc mạng ngoài khi phục vụ, và đóng gói được vào bản cài
  (`--add-data` trong `build.bat`).
- `/health`: kiểm tra nhanh service + CSDL + tác vụ đồng bộ nền còn sống
  (`"scheduler": "chua_chay"|"dang_chay"|"dang_dong_bo"`), dùng cho Windows Service giám sát và
  kiểm tra sau cài đặt.

### Bản đồ route chính (đều dưới `/cdc/`, trừ `POST /queue/submit`)

| Route | Vai trò xem | Vai trò thao tác | Router |
|---|---|---|---|
| `/setup`, `/login`, `/change-password`, `/logout` | công khai/đã đăng nhập | — | `routers/login.py` |
| `/dashboard` | mọi vai trò | đồng bộ máy chủ phụ: super_admin/admin/data_operator | `routers/dashboard.py` |
| `/hang-doi` | mọi vai trò | nhập: +data_operator; xoá: super_admin/admin | `routers/queue.py` |
| `/lich-su-nhap` | +data_operator | xoá nguyên lần nhập: super_admin/admin | `routers/import_history.py` |
| `/ca-benh`, `/o-dich` | mọi vai trò | — (đọc) | `routers/records.py` |
| `/loc-trung` | mọi vai trò | hợp nhất: +data_operator; khôi phục/tiêu chí: super_admin/admin | `routers/dedup.py` |
| `/xuat-du-lieu` | mọi vai trò (trang) | xuất file: super_admin/admin/data_operator (không viewer — dữ liệu có CCCD/SĐT) | `routers/xuat_du_lieu.py` |
| `/tai-khoan` | chỉ super_admin | chỉ super_admin | `routers/accounts.py` |
| `/tai-khoan-xa` | chỉ super_admin | chỉ super_admin | `routers/commune_accounts.py` |
| `/nhat-ky` | super_admin/admin | — (đọc) | `routers/audit_log.py` |
| `/sao-luu` | super_admin/admin | phục hồi + cấu hình chính sách: chỉ super_admin | `routers/backups.py` |
| `/cau-hinh` | chỉ super_admin | chỉ super_admin | `routers/settings.py` |
| `POST /queue/submit` (không có tiền tố `/cdc`) | — | xác thực bằng `gas_api_key` (header `X-GSBTN-Password`, tương thích nguyên trạng `Code.gs`) | `routers/submission_api.py` |

Nguyên tắc phân quyền chung: **xem** hầu như mở cho mọi vai trò đã đăng nhập (kể cả `viewer`);
**thao tác thay đổi dữ liệu** (nhập/xoá/hợp nhất) từ `data_operator` trở lên; **thao tác rủi ro
cao** (phục hồi sao lưu, cấu hình triển khai, quản lý tài khoản, sửa chính sách sao lưu) chỉ
`super_admin`. `viewer` bị chặn xuất dữ liệu hàng loạt dù chỉ là "xem" — vì file xuất chứa
CCCD/SĐT, rủi ro rò rỉ khác hẳn xem từng bản ghi trên màn hình.

### Giao diện bảng dữ liệu — kéo dãn cột, full chiều ngang, phân trang

- **Kéo dãn cột**: `webapp/static/app.js` tự gắn tay cầm kéo (`.cdc-col-resize`) vào mọi `<th>`
  trong MỌI bảng nằm trong `.table-responsive` — không cần gắn class riêng ở từng template.
  Không đè lên `.cdc-sort-link` (link sắp xếp lấp đầy `<th>` ở các trang có sort) vì tay cầm chỉ
  là 1 dải hẹp 6px sát mép phải. Độ rộng lưu vào `localStorage` (khoá theo đường dẫn trang + tên
  cột) nên tự nhớ lại lần sau — chỉ là tiện ích hiển thị cục bộ trình duyệt, không lưu server.
- **Full chiều ngang**: `webapp/static/style.css` — vùng nội dung (`max-width`) đã nới từ 1240px
  lên 2400px để dùng hết chiều rộng cửa sổ/màn hình thay vì bị khoá cứng; vẫn giữ nguyên cơ chế
  cuộn nội bộ (`height:100vh`/`overflow-y:auto`) đã có từ trước.
- **Phân trang**: `webapp/services/pagination.py::paginate(rows, page, page_size=50)` — cắt trang
  bằng Python SAU KHI router đã fetch đủ danh sách (không cần OFFSET ở SQL). Dùng cho 6 trang
  trước đây load hết 1 lần: `/hang-doi`, `/tai-khoan`, `/tai-khoan-xa`, `/nhat-ky`, `/lich-su-nhap`,
  `/sao-luu` — mỗi router tự dựng `pagination_base` giữ nguyên mọi filter đang lọc (xem mẫu
  `records.py::_list_view`, trang Ca bệnh/Ổ dịch đã phân trang chuẩn từ trước, dùng SQL
  `page`/`page_size` thật chứ không qua `paginate()`). `/hang-doi` có cả sort — sort không mang
  `page` (đổi cách sắp xếp tự về trang 1), `pagination_base` giữ nguyên `sort`/`dir` đang chọn.

### Tài khoản xã — cổng chỉ xem riêng (`/xa/*`)

Hoàn toàn tách biệt tài khoản CDC (`/cdc/*`, bảng `cdc_accounts`) — tài khoản xã (bảng
`commune_accounts`, mỗi xã/phường 1 tài khoản) đăng nhập tại `/xa/dang-nhap`, **chỉ xem được**
(không sửa/xoá/nộp) ca bệnh/ổ dịch thuộc đúng xã mình, dùng cookie phiên riêng
(`xa_session`, `webapp/commune_auth.py`) — không lẫn với `cdc_session`. Quản lý tài khoản xã
(tạo từng cái, nhập hàng loạt qua Excel, khoá/mở khoá, đặt lại mật khẩu) ở `/cdc/tai-khoan-xa`
(`routers/commune_accounts.py`), chỉ `super_admin`.

**Ranh giới bảo mật cốt lõi**: `webapp/routers/xa_view.py` LUÔN tự gán `admin_area = <xã đang
đăng nhập>` ở phía server (đọc từ `commune_auth.CommuneCurrentUser.commune`, không phải từ query
string) khi gọi `records_query.query_cases`/`core.query_records` — cố ý KHÔNG dùng lại
`webapp/routers/records.py::_list_view` vì hàm đó nhận `admin_area` trực tiếp từ tham số trình
duyệt gửi lên. Trang chi tiết tự kiểm tra lại `record["commune"]`/`record["admin_area"]` đúng xã
trước khi hiển thị (chặn kiểu tấn công đoán ID/IDOR — đổi số ID trên URL để xem bản ghi xã khác).

**Giới hạn đã biết**: lọc theo xã dùng so khớp **chính xác** (`commune = ?` / `admin_area = ?`),
không chuẩn hoá mờ (fuzzy). `cases.commune` lấy từ Excel nhập vào không được kiểm tra khớp
`OFFICIAL_COMMUNES`, còn `outbreaks.admin_area` suy ra tự động từ `location`
(`core.extract_admin_area`) nên chính tả có thể lệch với tên xã ghi trên tài khoản — hậu quả CHỈ
là xã đó thấy THIẾU vài bản ghi chính tả lệch (an toàn, không lộ dữ liệu chéo xã), không bao giờ
làm lộ nhầm dữ liệu xã khác. Tài khoản xã không có trang đổi mật khẩu tự phục vụ (CDC đặt lại hộ).

**Nhập hàng loạt tài khoản xã qua Excel** (`core.import_commune_accounts`, gọi từ `POST
/cdc/tai-khoan-xa/nhap-excel`): file `.xlsx`, dòng đầu là tiêu đề, cột bắt buộc "Xã/Phường", "Tên
đăng nhập", "Mật khẩu" (≥ 8 ký tự, CDC tự đặt sẵn — không tự sinh ngẫu nhiên), cột "Tên hiển thị"
tuỳ chọn. Mỗi dòng gọi `create_commune_account` riêng trong `try/except ValueError` — 1 dòng lỗi
(sai tên xã không thuộc `OFFICIAL_COMMUNES`, thiếu mật khẩu, trùng xã/tên đăng nhập...) chỉ bỏ
qua dòng đó, không làm hỏng cả file (theo đúng cách xử lý lỗi từng dòng của `import_excel`).

### Lọc trùng + xuất dữ liệu qua Web (Giai đoạn 5)

`webapp/routers/dedup.py` tái dùng nguyên `core.find_duplicate_groups`/`merge_duplicate_records`
— trang duyệt nhóm trùng (`/cdc/loc-trung/xem`) nhận **id bản ghi trực tiếp qua querystring**
(không phải `group_id`) để tránh phải quét lại toàn bộ (và có thể lệch kết quả nếu dữ liệu vừa
đổi) mỗi lần người dùng bấm "Duyệt & hợp nhất". `webapp/routers/xuat_du_lieu.py` tái dùng
`core.export_filtered_records`/`export_cases_by_commune`; file xuất dùng file tạm + tự xoá sau
khi gửi xong (`webapp/services/export_files.py`, `starlette.background.BackgroundTask`), không
ghi vào thư mục dữ liệu chính.

### Xóa theo lần nhập (`/cdc/lich-su-nhap`)

Trang mới liệt kê `import_batches` (mỗi dòng = 1 lần gọi `import_excel` thành công: tên file +
thời điểm nhập chính xác) kèm nút xóa nguyên lần nhập đó — dùng khi CDC phát hiện nhập nhầm
file. `core.delete_import_batch` khớp bản ghi cần xóa theo cặp `(source_file, imported_at)` của
batch (không phải theo `id` từng bản ghi) — `import_excel` gán CÙNG một mốc `imported_at` cho
mọi dòng của một lần gọi VÀ cho chính dòng `import_batches` sinh ra từ lần đó, nên cặp này xác
định đúng và chỉ đúng các bản ghi của lần nhập được chọn, kể cả khi cùng file được nhập lại nhiều
lần. Tự gọi `create_backup` trước khi xóa (xóa hàng loạt không có "thùng rác", chỉ khôi phục
được từ bản sao lưu). Xem trang: mọi vai trò trừ `viewer` (giống quyền nhập ở `/cdc/hang-doi`);
xóa: chỉ `super_admin`/`admin`.

Cột "Xã"/"Tuần" + bộ lọc theo 2 trường đó (`core.list_import_batches`) lấy qua LEFT JOIN với
`import_queue` (`q.import_batch_id = b.id`) — KHÔNG lưu trực tiếp trên `import_batches` (tránh
denormalize, luôn phản ánh đúng dữ liệu gốc ở hàng đợi). Mọi lần nhập qua Web hiện tại đều sinh ra
từ nhập 1 mục hàng đợi nên hầu hết batch có đủ xã/tuần; batch nhập bằng đường khác (test/tương
lai) hiện "—" thay vì đoán bừa.

### Đồng bộ máy chủ phụ chạy nền (Giai đoạn 7)

`webapp/scheduler.py` dùng `APScheduler` (`BackgroundScheduler`), khởi động/tắt qua `lifespan`
của `webapp/main.py`, chạy trong tiến trình Uvicorn nên không phụ thuộc có ai mở trình duyệt.
Chống chạy chồng lấp
bằng `threading.Lock` không chặn (`_run_lock`), dùng chung cho cả tác vụ định kỳ lẫn nút "Đồng
bộ ngay" trên dashboard — idempotent, bỏ qua im lặng thay vì xếp hàng nếu đang có lần chạy khác.
Đổi `secondary_sync_interval_minutes` (5-180 phút) cần khởi động lại tiến trình mới có hiệu lực
(APScheduler không tự reschedule job đang chạy).

### Windows Service + cấu hình triển khai (Giai đoạn 8)

`service_windows.py`: `run_server()` là phần lõi chạy Uvicorn, dùng chung cho cả `SvcDoRun` (chạy
như dịch vụ thật qua `win32serviceutil.ServiceFramework`) lẫn lệnh `run` (chạy tay) — đảm bảo 2
đường chạy không lệch hành vi. Khi chạy như dịch vụ thật (mọi lệnh trừ `run`), mặc định thư mục
dữ liệu là `C:\ProgramData\CDC Hai Phong\GiamSatDichBenh` (khác `%LOCALAPPDATA%` của app desktop
— ProgramData không gắn với 1 tài khoản Windows cụ thể, phù hợp tiến trình dịch vụ) — đặt qua
biến môi trường `GIAM_SAT_DICH_BENH_DATA_DIR` **trước khi** `deployment_config`/`core` được
import lần đầu (các module đó tính đường dẫn ngay lúc import), nên `deployment_config` import
cục bộ trong `run_server()`, không import ở đầu file. `webapp/routers/settings.py`
(`/cdc/cau-hinh`, chỉ super_admin): cổng/địa chỉ, tên miền công khai, khoá GAS, máy chủ phụ, thư
mục sao lưu — khoá bí mật (GAS API key, khoá máy chủ phụ) **không bao giờ hiện lại giá trị thật
lên trang** (ô mật khẩu trống; để trống khi lưu = giữ nguyên giá trị cũ). Nút "Khởi động lại dịch
vụ" gọi `service_windows.restart_service()` (Win32 Service Control Manager thật), báo lỗi rõ
ràng khi chưa cài đặt/thiếu quyền Administrator thay vì giả vờ thành công.

### Installer (Giai đoạn 9-10)

`setup-webapp-server.iss` — bộ cài **duy nhất** `CDC-GiamSatDichBenh-Server-Setup-v{version}.exe`,
`PrivilegesRequired=admin` vì phải đăng ký dịch vụ Windows. Wizard chỉ hỏi **đúng 1 câu** (cổng
lắng nghe) — tài khoản/GAS/đồng bộ/thư mục sao lưu cấu hình qua trình duyệt sau khi cài
(`/cdc/setup`, `/cdc/cau-hinh`). Dừng+gỡ dịch vụ cũ TRƯỚC khi copy file (`PrepareToInstall`,
tránh lỗi file bị khoá lúc nâng cấp); ghi `deployment.json` vào ProgramData CHỈ khi máy chưa
từng cài (giữ nguyên cấu hình/khoá bí mật khi nâng cấp). `build.bat` build `service_windows.py`
bằng PyInstaller (`--console`, loại trừ `PyQt5`/`PyQt6` phòng khi máy build có cài sẵn — webapp/
không dùng Qt, chỉ để tránh PyInstaller từ chối build vì xung đột Qt binding). CI
(`.github/workflows/release.yml`) có bước cài đặt/khởi động/gỡ cài **thật** trên `windows-latest`
(có quyền Administrator, khác sandbox phát triển) để xác nhận dịch vụ Windows hoạt động đúng
trước khi phát hành.

**Chưa kiểm thử được trên máy Windows thật có quyền Administrator** (chỉ kiểm thử được trong
sandbox phát triển không có quyền này, cộng với CI trên `windows-latest`).

### Tự cập nhật qua web (`/cdc/cau-hinh`, `webapp/services/web_update.py`)

Luồng: sao lưu CSDL → tải bộ cài từ GitHub Releases → xác minh SHA-256 → giao cho 1 tiến trình
PowerShell tách rời (`launch_silent_installer`) chạy `/VERYSILENT` rồi tự khởi động lại dịch vụ.
Trạng thái ghi vào `update_cache/web_update_status.json` để trình duyệt đọc lại được kể cả sau
khi dịch vụ tự khởi động lại giữa chừng.

**Cạm bẫy đã gặp thật — kẹt mãi ở "installing" dù bộ cài thật đã chạy xong.** Nguyên nhân: script
PowerShell tự sinh (`_create_installer_helper`) trước đây dùng `Move-Item -Force` để ghi đè
`web_update_status.json` — file đích LUÔN đã tồn tại (Python ghi "installing" trước đó), và
`Move-Item -Force` trên **Windows PowerShell 5.1 có bug đã biết**: vẫn báo `Cannot create a file
when that file already exists` dù đã có `-Force` (tái hiện được 100%, không phải do tranh chấp
khoá file — xác nhận được bằng cách chạy tay chính script bị kẹt). Vì `Write-UpdateStatus` được
gọi ở CẢ nhánh thành công lẫn nhánh `catch`, lỗi này khiến script luôn crash trước khi ghi được
trạng thái cuối (`installed` hoặc `failed`) — kể cả khi bộ cài Inno Setup đã chạy xong hoàn toàn
đúng (đã xác nhận: `VERSION.txt` trong thư mục cài đặt đã đổi đúng phiên bản mới, dịch vụ đã chạy
lại bình thường), giao diện vẫn hiện "đang cài đặt" vĩnh viễn. Đã sửa: dùng thẳng
`[System.IO.File]::Copy(..., $true)` thay `Move-Item -Force` để ghi đè tin cậy.

**Lối thoát dự phòng (phòng các nguyên nhân kẹt khác trong tương lai — mất mạng giữa chừng, dịch
vụ khởi động lại/mất điện đúng lúc đang tải...):** `web_update.get_public_status()` tự phát hiện
trạng thái "đang chạy" (`queued`/`backing_up`/`downloading`/`verifying`) mà không còn tiến trình
nào thực sự chạy trong process hiện tại (`_job_running=False` — chỉ đúng khi PHÁT hiện được vì
các trạng thái này luôn gắn với `perform_queued_update()` còn đang chạy trong CHÍNH process đó;
KHÔNG áp dụng logic này cho "installing" vì trạng thái đó bàn giao việc cài đặt thật cho tiến
trình PowerShell tách rời nên `_job_running` tự về `False` rất nhanh kể cả khi mọi việc đang diễn
ra bình thường — "installing" dùng ngưỡng thời gian riêng, 15 phút) → tự chuyển sang "failed" với
thông báo rõ, không khoá chết nút "Kiểm tra cập nhật". Ngoài ra có nút "Đặt lại (nếu bị kẹt)" trên
giao diện (`POST /cdc/cau-hinh/cap-nhat/dat-lai`) để super-admin tự xử lý ngay lập tức, không cần
đợi cơ chế tự phát hiện.

**Cạm bẫy đã gặp thật #2 — kẹt "installing" mà KHÔNG có nguyên nhân rõ ràng như trên (lần này bộ
cài thật còn chưa hề kịp chạy — không sinh ra file log Inno Setup nào, `VERSION.txt` không đổi).**
Nghi ngờ cao nhất: tiến trình PowerShell tách rời (`subprocess.Popen(..., DETACHED_PROCESS |
CREATE_NEW_PROCESS_GROUP)`) do chính dịch vụ Windows (chạy trong Session 0, tài khoản hệ thống)
tự bật lên đôi khi không thực sự chạy được — có thể do phần mềm diệt virus can thiệp tiến trình
nền mới tải về, chưa xác định được chắc chắn 100%, chưa tái hiện lại được theo ý muốn. **Giải pháp
thay thế không phụ thuộc cơ chế tách tiến trình đó:** `Cap_Nhat_May_Chu.bat` +
`Cap_Nhat_May_Chu.ps1` (cài sẵn cùng thư mục ứng dụng, có icon riêng trong Start Menu) — tự tải bản
mới nhất từ GitHub Releases, kiểm tra SHA-256, chạy bộ cài **ngay trong cửa sổ đang mở** (không
tách tiến trình ẩn) nên nếu lỗi sẽ HIỆN NGAY trên màn hình thay vì kẹt âm thầm. Dùng khi nút "Cập
nhật ứng dụng" trên trình duyệt bị kẹt. Yêu cầu chạy với quyền Administrator (chuột phải → "Run as
administrator").

**Cạm bẫy đã gặp thật #3 — viết `Cap_Nhat_May_Chu.ps1` lần đầu, kiểm tra SHA-256 luôn báo không
khớp mà không lỗi rõ ràng.** Nguyên nhân: `(Invoke-WebRequest -Uri ...).Content` khi tải
`SHA256SUMS.txt` từ GitHub Releases trả về **`byte[]` chứ không phải `string`** (tuỳ Content-Type
máy chủ trả về) — `-split "\`r?\`n"` trên mảng byte đó không báo lỗi, chỉ âm thầm tách thành từng
phần tử là 1 byte riêng lẻ, khiến bước so khớp dòng luôn tìm không ra (`$expectedLine` rỗng) mà
không có exception nào để lộ ra nguyên nhân thật. Sửa bằng cách tải `SHA256SUMS.txt` ra file tạm
rồi đọc lại bằng `Get-Content -Encoding UTF8` — luôn chắc chắn là text, không phụ thuộc
Content-Type của response.

## Mô hình dữ liệu

- **`cases`** — 48 trường danh sách ca bệnh + `birth_year`, thông tin file nguồn, `row_hash`,
  thời điểm nhập, JSON nguồn.
- **`outbreaks`** — 15 trường ổ dịch, `admin_area`, thông tin file nguồn, `row_hash`, thời
  điểm nhập, JSON nguồn.
- **`import_batches`** — nhật ký nhập Excel: số dòng đọc, thêm mới, trùng tuyệt đối, bỏ qua,
  cảnh báo.
- **`data_quality_issues`** — lỗi/cảnh báo chất lượng gắn với loại đối tượng và ID bản ghi.
- **`duplicate_actions`** — nhật ký xử lý lọc trùng: loại đối tượng, ID giữ lại, ID vào Thùng
  rác, giá trị hợp nhất, file sao lưu, thời điểm thao tác/khôi phục.
- **`duplicate_trash`** — JSON đầy đủ bản ghi bị loại trùng, ID gốc, thao tác nguồn, thời điểm
  xóa, thông tin khôi phục.
- **`commune_accounts`** — tài khoản riêng theo xã (đăng nhập `/xa`): username, mật khẩu băm
  PBKDF2-HMAC-SHA256 (200.000 vòng, salt ngẫu nhiên), trạng thái, lần đăng nhập gần nhất.
- **`cdc_accounts`** — tài khoản riêng từng quản trị viên CDC (đăng nhập `/cdc/login`), cùng
  cơ chế băm mật khẩu như trên; thay cho mật khẩu máy chủ dùng chung ở các thao tác quản trị.
- **`audit_log`** — thời điểm, actor, hành động, xã, chi tiết — ghi nhận đăng nhập, nộp hàng
  đợi, nhập CSDL, hợp nhất/loại trùng, khôi phục, xuất Excel, dọn hàng đợi, quản lý tài khoản.
- **`import_queue`** — hàng đợi nhập liệu: `id, commune, week, file_path, source
  ('server_chinh'|'server_phu'), status ('cho_nhap'|'da_nhap'|'loi'), received_at,
  imported_at, imported_by`.

### Cấu hình cột hiển thị danh sách ca bệnh

`case_view_config.py` (JSON cục bộ theo máy, `case_view_config.json` — không đồng bộ qua máy
chủ, giống `duplicate_config.py`): CDC tự chọn cột nào hiện trong tab "Ca bệnh", đổi tiêu đề,
và thêm **cột tính toán** từ dữ liệu khác — 3 loại: `age_years` (tuổi = năm hiện tại − năm
sinh), `days_between` (số ngày giữa 2 mốc thời gian trong `DATE_FIELDS`/`DATETIME_FIELDS`),
`concat` (nối nhiều cột). Tính lại mỗi lần hiển thị (`compute_row_values`), không lưu vào CSDL.
`query_records`/`CASE_TABLE_COLUMNS` đã mở rộng để SELECT đủ toàn bộ 48 trường + `birth_year`
(trước đây chỉ 12 cột cố định) — cần thiết để cột tuỳ chọn/tính toán truy cập được mọi trường.

**Hiện MỒ CÔI — chưa có giao diện gọi tới** kể từ khi gỡ `app.py` (nơi duy nhất từng gọi qua
`CaseColumnsSettingsDialog`, xem TASKS.md mục "Bổ sung sau khi kích hoạt thật"). `webapp/routers/
records.py` hiện tự có `CASE_DEFAULT_VISIBLE_COLUMNS` riêng (ẩn/hiện cột phía client, không đọc
`case_view_config.py`) — muốn dùng lại cột tính toán (`age_years`/`days_between`/`concat`)/đổi
tiêu đề đã lưu thì cần xây thêm 1 trang cấu hình trong `webapp/` gọi `case_view_config.py`
(module + dữ liệu JSON vẫn còn nguyên, chỉ thiếu giao diện).

### Hai lớp chống trùng

1. **Trùng tuyệt đối khi nhập**: `row_hash = SHA256(entity_type + JSON chuẩn hóa toàn bộ nội
   dung nghiệp vụ)` — chỉ bỏ qua dòng giống hệt đã nhập trước đó.
2. **Lọc trùng nghiệp vụ theo tiêu chí chọn**: `find_duplicate_groups()` tạo cặp ứng viên theo
   khóa chặn (case_code, CCCD, số điện thoại, họ tên+năm sinh, họ tên+xã, họ tên gần giống,
   khoảng cách ngày khởi phát); CDC tự bật/tắt tiêu chí nào coi là trùng (không chấm điểm/
   ngưỡng như bản cũ) — hai bản ghi trùng nếu khớp **ít nhất một** tiêu chí đang bật. Có thể
   lưu bộ tiêu chí thành preset (`dedup_criteria_sets`). `merge_duplicate_records()` sao lưu
   CSDL trước khi hợp nhất; `restore_duplicate_action()` khôi phục được.

### Gộp tự động (trùng 100%) và "Gộp trùng cập nhật" trên `/cdc/loc-trung/xem`

- **`core.auto_merge_exact_case_duplicates()`**: khác lớp 2 ở trên (chỉ so theo tiêu chí CDC
  chọn, luôn cần duyệt thủ công) — hàm này so khớp TOÀN BỘ 48 trường `CASE_FIELDS` (không phải
  tập tiêu chí đang bật); nhóm nào khớp tuyệt đối cả 48 trường thì không còn thông tin gì khác
  biệt để CDC phải chọn, nên tự loại bỏ ngay, giữ lại bản ghi ID NHỎ NHẤT (ca cũ). Gọi từ
  `webapp/routers/dedup.py::scan()` mỗi khi vai trò `data_operator` trở lên mở
  `/cdc/loc-trung?entity=case` — cố ý **không chạy cho `viewer`** (chỉ xem, không được sửa dữ
  liệu). Chỉ áp dụng cho ca bệnh (48 trường là con số riêng của `CASE_FIELDS`; ổ dịch chỉ 15
  trường, vẫn dùng cơ chế chấm điểm mờ như cũ, không có khái niệm "khớp tuyệt đối" tương tự).
  Vẫn ghi `duplicate_actions`/`duplicate_trash` như hợp nhất thủ công (action_type
  `auto_merge_exact`) nên khôi phục được bình thường qua `/cdc/loc-trung/lich-su`.
- **`core.merge_duplicates_take_latest()`** (nút "Gộp trùng cập nhật", route riêng
  `POST /cdc/loc-trung/hop-nhat-cap-nhat`, khác nút "Hợp nhất" gọi `merge_duplicate_records()`):
  tự động giữ ID nhỏ nhất trong các bản ghi ĐÃ CHỌN (qua checkbox trên bảng so sánh, không bắt
  buộc phải là cả nhóm), áp TOÀN BỘ giá trị của bản ghi có `imported_at` mới nhất (nhập gần đây
  nhất) lên bản ghi giữ lại — khác "Hợp nhất" (CDC tự chọn giá trị từng trường trong
  `CASE_MERGE_FIELDS`/`OUTBREAK_MERGE_FIELDS`, chỉ 14/12 trường), ở đây áp dụng cho MỌI trường
  hợp nhất được (`_mergeable_fields`, toàn bộ trừ `source_stt`) — coi bản ghi nhập mới nhất là
  bản cập nhật đầy đủ nhất, chỉ giữ nguyên ID cũ để không phá vỡ tham chiếu đã có.
- **Cột chọn nhiều trên `/cdc/loc-trung/xem`**: bảng so sánh có thêm cột checkbox (`name="ids"`,
  mặc định chọn hết) cho phép CDC bỏ chọn bớt bản ghi muốn giữ riêng, không xử lý cùng lượt —
  CẢ 3 nút ("Hợp nhất", "Gộp trùng cập nhật", "Xác nhận KHÔNG trùng") dùng chung MỘT `<form>`,
  phân biệt bằng `formaction` trên từng `<button>` (khỏi phải nhân bản bảng/checkbox cho từng
  hành động). `webapp/static/app.js` (`[data-dedup-table]`) đồng bộ: đếm số đã chọn, tự vô hiệu
  hoá lựa chọn "Bản ghi chính" (dropdown `keep`, dùng cho nút "Hợp nhất") nếu bản ghi đó vừa bị
  bỏ chọn. Tiêu đề trang + thanh 3 nút được ghim lại (`position: sticky`, class
  `.cdc-dedup-sticky`/`.cdc-dedup-actionbar`) để cuộn qua bảng so sánh/bảng chọn giá trị dài vẫn
  bấm được ngay, không phải cuộn lại lên đầu.

### Sao lưu và phục hồi

Chính sách nằm trong `backup_policy.json` (không nằm trong CSDL). Mỗi bản sao SQLite kiểm tra
`PRAGMA integrity_check`; trước khi phục hồi, hệ thống tạo thêm bản `before_restore`. Cơ chế
lưu giữ chọn theo mốc ngày/tuần/tháng + vài bản thủ công gần nhất.

## Xuất Excel chia theo xã

Một workbook, mỗi xã một sheet (tên cắt theo giới hạn 31 ký tự Excel) + sheet tổng hợp
`Tong_hop`. Khi một nhóm trùng có bản ghi ở nhiều xã: xã đại diện = xã của bản ghi có
`admission_date` **mới nhất** (gần ngày lập báo cáo nhất); nếu bằng nhau/thiếu dữ liệu, rơi
xuống so `onset_date` rồi `report_datetime`; nếu vẫn không phân định được, giữ xã của bản ghi
`id` nhỏ nhất và gắn cờ "cần CDC xác nhận thủ công". Các xã khác trong nhóm chỉ thấy tham
chiếu ở `Tong_hop`, không thấy dữ liệu cá nhân đầy đủ của ca thuộc xã khác.

## Máy chủ phụ Google Apps Script — vận hành

GAS là **"cửa sổ online" của chính máy chủ chính**, không phải hệ thống dữ liệu độc lập —
CSDL chính luôn là SQLite trên máy chủ chính.

### Quản lý mã nguồn Google Apps Script — KHÔNG còn nằm trong repo Git

`Code.gs`/`appsscript.json` **không còn được commit vào `cdc-hp/bcbtn`** (chủ đích — tránh lộ
thêm chi tiết luồng xử lý/xác thực nội bộ ra một public repo). Nguồn hiện chỉ tồn tại ở 2 nơi:

1. **Project Apps Script đang chạy thật** (`script.google.com`, scriptId xem trong
   `gas_deploy/.clasp.json` cục bộ) — luôn là bản "đang sống", phục vụ request thật.
2. **`gas_deploy/`** — thư mục làm việc cục bộ (đã có sẵn `.gitignore`) trên máy kỹ thuật viên
   phụ trách, chứa `Code.gs` + `appsscript.json` + `.clasp.json` (chứa `scriptId`). Đây là nơi
   DUY NHẤT còn giữ mã nguồn dạng file — **không tồn tại bản sao lưu nào khác trong Git**, nên
   nếu máy này mất mà chưa kịp `clasp pull`/backup thủ công, cách khôi phục còn lại là
   `clasp clone-script <scriptId>` thẳng từ project đang chạy (vẫn còn, chỉ mất phần lịch sử
   thay đổi/diff từng lần, không mất mã nguồn hiện tại).

Quy trình sửa `Code.gs` từ nay: sửa trực tiếp file trong `gas_deploy/` → `clasp push` (chỉ cập
nhật nội dung trong trình soạn thảo Apps Script, **chưa** ảnh hưởng bản đang phục vụ request
thật) → xác nhận đúng rồi mới `clasp deploy`/`clasp redeploy <deploymentId>` để cập nhật deployment
đang live (đúng deployment ID đang gắn trong `docs/config.js: GAS_URL`) — bước sau **ảnh hưởng
ngay lập tức** tới các xã đang nộp báo cáo thật, nên luôn kiểm tra kỹ trước khi redeploy, tốt
nhất làm ngoài giờ cao điểm nộp báo cáo.

- **Chuyển tiếp trực tiếp trước** (`Code.gs: tryForwardToMainServer`): nếu Script Property
  `MAIN_SERVER_URL` được cấu hình, mỗi lần nộp gọi thẳng `{MAIN_SERVER_URL}/queue/submit`
  (kèm `X-GSBTN-Password` từ `MAIN_SERVER_PASSWORD` nếu có). Máy chủ chính phản hồi (kể cả lỗi
  thật) thì trả thẳng cho xã, không đệm. Chỉ khi `UrlFetchApp.fetch` lỗi (không tới được) hoặc
  chưa cấu hình `MAIN_SERVER_URL` mới rơi xuống đệm.
- **Đệm khi không chuyển tiếp được**: Sheet `HangDoiPhu` (bảng hàng đợi tạm) + file gốc lưu
  Google Drive `MayChuPhu_GSBTN/<xã>/<tuần>/<file>.xlsx` — **không chia sẻ công khai**.
- **Đồng bộ bù** (`secondary_sync.pull_secondary_queue`): kéo các dòng `cho_dong_bo`, tạo bản
  ghi `import_queue` (`source='server_phu'`), đánh dấu `da_dong_bo` (idempotent). **Tự động**
  chạy theo chu kỳ qua `webapp/scheduler.py` (APScheduler, mặc định 20 phút, chỉnh ở
  `/cdc/cau-hinh`, 5-180 phút, lưu ở `secondary_sync_interval_minutes` — xem mục "Đồng bộ máy
  chủ phụ chạy nền" phía trên) khi đã cấu hình URL + khóa máy chủ phụ — không cần CDC bấm tay,
  nút "Đồng bộ ngay" trên dashboard vẫn còn để chạy ngay khi cần. Sau khi kéo thành công,
  `Code.gs: handleMarkSynced` **xoá (Thùng rác Drive, tự dọn hẳn sau ~30 ngày)** file Excel gốc
  tương ứng trên Drive — tránh Drive phình to theo thời gian, vì dữ liệu đã nằm an toàn trong
  CSDL chính.
- **Xác thực**: khóa `SHARED_KEY` dùng chung cho mọi xã trên GAS (khác với
  `commune_accounts`/`cdc_accounts` ở máy chủ chính — có chủ đích, GAS không tự nhiên hỗ trợ
  tốt việc đồng bộ danh sách tài khoản từ máy chủ chính sang). Chặng GAS → máy chủ chính dùng
  riêng `MAIN_SERVER_PASSWORD`, độc lập với `SHARED_KEY`. Từ khi có đường nộp thẳng
  `POST /queue/submit-xa` (xem mục "Web nộp báo cáo trực tiếp từ GitHub Pages" phía trên), còn
  thêm khóa thứ 3 cùng vai trò `public_submit_key` phía máy chủ chính — CDC nên đặt cả 3 khóa
  (`SHARED_KEY`, `MAIN_SERVER_PASSWORD`/`gas_api_key`, `public_submit_key`) độc lập, KHÔNG dùng
  chung 1 giá trị giữa `gas_api_key` và `public_submit_key` (2 khóa khác trust boundary — một cái
  chỉ 2 máy chủ biết, một cái mọi xã đều gõ vào form công khai); riêng `SHARED_KEY` và
  `public_submit_key` NÊN trùng nhau vì cả 2 đều là "khóa xã tự gõ vào form" — trùng để xã chỉ
  cần nhớ một khóa duy nhất.
- **`SHARED_KEY` không nằm trong bất kỳ file nào trong repo** (chủ đích thiết kế, không đồng
  bộ qua Git) — chỉ tồn tại trong Script Properties của project GAS đang chạy thật. Xem/đổi:
  `script.google.com` → đăng nhập đúng tài khoản Google đã tạo project → **Project Settings**
  (bánh răng) → **Script Properties** → dòng `SHARED_KEY`.

### Triển khai GAS lần đầu (tóm tắt — chi tiết đầy đủ xem `docs/huong-dan/4-google-apps-script.pdf`)

1. `script.google.com` (tài khoản Google CDC) → New project → dán nội dung `Code.gs`; bật hiện
   `appsscript.json` và dán nội dung `appsscript.json` tương ứng (phải có khối `webapp` với
   `executeAs: USER_DEPLOYING`, `access: ANYONE_ANONYMOUS`). Nguồn 2 file này **không nằm trong
   repo Git** (xem mục "Quản lý mã nguồn Google Apps Script" ngay dưới đây) — lấy từ thư mục cục
   bộ `gas_deploy/` trên máy kỹ thuật viên đang phụ trách, hoặc `clasp clone-script <scriptId>`
   nếu chỉ đang tạo lại project đã có.
2. Project Settings → Script Properties → thêm `SHARED_KEY` (bắt buộc), tùy chọn
   `ROOT_FOLDER_ID`, `MAIN_SERVER_URL`, `MAIN_SERVER_PASSWORD`, `TRACKING_START_WEEK` (dạng
   `YYYY-Www`, ví dụ `2026-W01` — mốc tuần CDC bắt đầu yêu cầu nộp báo cáo hằng tuần; dùng để
   tính danh sách "Tuần chưa báo cáo" trên tab Tình hình nộp, xem `listStatus`/`getTrackingStartWeek`
   trong `Code.gs`. Chưa cấu hình thì mục này chỉ hiện hướng dẫn thay vì đoán bừa mốc tuần).
3. Deploy → New deployment → Web app, Execute as **Me**, Who has access **Anyone** → copy Web
   app URL. Lần đầu có thể cần vào lại Manage deployments, sửa và Deploy lại một lần nữa để
   kích hoạt đúng quyền "Anyone".
4. Dán URL đó vào `GAS_URL` trong `docs/config.js`, commit & push nhánh `main` — GitHub Pages
   tự build lại, kiểm tra tại `https://cdc-hp.github.io/bcbtn/`.
5. Chỉ cần sửa lại `docs/config.js` khi tạo **deployment mới** (đổi ID). Nếu chỉ deploy lại
   đúng deployment cũ (New version), URL giữ nguyên.

### Mở máy chủ chính ra Internet (để GAS chuyển tiếp trực tiếp + quản trị viên truy cập từ xa)

**Domain thật đã có: `cdc-hp.io.vn`. Phương án đang dùng: Cloudflare Tunnel** — KHÔNG
port-forward, KHÔNG cần IP tĩnh/Dynamic DNS, KHÔNG cần quyền quản trị router. Lý do đổi từ
Caddy+port-forward sang phương án này: mạng CDC do nhà mạng (VNPT) quản lý thiết bị đầu cuối,
CDC không có quyền đăng nhập router để tự port-forward — Cloudflare Tunnel để máy chủ TỰ kết
nối ra ngoài tới Cloudflare (luôn được phép, không cần cấu hình gì ở phía mạng CDC), Cloudflare
nhận request từ domain rồi chuyển vào qua đúng đường kết nối đó.

Cài đặt: `cloudflared` (daemon nhỏ của Cloudflare) chạy **trên chính máy đang chạy Web App**,
đăng ký làm dịch vụ Windows qua lệnh `cloudflared.exe service install <token>` (token lấy
từ dashboard `one.dash.cloudflare.com` lúc tạo Tunnel — mỗi CDC/mỗi lần tạo tunnel có token
riêng, không dùng chung). Cấu hình "Public Hostname" trỏ `cdc-hp.io.vn` → `localhost:8765` làm
trực tiếp trên dashboard Cloudflare (không cần sửa file .yml thủ công cho cách làm khuyến nghị).
File mẫu cho ai muốn cấu hình bằng dòng lệnh thay vì dashboard:
`deploy/cloudflared-config.example.yml` (đã kiểm tra hợp lệ). Hướng dẫn từng bước đầy đủ (kể cả
cho người không rành kỹ thuật): `docs/huong-dan/5-mo-ra-internet.pdf`.

**Bắt buộc trước khi bật**: đặt `gas_api_key`/`public_submit_key` (`/cdc/cau-hinh`) — Cloudflare
Tunnel chỉ lo việc kết nối, không thay được xác thực của ứng dụng; request từ Internet vào
`POST /queue/submit`/`/queue/submit-xa` vẫn phải qua đúng khoá tương ứng, và quản trị viên vẫn
phải đăng nhập `cdc_accounts` như bình thường.

Sau khi tunnel "Connected" và Public Hostname đã cấu hình:
- **GAS chuyển tiếp trực tiếp**: đặt Script Property `MAIN_SERVER_URL = https://cdc-hp.io.vn`
  + `MAIN_SERVER_PASSWORD` = đúng giá trị `gas_api_key` đã đặt ở `/cdc/cau-hinh`.
- **Quản trị viên truy cập từ xa** (ngoài LAN CDC): mở trình duyệt tại
  `https://cdc-hp.io.vn/cdc/login` — không cần cài/cấu hình gì thêm, y hệt truy cập trong LAN.

**Phương án dự phòng** (nếu sau này CDC có máy chủ cố định + quyền quản trị router thật):
Caddy + port-forward truyền thống, cấu hình có sẵn ở `deploy/Caddyfile` (đã `caddy validate`
hợp lệ) nhưng hiện KHÔNG dùng — ít phụ thuộc bên thứ ba hơn nhưng cần hạ tầng mạng CDC không có
ở thời điểm hiện tại.

Đây là thay đổi có rủi ro bảo mật (máy chủ nhận request công khai từ Internet), cân nhắc kỹ và
luôn đảm bảo đã đặt các khoá bí mật trước khi bật.

**Cạm bẫy đã gặp thật — trình duyệt báo `ERR_DNS_NO_MATCHING_SUPPORTED_ALPN` ngay sau khi bấm
nút submit (vd "Nhập các mục đã chọn" ở `/cdc/hang-doi`), nhưng dữ liệu vẫn được xử lý đúng phía
máy chủ** (F5 lại thấy đúng kết quả). Đây là lỗi thương lượng HTTP/3 (QUIC) của Chrome với
Cloudflare — hay xảy ra ngay sau response POST → redirect 303, Chrome cố dùng lại kết nối QUIC
vừa cache nhưng bắt tay lỗi, trong khi request POST thực tế đã tới nơi và server xử lý xong
trước khi phản hồi bị rớt. Không phải lỗi ứng dụng, không mất dữ liệu — chỉ gây khó chịu. Cách
hết hẳn: vào `dash.cloudflare.com` → chọn domain `cdc-hp.io.vn` → tab **Network** → tắt
**"HTTP/3 (with QUIC)"** — Chrome khi đó chỉ dùng HTTP/2, không còn thương lượng QUIC nữa.

### Máy chủ dự phòng — cài đặt & vận hành

Failover **thủ công** (super-admin bấm nút, không tự động dò máy chính chết — tránh split-brain
khi chỉ mất mạng tạm thời). Module `ha_sync.py` + router `webapp/routers/ha.py` + middleware
chặn ghi trong `webapp/main.py`. **KHÔNG liên quan** "máy chủ phụ" Google Apps Script (mục trên)
— đó là đệm nộp báo cáo, đây là 1 bản cài **CÙNG ứng dụng này** trên máy khác để dự phòng.

**Máy dự phòng PHẢI đặt ở nơi khác điện/mạng với máy chính** (vd nhà admin, chi nhánh CDC khác)
— cạm bẫy đã gặp lúc thiết kế: đặt cùng văn phòng/LAN với máy chính thì mất điện/Internet tại chỗ
sẽ làm hỏng **CẢ HAI máy cùng lúc**, không còn bảo vệ được đúng loại sự cố nghiêm trọng nhất. Vì 2
máy ở 2 nơi khác nhau, chúng chỉ nói chuyện được qua Internet — KHÔNG dùng IP LAN.

**Cài đặt lần đầu:**
1. Cài bản Setup giống hệt máy chính lên máy thứ 2 (`CDC-GiamSatDichBenh-Server-Setup-vX.Y.Z.exe`).
2. Cài **cùng token** Cloudflare Tunnel (tunnel dùng chung cho `cdc-hp.io.vn`) lên máy đó
   (dashboard Tunnel → nút "Add a replica") — để Cloudflare tự định tuyến traffic công khai tới
   máy nào đang thật sự phục vụ (đang là chính).
3. **Cần thêm 1 Cloudflare Tunnel + tên miền RIÊNG cho TỪNG máy**, chỉ dùng để 2 máy gọi nhau
   (kéo snapshot/báo hạ cấp/hỏi vai trò — `/noi-bo/ha/*`) — KHÔNG dùng chung tunnel/tên miền
   `cdc-hp.io.vn` ở bước 2, vì Tunnel Replica cân bằng tải giữa các máy, không định tuyến được
   TỚI ĐÚNG 1 máy cụ thể. Trên dashboard Cloudflare: tạo thêm 1 Tunnel mới (`cloudflared tunnel
   create ...` hoặc qua dashboard) cho từng máy, đặt Public Hostname riêng (vd `may1.cdc-hp.io.vn`
   cho máy chính, `may2.cdc-hp.io.vn` cho máy dự phòng) → `localhost:8765` (cùng cổng, cùng app).
   Máy sẽ chạy 2 tiến trình `cloudflared` song song (2 token khác nhau) — vì
   `cloudflared.exe service install` chỉ hỗ trợ 1 dịch vụ tên "Cloudflared" mặc định, tunnel thứ 2
   cần đăng ký dịch vụ Windows với TÊN KHÁC bằng `sc.exe` (PowerShell, quyền Administrator):
   ```
   sc create CloudflaredHA binPath= "\"C:\Program Files (x86)\cloudflared\cloudflared.exe\" tunnel run --token <TOKEN_TUNNEL_RIENG>" start= auto
   sc start CloudflaredHA
   ```
   (Lưu ý `sc create` bắt buộc có dấu cách ngay sau `binPath=`/`start=`.)
4. Ở `/cdc/cau-hinh` của CẢ HAI máy: đặt `peer_server_url` = tên miền Cloudflare Tunnel RIÊNG của
   máy KIA (vd máy chính đặt `https://may2.cdc-hp.io.vn`, máy dự phòng đặt `https://may1.cdc-hp.io.vn`
   — **không phải IP, không phải `cdc-hp.io.vn`**), `peer_shared_key` **đặt TRÙNG giá trị ở cả 2
   máy, dùng khoá dài/ngẫu nhiên** (khoá riêng cho gọi máy-tới-máy, không dùng chung với
   `gas_api_key`/`public_submit_key` — và vì endpoint này giờ công khai ra Internet nên khoá yếu
   có thể bị dò, dù đã có giới hạn tần suất `ha_peer_limiter` làm chậm việc dò).
5. Mọi bản cài **MỚI** (lần đầu, kể cả máy chính) đều tự khởi động ở `server_role=standby` (ghi
   sẵn trong `deployment.json` bởi `setup-webapp-server.iss`, xem "Vì sao mặc định là dự phòng"
   dưới đây) — sau khi tạo tài khoản super-admin đầu tiên, app tự đưa thẳng tới `/cdc/cau-hinh`.
   Ở máy CHÍNH: bấm "Đặt máy này làm MÁY CHÍNH". Ở máy dự phòng: không cần làm gì thêm (đã đúng
   vai trò sẵn) — chỉ cần cấu hình `peer_server_url`/`peer_shared_key` xong là máy đó tự kéo
   snapshot CSDL định kỳ (mặc định 15 phút, chỉnh ở `standby_sync_interval_minutes`) từ máy chính
   qua `GET /noi-bo/ha/snapshot`. Nâng cấp bản cài SẴN CÓ không đụng tới `server_role` hiện có.

**Khi máy chính hỏng/tắt:** đăng nhập vào máy dự phòng → `/cdc/cau-hinh` → bấm "Đặt máy này làm
MÁY CHÍNH". Trước khi đổi vai trò, app tự **kéo bù 1 lần cuối** từ máy kia (trong lúc còn là dự
phòng — cố lấy dữ liệu mới nhất có thể, kể cả khi máy kia không phản hồi được thì bỏ qua lỗi này,
KHÔNG chặn việc thăng cấp), rồi mới đổi `server_role=primary`, rồi gọi báo máy cũ hạ cấp (`POST
/noi-bo/ha/demote`) nếu máy đó còn kết nối được; **nếu gọi thất bại (hiện cảnh báo đỏ)**, máy cũ
vẫn ghi `server_role=primary` trên đĩa — xem cơ chế tự vệ lúc khởi động ngay dưới đây để biết
chuyện gì xảy ra khi máy đó có điện/bật lại.

**Máy chính cũ mất điện rồi bật lại — tự vệ lúc khởi động:** `ha_sync.resolve_startup_conflict`
chạy đúng 1 lần lúc dịch vụ khởi động (`webapp/main.py::lifespan`, TRƯỚC khi nhận request) — nếu
máy này đang ghi `server_role=primary` trên đĩa, nó hỏi máy kia (`GET /noi-bo/ha/vai-tro`) xem
máy kia có đang CŨNG là chính không; nếu có, tự hạ cấp mình xuống dự phòng ngay (máy kia đáng tin
hơn vì vai trò đó phản ánh 1 hành động thật gần đây của super-admin, còn cấu hình "primary" trên
máy vừa bật lại chỉ là trạng thái cũ từ trước khi mất điện). Đây KHÔNG phải health-check định kỳ
— chỉ chạy 1 lần lúc khởi động nên không tạo rủi ro tự động chuyển đổi qua lại (flapping) khi mất
mạng tạm thời. Nếu không hỏi được máy kia (mất mạng, máy kia cũng chưa lên...), giữ nguyên vai
trò cũ, không đổi gì — an toàn về phía "im lặng bỏ qua". Trường hợp cả 2 máy cùng bật lại đồng
thời và cùng hỏi nhau cùng lúc, có thể **cả 2 cùng tự hạ cấp** (tạm thời không còn máy nào là
chính) — an toàn hơn dual-primary, chỉ cần super-admin vào 1 trong 2 máy bấm lại "Đặt máy này làm
máy chính".

**Vì sao mặc định là dự phòng (không phải chính):** trước đây bản cài mới mặc định
`server_role=primary`, nghĩa là quên bấm hạ cấp máy dự phòng ngay sau khi cài (bước thao tác thủ
công, dễ quên) sẽ để máy đó âm thầm ở trạng thái CÓ THỂ nhận ghi dữ liệu. Từ nay MỌI bản cài mới
(kể cả máy chính/máy duy nhất) đều bắt buộc phải qua 1 bước xác nhận thủ công rõ ràng ("Đặt máy
này làm MÁY CHÍNH" ở `/cdc/cau-hinh`, được tự động đưa tới ngay sau khi tạo tài khoản đầu tiên —
xem `webapp/routers/login.py::setup_submit`) mới thật sự phục vụ ghi dữ liệu — an toàn hơn dựa
vào việc nhớ bấm đúng nút ngay sau khi cài. Chỉ áp dụng cho CÀI MỚI (`setup-webapp-server.iss`,
nhánh chưa có `deployment.json`) — nâng cấp bản cài sẵn có KHÔNG bị đụng tới `server_role` hiện
tại, và giá trị mặc định trong code (`deployment_config.py`) vẫn là `"primary"` (chỉ ảnh hưởng
trường hợp hiếm file cấu hình cũ bị hỏng/đọc lỗi).

**Máy chính chủ động nhờ máy dự phòng đồng bộ ngay:** nút "Yêu cầu máy dự phòng đồng bộ ngay" ở
`/cdc/cau-hinh` (chỉ hiện khi đang là máy chính VÀ đã cấu hình đủ `peer_server_url`/
`peer_shared_key`) gọi `POST /cdc/vai-tro-may-chu/yeu-cau-may-kia-dong-bo`, máy chính gọi sang
`POST /noi-bo/ha/yeu-cau-dong-bo` trên máy dự phòng để nhờ máy đó tự kéo NGAY (không đợi chu kỳ
định kỳ) — dùng trước khi tắt máy chính để bảo trì. Chiều đồng bộ KHÔNG đổi: máy dự phòng vẫn luôn
là bên chủ động kéo, máy chính chỉ "nhờ kéo sớm hơn".

**Lỗi 403 khi đồng bộ (khác 401/409 do app tự trả về):** app chỉ trả 401 (sai khoá)/409 (máy kia
không đúng vai trò)/429 (dồn dập) cho `/noi-bo/ha/*` — KHÔNG bao giờ tự trả 403. Nếu thấy lỗi HTTP
403 lúc kéo snapshot/gọi máy kia, gần như chắc chắn là **Cloudflare tự chặn request TRƯỚC KHI tới
được app** (Bot Fight Mode/WAF chặn theo User-Agent trông giống bot — lỗi thật gặp phải: mặc định
`urllib` gửi `User-Agent: Python-urllib/3.x`, một trong những chữ ký bị chặn phổ biến nhất). Đã
đặt User-Agent riêng (`CDC-GiamSatDichBenh-HA/1.0`, xem `ha_sync.py::_REQUEST_HEADERS_BASE`) để dễ
nhận diện, nhưng nếu vẫn bị chặn: vào Cloudflare dashboard → đúng zone/tunnel của tên miền RIÊNG đó
(`may1.`/`may2.cdc-hp.io.vn`) → Security → tắt "Bot Fight Mode" cho hostname đó, hoặc thêm 1
Configuration Rule/WAF exception bỏ qua kiểm tra bot cho đúng hostname này — traffic hợp lệ ở đây
CHỈ có 2 máy tự gọi nhau qua khoá bí mật, không phải người dùng thật nên không cần lớp bảo vệ bot.

**Sự cố thật đã gặp — Bad Gateway "ở mạng khác" dù máy chính hoàn toàn khỏe:** khi CDC tự tay đăng
nhập/kết nối thêm 1 máy nữa vào CÙNG tunnel dùng chung (`cdc-hp.io.vn`, bước "Add a replica" ở
mục "Cài đặt lần đầu" trên), Cloudflare Tunnel Replica **cân bằng tải giữa MỌI máy đang kết nối —
KHÔNG có khái niệm "ưu tiên máy chính"**. Máy dự phòng vẫn có thể bị Cloudflare route trúng request
công khai (kể cả trang đăng nhập, xem dữ liệu) dù đang `server_role=standby`. Middleware
`_block_writes_when_standby` chỉ chặn được request GHI (trả 409 rõ ràng, xem "Giới hạn đã biết"
dưới đây) — request ĐỌC (GET) vẫn lọt qua, khiến quản trị viên có thể vô tình xem trúng dữ liệu CŨ
trên máy dự phòng (chỉ kéo bản sao mỗi ~15 phút/lần) mà không biết mình đang xem máy nào.

**Cách sửa — tự ngắt/nối Cloudflared theo vai trò:** bật cờ `manage_public_tunnel_service` ở
`/cdc/cau-hinh` (mặc định TẮT) để máy TỰ bật/tắt dịch vụ Windows tên đúng `Cloudflared` (tunnel
DÙNG CHUNG, KHÁC `CloudflaredHA` — tunnel riêng máy-tới-máy, luôn phải chạy bất kể vai trò) khớp
đúng `server_role` — dừng khi là dự phòng (ngắt khỏi Tunnel Replica, Cloudflare không còn máy nào
khác để lỡ route vào), bật lại khi được thăng làm chính. Cờ này chỉ nên bật khi đã cài đúng dịch
vụ tên "Cloudflared" theo hướng dẫn ở trên — bật sai máy/sai tên có thể vô tình đụng nhầm dịch vụ
khác. Xem `service_windows.py::set_public_tunnel_running`/`query_public_tunnel_status` và
`ha_sync.py::reconcile_public_tunnel_service` (gọi ở MỌI điểm đổi vai trò: thăng/hạ cấp thủ công,
bị máy kia báo hạ cấp, và mỗi lần khởi động dịch vụ để tự sửa lệch trạng thái).

**Đánh đổi cần biết khi bật cờ này:** nếu CẢ HAI máy cùng khởi động lại đồng thời và cùng tự hạ
cấp xuống `standby` (kịch bản "tự vệ lúc khởi động" ở trên), `cdc-hp.io.vn` sẽ **tạm ngừng hẳn**
(không còn connector nào nối tunnel dùng chung) cho tới khi super-admin bấm thăng cấp lại — thay
vì trước đây trang vẫn "lên" nhưng có thể phục vụ nhầm dữ liệu cũ từ máy dự phòng. Đây là đánh đổi
đúng hướng (ưu tiên đúng dữ liệu hơn uptime, khớp triết lý "failover thủ công, tránh split-brain"
đã chọn từ đầu) nhưng CDC cần hiểu rõ trước khi bật.

**An toàn cho test/CI (lý do cờ mặc định TẮT):** `webapp/main.py::lifespan` gọi
`reconcile_public_tunnel_service` ở MỌI lần khởi động app, kể cả khi dựng `TestClient` trong hàng
chục file test — máy dev/production chạy test có thể có THẬT dịch vụ Cloudflared đang phục vụ
traffic thật. Hàm kiểm tra cờ `manage_public_tunnel_service` TRƯỚC TIÊN, trả `None` ngay nếu tắt
mà không đụng gì tới `service_windows`/pywin32 — vì mọi test hiện có đều
`monkeypatch.setattr(deployment_config, "CONFIG_PATH", tmp_path / ...)` (cờ luôn về mặc định
`False`), không cần sửa test nào khác để giữ an toàn.

**Giới hạn đã biết (thiết kế có chủ đích, không phải lỗi):**
- Đồng bộ là kéo định kỳ — dữ liệu ghi vào máy chính giữa 2 lần đồng bộ gần nhất trước khi máy đó
  hỏng có thể chưa kịp có trên máy dự phòng tại thời điểm thăng cấp.
- Khi `server_role=standby`, middleware trong `main.py` chặn MỌI request ghi dữ liệu (POST/PUT/
  PATCH/DELETE) trừ đăng nhập/`/cdc/cau-hinh`/`/cdc/vai-tro-may-chu`/`/noi-bo/ha/` — kể cả xã nộp
  báo cáo (`/queue/submit-xa`) nếu Cloudflare lỡ định tuyến trúng máy dự phòng, xã sẽ thấy lỗi rõ
  ràng thay vì mất dữ liệu âm thầm.
- Cơ chế tự vệ lúc khởi động chỉ xử lý đúng lúc khởi động dịch vụ — nếu 2 máy cùng "primary" phát
  sinh theo cách khác (vd chỉnh tay cấu hình) mà không có máy nào khởi động lại, sẽ không tự phát
  hiện; vẫn cần super-admin chủ động kiểm tra khi nghi ngờ.
- `/noi-bo/ha/*` công khai ra Internet (qua tên miền Cloudflare Tunnel riêng của từng máy, không
  còn chỉ LAN nội bộ như bản thiết kế đầu tiên) — bảo vệ bằng khoá `peer_shared_key` +
  `ha_peer_limiter` (20 lần/5 phút mỗi IP, `webapp/services/rate_limit.py`), nhưng an toàn thật sự
  vẫn phụ thuộc khoá đủ dài/ngẫu nhiên; `GET /noi-bo/ha/snapshot` trả về TOÀN BỘ CSDL (dữ liệu ca
  bệnh thật) nếu đúng khoá.

## Build & test

```bat
python -m pytest -q          REM chạy toàn bộ test (tests/)
build.bat                     REM PyInstaller (service_windows.py) + Inno Setup (1 bộ cài duy nhất)
```

`.github/workflows/release.yml` build/test trên Windows khi push `main` hoặc tạo tag, quét
chặn dữ liệu cấm (`.db`, Excel, CSV...) lọt vào release, **cài đặt/khởi động/gỡ cài đặt thật**
bộ cài Web App trên runner (có quyền Administrator — bù đắp phần sandbox phát triển không kiểm
thử được, xem TASKS.md Giai đoạn 10); PR chỉ build/test, không tạo Release.
