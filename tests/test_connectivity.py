import socket
import sys

def check_ip(ip, port=3050):
    print(f"Testing {ip}:{port}...", end=" ")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        result = s.connect_ex((ip, port))
        if result == 0:
            print("SUCCESS")
            return True
        else:
            print(f"FAILED (Code: {result})")
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False
    finally:
        s.close()


if __name__ == "__main__":
    ips_to_test = ["172.22.144.1", "10.255.255.254"]

    # Also try to read resolv.conf
    try:
        with open("/etc/resolv.conf", "r") as f:
            for line in f:
                if "nameserver" in line:
                    ns = line.split()[1].strip()
                    if ns not in ips_to_test:
                        ips_to_test.append(ns)
    except:
        pass

    success = False
    for ip in ips_to_test:
        if check_ip(ip):
            success = True
        
    if not success:
        print("ALL CHECKS FAILED")
        sys.exit(1)

