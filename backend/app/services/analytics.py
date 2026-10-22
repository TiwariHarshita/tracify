"""Bounded, server-only analytics. No user SQL, paths, or client totals."""
import json
import threading
import time
from datetime import datetime, time as day_time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext

import duckdb
from fastapi import HTTPException

from app.schemas.analytics import EvaluateRequest
from app.services.csv_ingestion import ensure_profile, verified_source
from app.services.csv_parser import CsvRejected, is_number, parse_csv

CALCULATION_VERSION = "trace-analytics-v1"
MAX_GROUPS = 200
QUERY_SECONDS = 20
# Per process, never a shared DuckDB connection. Excess concurrent work fails
# explicitly instead of allocating an unbounded number of 128 MB instances.
SLOTS = threading.BoundedSemaphore(2)


def reject(message):
    raise HTTPException(422, message)


def decimal_value(value):
    if not is_number(value.strip()):
        reject("Numeric bounds must be finite decimal strings, such as 12.50.")
    with localcontext() as context:
        context.prec = 150
        number = Decimal(value.strip()).normalize()
    scale = max(0, -number.as_tuple().exponent)
    integer = max(0, number.adjusted() + 1) if number else 0
    if scale > 18 or integer + scale > 38:
        reject("Analytics supports exact numbers up to 38 digits, with at most 18 fractional digits. No value was rounded or dropped.")
    return number, scale, integer


def utc_value(value):
    value = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    # Explicit MVP convention: dates and naive timestamps are UTC.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(tzinfo=None).isoformat()


def encoded(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    return value


class Engine:
    def __init__(self, profile, rows, request):
        self.profile, self.rows, self.request = profile, rows, request
        self.columns = {column["key"]: column for column in profile["columns"]}
        self.column_indexes = {column["key"]: index for index, column in enumerate(profile["columns"])}
        # Only materialize typed fields that this batch can query. Parsed rows
        # remain the source of truth for table cells, so a metric does not pay
        # to duplicate every raw value from a wide CSV inside DuckDB.
        requested = {item.column for item in request.filters}
        for block in request.calculations:
            if block.type == "table":
                requested.add(block.sort_by)
            else:
                if block.column is not None:
                    requested.add(block.column)
                if block.group_by is not None:
                    requested.add(block.group_by)
        self.typed_keys = {key for key in requested if key in self.columns}
        self.sql_types = {}
        self.scales = {}
        self.deadline = time.monotonic() + QUERY_SECONDS
        self.expired = threading.Event()
        self.con = duckdb.connect(":memory:", config={
            "threads": "1", "memory_limit": "128MB", "enable_external_access": "false",
            "autoinstall_known_extensions": "false", "autoload_known_extensions": "false",
            "max_temp_directory_size": "0B",
        })
        self.timer = threading.Timer(QUERY_SECONDS, self.interrupt)
        self.timer.daemon = True
        self.timer.start()

    def interrupt(self):
        self.expired.set()
        self.con.interrupt()

    def close(self):
        self.timer.cancel()
        self.timer.join()
        self.con.close()

    def check_time(self):
        if self.expired.is_set() or time.monotonic() > self.deadline:
            raise HTTPException(422, "Calculation exceeded 20 seconds. Use a smaller CSV or fewer calculations.")

    def execute(self, sql, parameters=None):
        self.check_time()
        return self.con.execute(sql, parameters or [])

    def column(self, key):
        if key not in self.columns:
            reject(f"Unknown column key: {key}. Reload the dataset profile.")
        return self.columns[key]

    def load(self):
        # Rebuild typed data from verified original bytes, not editable sidecar
        # rows. No DuckDB CSV inference or second, different CSV parser.
        payload = []
        definitions = ["record_number BIGINT", "line_start BIGINT", "line_end BIGINT"]
        for index, column in enumerate(self.profile["columns"]):
            key = column["key"]
            if key not in self.typed_keys:
                continue
            if column["type"] == "number":
                scales, integers = [0], [0]
                for row in self.rows:
                    if row["cells"][index].strip():
                        _, scale, integer = decimal_value(row["cells"][index])
                        scales.append(scale)
                        integers.append(integer)
                scale = max(scales)
                if max(integers) + scale > 38:
                    reject(f'Column {column["name"]} cannot fit one exact decimal type. No calculation ran.')
                self.scales[key] = scale
                kind = f"DECIMAL(38,{scale})"
            else:
                kind = "TIMESTAMP" if column["type"] == "date" else "VARCHAR"
            self.sql_types[key] = kind
            definitions.append(f'"{key}" {kind}')
        for row in self.rows:
            self.check_time()
            item = {key: row[key] for key in ["record_number", "line_start", "line_end"]}
            for key in self.typed_keys:
                index, column = self.column_indexes[key], self.columns[key]
                value = row["cells"][index]
                if not value.strip():
                    item[key] = None
                elif column["type"] == "number":
                    item[key] = format(decimal_value(value)[0], "f")
                elif column["type"] == "date":
                    try:
                        item[key] = utc_value(value)
                    except (ValueError, OverflowError):
                        reject(f'Date in {column["name"]} is outside the supported UTC range.')
                else:
                    item[key] = value
            payload.append(item)
        self.execute("CREATE TABLE source (" + ", ".join(definitions) + ")")
        # JSON is a bound, in-memory string; external access stays disabled.
        keys = [(key, "BIGINT") for key in ["record_number", "line_start", "line_end"]]
        for key, kind in self.sql_types.items():
            keys.append((key, kind))
        select = ", ".join(f"CAST(value ->> '{key}' AS {kind})" for key, kind in keys)
        self.execute("INSERT INTO source SELECT " + select + " FROM json_each(?)", [json.dumps(payload, ensure_ascii=False)])

    def filters(self):
        predicates, parameters, descriptions = [], [], []
        for item in self.request.filters:
            column = self.column(item.column)
            key, name = '"' + item.column + '"', column["name"]
            if item.type == "category":
                if column["type"] not in {"category", "text"}:
                    reject("Category filters require a category or text column.")
                predicates.append(f"{key} IN (" + ", ".join("?" for _ in item.values) + ")")
                parameters.extend(item.values)
                descriptions.append(f"{name} equals one of {json.dumps(item.values, ensure_ascii=False)} (exact, case-sensitive labels)")
            elif item.type == "date_range":
                if column["type"] != "date":
                    reject("Date range filters require a date column.")
                start = datetime.combine(item.start, day_time.min, timezone.utc).isoformat()
                end = datetime.combine(item.end + timedelta(days=1), day_time.min, timezone.utc).isoformat()
                predicates.append(f"({key} >= CAST(? AS TIMESTAMP) AND {key} < CAST(? AS TIMESTAMP))")
                parameters.extend([start, end])
                descriptions.append(f"{name} is on or after {item.start} and on or before {item.end}, using UTC calendar days")
            elif item.type == "number_range":
                if column["type"] != "number":
                    reject("Number range filters require a number column.")
                bounds = []
                for value, operator in [(item.minimum, ">="), (item.maximum, "<=")]:
                    if value is not None:
                        number, _, _ = decimal_value(value)
                        bounds.append(number)
                        # Use the bound's own exact scale; never round a bound
                        # into the column's possibly smaller scale.
                        scale = decimal_value(value)[1]
                        predicates.append(f"{key} {operator} CAST(? AS DECIMAL(38,{scale}))")
                        parameters.append(format(number, "f"))
                if len(bounds) == 2 and bounds[0] > bounds[1]:
                    reject("Numeric minimum must not exceed maximum.")
                descriptions.append(f"{name} is between {item.minimum or 'no lower bound'} and {item.maximum or 'no upper bound'} (inclusive)")
            else:
                predicates.append(f"{key} IS {'NULL' if item.missing else 'NOT NULL'}")
                descriptions.append(f"{name} is {'missing' if item.missing else 'present'}")
        return " AND ".join(predicates) or "TRUE", parameters, "; AND ".join(descriptions) or "No report filters."

    def query(self, sql, parameters):
        cursor = self.execute(sql, parameters)
        names = [item[0] for item in cursor.description]
        rows = [{key: encoded(value) for key, value in zip(names, row)} for row in cursor.fetchall()]
        return rows, {"sql": sql, "parameters": parameters}

    def calculate(self, block, where, parameters, counts, count_query, filter_description):
        total, matched = counts["total_rows"], counts["matched_rows"]
        if block.type == "table":
            sort = self.column(block.sort_by)
            selected = ["record_number", "line_start", "line_end"]
            sql = "SELECT " + ", ".join(selected) + f' FROM source WHERE {where} ORDER BY source."{block.sort_by}" {block.direction.upper()} NULLS LAST, record_number ASC LIMIT ?'
            data, result_query = self.query(sql, parameters + [block.limit])
            # The query chooses rows by typed values. Cells are then restored
            # directly from the already-parsed source rows, avoiding a full
            # raw-string duplicate in DuckDB for every table calculation.
            source_rows = {row["record_number"]: row for row in self.rows}
            for item in data:
                source = source_rows[item["record_number"]]
                item.update({key: source["cells"][index] for key, index in self.column_indexes.items()})
            included, missing = len(data), 0
            limited = matched - included
            explanation = f'Show up to {block.limit} rows ordered by {sort["name"]}, {block.direction}ending; missing sort values last, ties by original record number. Return original cell strings.'
            postprocess = "None. Table cells are original CSV strings, including empty cells."
            result = {"rows": data, "columns": list(self.columns.values())}
        else:
            column = self.column(block.column) if block.column else None
            if block.operation in {"sum", "average"} and column["type"] != "number":
                reject("Sum and average require a number column. Mixed text is never silently coerced.")
            if block.operation in {"min", "max"} and column["type"] not in {"number", "date"}:
                reject("Min and max require a number or date column.")
            if block.group_by:
                group = self.column(block.group_by)
                allowed = {"category"} if block.type == "metric" else ({"number", "date"} if block.chart_type == "line" else {"category", "date"})
                if group["type"] not in allowed:
                    reject("Metric splits need a category; bar charts need category/date; line charts need number/date.")
            key = f'"{block.column}"' if column else "*"
            aggregate = {"sum": "SUM", "average": "SUM", "count": "COUNT", "min": "MIN", "max": "MAX"}[block.operation]
            expression = f"{aggregate}({key})"
            group_select = f'"{block.group_by}" AS group_value, ' if block.group_by else ""
            group_tail = f' GROUP BY "{block.group_by}" ORDER BY "{block.group_by}" ASC NULLS LAST LIMIT {MAX_GROUPS + 1}' if block.group_by else ""
            alias = "numerator" if block.operation == "average" else "value"
            sql = f"SELECT {group_select}{expression} AS {alias}, COUNT(*) AS matched_rows, COUNT({key}) AS included_rows FROM source WHERE {where}{group_tail}"
            data, result_query = self.query(sql, parameters)
            if len(data) > MAX_GROUPS:
                reject("More than 200 result groups. Apply a filter; no groups were silently dropped.")
            for row in data:
                row["excluded_missing"] = row["matched_rows"] - row["included_rows"]
                if block.operation == "average":
                    with localcontext() as context:
                        context.prec = 80
                        row["value"] = format((Decimal(row["numerator"]) / Decimal(row["included_rows"])).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP), "f") if row["included_rows"] else None
            included = sum(row["included_rows"] for row in data)
            missing, limited = matched - included, 0
            subject = column["name"] if column else "all rows"
            explanation = f'Calculate {block.operation} of {subject}' + (f', split by {self.columns[block.group_by]["name"]} (a missing group is retained as null).' if block.group_by else ".")
            explanation += " Missing selected values do not contribute; count without a column counts all matched rows. Empty sum/average/min/max is null; empty count is zero."
            postprocess = "Average = SQL numerator / SQL included_rows on the server, decimal precision 80, rounded to 6 fractional digits with ROUND_HALF_UP; zero denominator returns null." if block.operation == "average" else "Exact decimals are returned as strings; timestamps are UTC ISO strings; counts are integers. No client-side aggregation."
            result = {"rows": data}
            if block.type == "chart":
                result["chart_type"] = block.chart_type
        receipt = {
            "description": explanation + " Filters: " + filter_description,
            "queries": [count_query, result_query], "postprocessing": postprocess,
            "calculation": block.model_dump(mode="json"),
            "total_rows": total, "matched_rows": matched, "included_rows": included,
            "excluded_rows": total - included, "excluded_by_filters": total - matched,
            "excluded_missing_value": missing, "excluded_by_limit": limited,
            "filters": [item.model_dump(mode="json") for item in self.request.filters],
            "filter_logic": "AND", "calculation_version": CALCULATION_VERSION,
            "parser_version": self.profile["parser_version"], "dataset_sha256": self.profile["sha256"],
            "delimiter": self.profile["delimiter"],
            "column_mapping": [{"key": key, "name": value["name"], "inferred_type": value["type"], "sql_type": self.sql_types.get(key, "not materialized for this calculation")} for key, value in self.columns.items()],
            "source_relation": "source is rebuilt from every readable record of the verified original CSV using its stored delimiter and trace-csv-v1, projecting only typed columns required by this calculation; empty/whitespace values become SQL NULL. Record/source-line numbers are retained. Table cells are restored as original CSV strings for the selected record numbers. Dates and naive timestamps are UTC; offset timestamps are converted to UTC.",
        }
        return {"id": block.id, "type": block.type, "result": result, "receipt": receipt}

    def run(self):
        self.load()
        where, parameters, description = self.filters()
        data, count_query = self.query(f"SELECT COUNT(*) AS total_rows, COUNT(*) FILTER (WHERE {where}) AS matched_rows FROM source", parameters)
        results = [self.calculate(block, where, parameters, data[0], count_query, description) for block in self.request.calculations]
        self.check_time()
        return {"calculation_version": CALCULATION_VERSION, "dataset_sha256": self.profile["sha256"], "results": results}


def evaluate_dataset(dataset, request: EvaluateRequest):
    if request.expected_sha256 != dataset.sha256:
        raise HTTPException(409, "Dataset version changed. Reload its profile before calculating.")
    if not SLOTS.acquire(blocking=False):
        raise HTTPException(429, "Two calculations are already running. Try again shortly.", headers={"Retry-After": "2"})
    engine = None
    try:
        configuration = ensure_profile(dataset)
        # Verify the original again, and keep these exact bytes for this entire
        # batch. Sidecars are used for parse configuration only, never totals.
        profile, rows, _ = parse_csv(verified_source(dataset), configuration["delimiter"])
        if not profile["analysis_ready"]:
            reject("This CSV has unreadable records. Fix and re-upload it before calculating.")
        engine = Engine(profile, rows, request)
        response = engine.run()
        if len(json.dumps(response, ensure_ascii=False).encode("utf-8")) > 2 * 1024 * 1024:
            reject("Calculation response exceeds 2 MiB. Request fewer calculations or smaller tables; no result was truncated.")
        response["dataset_id"] = str(dataset.id)
        for item in response["results"]:
            item["receipt"]["dataset_id"] = str(dataset.id)
        return response
    except CsvRejected as exc:
        raise HTTPException(exc.status_code, exc.detail) from None
    except duckdb.Error:
        reject("The calculation exceeded the supported time, memory, or exact decimal range. Use a smaller CSV or fewer calculations; no partial result was returned.")
    finally:
        if engine is not None:
            engine.close()
        SLOTS.release()
