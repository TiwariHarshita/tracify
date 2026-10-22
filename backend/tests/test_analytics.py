from decimal import Decimal
from pathlib import Path

import duckdb
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.analytics import EvaluateRequest
from app.services.analytics import Engine
from app.services.csv_parser import parse_csv

CSV = b'amount,date,group,label\n0.10,2026-10-01T23:30:00-02:00,A,first\n0.20,2026-10-02T12:00:00Z,A,\n,2026-10-03,B,none\n2.70,2026-10-04,,other\n-1.00,2026-10-02,A,null\n'


def metric(operation="sum", column="c0", group_by=None, id="metric"):
    return dict(id=id, type="metric", operation=operation, column=column, group_by=group_by)


def run(data=CSV, calculations=None, filters=None):
    profile, rows, _ = parse_csv(data)
    request = EvaluateRequest(expected_sha256=profile["sha256"], calculations=calculations or [metric()], filters=filters or [])
    engine = Engine(profile, rows, request)
    try:
        return engine.run()
    finally:
        engine.close()


@pytest.mark.parametrize("operation,expected", [("sum","2.0"),("average","0.500000"),("count",4),("min","-1.0"),("max","2.7")])
def test_hand_checked_aggregates_and_missing_receipt(operation, expected):
    item=run(calculations=[metric(operation)])["results"][0]
    assert item["result"]["rows"][0]["value"]==expected
    r=item["receipt"]
    assert (r["total_rows"],r["included_rows"],r["excluded_rows"],r["excluded_missing_value"])==(5,4,1,1)
    assert r["excluded_by_filters"]==0


def test_count_star_vs_column_and_average_precision():
    response=run(calculations=[metric("count",None,id="all"),metric("count",id="present"),metric("average",group_by="c2",id="mean")])
    assert response["results"][0]["result"]["rows"][0]["value"]==5
    assert response["results"][1]["result"]["rows"][0]["value"]==4
    grouped=response["results"][2]["result"]["rows"]
    assert [row["group_value"] for row in grouped]==["A","B",None]
    assert [row["value"] for row in grouped]==["-0.233333",None,"2.700000"]
    assert grouped[1]["included_rows"]==0


@pytest.mark.parametrize("operation,expected", [("sum",None),("average",None),("count",0),("min",None),("max",None)])
def test_empty_results(operation, expected):
    item=run(calculations=[metric(operation)],filters=[dict(type="category",column="c2",values=["absent"])])["results"][0]
    assert item["result"]["rows"][0]["value"]==expected
    assert item["receipt"]["excluded_by_filters"]==5
    assert item["receipt"]["included_rows"]==0


def test_date_days_utc_offsets_and_shared_filters_for_metric_chart_table():
    blocks=[metric(),dict(id="chart",type="chart",chart_type="bar",operation="sum",column="c0",group_by="c2"),dict(id="table",type="table",sort_by="c0",limit=2)]
    results=run(calculations=blocks,filters=[dict(type="date_range",column="c1",start="2026-10-02",end="2026-10-02")])["results"]
    assert results[0]["result"]["rows"][0]["value"]=="-0.7"
    assert results[1]["result"]["rows"][0]["value"]=="-0.7"
    assert [row["record_number"] for row in results[2]["result"]["rows"]]==[2,1]
    assert all(result["receipt"]["matched_rows"]==3 for result in results)
    assert results[2]["receipt"]["excluded_by_filters"]==2
    assert results[2]["receipt"]["excluded_by_limit"]==1
    assert results[2]["receipt"]["excluded_rows"]==3
    assert results[0]["receipt"]["queries"][1]["parameters"]==["2026-10-02T00:00:00+00:00","2026-10-03T00:00:00+00:00"]


def test_numeric_bound_does_not_round_to_column_scale():
    item=run(data=b"amount\n1\n2\n3\n", filters=[dict(type="number_range",column="c0",minimum="1.5",maximum="2.9")])["results"][0]
    assert item["result"]["rows"][0]["value"]=="2"
    assert item["receipt"]["included_rows"]==1


def test_missing_filter_and_multiple_filters_are_anded():
    item=run(filters=[dict(type="missing",column="c0",missing=False),dict(type="category",column="c2",values=["A"]),dict(type="number_range",column="c0",minimum="0")])["results"][0]
    assert item["result"]["rows"][0]["value"]=="0.3"
    assert item["receipt"]["excluded_by_filters"]==3
    assert run(filters=[dict(type="missing",column="c2")])["results"][0]["result"]["rows"][0]["value"]=="2.7"


def test_exact_category_labels_and_sql_injection_is_a_bound_value():
    value="A') OR 1=1 --"
    item=run(data=("amount,group\n1,A\n2, A\n3,"+value+"\n").encode(),filters=[dict(type="category",column="c1",values=[value])])["results"][0]
    assert item["result"]["rows"][0]["value"]=="3"
    assert value not in item["receipt"]["queries"][1]["sql"]
    assert item["receipt"]["queries"][1]["parameters"]==[value]


def test_top_rows_ties_null_last_and_original_strings():
    result=run(data=b'amount,name\n2,A\n2,B\n,C\n10,D\n',calculations=[dict(id="top",type="table",sort_by="c0",limit=4)])["results"][0]
    assert [row["record_number"] for row in result["result"]["rows"]]==[4,1,2,3]
    assert result["result"]["rows"][-1]["c0"]==""
    assert result["result"]["rows"][0]["line_start"]==5


def test_dates_min_and_line_data_are_sorted_in_utc():
    results=run(calculations=[metric("min","c1"),dict(id="line",type="chart",chart_type="line",operation="count",group_by="c1")])["results"]
    assert results[0]["result"]["rows"][0]["value"]=="2026-10-02T00:00:00Z"
    assert results[1]["result"]["rows"][1]["group_value"]=="2026-10-02T01:30:00Z"


@pytest.mark.parametrize("block,filters", [
    (metric(column="c99"),[]), (metric(column="c2"),[]),
    (metric(group_by="c0"),[]),
    (dict(id="l",type="chart",chart_type="line",operation="sum",column="c0",group_by="c2"),[]),
    (metric(),[dict(type="date_range",column="c2",start="2026-10-01",end="2026-10-02")]),
    (metric(),[dict(type="number_range",column="c0",minimum="NaN")]),
    (metric(),[dict(type="number_range",column="c0",minimum="2",maximum="1")]),
    (metric(),[dict(type="category",column="c0",values=["1"])]),
])
def test_invalid_columns_operations_and_filters_reject(block,filters):
    with pytest.raises(HTTPException) as error:
        run(calculations=[block],filters=filters)
    assert error.value.status_code==422


@pytest.mark.parametrize("data", [b"amount\n1e99\n",b"amount\n0.0000000000000000001\n"])
def test_numeric_capacity_is_explicit_never_rounded(data):
    with pytest.raises(HTTPException,match="38 digits"):
        run(data=data)


def test_more_than_200_groups_is_an_error_not_truncated():
    data=("amount,date\n"+"".join(f"1,2026-01-01T00:{i//60:02}:{i%60:02}Z\n" for i in range(201))).encode()
    with pytest.raises(HTTPException,match="200 result groups"):
        run(data=data,calculations=[dict(id="chart",type="chart",chart_type="line",operation="sum",column="c0",group_by="c1")])


def test_empty_csv_table_and_grouped_results_are_empty_count_zero():
    result=run(data=b"amount,group\n",calculations=[metric("count",None),dict(id="table",type="table",sort_by="c0")])
    assert result["results"][0]["result"]["rows"][0]["value"]==0
    assert result["results"][1]["result"]["rows"]==[]


def test_schema_rejects_sql_paths_duplicate_ids_and_oversized_limits():
    base=dict(expected_sha256="0"*64,calculations=[metric()])
    for extra in [{"sql":"SELECT * FROM secret"},{"path":"/etc/passwd"},{"calculations":[metric(),metric()]},{"calculations":[dict(id="t",type="table",sort_by="c0",limit=101)]}]:
        with pytest.raises(ValidationError):EvaluateRequest(**(base|extra))
    with pytest.raises(ValidationError):EvaluateRequest(**(base|{"filters":[dict(type="date_range",column="c1",start="2026-10-02",end="2026-10-01")]}))


def test_query_receipt_replays_against_same_source():
    profile,rows,_=parse_csv(CSV)
    request=EvaluateRequest(expected_sha256=profile["sha256"],calculations=[metric()],filters=[dict(type="category",column="c2",values=["A"])])
    engine=Engine(profile,rows,request)
    try:
        item=engine.run()["results"][0]
        query=item["receipt"]["queries"][1]
        replay=engine.con.execute(query["sql"],query["parameters"]).fetchone()
        assert format(replay[0],"f")==item["result"]["rows"][0]["value"]
        assert replay[2]==item["receipt"]["included_rows"]
        assert engine.con.execute("SELECT current_setting('enable_external_access')").fetchone()[0] is False
    finally:engine.close()


def test_public_tips_known_totals():
    path=Path(__file__).resolve().parents[1]/"sample_data"/"tips.csv"
    if not path.exists():
        # Overlay check from the repository workspace.
        path=Path(__file__).resolve().parents[3]/"phase3-test-harness"/"sample_data"/"tips.csv"
    result=run(path.read_bytes(),calculations=[metric("sum","c0"),metric("sum","c1",id="tips"),metric("count",None,id="rows")])["results"]
    assert Decimal(result[0]["result"]["rows"][0]["value"])==Decimal("4827.77")
    assert Decimal(result[1]["result"]["rows"][0]["value"])==Decimal("731.58")
    assert result[2]["result"]["rows"][0]["value"]==244


def test_decimal_values_beyond_javascript_precision_remain_exact():
    item=run(data=b"amount\n9007199254740993.01\n0.09\n")["results"][0]
    assert item["result"]["rows"][0]["value"]=="9007199254740993.10"


def test_expired_budget_is_an_explicit_failure():
    profile,rows,_=parse_csv(CSV)
    request=EvaluateRequest(expected_sha256=profile["sha256"],calculations=[metric()])
    engine=Engine(profile,rows,request)
    try:
        engine.deadline=0
        with pytest.raises(HTTPException,match="exceeded 20 seconds"):
            engine.run()
    finally:engine.close()
