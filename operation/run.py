# Copyright (c) 2022 BAAI. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License")
# !/usr/bin/env python3
# -*- coding: UTF-8 -*-
''' TODO Copyright and Other info '''

import os
import sys
import time
import getpass
import yaml
from argparse import Namespace
import importlib
import json
import numpy as np

CURR_PATH = os.path.abspath(os.path.dirname(__file__))
sys.path.append(os.path.abspath(os.path.join(CURR_PATH, "../")))
from utils import host_manager
from utils import flagperf_logger

VERSION = "v0.1"
RUN_LOGGER = flagperf_logger.FlagPerfLogger()
HOST_MGR = host_manager.HostManager()


def usage():
    ''' Show usage and exit with exit_code. '''
    print("Usage: python3 ", __file__)
    print("Edit config file config/host.yaml in and run.")
    sys.exit(0)


def start_monitors(dp_path, case_log_dir, config):
    '''Start system and vendor's monitors.'''
    start_mon_cmd = "cd " + dp_path + " && " + sys.executable + " ../utils/sys_monitor.py -v " \
                    + config.VENDOR +  " -o restart -l " + case_log_dir
    timeout = 60
    RUN_LOGGER.debug("Run cmd in the host to start system monitor: " + start_mon_cmd)
    ret = HOST_MGR.run_command(start_mon_cmd, timeout)
    if ret != 0:
        RUN_LOGGER.error("Host that can't start system monitor")

    ven_mon_path = os.path.join(dp_path, "vendors", config.VENDOR,
                                config.VENDOR + "_monitor.py")
    start_mon_cmd = "cd " + dp_path + " && " + sys.executable \
                    + " " + ven_mon_path + " -o restart -l " + case_log_dir
    RUN_LOGGER.debug("Run cmd in the host to start vendor's monitor: " + start_mon_cmd)
    ret = HOST_MGR.run_command(start_mon_cmd, timeout)
    if ret != 0:
        RUN_LOGGER.error("Host can't start vendor's monitor")


def stop_monitors(dp_path, config):
    '''Stop system and vendor's monitors.'''
    stop_mon_cmd = "cd " + dp_path + " && " + sys.executable \
                   + " ../utils/sys_monitor.py -o stop"
    timeout = 60
    RUN_LOGGER.debug("Run cmd in the host to stop system monitor: " +
                     stop_mon_cmd)
    ret = HOST_MGR.run_command(stop_mon_cmd, timeout)
    if ret != 0:
        RUN_LOGGER.error("Host can't stop system monitor")

    ven_mon_path = os.path.join(dp_path, "vendors", config.VENDOR,
                                config.VENDOR + "_monitor.py")
    stop_mon_cmd = "cd " + dp_path + " && " + sys.executable \
                   + " " + ven_mon_path + " -o stop"
    RUN_LOGGER.debug("Run cmd in the host to stop vendor's monitor: " +
                     stop_mon_cmd)
    ret = HOST_MGR.run_command(stop_mon_cmd, timeout)
    if ret != 0:
        RUN_LOGGER.error("Host can't stop vendor's monitor")


def start_tasks(dp_path, config, base_args, curr_log_path, case):
    '''Start tasks in cluster, and NOT wait.'''

    op, df, spectflops, oplib, chip = case.split(":")
    env_dir = os.path.join(config.FLAGPERF_PATH, "benchmarks", op,
                           config.VENDOR, chip)

    env_shell = os.path.join(env_dir, "env.sh")
    req_file = os.path.join(env_dir, "requirements.txt")

    abs_log_path = os.path.join(dp_path, curr_log_path)

    start_cmd = "echo Hello FlagPerf > " + abs_log_path + "/hello.log.txt"

    if os.path.isfile(req_file):
        start_cmd += " && pip install -r " + req_file \
                     + " > " + abs_log_path + "/pip_install.log.txt " \
                     + "2>&1"

    if os.path.isfile(env_shell):
        if config.VENDOR == "iluvatar":
            start_cmd += " && export CUDA_VISIBLE_DEVICES=" + str(config.DEVICE) 
        start_cmd += " && source " + env_shell \
                     + " > " + abs_log_path + "/env.log.txt " \
                     + "2>&1"

    start_cmd += " && python3 " + config.FLAGPERF_PATH + "/host_main.py" + base_args \
                 + " > " + abs_log_path + "/host_main.log.txt " \
                 + "2>&1"

    RUN_LOGGER.debug("Run cmd in the host to start tasks, cmd=" + start_cmd)
    HOST_MGR.run_command(command=start_cmd, timeout=15, check=False)
    # Wait a moment for starting tasks.
    time.sleep(10)


def wait_for_finish(pid_file_path):
    '''wait the process of start_xxx_task.py finished.
    '''
    RUN_LOGGER.debug("check whether the task is running")
    while True:
        if host_manager.is_pid_running(pid_file_path) == False:
            break
        time.sleep(10)


def get_valid_cases(config):
    '''Check case config in test_conf, return valid cases list.'''
    if not isinstance(config.CASES, dict):
        RUN_LOGGER.error(
            "No valid cases found in config/host.yaml because config.CASES is not a dict...[EXIT]"
        )
        sys.exit(4)
    RUN_LOGGER.debug("Check configs of all test cases: " + ",".join(config.CASES))
    valid_cases = []
    cases_config_error = []
    for case in config.CASES:
        valid_cases.append(case)
    if len(valid_cases) == 0:
        RUN_LOGGER.error("No valid cases found in config/host.yaml...[EXIT]")
        sys.exit(4)
    RUN_LOGGER.debug("Valid cases: " + ",".join(valid_cases))
    RUN_LOGGER.info("Get valid cases list......[SUCCESS]")
    return valid_cases


def summary_logs(config, curr_log_path, cases):
    analysis_module_path = os.path.join("vendors",
                                        config.VENDOR,
                                        config.VENDOR + "_analysis")
    analysis_module_path = analysis_module_path.replace("/", ".")
    analysis_module = importlib.import_module(analysis_module_path)
    analysis_log = getattr(analysis_module, 'analysis_log', None)

    result = {}
    for case in cases:
        result[case] = {}

        case_log_dir = os.path.join(curr_log_path, case)
        # vendor monitor results like temp/power        
        vendor_monitor_path = os.path.join(case_log_dir,
                                            config.VENDOR + "_monitor.log")
        vendor_log = analysis_log(vendor_monitor_path, config)
        result[case]["vendor"] = vendor_log
        
        # system monitor results like CPU/MEM/POWER
        # for index in ["cpu", "mem", "pwr"]:
        for index in ["mem"]:
            monitor_path = os.path.join(case_log_dir, index + "_monitor.log")
            with open(monitor_path, 'r') as file:
                sys_log = [float(line.split("\t")[1][:-1]) for line in file if "\t" in line]
            result[case][index] = sys_log
        # FlagPerf Result
        flagperf_result_path = os.path.join(case_log_dir, "operation.log.txt")
        with open(flagperf_result_path, 'r') as file:
            key_lines = [line.strip() for line in file if 'FlagPerf Result' in line]
        result[case]["flagperf"] = key_lines

    return result


def analysis_log(key_logs, cases):
    for case in cases:
        RUN_LOGGER.info("*" * 50)
        RUN_LOGGER.info("Test Case {}".format(case))
        # RUN_LOGGER.info("Noderank {} with IP {}".format(noderank, host))

        RUN_LOGGER.info("1) Performance:")
        for line in key_logs[case]["flagperf"]:
            RUN_LOGGER.info("  " + line.split("]")[1])

        RUN_LOGGER.info("2) POWER:")
        RUN_LOGGER.info("  2.1) AI-chip POWER:")
        for node in key_logs[case]["vendor"]["power"].keys():
            pwr_series = key_logs[case]["vendor"]["power"][node]
            RUN_LOGGER.info(
                "    RANK {}'s AVERAGE: {} Watts, MAX: {} Watts, STD DEVIATION: {} Watts"
                .format(node, round(np.mean(pwr_series), 2),
                        round(np.max(pwr_series), 2),
                        round(np.std(pwr_series), 2)))

        RUN_LOGGER.info("  2.2) AI-chip TEMPERATURE:")
        for node in key_logs[case]["vendor"]["temp"].keys():
            temp_series = key_logs[case]["vendor"]["temp"][node]
            RUN_LOGGER.info(
                u"    RANK {}'s AVERAGE: {} \u00b0C, MAX: {} \u00b0C, STD DEVIATION: {} \u00b0C"
                .format(node, round(np.mean(temp_series), 2),
                        round(np.max(temp_series), 2),
                        round(np.std(temp_series), 2)))

        RUN_LOGGER.info("3) Utilization:")
        RUN_LOGGER.info("  3.1) SYSTEM MEMORY:")
        mem_series = key_logs[case]["mem"]
        RUN_LOGGER.info(
            "    AVERAGE: {} %, MAX: {} %, STD DEVIATION: {} %".format(
                round(np.mean(mem_series) * 100, 3),
                round(np.max(mem_series) * 100, 3),
                round(np.std(mem_series) * 100, 3)))

        RUN_LOGGER.info("  3.2) AI-chip MEMORY:")
        for node in key_logs[case]["vendor"]["mem"].keys():
            mem_series = key_logs[case]["vendor"]["mem"][node]
            RUN_LOGGER.info(
                "    RANK {}'s AVERAGE: {} %, MAX: {} %, STD DEVIATION: {} %".
                format(
                    node,
                    round(
                        np.mean(mem_series) * 100 /
                        key_logs[case]["vendor"]["max_mem"], 3),
                    round(
                        np.max(mem_series) * 100 /
                        key_logs[case]["vendor"]["max_mem"], 3),
                    round(
                        np.std(mem_series) * 100 /
                        key_logs[case]["vendor"]["max_mem"], 3)))



def print_welcome_msg():
    '''Print colorful welcome message to console.'''
    print("\033[1;34;40m==============================================\033[0m")
    print("\033[1;36;40m          Welcome to FlagPerf!\033[0m")
    print(
        "\033[1;36;40m      See more at https://github.com/FlagOpen/FlagPerf \033[0m"
    )
    print("\033[1;34;40m==============================================\033[0m")


def log_test_configs(cases, curr_log_path, dp_path, config):
    '''Put test configs to log '''
    RUN_LOGGER.info("--------------------------------------------------")
    RUN_LOGGER.info("Prepare to run flagperf benchmakrs with configs: ")
    RUN_LOGGER.info("Deploy path on host:\t" + dp_path)
    RUN_LOGGER.info("Vendor:\t\t" + config.VENDOR)
    RUN_LOGGER.info("Testcases:\t\t[" + ','.join(cases) + "]")
    RUN_LOGGER.info("Log path on host:\t" + curr_log_path)
    RUN_LOGGER.info("--------------------------------------------------")


def main():
    '''Main process to run all the testcases'''

    print_welcome_msg()

    # load yaml
    with open("configs/host.yaml", "r") as file:
        config_dict = yaml.safe_load(file)
        config = Namespace(**config_dict)

    # Set logger first
    timestamp_log_dir = "run" + time.strftime("%Y%m%d%H%M%S", time.localtime())
    curr_log_path = os.path.join(config.FLAGPERF_LOG_PATH, timestamp_log_dir)
    RUN_LOGGER.init(curr_log_path,
                    "flagperf_run.log",
                    config.FLAGPERF_LOG_LEVEL,
                    "both",
                    log_caller=True)

    RUN_LOGGER.info("======== Step 1: Check configs. ========")
    RUN_LOGGER.info("Initialize logger with log path: " + curr_log_path +
                    "......[SUCCESS]")

    # Check test environment and configs of testcases.
    HOST_MGR.init(logger=RUN_LOGGER)
    dp_path = os.path.abspath(config.FLAGPERF_PATH)
    cases = get_valid_cases(config)
    log_test_configs(cases, curr_log_path, dp_path, config)

    RUN_LOGGER.info("========= Step 2: Prepare and Run test cases. =========")

    for case in cases:
        RUN_LOGGER.info("======= Testcase: " + case + " =======")

        # Set command to start train script in container in the cluster
        log_dir = os.path.join(config.FLAGPERF_LOG_PATH,
                                         timestamp_log_dir)
        base_args = " --vendor " + config.VENDOR + " --case_name " + case \
                    + " --perf_path " + dp_path \
                    + " --nproc_per_node " + str(config.NPROC_PER_NODE) \
                    + " --log_dir " + os.path.join(dp_path, log_dir) \
                    + " --log_level " + config.FLAGPERF_LOG_LEVEL.upper() \

        RUN_LOGGER.info("-== Testcase " + case + " starts ==-")
        RUN_LOGGER.info("1) Start monitor in the host...")
        case_log_dir = os.path.join(curr_log_path, case)
        start_monitors(dp_path, case_log_dir, config)

        RUN_LOGGER.info("2) Start tasks in the host...")
        start_tasks(dp_path, config, base_args, curr_log_path, case)

        # Wait until start_xxx_task.py finished.
        RUN_LOGGER.info("3) Waiting for tasks end in the host...")
        pid_file_path = os.path.join( log_dir, "start_base_task.pid")
        wait_for_finish(pid_file_path)

        RUN_LOGGER.info("4) Stop monitor in the host...")
        stop_monitors(dp_path, config)
        RUN_LOGGER.info("-== Testcase " + case + " finished ==-")

    RUN_LOGGER.info("========= Step 3: Collect logs in the host. =========")
    RUN_LOGGER.info("1) summary logs")
    key_logs = summary_logs(config, curr_log_path, cases)
    RUN_LOGGER.debug(key_logs)
    jsonfile = os.path.join(dp_path, curr_log_path, "detail_result.json")
    json.dump(key_logs, open(jsonfile, "w"))

    RUN_LOGGER.info("2) analysis logs")
    analysis_log(key_logs, cases)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        usage()
    main()
    RUN_LOGGER.stop()
