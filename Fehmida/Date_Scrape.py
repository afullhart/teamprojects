import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time
import re
import csv
from datetime import datetime

# 1. Setup and Initialization
base_url = 'https://santarita.arizona.edu/transects'
domain = 'https://santarita.arizona.edu'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

# Define the output CSV filename in the current working directory
output_csv = 'srer_transect_dates.csv'

print(f"Fetching SRER directory: {base_url}")
response = requests.get(base_url, headers=headers)

if response.status_code == 200:
    soup = BeautifulSoup(response.content, 'html.parser')
    
    transect_links = soup.find_all('a', class_='listed-transect-link')
    srer_transect_urls = []
    
    for link in transect_links:
        href = link.get('href')
        full_url = urljoin(domain, href)
        srer_transect_urls.append(full_url)
                
    print(f"Successfully found {len(srer_transect_urls)} transect sub-pages.")
    print(f"Beginning data extraction. Writing to {output_csv}...\n")
    
    date_pattern = re.compile(r'\d{4}\s[A-Za-z]{3}\s\d{2}')
    
    # 2. Open the CSV file for writing
    with open(output_csv, mode='w', newline='') as file:
        writer = csv.writer(file)
        
        # --- Added 'Pasture' to the header row ---
        writer.writerow(['Pasture', 'Transect_ID', 'Date'])
        
        # 3. Loop through ALL extracted URLs
        for url in srer_transect_urls:
            
            # --- Extract both Pasture and Transect ID from the URL ---
            url_parts = url.split('/')
            transect_id = url_parts[-1]
            pasture = url_parts[-2] # Grabs the directory name right before the transect ID
            
            print(f"Accessing: Pasture {pasture} | Transect {transect_id}")
            
            sub_response = requests.get(url, headers=headers)
            
            if sub_response.status_code == 200:
                sub_soup = BeautifulSoup(sub_response.content, 'html.parser')
                page_text = sub_soup.get_text(separator=' ')
                
                found_dates = date_pattern.findall(page_text)
                unique_dates = sorted(list(set(found_dates)))
                
                # Format each date and write it to the CSV
                for raw_date in unique_dates:
                    try:
                        parsed_date = datetime.strptime(raw_date, '%Y %b %d').strftime('%Y-%m-%d')
                        
                        # --- Write the pasture label into the row ---
                        writer.writerow([pasture, transect_id, parsed_date])
                        
                    except ValueError:
                        # --- Write the pasture label here as well ---
                        writer.writerow([pasture, transect_id, raw_date])
                
            else:
                print(f"  -> Failed to load {transect_id} (Status: {sub_response.status_code})")
                
            # Pause to respect the server and avoid getting IP blocked
            time.sleep(1) 

    print(f"\nScraping complete! Data saved to {output_csv}")

else:
    print(f"Failed to load the main page. Status code: {response.status_code}")
