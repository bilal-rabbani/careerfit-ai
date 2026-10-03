import collections
import json
import os
import threading
import time

from graph import graph_a, graph_b
from graph.graph_a import ParseFailed
from graph.graph_b import AnalyzeFailed
from llm import router
from utils.cache import PARSE_CACHE
from utils.extract import ExtractionError, prepare_pasted


def _record(case, parsed, outcome, requests, elapsed):
    dump = lambda m: m.model_dump(mode="json")
    return {"case_id": case["id"], "requests": requests, "elapsed": round(elapsed, 1),
            "parsed_jd": dump(parsed.jd), "results": [dump(r) for r in outcome.results],
            "keywords": dump(outcome.keywords), "suggestions": [dump(s) for s in outcome.suggestions],
            "markdown": outcome.markdown, "warnings": parsed.warnings + outcome.warnings}


def run_eval(cases, keys, out_dir, only=None, pause=20, force=False):
    """Runs the real pipeline per case and saves one JSON file each. Resumable."""
    os.makedirs(out_dir, exist_ok=True)
    PARSE_CACHE.clear()
    counts, lock, real = collections.Counter(), threading.Lock(), router._raw_call

    def counting(cfg, system, user):          # counts HTTP requests, never logs keys or text
        with lock:
            counts["n"] += 1
        return real(cfg, system, user)

    router._raw_call = counting
    done, failed, stopped = [], [], False
    try:
        for case in cases:
            cid = case["id"]
            if only and cid not in only:
                continue
            path = f"{out_dir}/{cid}.json"
            if os.path.exists(path) and not force:
                print(f"[skip]   {cid} (already done)")
                continue
            counts.clear()
            t0 = time.time()
            try:
                jd, cv = prepare_pasted(case["jd"], "jd"), prepare_pasted(case["cv"], "cv")
                parsed = graph_a.parse_documents(jd.text, cv.text, keys)
                outcome = graph_b.analyze(parsed.jd, parsed.cv, cv.text, keys)
            except (ExtractionError, ParseFailed, AnalyzeFailed) as e:
                msg = str(e)
                print(f"[FAILED] {cid}: {msg[:300]}")
                failed.append(cid)
                if "All keys failed" in msg:
                    print("\nRate limits or bad keys stopped the run. Wait a few minutes and re-run this cell. "
                          "Finished cases are kept.")
                    stopped = True
                    break
                continue
            except Exception as e:
                print(f"[FAILED] {cid}: unexpected {type(e).__name__}")
                failed.append(cid)
                continue
            elapsed = time.time() - t0
            with open(path, "w") as f:
                json.dump(_record(case, parsed, outcome, counts["n"], elapsed), f, indent=1)
            done.append(cid)
            print(f"[ok]     {cid}: {counts['n']} requests, {elapsed:.0f}s, "
                  f"{len(outcome.results)} requirements, {len(outcome.suggestions)} suggestion(s)")
            if counts["n"] and pause:
                time.sleep(pause)
    finally:
        router._raw_call = real
    return done, failed, stopped


def load_records(out_dir):
    out = {}
    if os.path.isdir(out_dir):
        for fn in os.listdir(out_dir):
            if fn.endswith(".json"):
                with open(f"{out_dir}/{fn}") as f:
                    out[fn[:-5]] = json.load(f)
    return out
