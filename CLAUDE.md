# Ứng dụng Giám sát dịch bệnh — CDC Hải Phòng

Tài liệu **cốt lõi** của dự án: kiến trúc, schema, vận hành. Việc còn phải làm/backlog xem
[`TASKS.md`](TASKS.md). Hướng dẫn cài đặt/build cho người dùng cuối xem [`README.md`](README.md).

Desktop **PyQt6 + SQLite** để quản lý ca bệnh/ổ dịch, lọc trùng, chia sẻ trong LAN — mở rộng
thêm một tầng Web (xã nộp báo cáo qua GitHub Pages + Google Apps Script) và cơ chế nhiều máy
chủ/nhiều quản trị viên. Phiên bản hiện tại: xem `VERSION.txt`.

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
Xã/phường  ──►  GitHub Pages (docs/index.html, iframe)  ──►  Google Apps Script (Code.gs)
                 link cố định: cdc-hp.github.io/bcbtn         │  chuyển tiếp thẳng nếu
                                                                │  MAIN_SERVER_URL cấu hình,
                                                                ▼  không thì đệm Sheet/Drive
                                                        Máy chủ chính (lan_server.py + core.py, SQLite)
                                                                │
                          Máy trạm quản trị (remote_core.py) ◄──┤ đăng nhập /cdc/login,
                          — tài khoản riêng từng người            tài khoản trong cdc_accounts
```

- `core.py` là **lõi nghiệp vụ** dùng chung cho cả desktop (LAN) và Web — mọi tầng khác (Web
  API, GAS) chỉ bọc thêm quanh các hàm có sẵn (`import_excel`, `find_duplicate_groups`,
  `merge_duplicate_records`, `export_rows`...), không viết lại logic import/dedup/export.
- Toàn bộ AJAX của trang nộp báo cáo nằm **trong `doGet` của `Code.gs`** (cùng origin
  script.google.com), GitHub Pages chỉ là khung `<iframe>` — tránh vướng CORS.
- `docs/config.js` chứa `GAS_URL` hiện tại. Chỉ cần sửa khi tạo **deployment GAS mới** (đổi
  ID); nếu chỉ "New version" trên deployment cũ thì URL không đổi, không cần sửa gì ở đây.
- `gas_deploy/` (bị `.gitignore`) là thư mục làm việc với `clasp` để đẩy `Code.gs` lên project
  GAS thật (`scriptId` trong `gas_deploy/.clasp.json`) — không commit vào git.

### File chính

```text
app.py                 Giao diện, menu, lọc trùng, máy trạm và tab Server
core.py                SQLite, nhập/xuất, chất lượng, thuật toán lọc trùng, cdc_accounts
deployment_config.py   Cấu hình standalone/workstation/server
lan_server.py          HTTP API, /xa, /cdc/hang-doi, /cdc/login, chuyển máy chủ, khóa ghi khi sao lưu
lan_discovery.py       Tự dò máy chủ trong mạng LAN
remote_core.py         Lớp gọi API, retry và trạng thái kết nối máy trạm
backup_manager.py      Chính sách, kiểm tra, lưu giữ và phục hồi sao lưu
duplicate_config.py    Trọng số và ngưỡng lọc trùng
case_view_config.py    Cấu hình cột hiển thị danh sách ca bệnh (chọn/đổi tên/cột tính toán)
update_manager.py      Cập nhật ứng dụng
secondary_sync.py      Đồng bộ hàng đợi từ máy chủ phụ (Google Apps Script) khi online lại
setup.iss              Bộ cài tổng hợp (3 chế độ: đơn lẻ/máy trạm/máy chủ)
setup-server.iss       Bộ cài riêng — chỉ chế độ Máy chủ, cài 1 lần duy nhất
setup-admin.iss        Bộ cài riêng — chỉ máy trạm quản trị, đăng nhập tài khoản riêng
docs/                  GitHub Pages (index.html + config.js) + docs/huong-dan (nguồn HTML + PDF)
google_apps_script/    Code.gs + appsscript.json (nguồn — deploy qua gas_deploy/ với clasp)
tests/                 Kiểm thử lõi, lọc trùng, cấu hình, LAN, cdc_accounts, chuyển máy chủ
```

## Web App tập trung (`webapp/`) — đang chuyển sang, xem TASKS.md

Đang chuyển từ mô hình desktop PyQt6 + máy trạm quản trị riêng sang Web App chạy trên đúng 1
máy chủ — quản trị viên chỉ cần trình duyệt, không cài gì thêm (xem TASKS.md mục "Đang làm:
chuyển sang Web App tập trung" để biết đã xong tới giai đoạn nào). `app.py`/`lan_server.py`/
`setup-admin.iss` **vẫn giữ nguyên, chạy song song** cho tới khi Web App thay thế đủ và được
xác nhận dùng thật — chưa xoá gì.

- Chạy dev: `uvicorn webapp.main:app --reload` (không phải `python app.py`).
- `webapp/config.py`: đọc chung `deployment.json` với app desktop qua `deployment_config.py`
  (không tạo hệ cấu hình riêng) — `web_token_secret` dùng để ký cookie phiên.
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
  lúc chạy) — tránh phụ thuộc mạng ngoài khi phục vụ, và để đóng gói được vào bản cài sau này
  (Giai đoạn 9).
- `/health`: kiểm tra nhanh service + CSDL còn sống, dùng cho Windows Service giám sát (Giai
  đoạn 8) và kiểm tra sau cài đặt.

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
Mở từ nút "Cấu hình cột..." trên tab Ca bệnh (`app.CaseColumnsSettingsDialog`).

### Hai lớp chống trùng

1. **Trùng tuyệt đối khi nhập**: `row_hash = SHA256(entity_type + JSON chuẩn hóa toàn bộ nội
   dung nghiệp vụ)` — chỉ bỏ qua dòng giống hệt đã nhập trước đó.
2. **Lọc trùng nghiệp vụ theo tiêu chí chọn**: `find_duplicate_groups()` tạo cặp ứng viên theo
   khóa chặn (case_code, CCCD, số điện thoại, họ tên+năm sinh, họ tên+xã, họ tên gần giống,
   khoảng cách ngày khởi phát); CDC tự bật/tắt tiêu chí nào coi là trùng (không chấm điểm/
   ngưỡng như bản cũ) — hai bản ghi trùng nếu khớp **ít nhất một** tiêu chí đang bật. Có thể
   lưu bộ tiêu chí thành preset (`dedup_criteria_sets`). `merge_duplicate_records()` sao lưu
   CSDL trước khi hợp nhất; `restore_duplicate_action()` khôi phục được.

### Triển khai LAN

- Máy chủ và máy đơn lẻ dùng SQLite cục bộ; máy chủ mở HTTP API, mỗi request 1 kết nối SQLite
  riêng + WAL. Máy trạm gọi API, không truy cập file `.db` qua thư mục chia sẻ mạng.
- Mật khẩu máy chủ dùng chung là tùy chọn (để trống = API không yêu cầu header xác thực) —
  **độc lập** với tài khoản `cdc_accounts`/`commune_accounts` (hai đường xác thực song song,
  không loại trừ nhau, xem `lan_server._handle_queue_submit`).

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

- **Chuyển tiếp trực tiếp trước** (`Code.gs: tryForwardToMainServer`): nếu Script Property
  `MAIN_SERVER_URL` được cấu hình, mỗi lần nộp gọi thẳng `{MAIN_SERVER_URL}/queue/submit`
  (kèm `X-GSBTN-Password` từ `MAIN_SERVER_PASSWORD` nếu có). Máy chủ chính phản hồi (kể cả lỗi
  thật) thì trả thẳng cho xã, không đệm. Chỉ khi `UrlFetchApp.fetch` lỗi (không tới được) hoặc
  chưa cấu hình `MAIN_SERVER_URL` mới rơi xuống đệm.
- **Đệm khi không chuyển tiếp được**: Sheet `HangDoiPhu` (bảng hàng đợi tạm) + file gốc lưu
  Google Drive `MayChuPhu_GSBTN/<xã>/<tuần>/<file>.xlsx` — **không chia sẻ công khai**.
- **Đồng bộ bù** (`secondary_sync.pull_secondary_queue`): kéo các dòng `cho_dong_bo`, tạo bản
  ghi `import_queue` (`source='server_phu'`), đánh dấu `da_dong_bo` (idempotent). **Tự động**
  chạy theo chu kỳ (`MainWindow.run_auto_secondary_sync`, mặc định 20 phút, chỉnh ở tab Server
  → "Tự động đồng bộ mỗi", 5-180 phút, lưu ở `secondary_sync_interval_minutes`) khi ứng dụng
  đang chạy ở chế độ Máy đơn lẻ/Máy chủ (không chạy ở Máy trạm) và đã cấu hình URL + khóa máy
  chủ phụ — không cần CDC bấm tay, nút "Đồng bộ máy chủ phụ" trên tab Hàng đợi vẫn còn để chạy
  ngay khi cần. Sau khi kéo thành công, `Code.gs: handleMarkSynced` **xoá (Thùng rác Drive, tự
  dọn hẳn sau ~30 ngày)** file Excel gốc tương ứng trên Drive — tránh Drive phình to theo thời
  gian, vì dữ liệu đã nằm an toàn trong CSDL chính.
- **Xác thực**: khóa `SHARED_KEY` dùng chung cho mọi xã trên GAS (khác với
  `commune_accounts`/`cdc_accounts` ở máy chủ chính — có chủ đích, GAS không tự nhiên hỗ trợ
  tốt việc đồng bộ danh sách tài khoản từ máy chủ chính sang). Chặng GAS → máy chủ chính dùng
  riêng `MAIN_SERVER_PASSWORD`, độc lập với `SHARED_KEY`.
- **`SHARED_KEY` không nằm trong bất kỳ file nào trong repo** (chủ đích thiết kế, không đồng
  bộ qua Git) — chỉ tồn tại trong Script Properties của project GAS đang chạy thật. Xem/đổi:
  `script.google.com` → đăng nhập đúng tài khoản Google đã tạo project → **Project Settings**
  (bánh răng) → **Script Properties** → dòng `SHARED_KEY`.

### Triển khai GAS lần đầu (tóm tắt — chi tiết đầy đủ xem `docs/huong-dan/4-google-apps-script.pdf`)

1. `script.google.com` (tài khoản Google CDC) → New project → dán nội dung
   `google_apps_script/Code.gs`; bật hiện `appsscript.json` và dán nội dung
   `google_apps_script/appsscript.json` (phải có khối `webapp` với `executeAs: USER_DEPLOYING`,
   `access: ANYONE_ANONYMOUS`). Có thể dùng `clasp` (`gas_deploy/`) thay vì copy/dán thủ công.
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

### Mở máy chủ chính ra Internet (để GAS chuyển tiếp trực tiếp + máy trạm quản trị ở xa)

**Domain thật đã có: `cdc-hp.io.vn`. Phương án đang dùng: Cloudflare Tunnel** — KHÔNG
port-forward, KHÔNG cần IP tĩnh/Dynamic DNS, KHÔNG cần quyền quản trị router. Lý do đổi từ
Caddy+port-forward sang phương án này: mạng CDC do nhà mạng (VNPT) quản lý thiết bị đầu cuối,
CDC không có quyền đăng nhập router để tự port-forward — Cloudflare Tunnel để máy chủ TỰ kết
nối ra ngoài tới Cloudflare (luôn được phép, không cần cấu hình gì ở phía mạng CDC), Cloudflare
nhận request từ domain rồi chuyển vào qua đúng đường kết nối đó.

Cài đặt: `cloudflared` (daemon nhỏ của Cloudflare) chạy **trên chính máy đang chạy chế độ Máy
chủ**, đăng ký làm dịch vụ Windows qua lệnh `cloudflared.exe service install <token>` (token lấy
từ dashboard `one.dash.cloudflare.com` lúc tạo Tunnel — mỗi CDC/mỗi lần tạo tunnel có token
riêng, không dùng chung). Cấu hình "Public Hostname" trỏ `cdc-hp.io.vn` → `localhost:8765` làm
trực tiếp trên dashboard Cloudflare (không cần sửa file .yml thủ công cho cách làm khuyến nghị).
File mẫu cho ai muốn cấu hình bằng dòng lệnh thay vì dashboard:
`deploy/cloudflared-config.example.yml` (đã kiểm tra hợp lệ). Hướng dẫn từng bước đầy đủ (kể cả
cho người không rành kỹ thuật): `docs/huong-dan/5-mo-ra-internet.pdf`.

**Bắt buộc trước khi bật**: đặt mật khẩu máy chủ (tab Server) — đây là lớp xác thực duy nhất
cho request từ Internet khi không có token cá nhân (`cdc_accounts`)/không có `commune_token`.
Cloudflare Tunnel chỉ lo việc kết nối, không thay được xác thực của ứng dụng.

Sau khi tunnel "Connected" và Public Hostname đã cấu hình:
- **GAS chuyển tiếp trực tiếp**: đặt Script Property `MAIN_SERVER_URL = https://cdc-hp.io.vn`
  + `MAIN_SERVER_PASSWORD` = mật khẩu máy chủ.
- **Máy trạm quản trị ở xa** (ngoài LAN CDC): mở app → "Kết nối máy chủ LAN" → đổi "Địa chỉ máy
  chủ" thành `https://cdc-hp.io.vn` (thay vì IP LAN) — vẫn cùng 1 bản cài `setup-admin.iss`,
  chỉ khác giá trị nhập lúc cấu hình, không cần build riêng.

**Phương án dự phòng** (nếu sau này CDC có máy chủ cố định + quyền quản trị router thật):
Caddy + port-forward truyền thống, cấu hình có sẵn ở `deploy/Caddyfile` (đã `caddy validate`
hợp lệ) nhưng hiện KHÔNG dùng — ít phụ thuộc bên thứ ba hơn nhưng cần hạ tầng mạng CDC không có
ở thời điểm hiện tại.

Đây là thay đổi có rủi ro bảo mật (máy chủ nhận request công khai từ Internet), cân nhắc kỹ và
luôn đảm bảo đã đặt mật khẩu trước khi bật.

## Build & test

```bat
python -m pytest -q          REM chạy toàn bộ test (tests/)
build.bat                     REM build bằng PyInstaller + Inno Setup
```

`.github/workflows/release.yml` build/test trên Windows khi push `main` hoặc tạo tag, quét
chặn dữ liệu cấm (`.db`, Excel, CSV...) lọt vào release; PR chỉ build/test, không tạo Release.
