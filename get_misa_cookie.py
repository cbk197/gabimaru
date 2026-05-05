import sqlite3
import json
import shutil
import tempfile
from pathlib import Path

domain = "amisapp.misa.vn"   # change this


# ── helpers ────────────────────────────────────────────────────────────────────

def get_firefox_cookies(domain: str) -> list[dict]:
    """Return MISA cookies from the first Firefox profile that has them."""
    profiles_root = Path.home() / "Library/Application Support/Firefox/Profiles"
    if not profiles_root.exists():
        return []

    for profile in profiles_root.iterdir():
        db = profile / "cookies.sqlite"
        if not db.exists():
            continue

        temp_db = Path(tempfile.gettempdir()) / "ff_cookies_copy.sqlite"
        shutil.copy2(db, temp_db)

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT host, name, value, path, expiry, isSecure, isHttpOnly
            FROM moz_cookies
            WHERE host LIKE ?
            """,
            (f"%{domain}%",),
        )
        rows = cursor.fetchall()
        conn.close()

        if rows:
            print(f"[Firefox] Found {len(rows)} cookies in: {db}")
            return [
                {
                    "host": r[0],
                    "name": r[1],
                    "value": r[2],
                    "path": r[3],
                    "expiry": r[4],
                    "secure": bool(r[5]),
                    "httpOnly": bool(r[6]),
                }
                for r in rows
            ]

    return []


# ── main ───────────────────────────────────────────────────────────────────────

cookies = get_firefox_cookies(domain)

if not cookies:
    raise RuntimeError(
        f"No MISA cookies found for '{domain}' in Firefox. "
        "Please log in to the MISA portal in Firefox first."
    )

with open("cookies.json", "w", encoding="utf-8") as f:
    json.dump(cookies, f, indent=2)

print(f"[Firefox] Exported {len(cookies)} cookies to cookies.json")