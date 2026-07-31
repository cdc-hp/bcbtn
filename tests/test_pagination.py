"""Kiểm thử `webapp/services/pagination.py::paginate` — dùng chung cho các trang danh sách chưa
phân trang (Hàng đợi, Tài khoản, Tài khoản xã, Nhật ký kiểm toán, Lịch sử nhập, Sao lưu)."""

from __future__ import annotations

from webapp.services.pagination import paginate


def test_paginate_first_page():
    rows = list(range(120))
    page_rows, info = paginate(rows, page=1, page_size=50)
    assert page_rows == list(range(0, 50))
    assert info == {"page": 1, "total": 120, "total_pages": 3, "page_size": 50}


def test_paginate_middle_page():
    rows = list(range(120))
    page_rows, info = paginate(rows, page=2, page_size=50)
    assert page_rows == list(range(50, 100))
    assert info["page"] == 2


def test_paginate_last_page_partial():
    rows = list(range(120))
    page_rows, info = paginate(rows, page=3, page_size=50)
    assert page_rows == list(range(100, 120))
    assert info["total_pages"] == 3


def test_paginate_page_beyond_total_clamps_to_last_page():
    rows = list(range(10))
    page_rows, info = paginate(rows, page=99, page_size=50)
    assert page_rows == list(range(10))
    assert info["page"] == 1  # chỉ có 1 trang


def test_paginate_page_zero_or_negative_clamps_to_first_page():
    rows = list(range(10))
    page_rows, info = paginate(rows, page=0, page_size=50)
    assert info["page"] == 1
    page_rows, info = paginate(rows, page=-5, page_size=50)
    assert info["page"] == 1


def test_paginate_empty_rows():
    page_rows, info = paginate([], page=1, page_size=50)
    assert page_rows == []
    assert info == {"page": 1, "total": 0, "total_pages": 1, "page_size": 50}


def test_paginate_custom_page_size():
    rows = list(range(25))
    page_rows, info = paginate(rows, page=2, page_size=10)
    assert page_rows == list(range(10, 20))
    assert info["total_pages"] == 3
