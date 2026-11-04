import os
import re
from typing import Tuple, Any

try:
    import pyopenms as oms
except Exception:
    oms = None


def resolve_path(p):
    """
    Expand a user-relative filesystem path.

    This helper expands a path that may include a tilde (`~`) into an absolute
    path using the current user's home directory.

    Parameters
    ----------
    p : str
        Input path that may contain `~`.

    Returns
    -------
    str
        Expanded path with user home resolved.

    Notes
    -----
    This function does not validate that the path exists.
    """
    return os.path.expanduser(p)

def get_working_dir(requested=None):
    """
    Project folder used by every route.

    pyMSscreen works on one project folder per running container: the host
    folder UPLOADS_PATH, mounted at BASE_WORKING_DIR (/app/uploads). A folder
    sent by the frontend is ignored, so all routes read and write the same
    place and requests cannot reach other locations on the server.

    Parameters
    ----------
    requested : str, optional
        Folder sent by the frontend; only logged if it differs.

    Returns
    -------
    str
        BASE_WORKING_DIR (read at call time, so tests can override it).
    """
    from app import config
    base = config.BASE_WORKING_DIR
    if requested:
        req = os.path.abspath(os.path.expanduser(str(requested)))
        if req != base:
            print(f"Ignoring requested working directory {requested!r}; using {base}")
    return base


def _parse_json_safely(resp, step_name: str):
    status = getattr(resp, "status_code", None)
    try:
        payload = resp.json()
    except Exception:
        body = (getattr(resp, "text", "") or "").strip()
        snippet = body[:400].replace("\n", "\\n")
        return False, f"{step_name} returned non-JSON (HTTP {status}). Body starts with: {snippet or '<empty>'}"

    if status != 200:
        return False, f"{step_name} failed (HTTP {status}): {payload}"

    # require an explicit success
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return False, f"{step_name} returned unexpected payload: {payload!r}"

    return True, payload

def _post_and_check(step_name: str, url: str, payload: dict) -> Tuple[bool, Any]:
    import requests

    try:
        resp = requests.post(url, json=payload, timeout=None)
    except requests.RequestException as e:
        return False, f"{step_name} request error: {e}"
    return _parse_json_safely(resp, step_name)

def infer_polarity_from_name(path_or_name: str) -> str:
    s = os.path.basename(path_or_name).lower()
    if re.search(r'(?:^|[_\W])(pos|positive)(?:[_\W]|$)', s):
        return "positive"
    if re.search(r'(?:^|[_\W])(neg|negative)(?:[_\W]|$)', s):
        return "negative"
    return "unknown"

def detect_polarity_mzml(path_to_mzml: str) -> str:
    """
    Returns 'positive', 'negative', or 'unknown' by reading mzML metadata.
    Backstops to 'unknown' if pyopenms not available or file unreadable.
    """
    if oms is None:
        return "unknown"
    exp = oms.MSExperiment()
    try:
        oms.MzMLFile().load(path_to_mzml, exp)    
        for sp in exp:
            pol = sp.getInstrumentSettings().getPolarity()
            if pol == oms.IonSource.Polarity.POSITIVE:
                return "positive"
            if pol == oms.IonSource.Polarity.NEGATIVE:
                return "negative"
    except Exception as e:
      print(f"pyOpenMS load failed for {path_to_mzml}: {e}")
    return infer_polarity_from_name(path_to_mzml)



