"""Drive an AirScan/eSCL network scanner (e.g. HP ENVY 5000) directly over HTTP."""

import os
import re
import subprocess
import time
from dataclasses import dataclass

import httpx

ESCL_NS = "http://schemas.hp.com/imaging/escl/2011/05/03"
PWG_NS = "http://www.pwg.org/schemas/2010/12/sm"

# Region is in 1/300 inch, measured from the platen's origin corner (the one marked with the arrow).
DEFAULT_REGION = (0, 0, 1200, 1500)  # 4 x 5 inches
PLATEN_REGION = (0, 0, 2550, 3508)   # whole glass on the HP ENVY 5000 (8.5 x 11.69 in)
PREVIEW_DPI = 75


@dataclass
class Scanner:
    base_url: str

    @classmethod
    def discover(cls) -> "Scanner":
        url = os.getenv("SCANNER_URL")
        if url:
            return cls(url.rstrip("/"))
        host, port = _bonjour_lookup()
        return cls(f"http://{host}:{port}")

    def status(self) -> str:
        r = httpx.get(f"{self.base_url}/eSCL/ScannerStatus", timeout=10)
        r.raise_for_status()
        m = re.search(r"<pwg:State>(\w+)</pwg:State>", r.text)
        return m.group(1) if m else "Unknown"

    def scan(self, dpi: int = 600, region=DEFAULT_REGION) -> bytes:
        x, y, w, h = region
        settings = f"""<?xml version="1.0" encoding="UTF-8"?>
<scan:ScanSettings xmlns:scan="{ESCL_NS}" xmlns:pwg="{PWG_NS}">
  <pwg:Version>2.63</pwg:Version>
  <pwg:ScanRegions><pwg:ScanRegion>
    <pwg:ContentRegionUnits>escl:ThreeHundredthsOfInches</pwg:ContentRegionUnits>
    <pwg:XOffset>{x}</pwg:XOffset><pwg:YOffset>{y}</pwg:YOffset>
    <pwg:Width>{w}</pwg:Width><pwg:Height>{h}</pwg:Height>
  </pwg:ScanRegion></pwg:ScanRegions>
  <pwg:InputSource>Platen</pwg:InputSource>
  <scan:ColorMode>RGB24</scan:ColorMode>
  <scan:XResolution>{dpi}</scan:XResolution><scan:YResolution>{dpi}</scan:YResolution>
  <pwg:DocumentFormat>image/jpeg</pwg:DocumentFormat>
  <scan:DocumentFormatExt>image/jpeg</scan:DocumentFormatExt>
  <scan:Intent>Photo</scan:Intent>
</scan:ScanSettings>"""
        r = httpx.post(
            f"{self.base_url}/eSCL/ScanJobs",
            content=settings.encode(),
            headers={"Content-Type": "text/xml"},
            timeout=30,
        )
        if r.status_code == 503:
            raise RuntimeError("Scanner is busy. Wait for it to finish and try again.")
        r.raise_for_status()
        job = r.headers["Location"]
        if job.startswith("/"):
            job = self.base_url + job
        # 1200 dpi scans can take several minutes on this class of printer.
        for attempt in range(3):
            doc = httpx.get(f"{job}/NextDocument", timeout=600)
            if doc.status_code == 200:
                return doc.content
            if doc.status_code == 503:
                time.sleep(2)
                continue
            doc.raise_for_status()
        raise RuntimeError("Scanner did not return an image.")


def _bonjour_lookup(timeout: float = 4.0):
    """Find the first eSCL scanner on the local network via dns-sd (macOS)."""
    browse = _run_dns_sd(["-B", "_uscan._tcp", "local."], timeout)
    names = re.findall(r"_uscan\._tcp\.\s+(.+)$", browse, re.M)
    if not names:
        raise RuntimeError("No network scanner found. Is the printer on and on the same Wi-Fi?")
    resolved = _run_dns_sd(["-L", names[0].strip(), "_uscan._tcp", "local."], timeout)
    m = re.search(r"can be reached at (\S+?)\.?:(\d+)", resolved)
    if not m:
        raise RuntimeError(f"Could not resolve scanner {names[0]!r}.")
    return m.group(1), int(m.group(2))


def _run_dns_sd(args, timeout):
    proc = subprocess.Popen(["dns-sd", *args], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    time.sleep(timeout)
    proc.terminate()
    out, _ = proc.communicate()
    return out
