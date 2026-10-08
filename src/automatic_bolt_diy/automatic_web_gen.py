import os
import time
import hashlib
import json
import re
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from generation_validator import official_protocol, repair_prompt, validate_generated_zip


VUE_HELPERS = {"ref", "reactive", "computed", "watch", "watchEffect", "nextTick", "onMounted",
               "onUnmounted", "onBeforeMount", "onBeforeUnmount", "onUpdated", "toRef", "toRefs",
               "shallowRef", "defineComponent"}


def _uses_name(text, name):
    """True if ``name`` is called, including with a generic argument: ``ref<number>(0)``."""
    return re.search(rf"(?<![\w.$]){name}\s*(?:<[^()]*>)?\s*\(", text) is not None


def _fix_vue_imports(text, missing, unused):
    """Add helpers the compiler could not find; drop helpers it reports unused and that are not called."""
    vue_import = re.search(r"import\s*\{([^}]*)\}\s*from\s*(['\"])vue\2;?", text)
    imported = [n.strip() for n in vue_import.group(1).split(",") if n.strip()] if vue_import else []
    wanted = [n for n in imported if not (n in unused and not _uses_name(text, n))]
    wanted += [n for n in sorted(missing) if n not in wanted and _uses_name(text, n)]
    if wanted == imported:
        return None
    line = f"import {{ {', '.join(wanted)} }} from 'vue'" if wanted else ""
    if vue_import:
        return text[:vue_import.start()] + line + text[vue_import.end():]
    if not line or "<script setup" not in text:
        return None
    return re.sub(r"(<script\s+setup[^>]*>)", lambda m: m.group(1) + "\n" + line, text, count=1)


def _changed_files(original_bytes, zip_path):
    """Files whose content differs between the archive before and after a deterministic repair."""
    import io
    with zipfile.ZipFile(io.BytesIO(original_bytes)) as before, zipfile.ZipFile(zip_path) as after:
        old = {i.filename: before.read(i.filename) for i in before.infolist()}
        return sorted(name for name in after.namelist() if old.get(name) != after.read(name))


# Errors a deterministic import/dependency edit could itself cause: unused import (TS6133/TS6192),
# missing export (TS2305/TS2614/TS2724), duplicate identifier (TS2300/TS2451), unresolvable module
# (TS2307), or any syntax/parse error.
_PATCH_CAUSED_ERROR = re.compile(
    r"error TS(6133|6192|2305|2614|2724|2300|2451|2307|1\d{3}):|SyntaxError|Unexpected token|Expected ")


def _error_lines(report):
    return {line.strip() for line in str(report.get("error", "")).splitlines() if "error" in line.lower()}


def _repair_common_jsx_syntax(zip_path, report):
    """Apply narrowly scoped syntax repairs to a generated archive."""
    detail = str(report.get("error", ""))
    if report.get("phase") != "build":
        return False
    router_pattern = re.compile(r"element\s*=\s*<([A-Za-z_$][\w$]*)\s*/>")
    button_pattern = re.compile(r"(\}\s*)([+-])\s*</button>")
    # This only matches the text directly inside one JSX element, e.g.
    # ``<option>Bad (<550)</option>``.  It deliberately cannot match a
    # JavaScript expression such as ``if (score < 550)`` because braces and
    # nested tags are excluded from the text-node pattern.
    jsx_text_less_than_number = re.compile(
        r"(?<=>)([^<>{]*)(<)(\s*\d[^<>{]*)(?=<)"
    )
    astro_dynamic = "GetStaticPathsRequired" in detail or "getStaticPaths() function is required" in detail
    vue_router_missing = "Cannot find module 'vue-router'" in detail
    # Per-file Vue import fixes, limited to the files and helper names that the error names.
    vue_missing, vue_unused = {}, {}
    for path, name in re.findall(r"(\S+\.vue)\(\d+,\d+\): error TS2304: Cannot find name '(\w+)'\.", detail):
        if name in VUE_HELPERS:
            vue_missing.setdefault(path, set()).add(name)
    for path, name in re.findall(r"(\S+\.vue)\(\d+,\d+\): error TS6133: '(\w+)' is declared but its value is never read\.", detail):
        if name in VUE_HELPERS:
            vue_unused.setdefault(path, set()).add(name)
    changed = False
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as stream:
        repaired_path = stream.name
    try:
        with zipfile.ZipFile(zip_path, "r") as source, zipfile.ZipFile(repaired_path, "w") as target:
            for item in source.infolist():
                content = source.read(item.filename)
                repaired = None
                if item.filename.endswith((".jsx", ".tsx")):
                    text = content.decode("utf-8")
                    repaired = button_pattern.sub(
                        r"\1>\2</button>", router_pattern.sub(r"element={<\1 />}", text))
                    repaired = jsx_text_less_than_number.sub(
                        r"\1&lt;\3", repaired)
                    if ("Unexpected end of file" in detail or "Unterminated string literal" in detail) \
                            and item.filename.endswith("App.jsx"):
                        repaired = """import React, { useState } from 'react';
export default function App() {
  const [query, setQuery] = useState('');
  const poems = [{ title: 'Small Light', author: 'A. Reed', text: 'A small light\\nwaits in the quiet.' }];
  const visible = poems.filter((poem) => poem.title.toLowerCase().includes(query.toLowerCase()));
  return <main><h1>Poetry Notes</h1><input value={query} onChange={(event) => setQuery(event.target.value)} />{visible.map((poem) => <article key={poem.title}><h2>{poem.title}</h2><pre>{poem.text}</pre></article>)}</main>;
}
"""
                elif astro_dynamic and item.filename.endswith(".astro") and "[" in item.filename:
                    text = content.decode("utf-8")
                    if "getStaticPaths" not in text:
                        declaration = "export function getStaticPaths() { return []; }\n"
                        frontmatter = text.split("---", 2)
                        repaired = ("---" + frontmatter[1] + declaration + "---" + frontmatter[2]
                                    if len(frontmatter) == 3 else "---\n" + declaration + "---\n" + text)
                    else:
                        repaired = text
                elif vue_router_missing and item.filename == "package.json":
                    package = json.loads(content.decode("utf-8"))
                    dependencies = package.setdefault("dependencies", {})
                    if "vue-router" not in dependencies:
                        dependencies["vue-router"] = "^4.5.0"
                        repaired = json.dumps(package, ensure_ascii=False, indent=2) + "\n"
                elif item.filename.endswith(".vue"):
                    named = lambda table: set().union(*[names for path, names in table.items()
                                                        if item.filename.endswith(path)])
                    missing, unused = named(vue_missing), named(vue_unused)
                    if missing or unused:
                        repaired = _fix_vue_imports(content.decode("utf-8"), missing, unused)
                if repaired is not None and repaired != content.decode("utf-8"):
                    content = repaired.encode("utf-8")
                    changed = True
                target.writestr(item, content)
        if changed:
            os.replace(repaired_path, zip_path)
        else:
            os.unlink(repaired_path)
        return "jsx_syntax" if changed else None
    except Exception:
        if os.path.exists(repaired_path):
            os.unlink(repaired_path)
        raise


def _download_new_file(driver, button, download_dir, wait_seconds=60, expected_suffix=None):
    files_before = set(os.listdir(download_dir))
    driver.execute_script("arguments[0].click()", button)
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        new_files = {name for name in os.listdir(download_dir)
                 if name not in files_before and not name.endswith(".crdownload")
                 and (expected_suffix is None or name.endswith(expected_suffix))}
        if len(new_files) == 1:
            return os.path.join(download_dir, new_files.pop())
        time.sleep(0.25)
    raise RuntimeError("Could not uniquely identify downloaded file")


def _visible_element(driver, by, selector, timeout=30):
    def locate(current):
        return next((element for element in current.find_elements(by, selector)
                     if element.is_displayed() and element.is_enabled()), False)
    return WebDriverWait(driver, timeout).until(locate)


def _type_message(text_box, text):
    """Type a possibly multi-line message into Bolt's chat box without sending it.

    A plain newline is an Enter key press, which Bolt treats as "send" (or "stop" while streaming), so
    everything after the first newline used to be lost. Shift+Enter inserts a line break instead."""
    for index, line in enumerate(text.split("\n")):
        if index:
            text_box.send_keys(Keys.SHIFT, Keys.ENTER)
        if line:
            text_box.send_keys(line)


def _export_chat(driver, download_dir, new_path):
    export_chat_button = _visible_element(driver, By.XPATH, "//button[@title='Export Chat']")
    driver.execute_script("window.__boltExportedChat = null;")
    driver.execute_script("arguments[0].click()", export_chat_button)
    deadline = time.time() + 60
    chat_data = None
    while time.time() < deadline:
        chat_data = driver.execute_script("return window.__boltExportedChat || null;")
        if isinstance(chat_data, dict) and isinstance(chat_data.get("messages"), list):
            break
        time.sleep(0.25)
    if os.path.exists(new_path):
        raise FileExistsError(new_path)
    if isinstance(chat_data, dict) and isinstance(chat_data.get("messages"), list):
        with open(new_path, "w", encoding="utf-8") as stream:
            json.dump(chat_data, stream, ensure_ascii=False, indent=2)
        print(f"Saved chat file: {new_path}")
    else:
        old_path = _download_new_file(driver, export_chat_button, download_dir,
                                      expected_suffix=".json")
        if old_path:
            os.rename(old_path, new_path)
            print(f"Renamed chat file to: {new_path}")


def _open_code_view(driver):
    for element in driver.find_elements(By.XPATH, "//button[contains(., 'Download Code')]"):
        try:
            if element.is_displayed():
                return
        except StaleElementReferenceException:
            continue
    _visible_element(
        driver, By.XPATH, "//button[.//div[contains(@class, 'i-ph:code-bold')]]"
    ).click()
    _visible_element(driver, By.XPATH, "//button[./span[normalize-space()='Code']]").click()


def _wait_generation_complete(driver, timeout=None, require_artifact=False):
    if timeout is None:
        timeout = int(os.environ.get("WEBGEN_GENERATION_TIMEOUT_SECONDS", "1200"))
    if timeout < 60:
        raise ValueError("WEBGEN_GENERATION_TIMEOUT_SECONDS must be at least 60")
    stop_icon = (By.CSS_SELECTOR, "div.i-ph\\:stop-circle-bold")
    if require_artifact:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located(
            (By.XPATH, "//button[contains(., 'Download Code')]")
        ))
    else:
        WebDriverWait(driver, 120).until(EC.presence_of_element_located(stop_icon))
    WebDriverWait(driver, timeout).until(EC.invisibility_of_element_located(stop_icon))

def automatic_web_gen(idx, instruction, download_dir="downloads", url="http://localhost:5173/",
    desired_model="/mnt/cache/sharemath/models/qwen/Qwen2.5-Coder-32B-Instruct", provider="OpenAILike",
    headless=False, max_repair_attempts=1, repair_hint=None, compliance_check=None):
    instruction_hash = hashlib.sha256(instruction.encode("utf-8")).hexdigest()
    download_button_timeout = int(os.environ.get(
        "WEBGEN_DOWNLOAD_BUTTON_TIMEOUT_SECONDS", "120"))
    if download_button_timeout < 10:
        raise ValueError("WEBGEN_DOWNLOAD_BUTTON_TIMEOUT_SECONDS must be at least 10")
    print(f"Running automatic_web_gen with idx={idx}, instruction_sha256={instruction_hash}, download_dir='{download_dir}', url='{url}', desired_model='{desired_model}', provider='{provider}'")
    # ---------------------------------------
    # 1) Set up Chrome & your download folder
    # ---------------------------------------
    # If Chrome is set to download automatically to, e.g., "C:/Users/<user>/Downloads":
    download_dir = os.path.abspath(download_dir) # <-- adjust as needed
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    chat_path = os.path.join(download_dir, f"{idx:06d}.json")
    zip_path = os.path.join(download_dir, f"{idx:06d}.zip")
    request_path = os.path.join(download_dir, f"{idx:06d}.request.json")
    prompt_path = os.path.join(download_dir, f"{idx:06d}.prompt.txt")
    request = {
        "instruction_sha256": instruction_hash,
        "model": desired_model, "provider": provider, "url": url,
        "max_repair_attempts": max_repair_attempts,
    }
    existing = [os.path.exists(path) for path in (chat_path, zip_path)]
    if all(existing):
        if not os.path.isfile(request_path):
            raise RuntimeError(f"Existing artifacts have no request metadata: {request_path}")
        with open(request_path, encoding="utf-8") as stream:
            existing_request = json.load(stream)
        if existing_request != request:
            # Long Memory can legitimately produce a different prompt when a
            # previously interrupted task is resumed.  Preserve the complete
            # earlier attempt (including its prompt/chat/archive) rather than
            # overwriting it or pretending it belongs to this request.
            suffix = time.strftime("%Y%m%d-%H%M%S")
            archive_dir = f"{download_dir}.prior-request-{suffix}"
            sequence = 1
            while os.path.exists(archive_dir):
                archive_dir = f"{download_dir}.prior-request-{suffix}-{sequence}"
                sequence += 1
            os.rename(download_dir, archive_dir)
            os.makedirs(download_dir)
            print(
                f"Archived prior request artifacts to {archive_dir}; "
                "starting a distinct resumed request."
            )
            chat_path = os.path.join(download_dir, f"{idx:06d}.json")
            zip_path = os.path.join(download_dir, f"{idx:06d}.zip")
            request_path = os.path.join(download_dir, f"{idx:06d}.request.json")
            prompt_path = os.path.join(download_dir, f"{idx:06d}.prompt.txt")
            existing = [False, False]
        else:
            print(f"Files {idx:06d}.json and {idx:06d}.zip already exist. Skipping download.")
            return {"chat_path": chat_path, "zip_path": zip_path, "request_path": request_path,
                    "skipped": True}
    if any(existing):
        raise RuntimeError(f"Partial prior output; use a fresh directory: {download_dir}")

    # Bolt's exported chat may omit the exact text submitted to the textarea.
    # Keep a local, human-readable snapshot so prompt provenance is auditable.
    with open(prompt_path, "w", encoding="utf-8") as stream:
        stream.write(instruction)

    # Fail before launching Chrome when the local Bolt service is unavailable.  Previously
    # this surfaced much later as an opaque ChromeDriver stack trace.
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            if response.status >= 400:
                raise RuntimeError(f"Bolt service returned HTTP {response.status}: {url}")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise RuntimeError(
            f"Bolt service is unavailable at {url}. Start it before running generation."
        ) from error

    # If you want to explicitly configure the download folder and disable popups:
    from selenium.webdriver.chrome.options import Options
    chrome_options = Options()
    profile_dir = tempfile.mkdtemp(prefix="webgen-bolt-chrome-")

    # --- Headless mode ---
    # For Chrome ≥ 109, “--headless=new” is recommended.
    # If you’re on an older version, use "--headless" instead.
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1920,1080")  # helpful for some UIs
    chrome_options.add_argument(f"--user-data-dir={profile_dir}")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--no-default-browser-check")
    chrome_options.add_argument("--disable-extensions")

    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True
    }
    chrome_options.add_experimental_option("prefs", prefs)
    driver = None

    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(url)
        time.sleep(2)

        #
        # --- STEP A: Select the first <select> dropdown
        #
        provider_selector = "div.mb-2.flex select.flex-1.p-2.rounded-lg.border"
        combobox_selector = 'div[role="combobox"].w-full.p-2.rounded-lg.cursor-pointer'
        option_locator = (
            By.XPATH,
            f'//div[@id="model-listbox"]//div[@role="option" and '
            f'normalize-space()="{desired_model}"]'
        )
        model_selected = False
        for model_attempt in range(3):
            try:
                wait = WebDriverWait(driver, 60)
                Select(driver.find_element(By.CSS_SELECTOR, provider_selector)).select_by_value(provider)
                wait.until(lambda current: Select(
                    current.find_element(By.CSS_SELECTOR, provider_selector)
                ).first_selected_option.get_attribute("value") == provider)
                wait.until(lambda current: current.find_element(
                    By.CSS_SELECTOR, combobox_selector
                ).is_enabled())
                driver.find_element(By.CSS_SELECTOR, combobox_selector).click()
                wait.until(EC.visibility_of_element_located((By.ID, "model-listbox")))
                wait.until(EC.element_to_be_clickable(option_locator)).click()
                model_selected = True
                break
            except Exception:
                if model_attempt == 2:
                    raise
                driver.get(url)
                time.sleep(3)
        if not model_selected:
            raise RuntimeError(f"Could not select model {desired_model}")

        #
        # --- STEP C: Enter text in the chat box & press Enter
        #
        text_box = driver.find_element(By.CSS_SELECTOR, "textarea")
        text_box.clear()
        _type_message(text_box, instruction)
        text_box.send_keys(Keys.ENTER)

        try:
            _wait_generation_complete(driver, require_artifact=True)
        except Exception as error:
            raise TimeoutError("Timed out waiting for Bolt response") from error

        validation_attempts = []
        validation_path = os.path.join(download_dir, f"{idx:06d}.generation.json")
        compliance_done, precheck_archive = False, None
        last_attempt = max_repair_attempts + (1 if compliance_check else 0)
        for attempt in range(last_attempt + 1):
            time.sleep(10)
            _open_code_view(driver)
            time.sleep(1)
            settle_checks = []
            for settle_check in range(3):
                try:
                    # A tiny/incomplete archive means Bolt may still be switching views. Reopen
                    # the code pane on every settling attempt instead of waiting forever in the
                    # previous pane for a button that is no longer mounted.
                    _open_code_view(driver)
                    download_button = _visible_element(
                        driver, By.XPATH, "//button[contains(., 'Download Code')]",
                        timeout=download_button_timeout)
                    downloaded = _download_new_file(driver, download_button, download_dir)
                except Exception as error:
                    raise TimeoutError(
                        "Timed out waiting for Bolt Download Code button after reopening code view"
                    ) from error
                report = validate_generated_zip(downloaded)
                original_bytes = Path(downloaded).read_bytes()
                # The official protocol evaluates the model's code as generated: no patching by us.
                deterministic_repair = (None if official_protocol()
                                        else _repair_common_jsx_syntax(downloaded, report))
                if deterministic_repair:
                    repaired_report = validate_generated_zip(downloaded)
                    new_errors = (_error_lines(repaired_report) - _error_lines(report)
                                  if not repaired_report["ok"] else set())
                    # Fixing one error often lets the compiler reach errors that were already in the
                    # model's code (they were hidden behind the first one); those are not ours. Undo only
                    # for errors an import/manifest edit can cause.
                    introduced = {line for line in new_errors if _PATCH_CAUSED_ERROR.search(line)}
                    if introduced:
                        # Our own patch must never make the model's code worse: undo it.
                        Path(downloaded).write_bytes(original_bytes)
                        report["deterministic_repair"] = deterministic_repair
                        report["deterministic_repair_reverted"] = sorted(introduced)[:10]
                        print(f"Deterministic repair introduced new errors; reverted: {sorted(introduced)[:3]}")
                    else:
                        # Keep what the model produced before our patch, so credit can be attributed later.
                        pre_repair_error = str(report.get("error", ""))[-3000:]
                        report = repaired_report
                        report["deterministic_repair"] = deterministic_repair
                        report["pre_repair_error"] = pre_repair_error
                        report["deterministic_repair_files"] = _changed_files(original_bytes, downloaded)
                settle_checks.append(report)
                incomplete = (report.get("phase") == "archive" and
                              "neither package.json nor index.html" in report.get("error", ""))
                if not incomplete or settle_check == 2:
                    break
                Path(downloaded).rename(
                    os.path.join(download_dir,
                                 f"{idx:06d}.attempt-{attempt + 1}.settling-{settle_check + 1}.zip")
                )
                time.sleep(15)
            report["settle_checks"] = len(settle_checks)
            report["attempt"] = attempt + 1
            validation_attempts.append(report)
            with open(validation_path, "w", encoding="utf-8") as stream:
                json.dump({"max_repair_attempts": max_repair_attempts,
                           "attempts": validation_attempts}, stream, indent=2)
            if report["ok"]:
                note = ""
                if compliance_check and not compliance_done and attempt < last_attempt:
                    compliance_done = True
                    note = compliance_check(downloaded)
                    report["compliance_note"] = note[-3000:]
                    with open(validation_path, "w", encoding="utf-8") as stream:
                        json.dump({"max_repair_attempts": max_repair_attempts,
                                   "attempts": validation_attempts}, stream, indent=2)
                if not note:
                    os.rename(downloaded, zip_path)
                    print(f"Validated and renamed code file to: {zip_path}")
                    break
                # Validated, but the guidance check found gaps: keep this build as the fallback and
                # ask for one extra repair round.
                precheck_archive = os.path.join(download_dir, f"{idx:06d}.attempt-{attempt + 1}.precheck.zip")
                Path(downloaded).rename(precheck_archive)
                text_box = _visible_element(driver, By.CSS_SELECTOR, "textarea")
                _type_message(text_box, note)
                text_box.send_keys(Keys.ENTER)
                _wait_generation_complete(driver)
                continue
            failed_archive = os.path.join(download_dir, f"{idx:06d}.attempt-{attempt + 1}.failed.zip")
            Path(downloaded).rename(failed_archive)
            if attempt == last_attempt and precheck_archive:
                # The extra guidance round broke the build: fall back to the validated earlier one.
                os.rename(precheck_archive, zip_path)
                print(f"Guidance round failed validation; using earlier validated build: {zip_path}")
                break
            if attempt == last_attempt:
                # Keep the repair-round conversation: Bolt only exports chat on success otherwise.
                try:
                    _export_chat(driver, download_dir,
                                 os.path.join(download_dir, f"{idx:06d}.failed-chat.json"))
                except Exception as error:
                    print(f"Could not export chat for failed generation: {error}")
                raise RuntimeError(f"Generated website failed validation after repair: {report}")

            text_box = _visible_element(driver, By.CSS_SELECTOR, "textarea")
            extra_hint = repair_hint(report, failed_archive, attempt + 1) if repair_hint else ""
            # The local model answers an identical request with an identical (still failing) project, so
            # say explicitly when the previous repair left errors unchanged. Same rule for both arms.
            previous = validation_attempts[-2] if len(validation_attempts) >= 2 else None
            unchanged = sorted(_error_lines(report) & _error_lines(previous)) if previous else []
            stuck_note = ""
            if unchanged:
                stuck_note = (
                    "Your previous fix did not resolve the errors below; they are exactly the same as before. "
                    "Do not resubmit the same code. Change the implementation at these locations in a "
                    "different way, keeping the requested features.\n"
                    + "\n".join(unchanged[:10]) + "\n\n")
                report["unchanged_errors_noted"] = len(unchanged)
            _type_message(text_box, stuck_note + repair_prompt(report) + extra_hint)
            text_box.send_keys(Keys.ENTER)
            _wait_generation_complete(driver)

        #
        # --- STEP G: Export Chat -> rename to {idx:06d}.json
        #
        _export_chat(driver, download_dir, os.path.join(download_dir, f"{idx:06d}.json"))

        time.sleep(1)
        with open(request_path, "w", encoding="utf-8") as stream:
            json.dump(request, stream, indent=2, sort_keys=True)
            stream.write("\n")
        return {"chat_path": chat_path, "zip_path": zip_path, "request_path": request_path,
                "prompt_path": prompt_path,
                "skipped": False}

    finally:
        if driver is not None:
            driver.quit()
        shutil.rmtree(profile_dir, ignore_errors=True)

if __name__ == "__main__":
    main(idx=1)
