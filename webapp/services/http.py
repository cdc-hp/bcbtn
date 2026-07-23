"""Tiện ích HTTP dùng chung giữa nhiều router — hiện chỉ có xác định IP thật của client."""

from __future__ import annotations

from fastapi import Request


def client_ip(request: Request) -> str:
    """Ưu tiên IP thật của client khi phía trước có Cloudflare Tunnel/reverse proxy (header do
    hạ tầng đó gắn, không phải client tự khai nên không giả mạo được từ trình duyệt) — chỉ
    dùng request.client.host (IP kết nối TCP trực tiếp) khi truy cập thẳng qua LAN."""
    cf_ip = request.headers.get("cf-connecting-ip", "").strip()
    if cf_ip:
        return cf_ip
    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else ""
