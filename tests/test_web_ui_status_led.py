import os
import time
import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By

@pytest.fixture
def driver():
    # Initialize Chrome in headless mode
    options = webdriver.ChromeOptions()
    options.add_argument("headless")
    drv = webdriver.Chrome(options=options)
    yield drv
    drv.quit()

def test_status_indicator(driver):
    # Load the index.html file from the src/tac/web directory
    path = "file://" + os.path.abspath("src/tac/web/index.html")
    driver.get(path)
    time.sleep(1)  # allow time for the page to load and JavaScript to run
    
    # Check initial status (likely offline due to no WS connection)
    led = driver.find_element(By.ID, "statusIndicator")
    assert led.text.strip() == "offline", "Initial LED text should be offline"
    style = led.get_attribute("style")
    assert "red" in style, "Initial LED color should be red"
    
    # Simulate a successful websocket connection by calling onopen()
    driver.execute_script("socket.onopen();")
    time.sleep(0.5)
    led = driver.find_element(By.ID, "statusIndicator")
    assert led.text.strip() == "online", "LED text should change to online on open"
    style = led.get_attribute("style")
    assert "green" in style, "LED color should be green when online"
    
    # Simulate a websocket error by calling onerror()
    driver.execute_script("socket.onerror('error');")
    time.sleep(0.5)
    led = driver.find_element(By.ID, "statusIndicator")
    assert led.text.strip() == "offline", "LED text should revert to offline on error"
    style = led.get_attribute("style")
    assert "red" in style, "LED color should revert to red on error"
    
    # Simulate a websocket closure by calling onclose()
    driver.execute_script("socket.onclose();")
    time.sleep(0.5)
    led = driver.find_element(By.ID, "statusIndicator")
    assert led.text.strip() == "offline", "LED text should remain offline on close"
    style = led.get_attribute("style")
    assert "red" in style, "LED color should remain red on close"
    
if __name__ == "__main__":
    pytest.main()