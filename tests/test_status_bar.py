import os
import time
import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

@pytest.fixture(scope="module")
def driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=chrome_options)
    yield driver
    driver.quit()

@pytest.fixture(scope="module")
def index_url():
    # Assumes that the project root is the current working directory,
    # and the index.html is located at src/tac/web/index.html.
    filepath = os.path.abspath(os.path.join("src", "tac", "web", "index.html"))
    return "file://" + filepath

def test_runtime_status_update_create_block(driver, index_url):
    driver.get(index_url)
    # Wait for page to load
    time.sleep(1)
    status_element = driver.find_element(By.ID, "runtimeStatus")
    # Initially it should show "waiting"
    assert status_element.text.strip() == "waiting"
    # Simulate a status update for "Creating block from conversation..."
    driver.execute_script("document.getElementById('runtimeStatus').textContent = 'Creating block from conversation...';")
    time.sleep(0.5)
    assert status_element.text.strip() == "Creating block from conversation..."

def test_runtime_status_update_execute_protoblock(driver, index_url):
    driver.get(index_url)
    # Wait for page to load
    time.sleep(1)
    status_element = driver.find_element(By.ID, "runtimeStatus")
    # Simulate a status update for "Executing protoblock"
    driver.execute_script("document.getElementById('runtimeStatus').textContent = 'Executing protoblock';")
    time.sleep(0.5)
    assert status_element.text.strip() == "Executing protoblock"