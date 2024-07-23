#!/usr/bin/python3
import argparse
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

eogger = logging.getLogger(__name__)
pos_file = "gps-recording.json"


@dataclasses.dataclass
class Location:
    timestamp: float
    latitude: float
    longitude: float



CURRENT_POSITION: Location = None

nmea_exception: Optional[Exception] = None


def nmea_connector(nmea_ip: str, nmea_port: int):
    global CURRENT_POSITION, nmea_exception
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as stream:
                logger.info(f"Connecting to NMEA device at {nmea_ip}:{nmea_port}")
                stream.connect((nmea_ip, nmea_port))
                nmr = NMEAReader(stream)
                for raw_data, parsed_data in nmr:
                    parsed_data: NMEAMessage
                    # print(parsed_data)
                    if parsed_data.msgID == "RMC":
                        # print("RMC")
                        gps_time = datetime.combine(datetime.now(timezone.utc).date(), parsed_data.time).replace(
                            tzinfo=timezone.utc)
                        loc = Location(gps_time.timestamp(), latitude=parsed_data.lat, longitude=parsed_data.lon)
                        CURRENT_POSITION = loc
        except Exception as e:
            logger.error("Failed to connect to NMEA device")
            logger.exception(e)


def write_to_file(element, log_file_path):
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


def log_pos():
    global CURRENT_POSITION
    timestamp = time.time()
    location = CURRENT_POSITION
    element = {"timestamp": timestamp, "location": dataclasses.asdict(location)}
    write_to_file(element, pos_file)
    logger.info(f"Recorded time={datetime.fromtimestamp(timestamp)},location={location}")

def main():
    parser = argparse.ArgumentParser(
        prog='WifiAnalyzerLogger',
        description="Software to log and analyze wifi signal strength around and speed test specific network"
    )
    parser.add_argument("-n", "--nmea-ip", required=True, help="IP address of NMEA device")
    parser.add_argument("-p", "--nmea-port", required=True, type=int, help="NMEA port to scan")
    args = parser.parse_args()
    nmea_ip = args.nmea_ip
    nmea_port = args.nmea_port
    logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', datefmt='%Y-%m-%d %H:%M:%S',
                        level=logging.INFO)
    running = True
    last_pos: Optional[Location] = None
    logger.info("Starting NMEA")
    while running:
        try:
            nmea_connector(nmea_ip, nmea_port)
        except Exception as e:
            if Exception is KeyboardInterrupt:
                logger.info("Received keyboard interrupt, stopping")
            else:
                logger.exception(e)
            running = False

    logger.info("Exiting")
main()
