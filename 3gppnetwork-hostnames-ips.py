import asyncio
import pandas as pd
from tqdm.asyncio import tqdm
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import aiodns
import aiofiles
import logging

# Set event loop policy for Windows
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Asynchronous function to resolve the DNS chain
async def resolve_name_chain(resolver, hostname, log_file, resolved_names=None, resolved_ips=None):
    if resolved_names is None:
        resolved_names = []
    if resolved_ips is None:
        resolved_ips = []

    if hostname in resolved_names:
        return resolved_names, resolved_ips  # Avoid infinite loops

    resolved_names.append(hostname)

    try:
        cname_result = await resolver.query(hostname, 'CNAME')
        cname_host = cname_result.cname
        async with aiofiles.open(log_file, 'a') as f:
            await f.write(f"{hostname} is a CNAME for {cname_host}\n")
        return await resolve_name_chain(resolver, cname_host, log_file, resolved_names, resolved_ips)
    except aiodns.error.DNSError as e:
        async with aiofiles.open(log_file, 'a') as f:
            await f.write(f"No CNAME record for {hostname}: {e}\n")

    try:
        result = await resolver.query(hostname, 'A')
        ips = [ip.host for ip in result]
        async with aiofiles.open(log_file, 'a') as f:
            await f.write(f"{hostname} has A records: {', '.join(ips)}\n")
        resolved_ips.extend(ips)
    except aiodns.error.DNSError as e:
        async with aiofiles.open(log_file, 'a') as f:
            await f.write(f"No A records for {hostname}: {e}\n")

    try:
        result = await resolver.query(hostname, 'AAAA')
        ips = [ip.host for ip in result]
        async with aiofiles.open(log_file, 'a') as f:
            await f.write(f"{hostname} has AAAA records: {', '.join(ips)}\n")
        resolved_ips.extend(ips)
    except aiodns.error.DNSError as e:
        async with aiofiles.open(log_file, 'a') as f:
            await f.write(f"No AAAA records for {hostname}: {e}\n")

    return resolved_names, resolved_ips

async def resolve_hostname_with_semaphore(semaphore, resolver, hostname, country_code, network, results, log_file, pbar, valid_names):
    async with semaphore:
        resolved_names, resolved_ips = await resolve_name_chain(resolver, hostname, log_file)
        if resolved_ips:
            valid_names.append(hostname)
        results.append((hostname, resolved_ips, country_code, network))
        pbar.update(1)

async def resolve_hostnames(df, log_filename, log_dir):
    df["hostname"] = df.apply(
        lambda row: f"epdg.epc.mnc{int(row['MNC']):03d}.mcc{int(row['MCC']):03d}.pub.3gppnetwork.org",
        axis=1
    )

    hostnames = df["hostname"].tolist()
    country_codes = df["Country Code"].tolist()
    networks = df["Network"].tolist()
    max_workers = min(128, len(hostnames))
    semaphore = asyncio.Semaphore(max_workers)
    resolver = aiodns.DNSResolver()

    results = []
    valid_names = []

    with tqdm(total=len(hostnames), desc="Resolving hostnames", unit="hostname") as pbar:
        tasks = [
            resolve_hostname_with_semaphore(semaphore, resolver, hostnames[i], country_codes[i], networks[i], results, log_filename, pbar, valid_names)
            for i in range(len(hostnames))
        ]
        await asyncio.gather(*tasks)

    results_df = pd.DataFrame(results, columns=["Hostname", "IPAddresses", "CountryCode", "Network"])

    # Combine IP addresses into a single line for each hostname
    results_df["IPAddresses"] = results_df["IPAddresses"].apply(lambda x: ", ".join(x))

    # Save valid names to a file
    valid_names_filename = os.path.join(log_dir, "valid_names.txt")
    with open(valid_names_filename, 'w') as f:
        for name in sorted(valid_names):
            f.write(f"{name}\n")

    print(f"Resolved hostnames successfully. Valid names saved to {valid_names_filename}")

    return results_df

def output_to_csv(results_df, log_dir):
    """
    Outputs the resolved records to a CSV file.
    """
    # Sort the DataFrame alphanumerically by the Hostname column
    results_df = results_df.sort_values(by="Hostname")

    output_filename = os.path.join(log_dir, "hostname_resolution_results.csv")
    results_df.to_csv(output_filename, index=False)
    print(f"Results saved to {output_filename}")

def scrape_mcc_mnc(log_dir):
    url = 'https://www.mcc-mnc.com/'
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    table = soup.find('table', {'id': 'mncmccTable'})

    rows = table.find_all('tr')[1:]  # skip the header row
    data = []

    for row in rows:
        cols = row.find_all('td')
        mcc = cols[0].text.strip()
        mnc = cols[1].text.strip()
        iso = cols[2].text.strip()
        country = cols[3].text.strip()
        country_code = cols[4].text.strip()
        network = cols[5].text.strip()
        data.append({
            'MCC': mcc,
            'MNC': mnc,
            'ISO': iso,
            'Country': country,
            'Country Code': country_code,
            'Network': network,
            'Hostname': f"epdg.epc.mnc{mnc}.mcc{mcc}.pub.3gppnetwork.org"
        })

    df = pd.DataFrame(data)

    # Write DataFrame to a CSV file with a timestamp
    output_filename = os.path.join(log_dir, "mcc_mnc_data.csv")
    df.to_csv(output_filename, index=False)

    return df

async def main(country_code_filter=None):
    """
    Main function to orchestrate the resolution of hostnames and save results to a CSV file.

    Args:
        country_code_filter (str, optional): The country code to filter hostnames.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    if country_code_filter:
        log_dir = f"output_{country_code_filter}_{timestamp}"
    else:
        log_dir = f"output_{timestamp}"
    os.makedirs(log_dir, exist_ok=True)
    
    log_filename = os.path.join(log_dir, "name_resolution_log.log")
    logging.basicConfig(filename=log_filename, level=logging.INFO, format='%(asctime)s - %(message)s')

    # Scrape the MCC MNC data
    df = scrape_mcc_mnc(log_dir)

    # Filter by country code if provided
    if country_code_filter:
        df = df[df['Country Code'] == country_code_filter]

    # Print out the entire DataFrame and its columns for debugging
    print("DataFrame after loading/scraping:")
    print(df.head())  # Print the first few rows of the DataFrame
    print("Columns in the DataFrame:", df.columns)

    # Resolve the hostnames
    results_df = await resolve_hostnames(df, log_filename, log_dir)

    # Output the results to a CSV file
    output_to_csv(results_df, log_dir)

# Run the main function
if __name__ == "__main__":
    import sys
    country_code_filter = sys.argv[1] if len(sys.argv) > 1 else None

    # Create a new event loop and set it as the current event loop
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    new_loop.run_until_complete(main(country_code_filter))
