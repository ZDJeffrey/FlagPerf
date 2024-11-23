# Copyright  2022 BAAI. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License")
'''Cluster Manager'''

import os
import sys

CURR_PATH = os.path.abspath(os.path.dirname(__file__))
sys.path.append(os.path.join(CURR_PATH))
import run_cmd

from argparse import ArgumentParser

def is_substring(sub_str: str, main_str: str) -> bool:
    """
    Check if a substring is contained within a main string.

    Args:
        sub_str (str): The substring to search for.
        main_str (str): The main string to search within.

    Returns:
        bool: True if the substring is found within the main string, otherwise False.
    """
    return sub_str in main_str

def is_pid_running(pid_file_path, timeout=10):
    '''Return whether the process with pid is running in host.
        Return value:
            True: It is running.
            False: It isn't running.
    '''
    get_pid_cmd = "cat " + pid_file_path
    ret, outs = run_cmd.run_cmd_wait(get_pid_cmd, timeout)
    if ret == 0:
        task_pid = int(outs[0])
    else:
        print("Can't find pid file ", pid_file_path, "in container.")
        return False
    check_cmd = "ls /proc/" + str(task_pid) + "/cmdline"
    ret, outs = run_cmd.run_cmd_wait(check_cmd, timeout)
    if ret == 0:
        print("The process is running.")
        return True
    print("The process is not running.")
    return False

def replace_between_spaces(input, start, end, replacement):
    '''
    Replace the words between start and end with replacement.
    '''    
    parts = input.split()
    if start < 1 or end > len(parts) or start > end:
        raise ValueError("Invalid start or end index.")
    parts[start:end] = [replacement]
    return ' '.join(parts)

class HostManager():
    '''A Host manager that can make healthcheck, distribute files, and run a
       command in the host.
    '''

    def __init__(self):
        self.logger = None

    def init(self, logger):
        '''Init.'''
        self.logger = logger

    def _run_command(self, cmd, timeout=10):
        ''' Run cmd on host.
            Return exit code of cmd and stdout/stderr messages.
        '''
        self.logger.debug("Run cmd on host. cmd=" + cmd +
                          " timeout=" + str(timeout))
        ret, outs = run_cmd.run_cmd_wait(cmd, timeout)
        return ret, outs

    def healthcheck(self):
        '''Return the hosts not alive.
        '''
        return self.run_command(":")

    def get_hosts_list(self):
        '''Return the lists of all hosts.'''
        return self.hosts

    def get_hosts_count(self):
        '''Return count of the hosts.
        '''
        return len(self.hosts)

    def run_command(self, command, timeout=10, check=True):
        '''Run a command on the host.
        '''
        ret, outs = self._run_command(command, timeout)
        if check and ret != 0:
            self.logger.error("Run cmd=" + command + " [FAILED]. Output: " + outs[0])
        return ret

    def run_command_some_hosts(self,
                               command,
                               host_count,
                               timeout=10,
                               no_log=False):
        '''Run a command on each host with ssh.
        '''
        failed_hosts_ret = {}
        for i in range(0, host_count):
            self.logger.debug("host number:" + str(i))
            host = self.hosts[i]
            if os.getenv("EXEC_IN_CONTAINER", False):
                if is_substring("image_manager.py", 
                                command):
                    self.logger.debug(f"Skip running image_manager control in host:{str(i)}, \
                                        because EVN 'EXEC_IN_CONTAINER' is set to True")
                    continue
                elif is_substring("container_manager.py",
                                    command):
                    if is_substring("-o pidrunning", command):
                        command = command.replace('container_manager.py', 'cluster_manager.py')
                        start_str = "-o pidrunning "
                        end_str = " -f "
                        start_index = command.find(start_str) + len(start_str)
                        end_index = command.find(end_str)
                        command = command[0:start_index].strip() + ' ' +command[end_index:].strip()
                    else:
                        self.logger.debug(f"Skip running container_manager control in host:{str(i)}, \
                                        because EVN 'EXEC_IN_CONTAINER' is set to True")
                        continue
                elif is_substring("sys_monitor.py", command):
                    command = replace_between_spaces(command, 3, 4, "python3")
                elif is_substring("docker_images", command):
                    if is_substring("inference", command):
                        if is_substring("stop", command):
                            command = replace_between_spaces(command, 4, 5, "python3")
                        else:
                            command = replace_between_spaces(command, 3, 4, "python3") 
                    else:
                        command = replace_between_spaces(command, 3, 4, "python3")
                    self.logger.debug("replace python3 for command: " + command)

            ret, outs = self._run_command(command, host, timeout)
            if ret != 0:
                failed_hosts_ret[host] = ret
                if not no_log:
                    self.logger.error("Run cmd on host " + host + " cmd=" +
                                      command + " [FAILED]. Output: " +
                                      outs[0])
        return failed_hosts_ret

    def collect_files_some_hosts(self,
                                 remote_dir,
                                 local_dir,
                                 host_count,
                                 timeout=600):
        '''scp remote_dir from hosts in the cluster to <local_dir>/<host>.
        '''
        failed_hosts_ret = {}
        for i in range(0, host_count):
            host = self.hosts[i]
            if not os.path.exists(local_dir):
                self.logger.debug("Make local dir:" + local_dir)
                os.makedirs(local_dir)
            ret, outs = self._scp_dir_from_remote_host(host,
                                                       remote_dir,
                                                       local_dir,
                                                       timeout=timeout)
            if ret != 0:
                failed_hosts_ret[host] = ret
                self.logger.debug("Scp from " + host + ":" + remote_dir +
                                  " to " + local_dir + " [FAILED]. Output: " +
                                  outs[0])
        return failed_hosts_ret
    
def _parse_args():
    '''Get command args from input. '''
    parser = ArgumentParser(description="Manage a host. ")
    parser.add_argument("-o",
                        type=str,
                        required=True,
                        choices=['pidrunning'],
                        help="Operation on the host:"
                        "pidrunning Check wether the process is running.")

    args, _ = parser.parse_known_args()

    if args.o == 'pidrunning':
        parser.add_argument("-f",
                            type=str,
                            required=True,
                            help="pid file path in container.")
    args = parser.parse_args()
    return args

def main():
    '''
    Support command line for cluster manager. Called by cluster manager.
    Applied to multi-machine scenarios.
    '''
    args = _parse_args()
    operation = args.o
    ret = None
    outs = None

    if operation == "pidrunning":
        if is_pid_running(args.f):
            sys.exit(0)
        sys.exit(1)

    if ret == 0:
        print("Output: ", outs[0])
        print(operation, "successful.")
        sys.exit(0)
    print("Output: ", outs[0])
    print(operation, "failed.")
    sys.exit(ret)

if __name__ == "__main__":
    main()
