import csv
import io

import pytest
from app.services.csv_parser import CsvRejected, MAX_BYTES, parse_csv


def test_all_four_types_and_missing_are_inferred_from_all_readable_rows():
    data=b"amount,when,group,note\n1.25,2026-10-20,A,This is a long note that is intentionally longer than eighty characters so it remains free text.\n2,2026-10-21,B,Another note that is intentionally longer than eighty characters so it remains free text too.\n , ,A,\n"
    profile, rows, errors=parse_csv(data)
    assert [column["type"] for column in profile["columns"]]==["number","date","category","text"]
    assert [column["missing_count"] for column in profile["columns"]]==[1,1,0,1]
    assert profile["total_records"]==len(rows)==3
    assert profile["analysis_ready"] is True and errors==[]


def test_width_errors_and_blank_records_are_counted_and_all_lines_accounted():
    data=b"a,b\n1,2\n3\n\n4,5,6\n7,8\n"
    profile, rows, errors=parse_csv(data)
    assert profile["total_records"]==5
    assert profile["readable_rows"]==2
    assert profile["unreadable_rows"]==3
    assert len(errors)==3
    covered=[]
    for item in rows+errors:
        covered.extend(range(item["line_start"],item["line_end"]+1))
    assert sorted(covered)==[2,3,4,5,6]
    assert rows[-1]["cells"]==["7","8"]


def test_multiline_quoted_cells_keep_source_line_ranges():
    profile, rows, errors=parse_csv(b'a,b\r\n1,"hello\r\nworld"\r\n2,ok\r\n')
    assert profile["total_records"]==2 and not errors
    assert rows[0]["line_start"]==2 and rows[0]["line_end"]==3
    assert rows[0]["cells"][1]=="hello\r\nworld"
    assert rows[1]["line_start"]==4


@pytest.mark.parametrize("bad", [b'a,b\n1,"unterminated\n2,ok\n', b'a,b\n1,"bad"oops\n2,ok\n'])
def test_syntax_errors_quarantine_the_whole_remaining_range_without_guessing(bad):
    profile, rows, errors=parse_csv(bad)
    assert profile["total_records"] is None
    assert profile["analysis_ready"] is False
    assert errors[0]["code"]=="unparsed_range"
    assert errors[0]["line_start"]==2 and errors[0]["line_end"]==3
    assert profile["unparsed_lines"]==2
    assert "boundaries cannot be trusted" in errors[0]["reason"]


def test_valid_prefix_before_syntax_error_is_retained_and_count_is_not_invented():
    profile, rows, errors=parse_csv(b'a,b\n1,ok\n2,"broken\n3,ok\n')
    assert profile["known_records"]==1 and profile["total_records"] is None
    assert len(rows)==1 and errors[0]["line_start"]==3 and errors[0]["line_end"]==4


def test_na_labels_mixed_values_and_leading_zero_identifiers_are_not_coerced():
    profile, rows, _=parse_csv(b"id,value,label\n001,10,NA\n002,oops,null\n003,,N/A\n")
    assert profile["columns"][0]["type"]=="category"
    assert profile["columns"][1]["type"]=="text"
    assert profile["columns"][1]["missing_count"]==1
    assert profile["columns"][2]["missing_count"]==0
    assert rows[0]["cells"]==["001","10","NA"]


@pytest.mark.parametrize("data", [
    b"", b"\xff", b"a,b\n1,\x00", b"a,a\n1,2\n", b"a, a \n1,2\n", b"a,\n1,2\n",
])
def test_invalid_files_fail_explicitly_instead_of_partial_or_lossy_import(data):
    with pytest.raises(CsvRejected):
        parse_csv(data)


def test_utf8_bom_semicolon_and_zero_row_header_work():
    profile, rows, errors=parse_csv("\ufeffname;amount\nA;3\n".encode(),";")
    assert profile["columns"][0]["name"]=="name" and profile["columns"][1]["type"]=="number"
    assert len(rows)==1 and errors==[]
    empty, rows, errors=parse_csv(b"a,b\n")
    assert empty["total_records"]==0 and rows==errors==[]


def test_limits_reject_the_entire_request_without_truncating():
    with pytest.raises(CsvRejected) as caught:
        parse_csv(b"x"*(MAX_BYTES+1))
    assert caught.value.status_code==413


def test_literal_unicode_line_separator_is_not_treated_as_a_csv_record_boundary():
    profile, rows, _=parse_csv("a,b\n1,one\u2028two\n".encode())
    assert profile["total_records"]==1 and rows[0]["cells"][1]=="one\u2028two"


def test_invalid_iso_date_falls_back_to_text_with_reason():
    profile, _, _=parse_csv(b"when\n2026-10-21\n2026-02-30\n")
    assert profile["columns"][0]["type"]=="text"
    assert profile["columns"][0]["warnings"]


def test_iso_timestamps_are_dates_without_timezone_or_precision_rewrites():
    data=b"when\n2026-10-21T12:30:00Z\n2026-10-22T14:00:00+05:30\n"
    profile, rows, _=parse_csv(data)
    assert profile["columns"][0]["type"]=="date"
    assert rows[1]["cells"][0]=="2026-10-22T14:00:00+05:30"
