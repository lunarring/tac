import os
import time
import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By

@pytest.fixture(scope="module")
def driver():
    # You can change the webdriver if needed (e.g., Firefox, Chrome, Edge, etc.)
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    yield driver
    driver.quit()

@pytest.fixture(scope="module")
def index_url():
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../src/tac/web/index.html"))
    return "file://" + path

def test_text_entry_box_exists(driver, index_url):
    driver.get(index_url)
    time.sleep(1)  # wait for the page to load
    text_input = driver.find_element(By.ID, "userInput")
    assert text_input is not None
    # Check that the input box is reasonably large by verifying its height and width
    width = driver.execute_script("return arguments[0].offsetWidth;", text_input)
    height = driver.execute_script("return arguments[0].offsetHeight;", text_input)
    assert width >= 300
    assert height >= 40

def test_cube_properties(driver, index_url):
    driver.get(index_url)
    time.sleep(1)  # wait for Three.js scene to initialize
    # Retrieve cube properties using the global cube variable
    cube_wireframe = driver.execute_script("return window.cube ? window.cube.material.wireframe : null;")
    cube_pos_x = driver.execute_script("return window.cube ? window.cube.position.x : null;")
    assert cube_wireframe is True
    # We repositioned the cube to the right, so expect its x position to be greater than 0.5
    assert cube_pos_x is not None and cube_pos_x > 0.5