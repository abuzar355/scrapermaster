import time
import streamlit as st
from streamlit_tags import st_tags_sidebar
import pandas as pd
import json
from datetime import datetime
from scraper import fetch_html_selenium, save_raw_data, format_data, save_formatted_data, calculate_price, html_to_markdown_with_readability, create_dynamic_listing_model, create_listings_container_model,setup_selenium
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException

# Load URL and Tags Mapping from a Separate File
def load_url_tags_mapping():
    with open('url_tag_mapping.json', 'r') as file:
        return json.load(file)

url_tags_mapping = load_url_tags_mapping()

# Extract URLs and Display Names for the Dropdown
url_options = [""] + list(url_tags_mapping.keys()) + ["Custom URL"]

# Initialize Streamlit App
st.set_page_config(page_title="Universal Web Scraper")
st.title("Universal Web Scraper 🦑")

# Sidebar components
st.sidebar.title("Web Scraper Settings")
model_selection = st.sidebar.selectbox("Select Model", options=["gpt-4o-mini", "gpt-4o-2024-08-06"], index=0)

# Ensure 'tags_input' is initialized in session state
if 'tags_input' not in st.session_state:
    st.session_state['tags_input'] = []

# URL Dropdown
selected_url_key = st.sidebar.selectbox("Select Website", options=url_options, index=0)

# Check if the selected URL has changed or if it's the first selection
if selected_url_key and selected_url_key != "Custom URL" and selected_url_key != "":
    if 'last_selected_url' not in st.session_state or st.session_state['last_selected_url'] != selected_url_key:
        # Update tags based on the selected URL
        st.session_state['tags_input'] = url_tags_mapping[selected_url_key]["tags"]

    # Save the current URL as the last selected one
    st.session_state['last_selected_url'] = selected_url_key
else:
    # If "Custom URL" or no URL is selected, allow for custom tags
    st.session_state['tags_input'] = []

tags = st_tags_sidebar(
    label='Fields to Extract:',
    text='Press enter to add a tag',
    value=st.session_state['tags_input'],  # Use session state for tags
    suggestions=[],
    maxtags=-1,
    key='tags_input'
)

# If "Custom URL" is selected, show an input field to allow entering a new URL
if selected_url_key == "Custom URL":
    url_input = st.sidebar.text_input("Enter Custom URL")
    tags = st_tags_sidebar(
        label='Enter Fields to Extract:',
        text='Press enter to add a tag',
        value=[],  # Default value for custom URLs
        suggestions=[],  # No suggestions for custom URLs
        maxtags=-1,
        key='custom_tags_input'  # Use a unique key for custom URL input
    )
elif selected_url_key and selected_url_key != "":
    # Automatically populate URL and tags based on selection
    url_input = url_tags_mapping[selected_url_key]["url"]
    tags = st_tags_sidebar(
        label='Fields to Extract:',
        text='Press enter to add a tag',
        value=st.session_state['tags_input'],  # Tags based on the selected URL
        suggestions=[],  # No suggestions for predefined URLs
        maxtags=-1,
        key=f'tags_input_{selected_url_key}'  # Use a unique key based on the selected URL
    )
else:
    # If no URL is selected or it's an empty string
    url_input = ""
    tags = st_tags_sidebar(
        label='Enter Fields to Extract:',
        text='Press enter to add a tag',
        value=[],  # No tags by default when no URL is selected
        suggestions=[],  # No suggestions
        maxtags=-1,
        key='default_tags_input'  # Unique key for empty/default state
    )


# Process tags into a list
fields = tags

# Initialize variables to store token and cost information
input_tokens = output_tokens = total_cost = 0  # Default values

# Define the scraping function
def perform_scrape():
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    raw_html = fetch_html_selenium(url_input)
    markdown = html_to_markdown_with_readability(raw_html)
    save_raw_data(markdown, timestamp)
    DynamicListingModel = create_dynamic_listing_model(fields)
    DynamicListingsContainer = create_listings_container_model(DynamicListingModel)
    formatted_data = format_data(markdown, DynamicListingsContainer)
    formatted_data_text = json.dumps(formatted_data.dict())
    input_tokens, output_tokens, total_cost = calculate_price(markdown, formatted_data_text, model=model_selection)
    df = save_formatted_data(formatted_data, timestamp)

    return df, formatted_data, markdown, input_tokens, output_tokens, total_cost, timestamp


def perform_scrape_cecconi():
    driver = setup_selenium()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    try:
        # Open the Cecconi page
        driver.get(url_input)
        time.sleep(3)  # Give time for the page to load

        # Find all the ads (divs) with the class 'promo promo-type-vehicle' and 'promo promo-type-incentive'
        ads = driver.find_elements(By.CSS_SELECTOR, ".promo.promo-type-vehicle, .promo.promo-type-incentive")

        all_ads_html = []

        for ad in ads:
            # Extract the full ad's HTML content
            ad_html = ad.get_attribute("outerHTML")

            # Click the 'Offer Details and Disclaimers' button to open the modal/popup
            button = ad.find_element(By.CSS_SELECTOR, 'button[data-title="Offer Details and Disclaimers"]')
            driver.execute_script("arguments[0].scrollIntoView();", button)  # Scroll into view
            time.sleep(1)  # Add a small delay to ensure it's in view
            driver.execute_script("arguments[0].click();", button)

            # Wait for the modal dialog to appear
            WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, '.modal-dialog'))
            )
            
            # Scrape the modal's HTML content
            modal = driver.find_element(By.CSS_SELECTOR, '.modal-dialog')
            modal_html = modal.get_attribute("outerHTML")

            # Combine the ad's HTML and the modal's HTML
            full_ad_html = ad_html + modal_html

            # Append the full ad + modal HTML to the list
            all_ads_html.append(full_ad_html)

            # Close the modal dialog
            close_button = driver.find_element(By.CSS_SELECTOR, 'button.close[aria-label="Close"]')
            driver.execute_script("arguments[0].click();", close_button)

            time.sleep(1)  # Pause briefly between ads

        # Combine all ads' HTML content into a single block
        all_ads_content = "\n".join(all_ads_html)

        # Convert the ads' HTML content to Markdown
        ads_markdown = html_to_markdown_with_readability(all_ads_content)

        # Save the raw HTML and markdown content for future use
        save_raw_data(ads_markdown, timestamp)

        # Use dynamic models and process as needed
        DynamicListingModel = create_dynamic_listing_model(fields)
        DynamicListingsContainer = create_listings_container_model(DynamicListingModel)
        formatted_data = format_data(ads_markdown, DynamicListingsContainer)

        formatted_data_text = json.dumps(formatted_data.dict())
        input_tokens, output_tokens, total_cost = calculate_price(ads_markdown, formatted_data_text, model=model_selection)
        df = save_formatted_data(formatted_data, timestamp)

        return df, formatted_data, ads_markdown, input_tokens, output_tokens, total_cost, timestamp

    finally:
        driver.quit()


def perform_scrape_towne():
    driver = setup_selenium()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    try:
        # Open the Towne page
        driver.get(url_input)
        time.sleep(3)  # Give time for the page to load

        # Find all the ads (divs) with the class 'special-offer'
        ads = driver.find_elements(By.CSS_SELECTOR, ".special-offer.card")

        all_ads_html = []

        for ad in ads:
            # Extract the full ad's HTML content
            ad_html = ad.get_attribute("outerHTML")
            all_ads_html.append(ad_html)

            time.sleep(1)  # Pause briefly between ads

        # Combine all ads' HTML content into a single block
        all_ads_content = "\n".join(all_ads_html)

        # Convert the ads' HTML content to Markdown
        ads_markdown = html_to_markdown_with_readability(all_ads_content)

        # Save the raw HTML and markdown content for future use
        save_raw_data(ads_markdown, timestamp)

        # Use your dynamic models and process as before
        DynamicListingModel = create_dynamic_listing_model(fields)
        DynamicListingsContainer = create_listings_container_model(DynamicListingModel)
        formatted_data = format_data(ads_markdown, DynamicListingsContainer)

        formatted_data_text = json.dumps(formatted_data.dict())
        input_tokens, output_tokens, total_cost = calculate_price(ads_markdown, formatted_data_text, model=model_selection)
        df = save_formatted_data(formatted_data, timestamp)

        return df, formatted_data, ads_markdown, input_tokens, output_tokens, total_cost, timestamp

    finally:
        driver.quit()


def perform_scrape_westherr():
    driver = setup_selenium()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    try:
        # Open the Towne page
        driver.get(url_input)
        time.sleep(3)  # Give time for the page to load

        # Find all the ads (divs) with the class 'special-offer'
        ads = driver.find_elements(By.CSS_SELECTOR, ".row .col-lg-4.col-md-6")

        all_ads_html = []
        wait = WebDriverWait(driver, 20)  # Define WebDriverWait

        for index, ad in enumerate(ads):
          try:
            ad_full_html =""

            # Extract the full ad's HTML content
            ad_html = ad.get_attribute("outerHTML")
            ad_full_html += ad_html  # Append the ad's HTML to the full HTML content
                        # Click 'More Details' button
            more_details_button = ad.find_element(By.LINK_TEXT, "More Details")
            driver.execute_script("window.open(arguments[0].href);", more_details_button)
            driver.switch_to.window(driver.window_handles[-1])

            time.sleep(2)  # Allow page to load

            lease_terms_div = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.col-md-6 > div.border.rounded.bg-slate-50"))
                )         
            lease_terms_html = lease_terms_div.get_attribute("outerHTML")
            ad_full_html += lease_terms_html  # Append the lease terms to the ad's HTML content
            time.sleep(1)  # Pause briefly between ads

            all_ads_html.append(ad_full_html)
            # Locate the "Back to Special Listings" button
            driver.close()

            # Use JavaScript to click the button
            driver.switch_to.window(driver.window_handles[0])

            time.sleep(2)

          except StaleElementReferenceException:
                ads = driver.find_elements(By.CSS_SELECTOR, ".row .col-lg-4.col-md-6")

        # Combine all ads' HTML content into a single block
        all_ads_content = "\n".join(all_ads_html)

        # Convert the ads' HTML content to Markdown
        ads_markdown = html_to_markdown_with_readability(all_ads_content)

        # Save the raw HTML and markdown content for future use
        save_raw_data(ads_markdown, timestamp)

        # Use your dynamic models and process as before
        DynamicListingModel = create_dynamic_listing_model(fields)
        DynamicListingsContainer = create_listings_container_model(DynamicListingModel)
        formatted_data = format_data(ads_markdown, DynamicListingsContainer)

        formatted_data_text = json.dumps(formatted_data.dict())
        input_tokens, output_tokens, total_cost = calculate_price(ads_markdown, formatted_data_text, model=model_selection)
        df = save_formatted_data(formatted_data, timestamp)

        return df, formatted_data, ads_markdown, input_tokens, output_tokens, total_cost, timestamp

    finally:
        driver.quit()


def perform_scrape_northtown():

    driver = setup_selenium()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    try:
        # Open the Cecconi page
        driver.get(url_input)
        time.sleep(3)  # Give time for the page to load

        # Find all the ads (divs) with the class 'promo promo-type-vehicle' and 'promo promo-type-incentive'
        ads = driver.find_elements(By.CSS_SELECTOR, 'div.page-section[data-name="specials-listing-wrapper-1"] .promo.promo-type-vehicle') 

        all_ads_html = []

        for ad in ads:
            # Extract the full ad's HTML content
            ad_html = ad.get_attribute("outerHTML")

            # Click the 'Offer Details and Disclaimers' button to open the modal/popup
            button = ad.find_element(By.CSS_SELECTOR, 'button[data-title="Offer Details and Disclaimers"]')
            driver.execute_script("arguments[0].scrollIntoView();", button)  # Scroll into view
            time.sleep(1)  # Add a small delay to ensure it's in view
            driver.execute_script("arguments[0].click();", button)

            # Wait for the modal dialog to appear
            WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, '.modal-dialog'))
            )
            
            # Scrape the modal's HTML content
            modal = driver.find_element(By.CSS_SELECTOR, '.modal-dialog')
            modal_html = modal.get_attribute("outerHTML")

            # Combine the ad's HTML and the modal's HTML
            full_ad_html = ad_html + modal_html

            # Append the full ad + modal HTML to the list
            all_ads_html.append(full_ad_html)

            # Close the modal dialog
            close_button = driver.find_element(By.CSS_SELECTOR, 'button.close[aria-label="Close"]')
            driver.execute_script("arguments[0].click();", close_button)

            time.sleep(1)  # Pause briefly between ads

        # Combine all ads' HTML content into a single block
        all_ads_content = "\n".join(all_ads_html)

        # Convert the ads' HTML content to Markdown
        ads_markdown = html_to_markdown_with_readability(all_ads_content)

        # Save the raw HTML and markdown content for future use
        save_raw_data(ads_markdown, timestamp)

        # Use dynamic models and process as needed
        DynamicListingModel = create_dynamic_listing_model(fields)
        DynamicListingsContainer = create_listings_container_model(DynamicListingModel)
        formatted_data = format_data(ads_markdown, DynamicListingsContainer)

        formatted_data_text = json.dumps(formatted_data.dict())
        input_tokens, output_tokens, total_cost = calculate_price(ads_markdown, formatted_data_text, model=model_selection)
        df = save_formatted_data(formatted_data, timestamp)

        return df, formatted_data, ads_markdown, input_tokens, output_tokens, total_cost, timestamp

    finally:
        driver.quit()

# Handling button press for scraping
if 'perform_scrape' not in st.session_state:
    st.session_state['perform_scrape'] = False


if st.sidebar.button("Scrape"):
    with st.spinner('Please wait... Data is being scraped.'):
        if selected_url_key == "Cecconi":
            # Call the specific Cecconi scrape logic
            st.session_state['results'] = perform_scrape_cecconi()
        elif selected_url_key == "Towne":
            # Call the specific Cecconi scrape logic
            st.session_state['results'] = perform_scrape_towne()
        elif selected_url_key == "Westherr":
            # Call the specific Cecconi scrape logic
            st.session_state['results'] = perform_scrape_westherr()
        elif selected_url_key == "Northtown":
            # Call the specific Cecconi scrape logic
            st.session_state['results'] = perform_scrape_northtown()
        else:
            # Call the generic scrape logic for other URLs
            st.session_state['results'] = perform_scrape()

        st.session_state['perform_scrape'] = True


if st.session_state.get('perform_scrape'):
    df, formatted_data, markdown, input_tokens, output_tokens, total_cost, timestamp = st.session_state['results']
    # Display the DataFrame and other data
    st.write("Scraped Data:", df)
    st.sidebar.markdown("## Token Usage")
    st.sidebar.markdown(f"**Input Tokens:** {input_tokens}")
    st.sidebar.markdown(f"**Output Tokens:** {output_tokens}")
    st.sidebar.markdown(f"**Total Cost:** :green-background[***${total_cost:.4f}***]")

    # Create columns for download buttons
    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button("Download JSON", data=json.dumps(formatted_data.dict(), indent=4), file_name=f"{timestamp}_data.json")
    with col2:
        data_dict = formatted_data.dict() if hasattr(formatted_data, 'dict') else formatted_data
        first_key = next(iter(data_dict))
        main_data = data_dict[first_key]
        df = pd.DataFrame(main_data)
        st.download_button("Download CSV", data=df.to_csv(index=False), file_name=f"{timestamp}_data.csv")
    with col3:
        st.download_button("Download Markdown", data=markdown, file_name=f"{timestamp}_data.md")

# Ensure that these UI components are persistent and don't rely on re-running the scrape function
if 'results' in st.session_state:
    df, formatted_data, markdown, input_tokens, output_tokens, total_cost, timestamp = st.session_state['results']
