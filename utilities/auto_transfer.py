import os
import time
import logging
import traceback

import requests
import yaml

from ifcb.data.transfer.remote import RemoteIfcb
from ifcb.data.transfer.deposit import fileset_destination_dir

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

def load_config(config_file):
    logging.info(f'loading configuration from {config_file}...')

    with open(config_file) as fin:
        config = yaml.safe_load(fin)

    return config

def sync_ifcb(name, dashboard_url, ifcb_config):
    address = ifcb_config['address']
    netbios_name = ifcb_config.get('netbios_name',None)
    username = ifcb_config.get('username','ifcb')
    password = ifcb_config.get('password','ifcb')
    share = ifcb_config.get('share','Data')
    directory = ifcb_config.get('directory','')
    destination_directory = ifcb_config.get('destination')
    beads_destination_directory = ifcb_config.get('beads_destination')
    dataset = ifcb_config.get('dataset')
    timeout = int(ifcb_config.get('timeout',30))
    if dataset is None:
        raise ValueError('dataset must be specified')
    day_dirs = ifcb_config.get('day_dirs',False)

    def destination(lid):
        if day_dirs:
            dest = os.path.join(destination_directory, fileset_destination_dir(lid))
        else:
            dest = destination_directory

        return dest

    def hit_sync_endpoint(lid):
        url = f'{dashboard_url}/api/sync_bin?dataset={dataset}&bin={lid}'
        try:
            logging.info(f'hitting {url} ...')
            requests.get(url)
        except:
            logging.error(f'unable to reach {url}, {lid} not synced!')

    logging.info(f'connecting to {name} ...')

    try:
        ifcb = RemoteIfcb(address, username, password, netbios_name=netbios_name,
            share=share, directory=directory, timeout=timeout)

        with ifcb:
            ifcb.sync(destination, fileset_callback=hit_sync_endpoint)
            logging.info(f'completed transferring from {name}')
    except:
        logging.error(f'unable to transfer from {name}')
        traceback.print_exc()

    if beads_destination_directory is not None:
        logging.info(f'transferring beads ...')

        try:
            ifcb = RemoteIfcb(address, username, password, netbios_name=netbios_name,
                share=share, directory='beads', timeout=timeout)

            with ifcb:
                ifcb.sync(beads_destination_directory)
                logging.info(f'completed transferring beads from {name}')
        except:
            logging.error(f'unable to transfer beads from {name}')
            traceback.print_exc()

def sync_ifcbs(config):
    dashboard_url = config['dashboard']['url']
    logging.info(f'dashboard URL = {dashboard_url}')

    for name, ifcb_config in config['ifcbs'].items():
        logging.info(f'transferring from {name}...')
        sync_ifcb(name, dashboard_url, ifcb_config)

def main(config_file='transfer_config.yml'):
    config = load_config(config_file)
    sleep = config.get('sleep',60)
    while True:
        sync_ifcbs(config)
        logging.info(f'pausing for {sleep}s ...')
        time.sleep(sleep)

if __name__ == '__main__':
    main() 