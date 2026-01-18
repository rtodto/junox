import ipaddress,socket

class Utils:

    def __init__(self):
        pass

    @staticmethod
    def identify_address_type(target: str):
        try:
            ipaddress.ip_address(target)
            return "IP"
        except ValueError:
            try:
                ipaddress.ip_network(target)
                return "Network"
            except ValueError:
                return "Hostname"

    @staticmethod
    def resolve_hostname(hostname: str):
        try:
            return socket.gethostbyname(hostname)
        except socket.gaierror:
            return "Resolution failed"
        
