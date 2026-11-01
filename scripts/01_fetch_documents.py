#!/usr/bin/env python3
"""①入手: 一覧 CSV の url 列にある HTML・PDF を保存する（税大論叢の各論文の HTML、税大ジャーナルの PDF）。
保存名は url の SHA-1。"""

import argparse
import csv
import hashlib
import mimetypes
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


SOURCE_SLUGS = {
    "税大論叢": "nta_ronsou",
    "税大ジャーナル": "nta_journal",
    "日税研論集": "jtri_ronshu",
    "税法学": "zeihougaku",
    "租税法研究": "sozeihou_kenkyu"
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0 Safari/537.36"
)


def parse_args():
    parser = argparse.ArgumentParser(description="CSV の url 列から原本を保存する。")
    parser.add_argument("--input", required=True, help="入力 CSV")
    parser.add_argument("--output", required=True, help="出力 CSV")
    parser.add_argument(
        "--raw-root",
        default="raw",
        help="保存先ディレクトリ"
    )
    parser.add_argument("--limit", type=int, default=0, help="先頭から何行処理するか")
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="対象 source_title を絞る。複数回指定可"
    )
    parser.add_argument(
        "--emit-curl-config",
        default="",
        help="取得の代わりに curl -K 用 config を書き出す"
    )
    parser.add_argument("--overwrite", action="store_true", help="既存 raw を再取得する")
    return parser.parse_args()


def slug_for_source(source_title):
    return SOURCE_SLUGS.get(source_title, "misc")


def append_columns(fieldnames):
    result = list(fieldnames)
    for column in [
        "raw_path",
        "raw_format",
        "fetch_status",
        "fetch_http_status",
        "fetch_content_type",
        "fetch_bytes",
        "fetched_at",
        "fetch_error"
    ]:
        if column not in result:
            result.append(column)
    return result


def extension_from(url, content_type):
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix in {".html", ".htm", ".pdf"}:
        return suffix
    if content_type:
        lower = content_type.lower()
        if "pdf" in lower:
            return ".pdf"
        if "html" in lower:
            return ".html"
        guessed = mimetypes.guess_extension(lower.split(";")[0].strip())
        if guessed:
            return guessed
    return ".bin"


def raw_format_for(ext, content_type):
    if ext == ".pdf" or (content_type and "pdf" in content_type.lower()):
        return "pdf"
    if ext in {".html", ".htm"} or (content_type and "html" in content_type.lower()):
        return "html"
    return "binary"


def fetch_url(url):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=45) as response:
        payload = response.read()
        content_type = response.headers.get("Content-Type", "")
        status = getattr(response, "status", 200)
    return payload, content_type, status


def build_cache_path(raw_root, source_title, url, ext):
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return raw_root / slug_for_source(source_title) / f"{digest}{ext}"


def find_existing_raw(raw_root, source_title, url):
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    directory = raw_root / slug_for_source(source_title)
    if not directory.exists():
        return None
    matches = sorted(directory.glob(f"{digest}.*"))
    if not matches:
        return None
    preferred = [path for path in matches if path.suffix.lower() in {".html", ".htm", ".pdf"}]
    if preferred:
        return preferred[0]
    return matches[0]


def filtered_rows(rows, limit, sources):
    selected = rows
    if sources:
        source_set = set(sources)
        selected = [row for row in selected if row.get("source_title") in source_set]
    if limit > 0:
        selected = selected[:limit]
    return selected


def raw_path_for_curl(raw_root, source_title, url):
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix not in {".html", ".htm", ".pdf"}:
        suffix = ".html"
    return build_cache_path(raw_root, source_title, url, suffix)


def write_curl_config(config_path, raw_root, jobs):
    lines = []
    for source_title, url in jobs:
        out_path = raw_path_for_curl(raw_root, source_title, url)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        lines.append(f'url = "{url}"')
        lines.append(f'output = "{out_path}"')
        lines.append(f'user-agent = "{USER_AGENT}"')
        lines.append("")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    raw_root = Path(args.raw_root)
    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = append_columns(reader.fieldnames or [])

    selected_ids = {
        row["record_id"] for row in filtered_rows(rows, args.limit, args.source)
    }
    unique_jobs = {}
    for row in rows:
        if selected_ids and row["record_id"] not in selected_ids:
            continue
        url = (row.get("url") or "").strip()
        if not url:
            continue
        key = (row.get("source_title", ""), url)
        unique_jobs.setdefault(key, row)

    if args.emit_curl_config:
        write_curl_config(Path(args.emit_curl_config), raw_root, unique_jobs.keys())
        print(
            f"wrote_curl_config={args.emit_curl_config} unique_urls={len(unique_jobs)}",
            file=sys.stderr
        )
        return

    cache = {}
    ok_count = 0
    fail_count = 0
    skip_count = 0

    for (source_title, url), row in unique_jobs.items():
        try:
            cache_key = (source_title, url)
            if cache_key in cache:
                continue
            existing_raw = find_existing_raw(raw_root, source_title, url)
            if existing_raw and existing_raw.stat().st_size > 0 and not args.overwrite:
                cache[cache_key] = {
                    "raw_path": str(existing_raw),
                    "raw_format": raw_format_for(existing_raw.suffix.lower(), ""),
                    "fetch_status": "cached",
                    "fetch_http_status": "",
                    "fetch_content_type": "",
                    "fetch_bytes": str(existing_raw.stat().st_size),
                    "fetched_at": "",
                    "fetch_error": ""
                }
                skip_count += 1
                continue
            provisional_ext = extension_from(url, "")
            raw_path = build_cache_path(raw_root, source_title, url, provisional_ext)
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            if raw_path.exists() and raw_path.stat().st_size > 0 and not args.overwrite:
                cache[cache_key] = {
                    "raw_path": str(raw_path),
                    "raw_format": raw_format_for(raw_path.suffix.lower(), ""),
                    "fetch_status": "cached",
                    "fetch_http_status": "",
                    "fetch_content_type": "",
                    "fetch_bytes": str(raw_path.stat().st_size),
                    "fetched_at": "",
                    "fetch_error": ""
                }
                skip_count += 1
                continue
            payload, content_type, http_status = fetch_url(url)
            ext = extension_from(url, content_type)
            final_path = build_cache_path(raw_root, source_title, url, ext)
            if final_path != raw_path and raw_path.exists():
                raw_path.unlink()
            final_path.parent.mkdir(parents=True, exist_ok=True)
            final_path.write_bytes(payload)
            cache[cache_key] = {
                "raw_path": str(final_path),
                "raw_format": raw_format_for(ext, content_type),
                "fetch_status": "ok",
                "fetch_http_status": str(http_status),
                "fetch_content_type": content_type,
                "fetch_bytes": str(len(payload)),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "fetch_error": ""
            }
            ok_count += 1
        except HTTPError as exc:
            cache[(source_title, url)] = {
                "raw_path": "",
                "raw_format": "",
                "fetch_status": "http_error",
                "fetch_http_status": str(exc.code),
                "fetch_content_type": "",
                "fetch_bytes": "0",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "fetch_error": str(exc)
            }
            fail_count += 1
        except URLError as exc:
            cache[(source_title, url)] = {
                "raw_path": "",
                "raw_format": "",
                "fetch_status": "url_error",
                "fetch_http_status": "",
                "fetch_content_type": "",
                "fetch_bytes": "0",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "fetch_error": str(exc)
            }
            fail_count += 1
        except Exception as exc:
            cache[(source_title, url)] = {
                "raw_path": "",
                "raw_format": "",
                "fetch_status": "error",
                "fetch_http_status": "",
                "fetch_content_type": "",
                "fetch_bytes": "0",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "fetch_error": str(exc)
            }
            fail_count += 1

    written_rows = []
    for row in rows:
        if selected_ids and row["record_id"] not in selected_ids:
            written_rows.append(row)
            continue
        url = (row.get("url") or "").strip()
        if not url:
            row["fetch_status"] = "no_url"
            written_rows.append(row)
            continue
        fetched = cache.get((row.get("source_title", ""), url))
        if fetched:
            row.update(fetched)
        written_rows.append(row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(written_rows)

    print(
        f"unique_urls={len(unique_jobs)} ok={ok_count} cached={skip_count} "
        f"failed={fail_count} output={output_path}",
        file=sys.stderr
    )


if __name__ == "__main__":
    main()
