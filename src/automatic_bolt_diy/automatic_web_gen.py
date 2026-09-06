import os
import time
import hashlib
import json
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from generation_validator import repair_prompt, validate_generated_zip


def _download_new_file(driver, button, download_dir, wait_seconds=5):
    files_before = set(os.listdir(download_dir))
    driver.execute_script("arguments[0].click()", button)
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        new_files = {name for name in os.listdir(download_dir)
                     if name not in files_before and not name.endswith(".crdownload")}
        if len(new_files) == 1:
            return os.path.join(download_dir, new_files.pop())
        time.sleep(0.25)
    raise RuntimeError("Could not uniquely identify downloaded file")


def _visible_element(driver, by, selector, timeout=30):
    def locate(current):
        return next((element for element in current.find_elements(by, selector)
                     if element.is_displayed() and element.is_enabled()), False)
    return WebDriverWait(driver, timeout).until(locate)


def _open_code_view(driver):
    downloads = [element for element in driver.find_elements(
        By.XPATH, "//button[contains(., 'Download Code')]"
    ) if element.is_displayed()]
    if downloads:
        return
    _visible_element(
        driver, By.XPATH, "//button[.//div[contains(@class, 'i-ph:code-bold')]]"
    ).click()
    _visible_element(driver, By.XPATH, "//button[./span[normalize-space()='Code']]").click()


def _wait_generation_complete(driver, timeout=1200, require_artifact=False):
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
    headless=False, max_repair_attempts=1):
    instruction_hash = hashlib.sha256(instruction.encode("utf-8")).hexdigest()
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
            raise RuntimeError(f"Existing artifacts belong to a different request: {request_path}")
        print(f"Files {idx:06d}.json and {idx:06d}.zip already exist. Skipping download.")
        return {"chat_path": chat_path, "zip_path": zip_path, "request_path": request_path,
                "skipped": True}
    if any(existing):
        raise RuntimeError(f"Partial prior output; use a fresh directory: {download_dir}")

    # If you want to explicitly configure the download folder and disable popups:
    from selenium.webdriver.chrome.options import Options
    chrome_options = Options()

    # --- Headless mode ---
    # For Chrome ≥ 109, “--headless=new” is recommended.
    # If you’re on an older version, use "--headless" instead.
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1920,1080")  # helpful for some UIs

    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True
    }
    chrome_options.add_experimental_option("prefs", prefs)
    driver = webdriver.Chrome(options=chrome_options)

    try:
        driver.get(url)
        time.sleep(2)

        #
        # --- STEP A: Select the first <select> dropdown
        #
        model_select = Select(driver.find_element(
            By.CSS_SELECTOR, 
            "div.mb-2.flex select.flex-1.p-2.rounded-lg.border"
        ))
        model_select.select_by_value(provider)  

        # --- STEP B: open the custom combobox ---
        combobox = driver.find_element(
            By.CSS_SELECTOR,
            'div[role="combobox"].w-full.p-2.rounded-lg.cursor-pointer'
        )
        combobox.click()

        wait = WebDriverWait(driver, 120)

        # wait until the listbox itself is visible
        wait.until(EC.visibility_of_element_located((By.ID, "model-listbox")))

        # build a locator for the exact option text you want
        option_locator = (
            By.XPATH,
            f'//div[@id="model-listbox"]//div[@role="option" and '
            f'normalize-space()="{desired_model}"]'
        )

        # wait until that option is clickable, then click it
        wait.until(EC.element_to_be_clickable(option_locator)).click()

        #
        # --- STEP C: Enter text in the chat box & press Enter
        #
        text_box = driver.find_element(By.CSS_SELECTOR, "textarea")
        text_box.clear()
        text_box.send_keys(instruction)
        text_box.send_keys(Keys.ENTER)

        try:
            _wait_generation_complete(driver, require_artifact=True)
        except Exception as error:
            raise TimeoutError("Timed out waiting for Bolt response") from error

        validation_attempts = []
        validation_path = os.path.join(download_dir, f"{idx:06d}.generation.json")
        for attempt in range(max_repair_attempts + 1):
            time.sleep(10)
            _open_code_view(driver)
            time.sleep(1)
            settle_checks = []
            for settle_check in range(3):
                downloaded = _download_new_file(
                    driver,
                    WebDriverWait(driver, 30).until(EC.presence_of_element_located(
                        (By.XPATH, "//button[contains(., 'Download Code')]")
                    )),
                    download_dir,
                )
                report = validate_generated_zip(downloaded)
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
                os.rename(downloaded, zip_path)
                print(f"Validated and renamed code file to: {zip_path}")
                break
            Path(downloaded).rename(
                os.path.join(download_dir, f"{idx:06d}.attempt-{attempt + 1}.failed.zip")
            )
            if attempt == max_repair_attempts:
                raise RuntimeError(f"Generated website failed validation after repair: {report}")

            text_box = _visible_element(driver, By.CSS_SELECTOR, "textarea")
            text_box.send_keys(repair_prompt(report))
            text_box.send_keys(Keys.ENTER)
            _wait_generation_complete(driver)

        #
        # --- STEP G: Export Chat -> rename to {idx:06d}.json
        #
        export_chat_button = _visible_element(driver,
            By.XPATH,
            "//button[@title='Export Chat']"
        )
        old_path = _download_new_file(driver, export_chat_button, download_dir)
        if old_path:
            json_name = f"{idx:06d}.json"
            new_path = os.path.join(download_dir, json_name)
            if os.path.exists(new_path):
                raise FileExistsError(new_path)
            os.rename(old_path, new_path)
            print(f"Renamed chat file to: {new_path}")

        time.sleep(1)
        with open(request_path, "w", encoding="utf-8") as stream:
            json.dump(request, stream, indent=2, sort_keys=True)
            stream.write("\n")
        return {"chat_path": chat_path, "zip_path": zip_path, "request_path": request_path,
                "skipped": False}

    finally:
        driver.quit()

if __name__ == "__main__":
    main(idx=1)
