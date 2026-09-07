"""Local, model-free validation for a generated Bolt web application."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run(command: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True,
                          timeout=timeout, check=False)


def validate_generated_zip(zip_path: str | Path) -> dict:
    """Return a compact validation report without calling an LLM."""
    archive = Path(zip_path)
    with tempfile.TemporaryDirectory(prefix="webgen-validate-") as temp:
        app_dir = Path(temp)
        try:
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(app_dir)
        except Exception as error:
            return {"ok": False, "phase": "archive", "error": str(error)}

        package_path = app_dir / "package.json"
        port = _free_port()
        if package_path.is_file():
            try:
                package = json.loads(package_path.read_text(encoding="utf-8"))
            except Exception as error:
                return {"ok": False, "phase": "archive", "error": f"invalid package.json: {error}"}

            install = _run(["npm", "install", "--ignore-scripts"], app_dir, 300)
            if install.returncode:
                detail = (install.stderr or install.stdout)[-4000:]
                return {"ok": False, "phase": "install", "error": detail}

            scripts = package.get("scripts", {})
            if "build" in scripts:
                build = _run(["npm", "run", "build"], app_dir, 180)
                if build.returncode:
                    detail = (build.stderr or build.stdout)[-4000:]
                    return {"ok": False, "phase": "build", "error": detail}

            script = "dev" if "dev" in scripts else "start" if "start" in scripts else None
            if script is None:
                return {"ok": False, "phase": "start", "error": "no dev or start script"}
            command = ["npm", "run", script]
            if script == "dev":
                command += ["--", "--host", "127.0.0.1", "--port", str(port)]
        elif (app_dir / "index.html").is_file():
            command = [sys.executable, "-m", "http.server", str(port),
                       "--bind", "127.0.0.1"]
        else:
            return {"ok": False, "phase": "archive",
                    "error": "neither package.json nor index.html is present"}
        environment = dict(os.environ, PORT=str(port))
        process_log = tempfile.TemporaryFile(mode="w+")
        process = subprocess.Popen(command, cwd=app_dir, text=True, stdout=process_log,
                                   stderr=subprocess.STDOUT, env=environment)
        try:
            time.sleep(2)
            process_log.seek(0)
            startup_output = process_log.read()
            if process.poll() is not None:
                return {"ok": False, "phase": "start", "error": startup_output[-4000:]}
            match = re.search(r"https?://(?:localhost|127\.0\.0\.1):(\d+)", startup_output)
            browser_port = int(match.group(1)) if match else port

            options = Options()
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1024,768")
            driver = webdriver.Chrome(options=options)
            try:
                driver.get(f"http://127.0.0.1:{browser_port}/")
                time.sleep(1)
                height = driver.execute_script("return document.body && document.body.scrollHeight") or 0
                body_size = driver.execute_script(
                    "return document.body?.innerHTML.length || 0"
                )
                severe = [entry["message"] for entry in driver.get_log("browser")
                          if entry.get("level") == "SEVERE" and "favicon.ico" not in entry["message"]]
                if height <= 0 or body_size <= 0 or severe:
                    return {"ok": False, "phase": "runtime", "error": "\n".join(severe[-8:])
                            or f"page did not render (height={height}, body_size={body_size})"}
            finally:
                driver.quit()
        except Exception as error:
            return {"ok": False, "phase": "runtime", "error": str(error)}
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            process_log.close()

        return {"ok": True, "phase": "complete"}


def repair_prompt(report: dict) -> str:
    """Create a factual repair request from a failed local validation report."""
    detail = str(report.get("error", "unknown validation error"))[-5000:]
    guidance = ""
    if report.get("phase") == "build" and ("Expected identifier" in detail
                                             or "Transform failed" in detail
                                             or ".jsx" in detail):
        guidance = (
            "This is a JSX syntax failure. Escape literal comparison characters in JSX text, "
            "for example write '&lt;600' instead of '<600' and '&gt;600' instead of '>600'. "
            "Do not leave raw '<' or '>' followed by digits or identifier text inside JSX text.\n\n"
        )
        if "element=" in detail or "Expected \"{\"" in detail:
            guidance += (
                "For React Router routes, edit the source file directly and fix EVERY route "
                "with this exact rule: replace `element=<Component />` with "
                "`element={<Component />}`. For example, the exact corrected line is "
                "`<Route path=\"/\" element={<Leads />} />`; do not return until all route "
                "lines use curly braces around their component JSX.\n\n"
            )
    if "GetStaticPathsRequired" in detail or "getStaticPaths() function is required" in detail:
        guidance += (
            "This is an Astro dynamic-route build failure. The named file contains a route "
            "like src/pages/companies/[id].astro and must export getStaticPaths for a static "
            "build. Add an exported async function such as "
            "`export async function getStaticPaths() { return []; }` using the available "
            "local data when appropriate. Keep the existing page UI and route behavior; do "
            "not just delete the dynamic route.\n\n"
        )
    if "Unterminated string literal" in detail:
        guidance += (
            "This is an unterminated or truncated JavaScript string. Fix the source directly "
            "and prefer replacing long poetry/prose with a short valid summary or short excerpt; "
            "do not regenerate a full poem. Close the string with the matching delimiter, keep "
            "the surrounding object, array, and component source syntactically complete, and "
            "return a complete non-truncated artifact.\n\n"
        )
    return (
        "The generated website failed automated validation. Fix the existing project in place. "
        "Do not redesign it or remove requested features. Run the appropriate build/start checks "
        "and return the complete corrected artifact.\n\n"
        + guidance
        + f"Failure phase: {report.get('phase', 'unknown')}\nError:\n{detail}"
    )
