#!/usr/bin/python3
import dataclasses
import json
from datetime import datetime, timezone
import re
import logging
import threading
import time
import os
import subprocess
from typing import Optional, List
import socket

import pynmeagps
from pynmeagps import NMEAReader, NMEAMessage

logger = logging.getLogger(__name__)
log_file_path = "recording.json"


@dataclasses.dataclass
class NetworkInfo:
    SSID: Optional[str]
    SSID_HEX: Optional[str]
    BSSID: str
    CHAN: int
    FREQ: str
    RATE: str
    BANDWIDTH: str
    SIGNAL: float
    SECURITY: str


@dataclasses.dataclass
class Location:
    timestamp: float
    latitude: float
    longitude: float


def get_nearby_networks_info() -> List[NetworkInfo]:
    command = ["nmcli", "--terse", "-c", "no", "-e", "yes", "-f",
               'SSID,SSID-HEX,BSSID,CHAN,FREQ,RATE,BANDWIDTH,SIGNAL,SECURITY', "-m", "multiline", "device", "wifi",
               "list"]  # , "--rescan", "yes"]
    result = subprocess.run(command, stdout=subprocess.PIPE)
    list = []
    cur = []
    for line in result.stdout.decode().splitlines():
        elem = line.split(":", 1)
        cur.append(elem[1])
        if line.startswith("SECURITY"):
            list.append(NetworkInfo(*cur))
            cur = []
    return list


CURRENT_POSITION: Location = None


def nmea_connector():
    global CURRENT_POSITION
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as stream:
        stream.connect(("192.168.68.243", 5555))
        nmr = NMEAReader(stream)
        for raw_data, parsed_data in nmr:
            parsed_data: NMEAMessage
            if parsed_data.msgID == "RMC":
                gps_time = datetime.combine(datetime.now(timezone.utc).date(), parsed_data.time).replace(
                    tzinfo=timezone.utc)
                loc = Location(gps_time.timestamp(), latitude=parsed_data.lat, longitude=parsed_data.lon)
                CURRENT_POSITION = loc


def write_to_file(timestamp: float, location: Location, devices: List[NetworkInfo]):
    element = {"timestamp": timestamp, "location": dataclasses.asdict(location),
               "device": list(map(lambda x: dataclasses.asdict(x), devices))}
    first = False
    if not os.path.exists(log_file_path):
        with open(log_file_path, "w") as file:
            file.write("[")
            file.flush()
            first = True
    with open(log_file_path, mode="r+") as file:
        if not first:
            file.seek(0, 2)
            position = file.tell() - 2
            file.seek(position)
        else:
            file.seek(0, 2)
        if first:
            file.write("\n{}\n]".format(json.dumps(element)))
        else:
            file.write(",\n{}\n]".format(json.dumps(element)))
        file.flush()


def scan_signals():
    global CURRENT_POSITION
    logger.info("Scanning signals...")
    timestamp = time.time()
    while CURRENT_POSITION is None or CURRENT_POSITION.timestamp < timestamp:
        logger.info("Waiting for GPS Update")
        time.sleep(1)
    location = CURRENT_POSITION
    devices = get_nearby_networks_info()
    write_to_file(timestamp, location, devices)
    logger.info(f"Recorded time={datetime.fromtimestamp(timestamp)},location={location},devices_count={len(devices)}")


def main():
    logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', datefmt='%Y-%m-%d %H:%M:%S',
                        level=logging.INFO)
    logger.info("Starting NMEA Thread")
    nmea_thread = threading.Thread(target=nmea_connector)
    nmea_thread.daemon = True
    nmea_thread.start()
    logger.info("Starting recorder")
    running = True
    while running:
        try:
            scan_signals()
            # test_speed()
            time.sleep(5)
        except Exception as e:
            if Exception is KeyboardInterrupt:
                logger.info("Received keyboard interrupt, stopping")
            else:
                logger.exception(e)
            running = False

    logger.info("Exiting")


main()
