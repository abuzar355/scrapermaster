import os
import time
import re
import json
from datetime import datetime
from typing import List, Dict, Type
from selenium.common.exceptions import StaleElementReferenceException

import pandas as pd
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, create_model
import html2text
import tiktoken

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from openai import OpenAI

load_dotenv()

# Set up the Chrome WebDriver options

def setup_selenium():
    options = Options()

    # adding arguments
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    
    # Randomize user-agent to mimic different users
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    # Specify the path to the ChromeDriver
    service = Service(r"./chromedriver-win64/chromedriver.exe")  

    # Initialize the WebDriver
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def fetch_html_selenium(url):
    driver = setup_selenium()
    try:
        driver.get(url)
        
        # Add random delays to mimic human behavior
        time.sleep(5)  # Adjust this to simulate time for user to read or interact
        
        # Add more realistic actions like scrolling
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)  # Simulate time taken to scroll and read
        
        html = driver.page_source
        return html
    finally:
        driver.quit()

def clean_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove headers and footers based on common HTML tags or classes
    for element in soup.find_all(['header', 'footer']):
        element.decompose()  # Remove these tags and their content

    return str(soup)


def html_to_markdown_with_readability(html_content):

    
    cleaned_html = clean_html(html_content)  
    
    # Convert to markdown
    markdown_converter = html2text.HTML2Text()
    markdown_converter.ignore_links = False
    markdown_content = markdown_converter.handle(cleaned_html)
    
    return markdown_content

# Define the pricing for gpt-4o-mini without Batch API
pricing = {
    "gpt-4o-mini": {
        "input": 0.150 / 1_000_000,  # $0.150 per 1M input tokens
        "output": 0.600 / 1_000_000, # $0.600 per 1M output tokens
    },
    "gpt-4o-2024-08-06": {
        "input": 2.5 / 1_000_000,  # $0.150 per 1M input tokens
        "output": 10 / 1_000_000, # $0.600 per 1M output tokens
    },


    # Add other models and their prices here if needed
}

model_used="gpt-4o-mini"
    
def save_raw_data(raw_data, timestamp, output_folder='output'):
    # Ensure the output folder exists
    os.makedirs(output_folder, exist_ok=True)
    
    # Save the raw markdown data with timestamp in filename
    raw_output_path = os.path.join(output_folder, f'rawData_{timestamp}.md')
    with open(raw_output_path, 'w', encoding='utf-8') as f:
        f.write(raw_data)
    print(f"Raw data saved to {raw_output_path}")
    return raw_output_path


def remove_urls_from_file(file_path):
    # Regex pattern to find URLs
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'

    # Construct the new file name
    base, ext = os.path.splitext(file_path)
    new_file_path = f"{base}_cleaned{ext}"

    # Read the original markdown content
    with open(file_path, 'r', encoding='utf-8') as file:
        markdown_content = file.read()

    # Replace all found URLs with an empty string
    cleaned_content = re.sub(url_pattern, '', markdown_content)

    # Write the cleaned content to a new file
    with open(new_file_path, 'w', encoding='utf-8') as file:
        file.write(cleaned_content)
    print(f"Cleaned file saved as: {new_file_path}")
    return cleaned_content


def create_dynamic_listing_model(field_names: List[str]) -> Type[BaseModel]:
    """
    Dynamically creates a Pydantic model based on provided fields.
    field_name is a list of names of the fields to extract from the markdown.
    """
    # Create field definitions using aliases for Field parameters
    field_definitions = {field: (str, ...) for field in field_names}
    # Dynamically create the model with all field
    return create_model('DynamicListingModel', **field_definitions)


def create_listings_container_model(listing_model: Type[BaseModel]) -> Type[BaseModel]:
    """
    Create a container model that holds a list of the given listing model.
    """
    return create_model('DynamicListingsContainer', listings=(List[listing_model], ...))




def trim_to_token_limit(text, model, max_tokens=200000):
    encoder = tiktoken.encoding_for_model(model)
    tokens = encoder.encode(text)
    if len(tokens) > max_tokens:
        trimmed_text = encoder.decode(tokens[:max_tokens])
        return trimmed_text
    return text

def format_data(data, DynamicListingsContainer):



    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    system_message = """You are an intelligent text extraction and conversion assistant. Your task is to extract structured information 
                        from the given text and convert it into a pure JSON format. The JSON should contain only the structured data extracted from the text, 
                        with no additional commentary, explanations, or extraneous information. Make sure the information matches with correct object and reference should be correct.
                        You could encounter cases where you can't find the data of the fields you have to extract or the data will be in a foreign language.
                        If the Dislaimer data Or Deal Terms paragraph is provided then Make sure to Analayse and Break down the disclaimer or deal terms by making new fields like Disclaimer/Deal Term point 1 and point 2 in seperate fields, Like sepeare pair for every information in that Deal term/disclaimer
                        Please process the following text and provide the output in pure JSON format with no words before or after the JSON:"""

    user_message = f"Extract the following information from the provided text and make points if there is disclaimer:\nPage content:\n\n{data}"

    completion = client.beta.chat.completions.parse(
        model=model_used,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
        response_format=DynamicListingsContainer
    )
    return completion.choices[0].message.parsed
    



def save_formatted_data(formatted_data, timestamp, output_folder='output'):
    # Ensure the output folder exists
    os.makedirs(output_folder, exist_ok=True)
    
    # Prepare formatted data as a dictionary
    formatted_data_dict = formatted_data.dict() if hasattr(formatted_data, 'dict') else formatted_data

    # Save the formatted data as JSON with timestamp in filename
    json_output_path = os.path.join(output_folder, f'sorted_data_{timestamp}.json')
    with open(json_output_path, 'w', encoding='utf-8') as f:
        json.dump(formatted_data_dict, f, indent=4)
    print(f"Formatted data saved to JSON at {json_output_path}")

    # Prepare data for DataFrame
    if isinstance(formatted_data_dict, dict):
        # If the data is a dictionary containing lists, assume these lists are records
        data_for_df = next(iter(formatted_data_dict.values())) if len(formatted_data_dict) == 1 else formatted_data_dict
    elif isinstance(formatted_data_dict, list):
        data_for_df = formatted_data_dict
    else:
        raise ValueError("Formatted data is neither a dictionary nor a list, cannot convert to DataFrame")

    # Create DataFrame
    try:
        df = pd.DataFrame(data_for_df)
        print("DataFrame created successfully.")

        # Save the DataFrame to an Excel file
        excel_output_path = os.path.join(output_folder, f'sorted_data_{timestamp}.xlsx')
        df.to_excel(excel_output_path, index=False)
        print(f"Formatted data saved to Excel at {excel_output_path}")
        
        return df
    except Exception as e:
        print(f"Error creating DataFrame or saving Excel: {str(e)}")
        return None

def calculate_price(input_text, output_text, model=model_used):
    # Initialize the encoder for the specific model
    encoder = tiktoken.encoding_for_model(model)
    
    # Encode the input text to get the number of input tokens
    input_token_count = len(encoder.encode(input_text))
    
    # Encode the output text to get the number of output tokens
    output_token_count = len(encoder.encode(output_text))
    
    # Calculate the costs
    input_cost = input_token_count * pricing[model]["input"]
    output_cost = output_token_count * pricing[model]["output"]
    total_cost = input_cost + output_cost
    
    return input_token_count, output_token_count, total_cost




if __name__ == "__main__":
    driver = setup_selenium()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    try:
        # Open the Towne page
        driver.get("https://specials.westherr.com/specials/?dealer_id=11&")
        time.sleep(4)  # Give time for the page to load

        # Find all the ads (divs) with the class 'special-offer'
        ads = driver.find_elements(By.CSS_SELECTOR, ".row .col-lg-4.col-md-6")

        all_ads_html = []
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

            time.sleep(4)  # Allow page to load

            # Scrape the lease terms from the detailed page
            lease_terms_div = driver.find_element(By.CSS_SELECTOR, "div.col-md-6 > div.border.rounded.bg-slate-50")
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
        DynamicListingModel = create_dynamic_listing_model("MSRP")
        DynamicListingsContainer = create_listings_container_model(DynamicListingModel)
        formatted_data = format_data(ads_markdown, DynamicListingsContainer)

        formatted_data_text = json.dumps(formatted_data.dict())
        input_tokens, output_tokens, total_cost = calculate_price(ads_markdown, formatted_data_text, model=model_used)
        df = save_formatted_data(formatted_data, timestamp)

        print(df, formatted_data, ads_markdown, input_tokens, output_tokens, total_cost, timestamp)

    finally:
        driver.quit()