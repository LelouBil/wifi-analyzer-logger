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

logger = logging.getLogger(__name__)
signal_file = "signal-recording.json"
speed_file = "speed-recording.json"


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


@dataclasses.dataclass
class PingRun:
    timestamp: float
    ping_time_ms: float
    failed: bool


@dataclasses.dataclass
class IPerfRun:
    timestamp: float
    iperf_bandwidth_kbits_sec: float
    failed: bool


@dataclasses.dataclass
class SpeedTestResults:
    ping_runs: List[PingRun]
    iperf_default: List[IPerfRun]
    iperf_reversed: List[IPerfRun]


def run_ping(ping_ip):
    timestamp = time.time()
    command = ["ping", ping_ip, "-c", "1", "-W", "3"]
    result = subprocess.run(command, stdout=subprocess.PIPE)
    lines = result.stdout.decode().splitlines()
    last = lines[-1]
    if not last.startswith("rtt"):
        return PingRun(timestamp, -1, True)
    ms = last.split("/")[4]
    logger.info("Ping done")
    return PingRun(timestamp, float(ms), False)


def run_iperf(iperf_ip, iperf_port, reversed=False):
    timestamp = time.time()
    command = ["iperf", "-c", iperf_ip, "-p", str(iperf_port), "--format", "k"]
    if reversed:
        command.append("-r")
    result = subprocess.run(command, stdout=subprocess.PIPE)
    lines = result.stdout.decode().splitlines()
    res = lines[-1]
    if "failed" in res:
        logger.error("Failed IPerf")
        logger.info(lines)
        return IPerfRun(timestamp, -1, True)
    # language=regexp
    regex = "(\\d+) Kbits/sec"
    match = re.search(regex, res)
    num = float(match.group(1))
    logger.info(f"IPerf done, reversed={reversed}")
    return IPerfRun(timestamp, num, False)


def run_speed_tests(iperf_ip, iperf_port) -> SpeedTestResults:
    logger.info("Starging speed tests")
    ping_runs = []
    iperf_runs = []
    iperf_reversed = []
    logger.info("Doing pings")
    for i in range(10):
        res = run_ping(iperf_ip)
        if res.failed:
            logger.info("Failed ping")
        ping_runs.append(res)
    if any(r.failed for r in ping_runs):
        logger.warning("Not running iperf since pings failed")
    else:
        logger.info("Doing IPerf")
        for i in range(3):
            res = run_iperf(iperf_ip, iperf_port)
            iperf_runs.append(res)
            res_rev = run_iperf(iperf_ip, iperf_port, reversed=True)
            iperf_reversed.append(res_rev)

    return SpeedTestResults(ping_runs, iperf_reversed=iperf_reversed, iperf_default=iperf_runs)


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


def scan_signals():
    global CURRENT_POSITION
    logger.info("Scanning signals...")
    timestamp = time.time()
    location = CURRENT_POSITION
    devices = get_nearby_networks_info()
    element = {"timestamp": timestamp, "location": dataclasses.asdict(location),
               "device": list(map(lambda x: dataclasses.asdict(x), devices))}
    write_to_file(element, signal_file)
    logger.info(f"Recorded time={datetime.fromtimestamp(timestamp)},location={location},devices_count={len(devices)}")


def connect_network(test_bssid: str, password: str):
    command = ["nmcli", "device", "wifi", "connect", test_bssid, "password", password]
    res = subprocess.run(command, stdout=subprocess.PIPE)
    if res.returncode != 0:
        logger.error("Connect failed")
        raise Exception


def disconnect_network():
    command = ["nmcli", "device", "wifi", "disconnect"]
    res = subprocess.run(command, stdout=subprocess.pipe)
    if res.returncode != 0:
        logger.error("Connect failed")
        raise Exception


def test_speed(test_bssid: str, password: str, iperf_ip: str, iperf_port: int):
    global CURRENT_POSITION
    connect_network(test_bssid, password)
    timestamp = time.time()
    location = CURRENT_POSITION
    speed_res = run_speed_tests(iperf_ip, iperf_port)
    element = {"timestamp": timestamp, "location": dataclasses.asdict(location),
               "speed_info": dataclasses.asdict(speed_res)}
    write_to_file(element, speed_file)
    # todo disconnect network
    pass


def main():
    parser = argparse.ArgumentParser(
        prog='WifiAnalyzerLogger',
        description="Software to log and analyze wifi signal strength around and speed test specific network"
    )
    parser.add_argument("-n", "--nmea-ip", required=True, help="IP address of NMEA device")
    parser.add_argument("-p", "--nmea-port", required=True, type=int, help="NMEA port to scan")
    parser.add_argument("-t", "--test-network", required=True, help="BSSID of the network to test")
    parser.add_argument("--password", required=True, help="Password for the BSSID")
    parser.add_argument("--iperf-ip", required=True, help="IP address of the iperf server")
    parser.add_argument("--iperf-port", required=True, type=int, help="Port of the iperf server")
    args = parser.parse_args()
    nmea_ip = args.nmea_ip
    nmea_port = args.nmea_port
    test_network_bssid = args.test_network
    test_network_password = args.password
    iperf_ip = args.iperf_ip
    iperf_port = args.iperf_port
    logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', datefmt='%Y-%m-%d %H:%M:%S',
                        level=logging.INFO)
    logger.info("Starting NMEA Thread")
    nmea_thread = threading.Thread(target=lambda: nmea_connector(nmea_ip, nmea_port))
    nmea_thread.daemon = True
    nmea_thread.start()
    logger.info("Starting recorder")
    running = True
    last_pos: Optional[Location] = None
    while running:
        try:
            if nmea_exception is not None:
                raise nmea_exception
            if (last_pos is None and CURRENT_POSITION is not None) or (
                    CURRENT_POSITION is not None and CURRENT_POSITION.timestamp > last_pos.timestamp):
                scan_signals()
                test_speed(test_network_bssid, test_network_password, iperf_ip, iperf_port)
                last_pos = CURRENT_POSITION
            else:
                logger.info("Waiting for GPS Update")
            time.sleep(1)
        except Exception as e:
            if Exception is KeyboardInterrupt:
                logger.info("Received keyboard interrupt, stopping")
            else:
                logger.exception(e)
            running = False

    logger.info("Exiting")


main()
