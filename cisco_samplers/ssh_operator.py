"""
SSHOperator, designed to encapsulate ssh transport used to collect data point and
perform  remote command execution.

It also designed to re-use the connection to the remote host to avoid the overhead.

Author: Mus
 spyroot@gmail.com
 mbayramo@stanford.edu
"""
import time
import logging
import threading
import subprocess
from pathlib import Path
from os.path import expanduser
from typing import List, Optional, Tuple, Dict, Union
import paramiko
from paramiko.client import SSHClient


class PublicKeyNotFound(Exception):
    """Exception raised when the SSH public key is not found."""

    def __init__(self, message="Public key not found. Please generate it first using ssh-keygen."):
        self.message = message
        super().__init__(self.message)


class CommandNotFound(Exception):
    """Exception raised when the SSH public key is not found."""

    def __init__(self, message="Public key not found. Please generate it first using ssh-keygen."):
        self.message = message
        super().__init__(self.message)


class SSHOperator:
    def __init__(
            self,
            remote_hosts: Union[str, List[str]],
            username: str = "capv",
            password: Optional[str] = None,
            public_key_path: Optional[str] = None,
            is_password_auth_only: bool = True
    ):
        """
        :param remote_hosts:  a list of remote host. ssh runner will try to hold connection to multiplex
        :param username:  the username
        :param password:  the password
        :param is_password_auth_only: whether we do only password authentication or not
        :param public_key_path:  path to a public the public key
        """

        if remote_hosts is None:
            raise ValueError("remote_hosts cannot be None. "
                             "Please provide a list of remote hosts.")

        if isinstance(remote_hosts, str):
            remote_hosts = [remote_hosts]
        elif not isinstance(remote_hosts, list) or not all(isinstance(host, str) for host in remote_hosts):
            raise ValueError("remote_hosts must be a string or a list of strings.")

        self._remote_hosts = remote_hosts
        self._username = username
        self._password = password
        self._is_password_auth = is_password_auth_only
        self._is_pubkey_authenticated = False

        if password is None and is_password_auth_only:
            raise ValueError("password is required for password authentication.")

        if public_key_path is None:
            default_pubkey_path = Path(f"{expanduser('~')}/.ssh/id_rsa.pub").resolve().absolute()
            if not Path(default_pubkey_path).exists():
                raise PublicKeyNotFound(f"Public key not found "
                                        f"at the default path: {default_pubkey_path}. "
                                        f"Make sure you generate key first")
            self._public_key_path = default_pubkey_path

        # all persistent connection
        self._persistent_connections = {}

        # for key auth we need push key if it is first time.
        if self._is_password_auth is False:
            SSHOperator.__check_required()
            self.__initial_pubkey_exchange()

    @staticmethod
    def __check_required() -> None:
        """Check required tools.
        :return: None
        :raises: CommandNotFound
        """
        try:
            subprocess.run(["ssh-copy-id", "-h"],
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
        except FileNotFoundError:
            raise CommandNotFound(
                "ssh-copy-id command not found. "
                "Please ensure it is installed and in your PATH."
            )

        try:
            subprocess.run(["sshpass", "-V"],
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
        except FileNotFoundError:
            raise CommandNotFound(
                "sshpass command not found. "
                "Please ensure it is installed and in your PATH."
            )

    def __enter__(self):
        """
        Return the instance itself when entering the context.
        """
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Ensure all connections are closed when exiting the context.
        """

        logging.debug("closing connections")
        self.close_all()

    def close_all(self):
        """Close all connections to remote host
        :return:
        """
        for host_key, client in self._persistent_connections.items():
            try:
                if client:
                    client.close()
            except Exception as e:
                print(f"Error closing connection for {host_key}: {e}")
        self._persistent_connections.clear()

    def get_ssh_connection(
            self,
            host_key: str
    ) -> SSHClient:
        """
        Return a connection to the remote host.

        :param host_key: a key for active connectio n
        :raise Exception up to the stack
        :return:
        """
        if ':' in host_key:
            ip, port = host_key.split(':')
            port = int(port)
        else:
            ip, port = host_key, 22

        normalized_key = self.__normalize_host_key(host_key)

        if normalized_key not in self._persistent_connections:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.load_system_host_keys()
            try:
                client.connect(ip, port=port, username=self._username, password=self._password)
                self._persistent_connections[normalized_key] = client
            except Exception as e:
                print(f"Error {normalized_key}: {e}")
                client.close()
                del client
                raise e

        return self._persistent_connections[normalized_key]

    def broadcast(
            self,
            command: str,
            best_effort: Optional[bool] = False
    ) -> Dict[str, Tuple[str, int, float]]:
        """
        Broadcast a command to multiple hosts concurrently and collect outputs.

        :param command: The command to broadcast.
        :param best_effort: Optional flag to ignore exceptions.
        :return: A dict where keys are host addresses and values are
                 tuples of output, exit code, and execution time.
        """
        outputs = {}
        threads = []

        for host in self._persistent_connections:
            thread = threading.Thread(
                target=self._execute_command,
                args=(host, command, outputs, best_effort))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        return outputs

    def _execute_command(
            self,
            host: str,
            command: str,
            outputs: Dict[str, Tuple[str, int, float]], best_effort: bool
    ):
        """
        Execute a command on a remote host and store the output,
        exit code, and execution time.

        :param host: The host address.
        :param command: The command to execute.
        :param outputs: A dictionary to store the output, exit code, and execution time.
        :param best_effort: Flag to ignore exceptions.
        """
        try:
            output, exit_code, exec_time = self.run(host, command)
            outputs[host] = (output, exit_code, exec_time)
        except Exception as e:
            if not best_effort:
                raise e

    def run(
            self,
            host: str,
            command: str
    ) -> Tuple[str, int, float]:
        """
        Run a command on remote host and capture output.
        exit code and how much time took to execute.

        :param host: a remote host that we execute the command
        :param command: a shell command.
        :return:  A tuple containing: (output, exit code, execution time)
        """
        if not command:
            raise ValueError("Command cannot be empty or None.")

        if not host:
            raise ValueError("Remote host cannot be empty or None.")

        client = self.get_ssh_connection(host)
        logging.debug("executing command {} on a host {}".format(command, host))

        start_time = time.time()

        try:
            stdin, stdout, stderr = client.exec_command(command)
            # This blocks until the command finishes
            stdout.channel.recv_exit_status()
            output = stdout.read().decode('utf-8').strip()
            exit_code = stdout.channel.exit_status
        except Exception as e:
            print(f"Error {e}")
            output = ""
            exit_code = -1
        finally:
            end_time = time.time()

        return output, exit_code, end_time - start_time

    def __initial_pubkey_exchange(self):
        """Initial authentication
        :return:
        """
        self.__push_keys()
        if self._password:
            self._is_pubkey_authenticated = False
        else:
            self._is_pubkey_authenticated = True

        for rh in self._remote_hosts:
            try:
                output, exit_code, _ = self.run(
                    rh, f"echo 'ping'")
                if exit_code != 0 or output.strip() != "ping":
                    raise Exception(f"Failed to verify remote shell connectivity for host {rh}")
            except Exception as e:
                print("Exception while executing")
                print(e)
                self._release_connection(rh)
                raise e

    @staticmethod
    def run_command(cmd):
        """Run local command.
        :param cmd:
        :return:
        """
        result = subprocess.run(
            cmd, capture_output=True, text=True, shell=True
        )
        if result.returncode == 0:
            return result.stdout.strip().split('\n')
        else:
            raise Exception(f"Command '{cmd}' failed with error: {result.stderr.strip()}")

    def __push_keys(
            self
    ) -> None:
        """For initial for ssh key auth method, connection we copy ssh key to
        remote nodes by leveraging ssh-copy-id all follow up ssh connection
        will use key authentication.

        Note it assumes server accept that.

        :return: None
        """
        pub_key_path = Path(self._public_key_path)
        if not pub_key_path.exists():
            raise PublicKeyNotFound(f"Not found {pub_key_path}")

        try:
            process = subprocess.run(
                ["ssh-copy-id", "-h"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        except FileNotFoundError:
            raise CommandNotFound(
                "ssh-copy-id command not found. "
                "Please ensure it is installed and in your PATH."
            )

        with open(self._public_key_path, "r") as file:
            public_key = file.read().strip()
            for host in self._remote_hosts:
                if ':' in host:
                    ip_address, port = host.split(':')
                    port = int(port)
                else:
                    ip_address, port = host, 22

                _process = subprocess.run(
                    [
                        "sshpass", "-p",
                        self._password, "ssh-copy-id",
                        f"-p {port}",
                        f"{self._username}@{ip_address}"
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

    def _release_connection(
            self,
            host_key: str
    ) -> None:
        """
        Closes the SSH connection for a specific host
        and removes it from the persistent connections.

        :param host_key: IP address or hostname
        """
        host_key = self.__normalize_host_key(host_key)
        if host_key in self._persistent_connections:
            if self._persistent_connections[host_key] is not None:
                self._persistent_connections[host_key].close()
            del self._persistent_connections[host_key]

    @staticmethod
    def __normalize_host_key(
            host_key: str) -> str:
        """
        Normalize the host key to ensure a consistent format.
        :param host_key: The original host key, which may or may not include a port.
        :return: A normalized host key in the format 'ip:port'.
        """
        if ':' in host_key:
            ip, port = host_key.split(':')
        else:
            ip = host_key
            port = '22'
        return f"{ip}:{port}"

    def has_active_connection(
            self,
            host_key: str
    ) -> bool:
        """
        Check if there is an active SSH connection for the given host key.
        :param host_key: The host key, typically in the format 'ip:port'.
        :return: True if an active connection exists, False otherwise.
        """
        client = self.get_ssh_connection(host_key)
        if client and client.get_transport() and client.get_transport().is_active():
            return True
        return False

    def get_active_ssh_connection(
            self, host_key: str) -> SSHClient:
        """Return ssh connection for passed host
        :param host_key: is host key either IP , IP:port
        :return: SSHClient
        """
        return self._persistent_connections.get(self.__normalize_host_key(host_key))