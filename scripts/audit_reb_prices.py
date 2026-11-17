    query = {"KEY": api_key, "Type": "json", "pIndex": 1, "pSize": 1000}
    query.update(args)
    req = urllib.request.Request(ROOT + service + ".do?" + urllib.parse.urlencode(query),
                                 headers={"Accept": "application/json",
                                          "User-Agent": "SeoulAptDashboard/1.8.3-audit"})
    try:
        with urllib.request.urlopen(req, timeout=25) as result:
            value = json.load(result)
    except urllib.error.HTTPError as exc:
        return {"status": "HTTP_" + str(exc.code), "rows": [], "total": None}
    except NETWORK_ERRORS as exc:
        return {"status": "TRANSPORT_" + type(exc).__name__, "rows": [], "total": None}
    except (ValueError, UnicodeError, json.JSONDecodeError):
        return {"status": "INVALID_BODY", "rows": [], "total": None}
    return interpret(value, service)


def months_of(rows, stat_id, allowed_region="500008", allowed_item="100001"):
    months = set()
    for r in rows:
        if (str(r.get("STATBL_ID")) == stat_id
                and str(r.get("CLS_ID")) == allowed_region
                and str(r.get("ITM_ID")) == allowed_item):
            v = str(r.get("WRTTIME_IDTFR_ID", ""))
            if re.fullmatch(r"\d{6}", v) and v[4:] in {f"{n:02d}" for n in range(1, 13)}:
                months.add(v[:4] + "-" + v[4:])
    return sorted(months)


def run_probe(api_key, requester=request, sleeper=time.sleep):
    report = ["# REB R-ONE v1.8.3 independent price coverage audit (READ ONLY)",
              "No file writes, no repository commits, no deployment, no raw values/URLs/secrets.", ""]
    responses = []

    # Catalog must be queried as a collection. Filter by exact STATBL_ID;
    # NEVER use catalog[0] as metadata of a requested table.
    catalog = requester(api_key, "SttsApiTbl", {})
    report.append("CATALOG status=" + safe_text(catalog["status"]) +
                  " returned=" + str(len(catalog["rows"])) +
                  " total=" + str(catalog["total"]))
    by_id = {str(r.get("STATBL_ID")): r for r in catalog["rows"]}
    extra_rent = sorted((str(r.get("STATBL_ID", "")), str(r.get("STATBL_NM", "")))
                        for r in catalog["rows"] if "아파트" in str(r.get("STATBL_NM", ""))
                        and "전세" in str(r.get("STATBL_NM", ""))
                        and ("평균" in str(r.get("STATBL_NM", ""))
                             or "중위" in str(r.get("STATBL_NM", ""))))
    report.append("CATALOG rental candidate IDs: " +
                  (", ".join(safe_text(code) for code, _ in extra_rent[:20]) or "not identified"))
    if not catalog["rows"]:
        report.append("NOTE: No catalog rows: cannot infer any table's metadata end-year.")
    report.append("")
    for label, stat_id in TABLES:
        record = by_id.get(stat_id)
        report.append("## " + label + " / " + stat_id)
        if record is None:
            report.append("METADATA: exact ID not found in returned catalog page")
        else:
            title = str(record.get("STATBL_NM", ""))
            end = safe_text(record.get("DATA_END_YY", ""))
            report.append("METADATA: exact_id_match=yes end_hint=" + end +
                          " rent_in_title=" + str("전세" in title))
        # Compare the existing production end boundary against a +1-year end.
        # The current live source has 2025 in the 2000..2026 query but zero
        # rows from 2025..2025. This is consistent with, not proof of,
        # an exclusive END_WRTTIME year boundary. Verify with 2027 here.
        for desc, lo, hi in (("full_range", "2000", "2026"),
                             ("full_range_plus_one", "2000", "2027"),
                             ("year_2026_plus_one", "2026", "2027")):
            result = requester(api_key, "SttsApiTblData", {
                "STATBL_ID": stat_id, "DTACYCLE_CD": "MM",
                "CLS_ID": "500008", "ITM_ID": "100001",
                "START_WRTTIME": lo, "END_WRTTIME": hi,
            })
            matched = months_of(result["rows"], stat_id)
            responses.append((label, desc, result["status"], matched, result["total"]))
            report.append(desc + " status=" + safe_text(result["status"]) +
                          " total=" + str(result["total"]) +
                          " sample_rows=" + str(len(result["rows"])) +
                          " seoul_months=" + str(len(matched)) +
                          " first=" + (matched[0] if matched else "none") +
                          " last=" + (matched[-1] if matched else "none") +
                          " year_2025=" + str(sum(m.startswith("2025-") for m in matched)) +
                          " year_2026=" + str(sum(m.startswith("2026-") for m in matched)))
            sleeper(0.55)
        report.append("")
    # Strong positive evidence should not be hidden by an unrelated
    # transport failure from another table or diagnostic subquery.
    if any(code == "INFO-000" and any(x.startswith("2026-") for x in months)
           for _, _, code, months, _ in responses):
        state = "2026_OBSERVATIONS_FOUND"
    elif any(code.startswith("TRANSPORT_") for _, _, code, _, _ in responses):
        state = "INCONCLUSIVE_TRANSPORT_ERRORS"
    elif any(code not in ("INFO-000", "INFO-200") for _, _, code, _, _ in responses):
        state = "INCONCLUSIVE_API_STATUS"
    elif all(desc != "full_range" or code == "INFO-000"
             for _, desc, code, _, _ in responses):
        state = "REVIEW_FULL_RANGE_COVERAGE"
    else:
        state = "NO_CONCLUSIVE_PRICE_DATA"
    # Report evidence for an end-year-exclusive boundary (hypothesis only).
    boundary_hints = []
    for label, _ in TABLES:
        old = next(((code, months) for name, desc, code, months, _ in responses
                    if name == label and desc == "full_range"), None)
        new = next(((code, months) for name, desc, code, months, _ in responses
                    if name == label and desc == "full_range_plus_one"), None)
        if old and new and old[0] == "INFO-000" and new[0] == "INFO-000":
            o2026 = {m for m in old[1] if m.startswith("2026-")}
            n2026 = {m for m in new[1] if m.startswith("2026-")}
            if not o2026 and n2026:
                boundary_hints.append(label)
    report.append("END_YEAR_BOUNDARY_SUSPECTED: " +
                  (", ".join(boundary_hints) if boundary_hints else "not demonstrated"))
    report.insert(2, "AUDIT_STATUS: " + state)
    report.extend(["",
                   "Notes:",
                   "- INFO-200 is a no-rows result for THAT request, not proof data never existed.",
                   "- Compare 2000..2026 with 2000..2027 to assess END_WRTTIME exclusivity.",
                   "- Catalog end-year is a hint, not reliable proof of last monthly observation.",
                   "- Rent table IDs remain candidates until exact Seoul/metric/unit rows validated.",
                   "- Cached 2025 data does not make a new 2025 query automatically successful."])
    return "\n".join(report) + "\n"


def main():
    key = os.environ.get("REB_API_KEY", "").strip()
    if not key:
        raise SystemExit("Missing REB_API_KEY")
    text = run_probe(key)
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)


if __name__ == "__main__":
    main()
