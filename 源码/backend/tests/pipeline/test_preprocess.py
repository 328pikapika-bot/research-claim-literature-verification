from app.pipeline.stages.preprocess import _build_input_summary_text


def test_build_input_summary_text_is_human_readable():
    summary = _build_input_summary_text(
        {
            "document_count": 2,
            "total_chars": 12340,
            "uploaded_file_count": 1,
            "resolved_file_count": 1,
            "missing_file_ids": [],
            "truncated_file_count": 0,
            "subject_area": "医学",
            "year_range": [2020, 2026],
            "language_pref": "zh",
        }
    )

    assert summary.startswith("已读取 2 份输入材料")
    assert "12,340 字符" in summary
    assert "年份范围：2020-2026" in summary
