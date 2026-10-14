"""GZIP THE API RESPONSES (2026-10-14).

User: "site takes forever to load I need it to load faster".

MEASURED on the box, uncompressed, with no content-encoding on ANY response even when the client
sends Accept-Encoding: gzip:

    /api/tennis/history        9.06 MB    4.06s cold / 0.70s warm   (lazy -- history tab only)
    /api/tennis/track-record   1.32 MB    0.81s                     (board + dog tab)
    /api/tennis/today          691 KB     0.04s
    the JS bundle              705 KB                               (already immutable-cached)

So a first page load moves about 2.7 MB before the history tab is even opened, and opening it
adds 9 MB. These are JSON and JS: they compress five to ten times.

Server TIME is not the problem -- track-record is 0.81s and today is 0.04s. The bytes are.

GZipMiddleware with minimum_size=1000 so small responses are not wrapped pointlessly. Added
BEFORE the CORS middleware in source order, which in Starlette means it runs OUTSIDE it and
therefore compresses everything including CORS-handled responses.

This changes transport only. No payload, no route and no number is touched.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
s = io.open(P, encoding="utf-8").read()
assert "GZipMiddleware" not in s, "already patched"

OLD = """app = FastAPI(title="MLB Pitcher Matchup Predictor")

app.add_middleware(
    CORSMiddleware,"""
NEW = """app = FastAPI(title="MLB Pitcher Matchup Predictor")

# COMPRESSION (2026-10-14, user "site takes forever to load"). Nothing was compressed, so a first
# load moved ~2.7 MB (bundle 705 KB + /today 691 KB + /track-record 1.32 MB) and the history tab
# added 9.06 MB on top. Server time was never the issue -- track-record answers in 0.81s -- the
# bytes were. These payloads are JSON and compress five to ten times.
#
# minimum_size=1000 so tiny responses are not wrapped for nothing. Declared before CORSMiddleware
# so it sits OUTSIDE it in the stack and compresses those responses too.
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,"""
assert s.count(OLD) == 1, "the app/middleware block was not found"
s = s.replace(OLD, NEW)

# the import, next to the CORS one
if "from fastapi.middleware.cors import CORSMiddleware" in s:
    s = s.replace("from fastapi.middleware.cors import CORSMiddleware",
                  "from fastapi.middleware.cors import CORSMiddleware\n"
                  "from fastapi.middleware.gzip import GZipMiddleware", 1)
else:
    raise AssertionError("could not find the CORSMiddleware import to anchor on")

io.open(P, "w", encoding="utf-8", newline="").write(s)
import ast

ast.parse(s)
print("patched main.py -- syntax OK")
print("   GZipMiddleware refs: %d" % s.count("GZipMiddleware"))
print("RESULT: OK")
