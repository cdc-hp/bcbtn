// Link deploy Google Apps Script (máy chủ phụ) — sửa giá trị này khi CDC deploy lại
// (Deploy → Manage deployments → Edit → New version, GIỮ NGUYÊN deployment để URL không đổi;
// chỉ cần sửa GAS_URL ở đây nếu thật sự tạo một deployment mới với ID khác).
var GAS_URL = "https://script.google.com/macros/s/AKfycbySJby7Yx1oOXeAw8bjcSILMsVw6c0ua8FEulR7vo730-mpHte2l5Grfo2ugcnVGlPh/exec";

// Địa chỉ Internet công khai của máy chủ chính (Cloudflare Tunnel, vd. "https://cdc-hp.io.vn")
// — trang nộp báo cáo (index.html) thử gọi thẳng vào đây TRƯỚC, chỉ rơi xuống GAS_URL ở trên
// khi không kết nối được (mạng lỗi/máy chủ chính tắt). Để trống ("") nếu máy chủ chính CHƯA mở
// ra Internet — trang sẽ bỏ qua bước gọi thẳng và luôn nộp qua GAS_URL như trước, không cần đổi
// gì thêm. Máy chủ chính cũng phải cấu hình khoá `public_submit_key` ở /cdc/cau-hinh thì mới
// nhận request thẳng từ đây (xem CLAUDE.md mục "Web nộp báo cáo trực tiếp từ GitHub Pages").
var MAIN_SERVER_URL = "";
