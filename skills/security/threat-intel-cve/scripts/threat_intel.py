#!/usr/bin/env python3
"""Read-only public vulnerability lookups. Python stdlib; no package execution."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

CVE = re.compile(r"CVE-\d{4}-\d{4,}", re.I)
GH_ECOSYSTEMS = {"PyPI": "pip", "npm": "npm", "Go": "go",
                 "crates.io": "rust", "RubyGems": "rubygems",
                 "Maven": "maven", "NuGet": "nuget", "Packagist": "composer"}
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
MAX_BYTES = 40 * 1024 * 1024


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("redirect refused; review source endpoint")


def request(source, url, payload=None, headers=None):
    """Do not follow response-controlled URLs or expose credentials in errors."""
    started = now()
    body = None if payload is None else json.dumps(payload).encode()
    hdr = {"User-Agent": "Semantier-threat-intel-cve/0.1.0",
           "Accept": "application/json", **(headers or {})}
    if body is not None:
        hdr["Content-Type"] = "application/json"
    try:
        req = urllib.request.Request(url, data=body, headers=hdr)
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=25) as res:
            raw = res.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("response exceeds size bound")
            data = json.loads(raw)
            link = res.headers.get("Link", "")
        return {"source": source, "url": url, "retrieved_at": started,
                "status": "ok", "sha256": hashlib.sha256(raw).hexdigest(),
                "has_next_page": 'rel="next"' in link, "data": data}
    except urllib.error.HTTPError as exc:
        return {"source": source, "url": url, "retrieved_at": started,
                "status": "unavailable", "reason": "http_" + str(exc.code)}
    except (urllib.error.URLError, TimeoutError, socket.timeout, ssl.SSLError,
            OSError, ValueError) as exc:
        return {"source": source, "url": url, "retrieved_at": started,
                "status": "unavailable", "reason": type(exc).__name__}


def unavailable(source, reason):
    return {"source": source, "status": "unavailable",
            "retrieved_at": now(), "reason": reason}


def osv_lookup(ecosystem, name, version):
    payload = {"package": {"ecosystem": ecosystem, "name": name}, "version": version}
    receipts, records = [], []
    for _ in range(5):
        receipt = request("osv", "https://api.osv.dev/v1/query", payload)
        receipts.append(receipt)
        if receipt["status"] != "ok":
            return records, receipts, False
        data = receipt["data"]
        if not isinstance(data, dict) or not isinstance(data.get("vulns", []), list):
            receipt["status"] = "invalid_response"
            return records, receipts, False
        records.extend(data.get("vulns", []))
        token = data.get("next_page_token")
        if not token:
            return records, receipts, True
        payload["page_token"] = token
    return records, receipts, False


def github_lookup(ecosystem, name, version, kind):
    if ecosystem not in GH_ECOSYSTEMS:
        return [], [unavailable("github_" + kind, "unsupported_ecosystem")], False
    records, receipts = [], []
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2026-03-10"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    # GitHub defaults exclude malware: always make a separate type=malware query.
    params = {"ecosystem": GH_ECOSYSTEMS[ecosystem], "affects": name + "@" + version,
              "type": kind, "per_page": 100}
    # Stop at the first page; cursor pagination is reported rather than guessed.
    receipt = request("github_" + kind, "https://api.github.com/advisories?" +
                      urllib.parse.urlencode(params), headers=headers)
    receipts.append(receipt)
    if receipt["status"] != "ok" or not isinstance(receipt.get("data"), list):
        if receipt["status"] == "ok":
            receipt["status"] = "invalid_response"
        return records, receipts, False
    records.extend(receipt["data"])
    return records, receipts, not receipt["has_next_page"]


def package_lookup(ecosystem, name, version):
    groups, receipts, coverage = [], [], {}
    records, evidence, complete = osv_lookup(ecosystem, name, version)
    groups.append(("osv", records))
    receipts.extend(evidence)
    coverage["osv"] = complete
    for kind in ("reviewed", "malware"):
        records, evidence, complete = github_lookup(ecosystem, name, version, kind)
        groups.append(("github_" + kind, records))
        receipts.extend(evidence)
        coverage["github_" + kind] = complete
    findings = []
    # Keep source records separate; the agent groups explicit aliases without losing provenance.
    for source, records in groups:
        for record in records:
            if not isinstance(record, dict):
                coverage[source] = False
                continue
            withdrawn = record.get("withdrawn") or record.get("withdrawn_at")
            ident = record.get("id") if source == "osv" else record.get("ghsa_id")
            if not ident:
                coverage[source] = False
                continue
            aliases = record.get("aliases", []) if source == "osv" else [
                x["value"] for x in record.get("identifiers", []) if "value" in x]
            findings.append({
                "id": ident, "aliases": aliases, "source": source,
                "status": "withdrawn" if withdrawn else "reported_affected",
                "kind": "malicious_package" if source == "github_malware" or
                        str(ident).startswith("MAL-") else "vulnerability",
                "applicability": "source_reported_version_match",
                "summary": record.get("summary", ""),
                "record": record})
    return {"mode": "package", "package": {"ecosystem": ecosystem, "name": name,
            "version": version}, "coverage": coverage, "findings": findings,
            "evidence": receipts,
            "interpretation": "No matches is not proof of safety; assess runtime exposure separately."}


def cve_lookup(cve):
    if not CVE.fullmatch(cve):
        raise ValueError("Use a full CVE identifier")
    cve = cve.upper()
    nvd_headers = {}
    if os.environ.get("NVD_API_KEY"):
        nvd_headers["apiKey"] = os.environ["NVD_API_KEY"]
    nvd = request("nvd", "https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=" +
                  cve, headers=nvd_headers)
    kev = request("cisa_kev", KEV_URL)
    epss = request("epss", "https://api.first.org/data/v1/epss?cve=" + cve)
    kev_match = None
    kev_state = "unknown"
    if kev["status"] == "ok":
        data = kev["data"]
        if (isinstance(data, dict) and isinstance(data.get("vulnerabilities"), list)
                and all(isinstance(v, dict) and isinstance(v.get("cveID"), str)
                        for v in data["vulnerabilities"])):
            kev_match = next((v for v in data["vulnerabilities"]
                              if v.get("cveID") == cve), None)
            kev_state = "listed" if kev_match else "not_listed"
        else:
            kev["status"] = "invalid_response"
    nvd_state, epss_state = "unknown", "unknown"
    if nvd["status"] == "ok":
        data = nvd["data"]
        records = data.get("vulnerabilities") if isinstance(data, dict) else None
        if isinstance(records, list) and all(isinstance(v, dict) and
                isinstance(v.get("cve"), dict) for v in records):
            matching = [v["cve"] for v in records if v["cve"].get("id") == cve]
            nvd_state = ("rejected" if matching[0].get("vulnStatus") == "Rejected"
                         else "found") if matching else "not_found"
        else:
            nvd["status"] = "invalid_response"
    if epss["status"] == "ok":
        data = epss["data"]
        records = data.get("data") if isinstance(data, dict) else None
        if isinstance(records, list) and all(isinstance(v, dict) for v in records):
            matching = [v for v in records if v.get("cve") == cve]
            epss_state = "found" if matching else "not_found"
        else:
            epss["status"] = "invalid_response"
    return {"mode": "cve", "id": cve, "kev_status": kev_state,
            "nvd_status": nvd_state, "epss_status": epss_state,
            "kev_entry": kev_match, "evidence": [nvd, kev, epss],
            "interpretation": "KEV absence is not absence of exploitation; EPSS is not asset compromise probability."}


def valid_package(item):
    if not isinstance(item, dict):
        raise ValueError("Each package must be an object")
    for key in ("ecosystem", "name", "version"):
        value = item.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise ValueError("Each package needs bounded ecosystem, name and exact version strings")
        if any(ord(c) < 32 for c in value):
            raise ValueError("Control characters are not allowed")
    if re.search(r"[<>=~^*\s]|\$\{|://", item["version"]):
        raise ValueError("Version must be resolved, not a range, URL or placeholder")
    if not re.fullmatch(r"[A-Za-z0-9@._/+:-]+", item["name"]):
        raise ValueError("Use a registry package name without query separators")
    if item["name"].startswith(("http:", "https:", "file:", "git+")):
        raise ValueError("Use registry package coordinates, not repository URLs")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("package")
    for key in ("ecosystem", "name", "version"):
        p.add_argument("--" + key, required=True)
    inv = sub.add_parser("inventory")
    inv.add_argument("--file", required=True, help="JSON list of public package coordinates")
    for command in (p, inv):
        command.add_argument("--share-package-coordinates", action="store_true",
                             help="Send only the selected public package names and versions to OSV/GitHub")
    c = sub.add_parser("cve")
    c.add_argument("id")
    args = parser.parse_args(argv)
    try:
        if args.mode == "cve":
            result = cve_lookup(args.id)
        else:
            if not args.share_package_coordinates:
                parser.error("Review public coordinates and pass --share-package-coordinates before lookup")
            items = ([{"ecosystem": args.ecosystem, "name": args.name, "version": args.version}]
                     if args.mode == "package" else
                     json.loads(Path(args.file).read_text(encoding="utf-8")))
            if not isinstance(items, list) or not 1 <= len(items) <= 50:
                parser.error("Inventory must be a JSON list of 1 to 50 selected public packages")
            # Validate the entire selection before the first outbound request.
            for item in items:
                valid_package(item)
            result = {"mode": args.mode, "results": [
                package_lookup(i["ecosystem"], i["name"], i["version"]) for i in items]}
        result["schema_version"] = "threat-intel-cve.v1"
        result["generated_at"] = now()
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
