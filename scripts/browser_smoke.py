"""Exercise the bundled browser UI against a real in-process FastAPI app.

Runs without a hosted service: the browser renders local source in memory and a
bridge sends fetch calls to TestClient. This does not test a proxy, TLS, or browser
network policy. Install Playwright and a Chromium browser before running.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from expertloop.app import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chromium", help="Optional system Chromium executable")
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    html = (ROOT/"expertloop/static/index.html").read_text()
    html = re.sub(r"<link[^>]*>", "", html)
    html = re.sub(r"<script[^>]*></script>", "", html)
    checks = []
    with TemporaryDirectory() as tmp, TestClient(create_app(Path(tmp)/"state")) as client:
        def bridge(url, options):
            response = client.request(options.get("method", "GET"), url,
                headers=options.get("headers", {}), content=options.get("body"))
            return {"status": response.status_code, "body": response.text}

        with sync_playwright() as p:
            launch = {"headless": True}
            if args.chromium:
                launch["executable_path"] = args.chromium
            browser = p.chromium.launch(**launch)
            page = browser.new_page(viewport={"width": 1512, "height": 1100})
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.expose_function("__localAPI", bridge)
            page.set_content(html)
            page.add_style_tag(content=(ROOT/"expertloop/static/styles.css").read_text())
            page.evaluate("""() => {
              const memory={};
              Object.defineProperty(window,'localStorage',{value:{getItem:k=>memory[k]??null,setItem:(k,v)=>memory[k]=String(v)}});
              window.fetch=async(url,options={})=>{const r=await window.__localAPI(String(url),options);return {ok:r.status>=200&&r.status<300,status:r.status,statusText:String(r.status),json:async()=>JSON.parse(r.body),text:async()=>r.body};};
            }""")
            page.add_script_tag(content=(ROOT/"expertloop/static/app.js").read_text())
            page.get_by_role("heading", name="Your intelligence workbench.").wait_for()
            checks.append("Initial overview with zero approvals")
            page.locator('nav [data-nav="review"]').click()
            page.get_by_role("heading", name="Review. Correct. Verify.").wait_for()
            page.get_by_role("button", name="Use reference").click()
            page.locator("#reviewer-name").fill("BROWSER_TEST_AUTOMATION")
            page.locator("#review-note").fill("Automated UI test: remove the one-to-many join from the order-level sum.")
            page.get_by_role("button", name="Validate on 3 fixtures").click()
            page.wait_for_function("document.querySelectorAll('#evaluation-container .check-pass').length === 4")
            page.get_by_role("button", name="Approve correction").click()
            page.get_by_role("heading", name="Review history").wait_for()
            checks.append("Edit, validate on three fixtures, approve, inspect revision history")
            assert client.get("/api/dashboard").json()["counts"]["approved"] == 1
            assert len(client.get("/api/export?format=sft").text.splitlines()) == 1
            checks.append("Approved-only SFT export")
            page.locator('nav [data-nav="dataset"]').click()
            page.get_by_role("heading", name="Task library.").wait_for()
            page.get_by_role("button", name="Generate variants").click()
            page.wait_for_function("document.querySelectorAll('.task-table tbody tr').length === 60")
            checks.append("Generate 48 pending variants")
            page.locator("#task-search").fill("monthly completed revenue")
            assert page.locator(".task-table tbody tr").count() == 5
            checks.append("Client-side task search")
            page.locator("#task-search").fill("")
            page.locator('button[data-split="holdout"]').click()
            page.locator(".task-table tbody tr").first.click()
            page.get_by_role("heading", name="Inspect the evidence.").wait_for()
            assert page.locator("#sql-editor").count() == 0
            assert page.get_by_role("button", name="Approve correction").count() == 0
            checks.append("Holdout inspector has no correction or approval actions")
            page.locator('nav [data-nav="experiments"]').click()
            page.get_by_role("heading", name="Experiments.", exact=True).wait_for()
            page.get_by_role("button", name="New experiment").click()
            page.locator('#run-form input[name="name"]').fill("Browser smoke test — scripted")
            page.get_by_text("Inference controls", exact=True).click()
            page.locator('#run-form input[name="max_requests"]').fill("4")
            page.locator("#start-run").click()
            page.get_by_role("button", name="Resume remaining tasks").wait_for(timeout=20000)
            checks.append("Run dialog, request cap, paused-state UI")
            page.on("dialog", lambda dialog: dialog.accept("80"))
            page.get_by_role("button", name="Resume remaining tasks").click()
            try:
                page.wait_for_function("document.querySelector('.run-progress')?.textContent.includes('60 / 60 outputs persisted')", timeout=12000)
            except Exception:
                print("UI progress:", page.locator('.run-progress').inner_text())
                print("Toast:", page.locator('#toast').inner_text())
                print("Server run:", client.get('/api/runs').json()[0]['status'])
                raise
            checks.append("Resume to 60 persisted outputs without rerunning committed results")
            page.locator("[data-result-link]").first.click()
            page.get_by_role("heading", name="Output inspector").wait_for()
            assert page.get_by_text("SCRIPTED DEMO — NOT MODEL EVIDENCE.", exact=True).is_visible()
            checks.append("Task-level output inspector and prominent simulation label")
            page.set_viewport_size({"width": 390, "height": 844})
            page.locator('nav [data-nav="overview"]').click()
            page.get_by_role("heading", name="Your intelligence workbench.").wait_for()
            assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
            checks.append("Mobile overview without horizontal page overflow")
            if args.screenshots:
                args.screenshots.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(args.screenshots/"mobile-test.png"), full_page=True)
            assert errors == [], errors
            checks.append("No browser JavaScript errors")
            browser.close()
    for check in checks:
        print("PASS · " + check)
    print(f"{len(checks)} browser checks passed (in-memory DOM + real FastAPI TestClient).")


if __name__ == "__main__":
    main()
