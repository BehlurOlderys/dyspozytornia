import paramiko
import logging


logger = logging.getLogger(__name__)

public_key_path = "C:\\Users\\ebora\\.ssh\\id_rsa.pub"


def send_command_via_ssh(unit_name, command):
    ssh_connection = paramiko.SSHClient()
    ssh_connection.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_connection.connect(unit_name, username="pi", key_filename=public_key_path)
    stdin, stdout, stderr = ssh_connection.exec_command(command)
    logger.debug(f"StdOut from {command}@{unit_name}: {stdout}")
    logger.debug(f"StdErr from {command}@{unit_name}: {stderr}")
    ssh_connection.close()
