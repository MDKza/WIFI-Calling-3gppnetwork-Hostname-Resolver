# 3GPP Network Hostname Resolver for WIFI Calling

With the constant need to allow WIFI calling around the world through different firewalls I found the need to gather the hostnames for all the WIFI calling endpoints in many countries around the world. This information wasnt easily available online. This Python script automates the process of resolving hostnames from the 3GPP (3rd Generation Partnership Project) network. It scrapes MCC (Mobile Country Code) and MNC (Mobile Network Code) data from the website [https://www.mcc-mnc.com/](https://www.mcc-mnc.com/), constructs hostnames based on this data, and then uses DNS resolution to find the corresponding IP addresses. 

## Features

*   **Web Scraping:** Fetches the latest MCC/MNC data from mcc-mnc.com.
*   **Hostname Construction:** Generates hostnames based on the scraped data. Format:
`epdg.epc.mnc{MNC}.mcc{MCC}.pub.3gppnetwork.org`
*   **Multiple IP Address Handling:**  Can resolve a single hostname to multiple IP addresses.
*   **Country Code Filtering:** Allows you to filter the data by a specific country code.
*   **Detailed Output:** Saves results to a CSV file with hostname, IP addresses, country code, and network information.
*   **Summary Report:** Prints a summary of the resolution process.

## Prerequisites

*   **Python:** Make sure you have Python 3.7 or higher installed.
*   **Libraries:** You need to install the following Python libraries:
- `aiofiles`
- `aiodns`
- `tqdm`
- `pandas`
- `beautifulsoup4`
- `requests`
    
You can install them using `pip`:

```bash
pip install aiofiles aiodns tqdm pandas beautifulsoup4 requests
```

## How to Use
1. Save the script: Save the provided Python script as a file (e.g., 3gppnetwork-hostnames-ips.py).
2. Change "[path-to-directory]" on line 110 to the directory to the working directory.
3. Run the script:
Without any arguments, to resolve hostnames for all countries:

```bash
python 3gppnetwork-hostnames-ips.py
```
* Optional: With a country code to filter results (country code is based off of dialing codes e.g., United Kingdom: 44, United States of America: 1, South Africa: 27):

```bash
python hostname_resolver.py 44  # Filter for the country code 44
```

4. Check the output:
The script will first save the scraped MCC/MNC data to a CSV file with a timestamp in the selected directory.
It will then print a progress bar during the resolution process.
The final results will be saved in the selected directory in a CSV file named hostname_resolution_results_{country_code}_{timestamp}.csv (or without the country code if not specified).
A summary of resolved and unresolved hostnames will be printed to the console.

## Important Note
The script is designed to scrape the MCC/MNC data from the website https://www.mcc-mnc.com/. If the website structure or data format changes, the script might need to be updated accordingly.

## Contributing
Feel free to fork this repository and submit pull requests if you have improvements or additional features to add.
