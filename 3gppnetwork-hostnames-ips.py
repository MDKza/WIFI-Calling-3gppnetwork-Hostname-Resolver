import asyncio
import pandas as pd
from tqdm.asyncio import tqdm
import socket
import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# Define an asynchronous function to check hostname resolution
async def check_hostname_resolution(hostname):
    """
    Asynchronously resolves a hostname to its IP addresses.

    Args:
        hostname (str): The hostname to resolve.

    Returns:
        list: A list of tuples, each containing the hostname and a resolved IP address (or None if resolution fails).
    """
    try:
        # Use asyncio to get all IP addresses associated with the hostname
        result = await asyncio.get_event_loop().getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        # Return a list of tuples: (hostname, IP address)
        return [(hostname, addr[4][0]) for addr in result]
        # Catch the error if the hostname resolution fails
    except socket.gaierror:
        # Return the hostname with a None value for IP address if resolution fails
        return [(hostname, None)]

# Define an asynchronous function to resolve hostnames using a semaphore
async def resolve_hostname_with_semaphore(semaphore, hostname, country_code, network, results, pbar):
    """
    Asynchronously resolves a hostname while controlling concurrency using a semaphore.

    Args:
        semaphore (asyncio.Semaphore): The semaphore to control concurrent tasks.
        hostname (str): The hostname to resolve.
        country_code (str): The country code associated with the hostname.
        network (str): The network name associated with the hostname.
        results (list): The list to store results (hostname, IP address, country code, network).
        pbar (tqdm): The progress bar to update.
    """
    async with semaphore: # acquire the semaphore to limit the number of concurrent tasks
        # Call the function to resolve the hostname
        result = await check_hostname_resolution(hostname)
        # Append all resolved IP addresses (including multiple) to the results list
        results.extend([(ip[0], ip[1], country_code, network) for ip in result]) 
        # Update the progress bar
        pbar.update(1)
        

def get_latest_csv_file(directory, pattern):
    """
    Finds the latest CSV file in a directory matching a given pattern.

    Args:
        directory (str): The directory to search in.
        pattern (str): The regular expression pattern to match filenames.

    Returns:
        str or None: The full path to the latest CSV file, or None if no matching file is found.
    """
    # List all files in the directory that match the pattern
    files = [f for f in os.listdir(directory) if re.match(pattern, f)]
    # Sort files in reverse chronological order based on the timestamp in the filename
    files.sort(reverse=True, key=lambda x: datetime.strptime(re.search(r'\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}', x).group(), '%Y-%m-%d_%H-%M-%S'))
    # Return the full path of the latest file
    return os.path.join(directory, files[0]) if files else None

def scrape_mcc_mnc_data():
    """
    Scrapes MCC/MNC data from the mcc-mnc.com website.

    Returns:
        pandas.DataFrame: A DataFrame containing the scraped MCC/MNC data.
    """
    url = "https://www.mcc-mnc.com/" # URL of the website to scrape
    response = requests.get(url) # Fetch the content of the webpage
    response.raise_for_status() # Raise an exception for HTTP errors if any

    soup = BeautifulSoup(response.text, "html.parser") # Parse the HTML content
    table = soup.find("table") # Find the first table in the parsed content

    if table is None:
        raise ValueError("Unable to find the data table on the website.")

    data = []
    for row in table.find_all("tr")[1:]: # Iterate over each row in the table (skipping the header row)
        cells = row.find_all("td") # Extract data from cells of each row
        if len(cells) == 6: # Ensure the row has the expected number of columns
            data.append([cell.text.strip() for cell in cells]) # Append the data to the list

    df = pd.DataFrame(data, columns=["MCC", "MNC", "ISO", "COUNTRY", "COUNTRY CODE", "NETWORK"]) # Create a DataFrame from the data
    return df

# Define the main asynchronous function
async def main(country_code_filter=None):
    """
    The main function to scrape MCC/MNC data, filter it (optionally), resolve hostnames, 
    and save the results.

    Args:
        country_code_filter (str, optional): If provided, filters the data by the specified country code. Defaults to None.
    """
    directory = "[path-to-directory]" # directory to save the data to
    pattern = r'mcc_mnc_data_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.csv' # regular expression to match file names

    try:
        # scrape MCC/MNC data from the website
        df = scrape_mcc_mnc_data()
        #print the data to the console
        print(df)
        #get the current datetime
        now = datetime.now()
        #format datetime
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        #create a save path for the data
        save_path = os.path.join(directory, f"mcc_mnc_data_{timestamp}.csv")
        #save data to CSV
        df.to_csv(save_path, index=False)
        #display where data is saved
        print(f"Data saved to: {save_path}")
    except (requests.exceptions.RequestException, ValueError) as e:
        #if error, print error to console
        print(f"An error occurred while scraping or saving data: {e}")
        #return nothing
        return
    
    #get the latest csv file
    latest_file = save_path
    print(f"Using source file: {latest_file}")
    #if a country code filter is given
    if country_code_filter:
        print(f"Filtering data for country code: {country_code_filter}")
        #filter the df to match given country code
        df = df[df["COUNTRY CODE"] == country_code_filter]
        #if the dataframe is empty, print error and return nothing
        if df.empty:
            print(f"No data found for country code: {country_code_filter}")
            return
    # Create a new column "hostname" by applying a function to each row
    df["hostname"] = df.apply(
        #create the hostname using lambda function
        lambda row: f"epdg.epc.mnc{int(row['MNC']):03d}.mcc{int(row['MCC']):03d}.pub.3gppnetwork.org",
        axis=1
    )
    # Create lists of hostnames, country codes, and networks from the DataFrame
    hostnames = df["hostname"].tolist()
    country_codes = df["COUNTRY CODE"].tolist()
    networks = df["NETWORK"].tolist()
    # limit maximum number of concurrent workers
    max_workers = min(32, len(hostnames))  
    # Create a semaphore to limit concurrent tasks
    semaphore = asyncio.Semaphore(max_workers)
    results = [] # results array
    #use tqdm to display a progress bar
    with tqdm(total=len(hostnames), desc="Resolving hostnames", unit="hostname") as pbar:
        # Create tasks to resolve each hostname concurrently
        tasks = [
            resolve_hostname_with_semaphore(semaphore, hostnames[i], country_codes[i], networks[i], results, pbar)
            for i in range(len(hostnames))
        ]
        #wait for the tasks to complete
        await asyncio.gather(*tasks)

    # Aggregate IP addresses into columns within rows
    results_df = pd.DataFrame(results, columns=["Hostname", "IP Address", "Country Code", "Network"])
    results_df = (results_df.groupby(["Hostname", "Country Code", "Network"])["IP Address"]
                  .apply(list)
                  .reset_index()
                  .rename(columns={"IP Address": "IP Addresses"}))
    
    # Create columns for individual IP addresses (up to a maximum)
    max_ips = results_df["IP Addresses"].apply(len).max()
    for i in range(1, max_ips + 1):
        results_df[f"IP Address {i}"] = results_df["IP Addresses"].apply(lambda x: x[i-1] if i <= len(x) else None)

    results_df.drop(columns=["IP Addresses"], inplace=True)

    # Generate output file
    output_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_filename = os.path.join(
        directory, 
        f"hostname_resolution_results{'_'+country_code_filter if country_code_filter else ''}_{output_timestamp}.csv"
    )
    results_df.to_csv(output_filename, index=False)

    # Display results summary
    resolved_hostnames = results_df.shape[0]  # Number of unique hostnames resolved
    total_ips = results_df.filter(like='IP Address').notnull().sum().sum()  # Total IP addresses found
    print("\nResolution Summary:")
    print(f"Source File:      {latest_file}")
    if country_code_filter:
        print(f"Country Code Filter: {country_code_filter}")
    print(f"Total Hostnames:    {resolved_hostnames}")
    print(f"Total IP Addresses: {total_ips}")


if __name__ == "__main__":
    import sys
    country_code_filter = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(main(country_code_filter))
