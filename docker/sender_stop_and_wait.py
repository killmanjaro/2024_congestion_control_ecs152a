#!/usr/bin/env python3
import socket
import time

# Constants
PACKET_SIZE = 1024
SEQ_ID_SIZE = 4
MESSAGE_SIZE = PACKET_SIZE - SEQ_ID_SIZE
RECEIVER_IP = '127.0.0.1'
RECEIVER_PORT = 5001
TIMEOUT = 1.0
MAX_RETRIES = 50
FILE_PATH = 'file.mp3'

def create_packet(seq_id, data):
    """Create a packet with sequence number and data."""
    seq_bytes = int.to_bytes(seq_id, SEQ_ID_SIZE, signed=True, byteorder='big')
    return seq_bytes + data

def parse_ack(ack_packet):
    """Parse acknowledgment to extract sequence ID."""
    if len(ack_packet) >= SEQ_ID_SIZE:
        ack_id = int.from_bytes(ack_packet[:SEQ_ID_SIZE], signed=True, byteorder='big')
        return ack_id
    return -1

def send_file_stop_and_wait():
    """
    Send file using Stop-and-Wait protocol.
    Returns: (throughput, avg_delay, performance_metric)
    """
    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT)

    # Read file data
    try:
        with open(FILE_PATH, 'rb') as f:
            file_data = f.read()
    except Exception:
        return None, None, None
    
    total_bytes = len(file_data)
    total_packets = (total_bytes + MESSAGE_SIZE - 1) // MESSAGE_SIZE
    
    # Start timing for throughput
    start_time = time.time()
    
    # Variables for tracking
    seq_id = 0
    packet_delays = []
    offset = 0
    packets_sent = 0
    
    # Send all packets
    while offset < total_bytes:
        # Prepare data chunk
        chunk = file_data[offset:offset + MESSAGE_SIZE]
        packet = create_packet(seq_id, chunk)
        
        # Track when this packet was first sent
        first_send_time = time.time()
        ack_received = False
        retries = 0
        
        while not ack_received and retries < MAX_RETRIES:
            # Send packet
            try:
                sock.sendto(packet, (RECEIVER_IP, RECEIVER_PORT))
                packets_sent += 1
            except Exception:
                retries += 1
                continue
            
            try:
                # Wait for ACK
                ack_packet, _ = sock.recvfrom(PACKET_SIZE)
                ack_id = parse_ack(ack_packet)
                
                # Check if ACK matches expected sequence
                expected_ack = seq_id + len(chunk)
                if ack_id == expected_ack:
                    # Calculate delay from first send to ACK receipt
                    packet_delay = time.time() - first_send_time
                    packet_delays.append(packet_delay)
                    
                    # Move to next packet
                    seq_id = expected_ack
                    offset += len(chunk)
                    ack_received = True
            except socket.timeout:
                retries += 1
                
        if not ack_received:
            sock.close()
            return None, None, None
    
    # Send empty packet to signal end
    final_packet = create_packet(seq_id, b'')
    sock.sendto(final_packet, (RECEIVER_IP, RECEIVER_PORT))

    try:
        ack_packet, _ = sock.recvfrom(PACKET_SIZE)
        fin_packet, _ = sock.recvfrom(PACKET_SIZE)
    except socket.timeout:
        pass

    # Send FINACK
    finack_packet = create_packet(0, b'==FINACK==')
    sock.sendto(finack_packet, (RECEIVER_IP, RECEIVER_PORT))
    
    # Calculate metrics
    end_time = time.time()
    total_time = end_time - start_time
    
    sock.close()
    
    # Calculate results
    throughput = total_bytes / total_time
    avg_delay = sum(packet_delays) / len(packet_delays) if packet_delays else 0
    performance_metric = (0.3 * throughput / 1000) + (0.7 / avg_delay) if avg_delay > 0 else 0
    
    return throughput, avg_delay, performance_metric

def main():
    """Run once and output metrics."""
    throughput, avg_delay, metric = send_file_stop_and_wait()
    
    if throughput is not None:
        # Output in required format (3 lines)
        print(f"{throughput:.7f}")
        print(f"{avg_delay:.7f}")
        print(f"{metric:.7f}")
    else:
        print("0.0000000")
        print("0.0000000")
        print("0.0000000")

if __name__ == "__main__":
    main()
